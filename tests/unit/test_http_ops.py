from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graphviz_mcp.config import Settings
from graphviz_mcp.http_ops import READY_TTL_S, ReadinessProbe
from graphviz_mcp.runner import Runner

FAKE_DOT = """#!/bin/sh
echo x >> "{log}"
sleep {delay}
if [ -e "{broken}" ]; then exit 1; fi
cat > /dev/null
echo '<svg/>'
"""


class Env:
    def __init__(self, tmp_path: Path, settings: Settings, delay: float = 0) -> None:
        self.log = tmp_path / "calls.log"
        self.broken = tmp_path / "broken"
        script = tmp_path / "dot"
        script.write_text(FAKE_DOT.format(log=self.log, broken=self.broken, delay=delay))
        script.chmod(0o755)
        self.runner = Runner(settings, {"dot": script})
        self.app: Any = SimpleNamespace(caps=SimpleNamespace(programs={"dot": script}), runner=self.runner)

    @property
    def spawns(self) -> int:
        return len(self.log.read_text().splitlines()) if self.log.exists() else 0


@pytest.fixture
def env(tmp_path: Path, settings: Settings) -> Env:
    return Env(tmp_path, settings)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr("graphviz_mcp.http_ops.time", SimpleNamespace(monotonic=c))
    return c


async def test_success_is_cached_until_the_ttl_expires(env: Env, clock: Clock) -> None:
    probe = ReadinessProbe(env.app)
    assert await probe.check() == (True, "ok")
    assert await probe.check() == (True, "ok")
    assert env.spawns == 1
    clock.now += READY_TTL_S - 1
    await probe.check()
    assert env.spawns == 1
    clock.now += 2
    await probe.check()
    assert env.spawns == 2


async def test_failure_is_not_cached(env: Env, clock: Clock) -> None:
    env.broken.touch()
    probe = ReadinessProbe(env.app)
    ok, reason = await probe.check()
    assert not ok and "exit status 1" in reason
    env.broken.unlink()
    assert await probe.check() == (True, "ok")
    assert env.spawns == 2


async def test_missing_dot_is_not_ready(env: Env) -> None:
    env.app.caps.programs.clear()
    assert await ReadinessProbe(env.app).check() == (False, "dot is not available")
    assert env.spawns == 0


async def test_concurrent_checks_share_one_probe(tmp_path: Path, settings: Settings, clock: Clock) -> None:
    slow = Env(tmp_path, settings, delay=0.3)
    probe = ReadinessProbe(slow.app)
    results = await asyncio.gather(*(probe.check() for _ in range(8)))
    assert results == [(True, "ok")] * 8
    assert slow.spawns == 1


async def test_probe_does_not_need_a_free_slot(tmp_path: Path, settings: Settings, clock: Clock) -> None:
    from dataclasses import replace

    tight = replace(settings, concurrency=1, queue_size=1, queue_wait_s=5)
    env = Env(tmp_path, tight)
    async with env.runner.call_slot():  # the only slot is taken by a "real" call
        assert await ReadinessProbe(env.app).check() == (True, "ok")
        assert env.runner.active == 1
        assert env.runner.waiting == 0
