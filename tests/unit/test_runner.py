from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from graphviz_mcp.config import Settings
from graphviz_mcp.runner import Busy, OutputTooLarge, Runner, TimedOut, UnknownProgram, scrub

SH = Path("/bin/sh")
SLEEP = Path("/bin/sleep") if Path("/bin/sleep").exists() else Path("/usr/bin/sleep")


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def wait_dead(pid: int, secs: float = 3.0) -> bool:
    for _ in range(int(secs / 0.05)):
        if not alive(pid):
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.fixture
def runner(settings: Settings) -> Runner:
    return Runner(settings, {"sh": SH, "sleep": SLEEP, "yes": Path("/usr/bin/yes")})


async def test_unknown_program(runner: Runner) -> None:
    async with runner.workdir() as wd:
        with pytest.raises(UnknownProgram):
            await runner.run("rm", ["-rf", "/"], workdir=wd)


async def test_stdin_stdout_roundtrip(runner: Runner) -> None:
    async with runner.workdir() as wd:
        r = await runner.run("sh", ["-c", "cat; echo err >&2; exit 3"], b"hello", workdir=wd)
    assert (r.stdout, r.stderr.strip(), r.returncode) == (b"hello", "err", 3)


async def test_workdir_removed_and_is_cwd(runner: Runner) -> None:
    async with runner.workdir() as wd:
        r = await runner.run("sh", ["-c", "pwd -P; touch f"], workdir=wd)
        assert (wd / "f").exists()
        assert Path(r.stdout.decode().strip()) == wd.resolve()
    assert not wd.exists()


async def test_environment_is_minimal(runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "x")
    async with runner.workdir() as wd:
        r = await runner.run("sh", ["-c", "env"], workdir=wd)
    assert b"SECRET_TOKEN" not in r.stdout and b"HOME=" in r.stdout


async def test_timeout_kills_process_group(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=0.5), {"sh": SH})
    async with runner.workdir() as wd:
        with pytest.raises(TimedOut):
            await runner.run("sh", ["-c", "sleep 30 & echo $! > child; echo $$ > me; wait"], workdir=wd)
        child, me = int((wd / "child").read_text()), int((wd / "me").read_text())
    assert await wait_dead(child) and await wait_dead(me)


async def test_cancellation_kills_only_that_call(runner: Runner) -> None:
    async with runner.workdir() as wd1, runner.workdir() as wd2:
        t1 = asyncio.create_task(runner.run("sh", ["-c", "echo $$ > pid; sleep 30"], workdir=wd1))
        t2 = asyncio.create_task(runner.run("sh", ["-c", "echo $$ > pid; sleep 1; echo ok"], workdir=wd2))
        await asyncio.sleep(0.5)
        pid1, pid2 = int((wd1 / "pid").read_text()), int((wd2 / "pid").read_text())
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
        assert await wait_dead(pid1)
        assert (await t2).stdout.strip() == b"ok"
    assert not alive(pid2)


async def test_output_cap_kills_producer(settings: Settings) -> None:
    runner = Runner(replace(settings, max_output_bytes=100_000), {"yes": Path("/usr/bin/yes")})
    async with runner.workdir() as wd:
        with pytest.raises(OutputTooLarge):
            await runner.run("yes", [], workdir=wd)


async def test_stderr_is_capped_not_fatal(settings: Settings) -> None:
    runner = Runner(replace(settings, max_stderr_bytes=1000), {"sh": SH})
    async with runner.workdir() as wd:
        r = await runner.run("sh", ["-c", "yes e | head -c 500000 >&2; echo done"], workdir=wd)
    assert len(r.stderr) == 1000 and r.stdout.strip() == b"done"


async def test_queue_full_gives_busy(settings: Settings) -> None:
    runner = Runner(replace(settings, concurrency=1, queue_size=1, queue_wait_s=5), {"sleep": SLEEP})
    async with runner.workdir() as wd:
        running = asyncio.create_task(runner.run("sleep", ["1"], workdir=wd))
        await asyncio.sleep(0.2)
        waiting = asyncio.create_task(runner.run("sleep", ["0.1"], workdir=wd))
        await asyncio.sleep(0.2)
        with pytest.raises(Busy):
            await runner.run("sleep", ["0.1"], workdir=wd)
        await asyncio.gather(running, waiting)
    assert runner.active == 0 and runner.waiting == 0


async def test_slot_false_ignores_the_concurrency_limit(settings: Settings) -> None:
    runner = Runner(replace(settings, concurrency=1, queue_size=1, queue_wait_s=5), {"sleep": SLEEP})
    async with runner.workdir() as wd:
        running = asyncio.create_task(runner.run("sleep", ["1"], workdir=wd))
        waiting = asyncio.create_task(runner.run("sleep", ["0.1"], workdir=wd))
        await asyncio.sleep(0.2)  # one call is running and the queue is full
        with pytest.raises(Busy):
            await runner.run("sleep", ["0"], workdir=wd)
        r = await runner.run("sleep", ["0"], workdir=wd, slot=False)
        assert r.returncode == 0
        assert runner.active == 1 and runner.waiting == 1  # the unslotted run is not counted
        await asyncio.gather(running, waiting)


