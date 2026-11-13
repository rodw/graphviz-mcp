"""BodyLimit behind a real uvicorn, driven with raw sockets: checks what the server does that a fake cannot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
import uvicorn

from graphviz_mcp.security import BodyLimit, BodyRule

LIMIT = 1000


@dataclass
class Seen:
    calls: int = 0
    sizes: list[int] = field(default_factory=list)


@dataclass
class Live:
    port: int
    seen: Seen


@pytest.fixture
async def live() -> AsyncIterator[Live]:
    async with serve(LIMIT) as value:
        yield value


@asynccontextmanager
async def serve(limit: int) -> AsyncIterator[Live]:
    seen = Seen()

    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        seen.calls += 1
        size = 0
        while True:
            m = await receive()
            size += len(m.get("body", b""))
            if not m.get("more_body"):
                break
        seen.sizes.append(size)
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-length", b"2")]})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = BodyLimit(app, [BodyRule("/mcp", False, limit)])
    server = uvicorn.Server(uvicorn.Config(wrapped, host="127.0.0.1", port=0, log_config=None, access_log=False))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield Live(port, seen)
    finally:
        server.should_exit = True
        await task


async def exchange(port: int, head: str, chunks: list[bytes]) -> tuple[bytes, bool]:
    """Send a request head and body pieces; return (everything the server sent, whether it closed the connection)."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(head.encode() + b"\r\n\r\n")
    try:
        for c in chunks:
            writer.write(c)
            await writer.drain()
    except (ConnectionError, OSError):
        pass  # the server refused and hung up while we were still sending: expected
    try:
        data = await asyncio.wait_for(reader.read(65536), 5)
    except (ConnectionError, OSError):
        data = b""
    try:
        closed = await asyncio.wait_for(reader.read(1), 0.5) == b""
    except TimeoutError:
        closed = False  # still open: keep-alive
    except (ConnectionError, OSError):
        closed = True
    writer.close()
    return data, closed


def chunk(payload: bytes) -> bytes:
    return f"{len(payload):x}\r\n".encode() + payload + b"\r\n"


HEAD = "POST /mcp HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json"


async def test_a_chunked_body_past_the_limit_gets_413_and_the_connection_closes(live: Live) -> None:
    pieces = [chunk(b"a" * 400) for _ in range(10)] + [b"0\r\n\r\n"]
    data, closed = await exchange(live.port, HEAD + "\r\nTransfer-Encoding: chunked", pieces)
    assert data.startswith(b"HTTP/1.1 413") and closed
    assert live.seen.calls == 0


async def test_a_chunked_body_within_the_limit_is_delivered(live: Live) -> None:
    data, _ = await exchange(live.port, HEAD + "\r\nTransfer-Encoding: chunked", [chunk(b"a" * 400), b"0\r\n\r\n"])
    assert data.startswith(b"HTTP/1.1 200") and live.seen.sizes == [400]


async def test_a_declared_length_over_the_limit_gets_413_without_sending_the_body(live: Live) -> None:
    data, closed = await exchange(live.port, HEAD + f"\r\nContent-Length: {LIMIT + 1}", [])
    assert data.startswith(b"HTTP/1.1 413") and closed and live.seen.calls == 0


async def test_a_body_longer_than_its_content_length_never_over_delivers(live: Live) -> None:
    data, _ = await exchange(live.port, HEAD + "\r\nContent-Length: 10", [b"a" * 10 + b"b" * 5000])
    assert live.seen.sizes[:1] == [10]  # uvicorn frames by Content-Length; the excess is not part of this body
    assert data.startswith(b"HTTP/1.1 200")


async def test_a_malformed_content_length_never_reaches_the_app(live: Live) -> None:
    data, _ = await exchange(live.port, HEAD + "\r\nContent-Length: abc", [b"xyz"])
    assert data.startswith(b"HTTP/1.1 400") and live.seen.calls == 0


async def test_a_client_still_sending_a_multi_megabyte_body_receives_the_413_not_a_reset() -> None:
    """Replying and closing with unread request data makes the OS reset the connection and can eat the response."""
    limit = 4_000_000
    async with serve(limit) as live:
        body = b"a" * (limit + 100_000)  # far larger than any socket buffer
        data, closed = await exchange(live.port, HEAD + f"\r\nContent-Length: {len(body)}", [body])
        assert data.startswith(b"HTTP/1.1 413") and closed and live.seen.calls == 0
