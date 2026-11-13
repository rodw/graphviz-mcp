"""The only place a process is spawned.

argv list (never a shell), binary from an allowlist resolved at startup, own process
group, rlimits, streamed stdout with a hard cap, SIGTERM then SIGKILL of the whole
group, per-call temp dir. Takes stdin bytes and returns stdout bytes.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import os
import shutil
import signal
import tempfile
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

_GRACE_S = 1.0
_slot_held: contextvars.ContextVar[bool] = contextvars.ContextVar("gvmcp_slot_held", default=False)
# time.monotonic() value by which the current tool call (see Runner.call_slot) must be finished
_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("gvmcp_deadline", default=None)
_CHUNK = 65536


class RunnerError(Exception):
    """Base class; ``kind`` is a stable machine-readable label for logs."""

    kind = "error"


class Busy(RunnerError):
    kind = "busy"


class TimedOut(RunnerError):
    kind = "timeout"


class OutputTooLarge(RunnerError):
    kind = "output_too_large"


class UnknownProgram(RunnerError):
    kind = "unknown_program"


@dataclass(frozen=True)
class RunResult:
    stdout: bytes
    stderr: str
    returncode: int
    duration_s: float


def _limits(cpu_s: int, mem_bytes: int, fsize: int) -> None:
    """preexec_fn: only calls setrlimit."""
    import resource

    for which, value in (
        (resource.RLIMIT_CPU, cpu_s),
        (resource.RLIMIT_FSIZE, fsize),
        (getattr(resource, "RLIMIT_AS", None), mem_bytes),
        (resource.RLIMIT_CORE, 0),
    ):
        if which is None or value < 0:
            continue
        try:
            resource.setrlimit(which, (value, value))
        except (ValueError, OSError):  # e.g. RLIMIT_AS unsupported on macOS
            pass


def scrub(text: str, replacements: Mapping[str, str]) -> str:
    for needle, repl in sorted(replacements.items(), key=lambda kv: -len(kv[0])):
        if needle:
            text = text.replace(needle, repl)
    return text


class Runner:
    def __init__(self, settings: Settings, programs: Mapping[str, Path]) -> None:
        self._s = settings
        self._programs = dict(programs)
        self._sem = asyncio.Semaphore(settings.concurrency)
        self._waiting = 0
        self.active = 0

    @property
    def programs(self) -> Mapping[str, Path]:
        return self._programs

    @property
    def waiting(self) -> int:
        return self._waiting

    @contextlib.asynccontextmanager
    async def workdir(self) -> AsyncIterator[Path]:
        """Per-call temp dir, removed afterwards even on cancellation."""
        base = self._s.tmp_dir
        if base is not None:
            base.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix="gvmcp-", dir=base))
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def scrubber(self, workdir: Path | None = None) -> dict[str, str]:
        repl = {str(self._s.graphviz_bin): "<graphviz>"}
        if workdir is not None:
            repl[str(workdir)] = "<tmp>"
            with contextlib.suppress(OSError):
                repl[str(workdir.resolve())] = "<tmp>"
        return repl

    @contextlib.asynccontextmanager
    async def call_slot(self) -> AsyncIterator[None]:
        """Hold one concurrency slot for a whole tool call (parse pre-pass, pre-flight and the run itself).

        The busy decision is made once, up front. Individual runs inside the block do not take another slot.
        The block also gets one wall-clock budget (``timeout_s``), shared by every run in it and starting once the
        slot is held, so time spent queueing is not counted. A nested block keeps the outer budget.
        """
        async with self._slot():
            token = _slot_held.set(True)
            deadline_token = _deadline.set(_deadline.get() or time.monotonic() + self._s.timeout_s)
            try:
                yield
            finally:
                _deadline.reset(deadline_token)
                _slot_held.reset(token)

    @contextlib.asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        if _slot_held.get():
            yield
            return
        if self._sem.locked() and self._waiting >= self._s.queue_size:
            raise Busy("server busy: too many calls queued")
        self._waiting += 1
        try:
            try:
                async with asyncio.timeout(self._s.queue_wait_s):
                    await self._sem.acquire()
            except TimeoutError:
                raise Busy("server busy: timed out waiting for a free slot") from None
        finally:
            self._waiting -= 1
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1
            self._sem.release()

    def _env(self, workdir: Path) -> dict[str, str]:
        env = {
            "PATH": f"{self._s.graphviz_bin}:/usr/bin:/bin",
            "HOME": str(workdir),
            "TMPDIR": str(workdir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        if self._s.attr_policy != "unrestricted":
            # Graphviz "server mode": safefile() then refuses every file load (image=, shapefile=,
            # <IMG SRC>), a second line of defense beneath the attribute policy.
            env["SERVER_NAME"] = "graphviz-mcp"
        for keep in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "FONTCONFIG_PATH", "FONTCONFIG_FILE"):
            if keep in os.environ:
                env[keep] = os.environ[keep]
        return env

    async def run(
        self,
        program: str,
        args: Sequence[str],
        stdin: bytes | None = None,
        *,
        workdir: Path,
        timeout_s: float | None = None,
        slot: bool = True,
    ) -> RunResult:
        """Run ``program``. ``slot=False`` skips the concurrency limit (and the busy check) entirely."""
        binary = self._programs.get(program)
        if binary is None:
            raise UnknownProgram(f"program {program!r} is not available")
        timeout = self._s.timeout_s if timeout_s is None else timeout_s
        reported = timeout  # what a timeout message names
        if (deadline := _deadline.get()) is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimedOut(f"timed out after {self._s.timeout_s:g}s")
            if remaining < timeout:
                timeout, reported = remaining, self._s.timeout_s  # the shared budget, not this run's share, ran out
        if not slot:
            return await self._spawn(binary, args, stdin, workdir, timeout, reported)
        async with self._slot():
            return await self._spawn(binary, args, stdin, workdir, timeout, reported)

    async def _spawn(
        self, binary: Path, args: Sequence[str], stdin: bytes | None, workdir: Path, timeout: float, reported: float
    ) -> RunResult:
        s = self._s
        mem = s.memory_mb * 1024 * 1024 if s.memory_mb else -1
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            *args,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=self._env(workdir),
            process_group=0,
            preexec_fn=lambda: _limits(s.cpu_limit_s, mem, s.max_output_bytes),
        )
        try:
            async with asyncio.timeout(timeout):
                out, err = await self._communicate(proc, stdin)
                rc = await proc.wait()
        except TimeoutError:
            await self._kill(proc)
            raise TimedOut(f"timed out after {reported:g}s") from None
        except BaseException:
            await asyncio.shield(self._kill(proc))
            raise
        return RunResult(out, err.decode("utf-8", "replace"), rc, time.monotonic() - started)

    async def _communicate(self, proc: asyncio.subprocess.Process, stdin: bytes | None) -> tuple[bytes, bytes]:
        s = self._s
        assert proc.stdout is not None and proc.stderr is not None
        feed = asyncio.create_task(self._feed(proc, stdin))
        out_t = asyncio.create_task(self._read(proc.stdout, s.max_output_bytes, fatal=True))
        err_t = asyncio.create_task(self._read(proc.stderr, s.max_stderr_bytes, fatal=False))
        tasks = (feed, out_t, err_t)
        try:
            # First failure (e.g. output cap) propagates immediately.
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in done:
                if t.exception() is not None:
                    raise t.exception()  # type: ignore[misc]
            await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            raise
        return out_t.result(), err_t.result()

    @staticmethod
    async def _feed(proc: asyncio.subprocess.Process, data: bytes | None) -> None:
        if data is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the program exited or stopped reading; its exit status tells the story
        finally:
            with contextlib.suppress(Exception):
                proc.stdin.close()

    @staticmethod
    async def _read(stream: asyncio.StreamReader | None, cap: int, *, fatal: bool) -> bytes:
        assert stream is not None
        buf = bytearray()
        while chunk := await stream.read(_CHUNK):
            room = cap - len(buf)
            if room > 0:
                buf += chunk[:room]
            if len(chunk) > room and fatal:
                raise OutputTooLarge(f"output exceeds the {cap}-byte limit")
        return bytes(buf)

    @staticmethod
    def _signal_group(proc: asyncio.subprocess.Process, sig: int) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, sig)

    async def _kill(self, proc: asyncio.subprocess.Process) -> None:
        self._signal_group(proc, signal.SIGTERM)
        try:
            async with asyncio.timeout(_GRACE_S):
                await proc.wait()
        except TimeoutError:
            pass
        self._signal_group(proc, signal.SIGKILL)
        await proc.wait()
        # Pipes we stopped reading would otherwise stay open until garbage collection.
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()
