"""Host / Origin checks for the plain HTTP routes (the SDK only protects its own /mcp endpoint)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOG = logging.getLogger("graphviz_mcp")

LOCAL_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")


def default_allowed_hosts(extra: Iterable[str] = ()) -> list[str]:
    return [*LOCAL_HOSTS, *extra]


def allowed_origins(hosts: Iterable[str]) -> list[str]:
    return [f"{scheme}://{h}" for h in hosts for scheme in ("http", "https")]


def _match(value: str, pattern: str) -> bool:
    """Exact match, or ``base:*`` meaning base with any numeric port (no glob characters: IPv6 has '[')."""
    if pattern.endswith(":*"):
        base = pattern[:-2]
        if value == base:
            return True
        return value.startswith(base + ":") and value[len(base) + 1 :].isdigit()
    return value == pattern


def host_allowed(host: str | None, patterns: Iterable[str]) -> bool:
    if not host:
        return False
    host = host.lower()
    return any(_match(host, p.lower()) for p in patterns)


def origin_allowed(origin: str | None, patterns: Iterable[str]) -> bool:
    """Absent Origin (non-browser clients) is allowed; a present Origin must match the allow list."""
    if origin is None:
        return True
    origin = origin.lower()
    return any(_match(origin, p.lower()) for p in patterns)


class HostGuard:
    """Reject requests whose Host header is not allowed (DNS-rebinding defense for every route)."""

    def __init__(self, app: ASGIApp, hosts: list[str]) -> None:
        self.app = app
        self.hosts = hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if not host_allowed(headers.get("host"), self.hosts):
                body = json.dumps({"error": "host not allowed"}).encode()
                if scope["type"] == "http":
                    await send({"type": "http.response.start", "status": 421,
                                "headers": [(b"content-type", b"application/json"),
                                            (b"content-length", str(len(body)).encode())]})  # fmt: skip
                    await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DRAIN_FACTOR = 2  # after refusing, discard at most this many limits' worth of the client's remaining body ...
DRAIN_TIMEOUT_S = 2.0  # ... and for at most this long


async def _drain(receive: Receive, budget: int) -> None:
    """Read and throw away up to ``budget`` bytes of an already-refused body, without keeping any of it.

    Closing a connection that still has unread request data makes the OS reset it, which can destroy the response
    before the client reads it. Draining lets a client that is still sending see the 413. The budget and timeout
    keep an endless or very slow sender from holding the connection: past them the response goes out regardless.
    """
    try:
        async with asyncio.timeout(DRAIN_TIMEOUT_S):
            while budget > 0:
                message = await receive()
                if message["type"] != "http.request":
                    return
                budget -= len(message.get("body", b""))
                if not message.get("more_body", False):
                    return
    except TimeoutError:
        pass


def json_error(status: int, message: str) -> Response:
    return JSONResponse({"error": message}, status_code=status)


@dataclass(frozen=True)
class BodyRule:
    """A request-body ceiling for one path (exact) or path prefix, and how to word the rejection."""

    path: str
    prefix: bool
    limit: int
    respond: Callable[[int, str], Response] = json_error

    def matches(self, path: str) -> bool:
        return path.startswith(self.path) if self.prefix else path == self.path


def declared_length(headers: Iterable[tuple[bytes, bytes]]) -> int | None:
    """The one valid ``Content-Length`` value, or None when absent. Raises ValueError if malformed or repeated."""
    values = [v for k, v in headers if k.lower() == b"content-length"]
    if not values:
        return None
    if len(values) > 1:
        raise ValueError("repeated Content-Length")
    text = values[0].decode("latin-1")
    if not (text.isascii() and text.isdigit()):  # str.isdigit() alone accepts e.g. "²", which int() then refuses
        raise ValueError("malformed Content-Length")
    return int(text)


class BodyLimit:
    """Enforce a request-body ceiling before the SDK or Starlette sees the request.

    The body is read here, chunk by chunk, up to the limit and then replayed to the inner app, so an oversized
    request is refused without ever reaching it (raising from ``receive`` instead would be swallowed by the SDK's
    broad ``except``). ``Content-Length`` is only a hint for refusing early; the running byte count is what counts.
    """

    def __init__(self, app: ASGIApp, rules: Sequence[BodyRule]) -> None:
        self.app = app
        self.rules = tuple(rules)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        rule = None
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            rule = next((r for r in self.rules if r.matches(scope["path"])), None)
        if rule is None:
            await self.app(scope, receive, send)
            return

        async def reject(status: int, reason: str, seen: int, drain: bool = False) -> None:
            if drain:
                await _drain(receive, rule.limit * DRAIN_FACTOR)
            LOG.info("request body refused", extra={"path": scope["path"], "reason": reason, "bytes": seen})
            message = "request body too large" if status == 413 else "invalid request body length"
            response = rule.respond(status, message)
            response.headers["Connection"] = "close"
            await response(scope, receive, send)

        try:
            declared = declared_length(scope["headers"])
        except ValueError:
            await reject(400, "malformed", 0)
            return
        if declared is not None and declared > rule.limit:
            await reject(413, "declared", declared, drain=True)
            return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":  # the client went away mid-body
                return
            body = message.get("body", b"")
            total += len(body)
            if total > rule.limit:
                await reject(413, "streamed", total, drain=True)
                return
            if declared is not None and total > declared:
                await reject(400, "exceeds-declared", total)
                return
            if body:
                chunks.append(body)
            if not message.get("more_body", False):
                break

        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
