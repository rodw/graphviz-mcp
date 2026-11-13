"""Start and drive containers of the built Docker image (tests marked `docker_image`)."""

from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx2

from graphviz_mcp.runner import RunResult

DOCKER_IMAGE = os.environ.get("GVMCP_TEST_DOCKER_IMAGE", "graphviz-mcp:dev")
PREFIX = "graphviz-mcp-test-"
# `make test.docker-image.coverage` points this at a world-writable host directory and runs the coverage-instrumented
# image: every server process then writes its coverage data there when it exits (see Dockerfile.test-coverage).
COVERAGE_DIR = os.environ.get("GVMCP_DOCKER_COVERAGE_DIR")
HARDENING = [
    "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m", "--cap-drop=ALL",
    "--security-opt", "no-new-privileges", "--pids-limit", "512", "--memory", "5g", "--memory-swap", "5g",
]  # fmt: skip


def docker(
    *args: str, stdin: bytes | None = None, check: bool = True, timeout: float = 120
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["docker", *args], input=stdin, capture_output=True, check=check, timeout=timeout)


def coverage_args() -> list[str]:
    """`docker run` options that let a coverage-instrumented server write its data (empty for a normal run)."""
    if not COVERAGE_DIR:
        return []
    args = ["-v", f"{COVERAGE_DIR}:/cov"]
    if core := os.environ.get("COVERAGE_CORE"):
        args += ["-e", f"COVERAGE_CORE={core}"]
    return args


def docker_image_available() -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True).returncode == 0
    except OSError:  # no `docker` executable on PATH
        return False


@dataclass
class Container:
    name: str
    port: int
    env: Mapping[str, str] = field(default_factory=dict)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.base}/mcp"

    def exec(
        self, program: str, args: list[str], stdin: str | bytes = b"", user: str | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        data = stdin.encode() if isinstance(stdin, str) else stdin
        extra = ["-u", user] if user else []
        return docker("exec", "-i", *extra, self.name, program, *args, stdin=data, check=False)

    def cli(self, program: str, args: list[str], stdin: str | bytes = b"") -> subprocess.CompletedProcess[bytes]:
        return self.exec(f"/opt/graphviz/bin/{program}", args, stdin)

    def processes(self) -> list[str]:
        """`pid cmdline` for every process in the container (the Docker image has no `ps`; read /proc instead)."""
        script = (
            "import os\n"
            "for p in sorted(os.listdir('/proc'), key=lambda x: int(x) if x.isdigit() else 0):\n"
            "    if p.isdigit():\n"
            "        try: print(p, open(f'/proc/{p}/cmdline','rb').read().replace(b'\\0', b' ').decode())\n"
            "        except OSError: pass\n"
        )
        out = docker("exec", self.name, "python3", "-c", script, check=False).stdout.decode()
        return [ln for ln in out.splitlines() if re.match(r"\d+ ", ln) and "python3 -c" not in ln]

    def graphviz_processes(self) -> list[str]:
        return [ln for ln in self.processes() if "/opt/graphviz/bin/" in ln]

    def logs(self) -> str:
        r = docker("logs", self.name, check=False)
        return r.stdout.decode() + r.stderr.decode()

    def remove(self) -> None:
        if COVERAGE_DIR:  # coverage data is only written when the server exits normally, never on SIGKILL
            docker("stop", "-t", "10", self.name, check=False, timeout=60)
        docker("rm", "-f", self.name, check=False)


def start(
    env: Mapping[str, str] | None = None, volumes: Mapping[Path, str] | None = None, extra: list[str] | None = None
) -> Container:
    name = PREFIX + uuid.uuid4().hex[:10]
    args = ["run", "-d", "--name", name, *HARDENING, "-p", "127.0.0.1::8000"]
    for k, v in (env or {}).items():
        args += ["-e", f"{k}={v}"]
    for host, target in (volumes or {}).items():
        args += ["-v", f"{host}:{target}:ro"]
    args += [*coverage_args(), *(extra or []), DOCKER_IMAGE]
    docker(*args)
    try:
        port = int(docker("port", name, "8000/tcp").stdout.decode().split(":")[-1])
        c = Container(name, port, dict(env or {}))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx2.get(f"{c.base}/ready", timeout=2).status_code == 200:
                    return c
            except httpx2.HTTPError:
                pass
            state = docker("inspect", "-f", "{{.State.Running}}", name, check=False).stdout.decode().strip()
            if state != "true":
                raise RuntimeError(f"container exited:\n{docker('logs', name, check=False).stderr.decode()}")
            time.sleep(0.3)
        raise RuntimeError(f"container not ready:\n{docker('logs', name, check=False).stderr.decode()}")
    except BaseException:
        docker("rm", "-f", name, check=False)
        raise


class ContainerRunner:
    """Just enough of `graphviz_mcp.runner.Runner` to let in-process code (the policy engine) run the *container's*
    Graphviz through `docker exec`: real programs of the pinned image, no Graphviz on the host."""

    def __init__(self, container: Container) -> None:
        self._c = container

    @asynccontextmanager
    async def workdir(self) -> AsyncIterator[Path]:
        yield Path("/nonexistent")

    def scrubber(self, workdir: Path | None = None) -> dict[str, str]:
        return {}

    async def run(
        self,
        program: str,
        args: Sequence[str],
        stdin: bytes | None = None,
        *,
        workdir: Path,
        timeout_s: float | None = None,
    ) -> RunResult:
        r = self._c.cli(program, list(args), stdin or b"")
        return RunResult(
            stdout=r.stdout, stderr=r.stderr.decode("utf-8", "replace"), returncode=r.returncode, duration_s=0.0
        )
