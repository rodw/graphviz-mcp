"""Host / Origin checks for the plain HTTP routes (the SDK only protects its own /mcp endpoint)."""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

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