async def test_queue_wait_timeout_gives_busy(settings: Settings) -> None:
    runner = Runner(replace(settings, concurrency=1, queue_size=5, queue_wait_s=0.3), {"sleep": SLEEP})
    async with runner.workdir() as wd:
        running = asyncio.create_task(runner.run("sleep", ["1"], workdir=wd))
        await asyncio.sleep(0.1)
        with pytest.raises(Busy):
            await runner.run("sleep", ["0.1"], workdir=wd)
        await running


def test_scrub() -> None:
    assert scrub("error in /a/b/c and /a/b", {"/a/b": "<x>", "/a/b/c": "<y>"}) == "error in <y> and <x>"


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS is only enforced on Linux")
async def test_memory_limit_enforced_on_linux(settings: Settings) -> None:
    # The child must really try to allocate more than the limit: a streaming pipeline (head | tr | wc) never holds the
    # data, so it would not exercise RLIMIT_AS. A MemoryError also distinguishes "limited" from "failed to start".
    runner = Runner(replace(settings, memory_mb=256), {"py": Path(sys.executable)})
    code = (
        "try:\n    bytearray(500_000_000)\nexcept MemoryError:\n    print('limited')\nelse:\n    print('allocated')\n"
    )
    async with runner.workdir() as wd:
        r = await runner.run("py", ["-c", code], workdir=wd)
    assert r.stdout.strip() == b"limited", r


async def test_call_slot_is_held_once_for_nested_runs(settings: Settings) -> None:
    """One tool call = one slot: runs inside call_slot() never wait for (or fail to get) another slot."""
    runner = Runner(replace(settings, concurrency=1, queue_size=1, queue_wait_s=0.2), {"sleep": SLEEP})
    async with runner.workdir() as wd, runner.call_slot():
        assert runner.active == 1
        await runner.run(
            "sleep", ["0.05"], workdir=wd
        )  # would deadlock/Busy with concurrency=1 if it took a second slot
        await runner.run("sleep", ["0.05"], workdir=wd)
        assert runner.active == 1
    assert runner.active == 0


async def test_call_slot_blocks_other_calls(settings: Settings) -> None:
    runner = Runner(replace(settings, concurrency=1, queue_size=0 + 1, queue_wait_s=0.2), {"sleep": SLEEP})
    async with runner.workdir() as wd, runner.call_slot():
        waiter = asyncio.create_task(
            runner.run("sleep", ["0.01"], workdir=wd)
        )  # inherits the held slot via contextvars
        await waiter

    async def other() -> None:
        async with runner.call_slot():
            await asyncio.sleep(0.6)

    holder = asyncio.create_task(other())
    await asyncio.sleep(0.1)
    with pytest.raises(Busy):
        async with runner.call_slot():
            pass
    await holder


async def test_call_shares_one_budget_across_runs(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=1), {"sleep": SLEEP})
    async with runner.workdir() as wd, runner.call_slot():
        started = time.monotonic()
        await runner.run("sleep", ["0.6"], workdir=wd)
        with pytest.raises(TimedOut, match=r"timed out after 1s"):  # the call budget, not the 0.4s remainder
            await runner.run("sleep", ["0.6"], workdir=wd)
        assert time.monotonic() - started < 1.4


async def test_exhausted_budget_does_not_spawn(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=0.3), {"sh": SH})
    async with runner.workdir() as wd, runner.call_slot():
        await asyncio.sleep(0.4)
        with pytest.raises(TimedOut):
            await runner.run("sh", ["-c", "touch ran"], workdir=wd)
        assert not (wd / "ran").exists()


async def test_no_budget_outside_a_call(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=1), {"sleep": SLEEP})
    async with runner.workdir() as wd:
        await runner.run("sleep", ["0.6"], workdir=wd)
        await runner.run("sleep", ["0.6"], workdir=wd)


async def test_explicit_shorter_timeout_wins_and_nested_call_keeps_outer_budget(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=1), {"sleep": SLEEP})
    async with runner.workdir() as wd, runner.call_slot():
        with pytest.raises(TimedOut, match=r"timed out after 0\.2s"):
            await runner.run("sleep", ["1"], workdir=wd, timeout_s=0.2)
        await asyncio.sleep(0.7)
        async with runner.call_slot():  # must not restart the clock
            with pytest.raises(TimedOut):
                await runner.run("sleep", ["0.6"], workdir=wd)


async def test_queue_time_is_not_charged_to_the_budget(settings: Settings) -> None:
    runner = Runner(replace(settings, timeout_s=1, concurrency=1, queue_size=2, queue_wait_s=5), {"sleep": SLEEP})

    async def hold() -> None:
        async with runner.workdir() as wd:
            await runner.run("sleep", ["0.6"], workdir=wd)

    first = asyncio.create_task(hold())
    await asyncio.sleep(0.1)
    async with runner.call_slot(), runner.workdir() as wd:  # waits ~0.5s for the slot first
        await runner.run("sleep", ["0.8"], workdir=wd)
    await first
