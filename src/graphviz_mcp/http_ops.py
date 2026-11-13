"""Operational endpoints (/health, /ready, /version) and the Web UI routes."""

from __future__ import annotations

import platform
import time
from importlib import metadata
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from .server import App

_STARTED = time.monotonic()
_NO_STORE = {"Cache-Control": "no-store"}


def _json(data: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=_NO_STORE)


def version_document(app: App) -> dict[str, Any]:
    from .server import package_version

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


async def readiness(app: App) -> tuple[bool, str]:
    """Ready = the startup capability gate passed and a trivial dot invocation works right now."""
    if "dot" not in app.caps.programs:
        return False, "dot is not available"
    try:
        async with app.runner.workdir() as wd:
            res = await app.runner.run("dot", ["-Tsvg"], b"digraph{a}", workdir=wd, timeout_s=10)
    except Exception as exc:
        return False, f"dot invocation failed: {type(exc).__name__}"
    if res.returncode != 0 or b"<svg" not in res.stdout:
        return False, f"dot invocation failed (exit status {res.returncode})"
    return True, "ok"


def register_http_routes(app: App) -> None:
    server = app.server

    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return _json({"status": "ok", "uptime_seconds": round(time.monotonic() - _STARTED, 1)})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(request: Request) -> Response:
        ok, reason = await readiness(app)
        body: dict[str, Any] = {"status": "ready" if ok else "not ready", "reason": reason}
        if ok:
            body.update(graphviz=app.caps.version, active_calls=app.runner.active, queued_calls=app.runner.waiting)
        return _json(body, 200 if ok else 503)

    @server.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> Response:
        return _json(version_document(app))

    from .web.routes import register_web_routes

    register_web_routes(app)


__all__ = ["readiness", "register_http_routes", "version_document"]
