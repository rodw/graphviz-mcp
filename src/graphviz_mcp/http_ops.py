"""Operational endpoints (/health, /ready, /version) and the Web UI routes."""

from __future__ import annotations

import asyncio
import platform
import time
from importlib import metadata
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .app import App
from .meta import package_version
from .web.routes import register_web_routes

_STARTED = time.monotonic()
_NO_STORE = {"Cache-Control": "no-store"}


def _json(data: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=_NO_STORE)


def version_document(app: App) -> dict[str, Any]:
    try:
        sdk = metadata.version("mcp")
    except metadata.PackageNotFoundError:  # pragma: no cover
        sdk = "unknown"
    caps = app.caps
    return {
        "service": {"name": "graphviz-mcp", "version": package_version()},
        "graphviz": {
            "version": caps.version,
            "version_line": caps.version_line,
            "plugins": {k: list(v) for k, v in caps.plugins.items()},
        },
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation()},
        "mcp_sdk": {"version": sdk},
        "platform": {"system": platform.system(), "machine": platform.machine()},
    }


READY_TTL_S = 30.0  # how long a successful smoke test is trusted


async def _smoke_test(app: App) -> tuple[bool, str]:
    """A trivial dot run. It takes no call slot, so a busy server is still ready."""
    if "dot" not in app.caps.programs:
        return False, "dot is not available"
    try:
        async with app.runner.workdir() as wd:
            res = await app.runner.run("dot", ["-Tsvg"], b"digraph{a}", workdir=wd, timeout_s=10, slot=False)
    except Exception as exc:
        return False, f"dot invocation failed: {type(exc).__name__}"
    if res.returncode != 0 or b"<svg" not in res.stdout:
        return False, f"dot invocation failed (exit status {res.returncode})"
    return True, "ok"


class ReadinessProbe:
    """Ready = the startup capability gate passed and a trivial dot invocation worked within the last TTL.

    A success is cached for ``READY_TTL_S`` and failures are not, so recovery shows at once. The lock makes
    concurrent callers share one probe, so at most one probe process exists at a time however often /ready is hit.
    """

    def __init__(self, app: App) -> None:
        self._app = app
        self._lock = asyncio.Lock()
        self._ok_at: float | None = None

    def _fresh(self) -> bool:
        return self._ok_at is not None and time.monotonic() - self._ok_at < READY_TTL_S

    async def check(self) -> tuple[bool, str]:
        if self._fresh():
            return True, "ok"
        async with self._lock:
            if self._fresh():  # another caller refreshed it while this one waited
                return True, "ok"
            ok, reason = await _smoke_test(self._app)
            self._ok_at = time.monotonic() if ok else None
            return ok, reason


async def readiness(app: App) -> tuple[bool, str]:
    """One-off, uncached readiness check (the /ready route uses a cached :class:`ReadinessProbe`)."""
    return await _smoke_test(app)


def register_http_routes(app: App) -> None:
    server = app.server
    probe = ReadinessProbe(app)

    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return _json({"status": "ok", "uptime_seconds": round(time.monotonic() - _STARTED, 1)})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(request: Request) -> Response:
        ok, reason = await probe.check()
        body: dict[str, Any] = {"status": "ready" if ok else "not ready", "reason": reason}
        if ok:
            body.update(graphviz=app.caps.version, active_calls=app.runner.active, queued_calls=app.runner.waiting)
        return _json(body, 200 if ok else 503)

    @server.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> Response:
        return _json(version_document(app))

    register_web_routes(app)


__all__ = ["ReadinessProbe", "readiness", "register_http_routes", "version_document"]
