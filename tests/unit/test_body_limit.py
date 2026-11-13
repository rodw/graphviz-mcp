"""BodyLimit at the ASGI level: fake receive/send and a spy inner app, so no network and no SDK are involved."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import pytest

from graphviz_mcp.security import BodyLimit, BodyRule, declared_length

LIMIT = 100
RULE = BodyRule("/mcp", False, LIMIT)


class Spy:
    """Inner app: records the body it was handed and what receive() returned afterwards."""

    def __init__(self) -> None:
        self.calls = 0
        self.body = b""
        self.after: dict[str, Any] | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.calls += 1
        while True:
            m = await receive()
            self.body += m.get("body", b"")
            if not m.get("more_body"):
                break
        self.after = await receive()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def scope(path: str = "/mcp", method: str = "POST", headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {"type": "http", "method": method, "path": path, "headers": headers or []}


class Wire:
    """A scripted client: yields the given chunks, then a disconnect; counts how many bytes were pulled."""

    def __init__(self, chunks: list[bytes], *, endless: bool = False, disconnect_early: bool = False) -> None:
        self.chunks = list(chunks)
        self.endless = endless
        self.disconnect_early = disconnect_early
        self.pulled = 0
        self.receives = 0
        self.receives_at_response: int | None = None
        self.sent: list[MutableMapping[str, Any]] = []

    async def receive(self) -> MutableMapping[str, Any]:
        self.receives += 1
        if self.disconnect_early and self.receives > len(self.chunks):
            return {"type": "http.disconnect"}
        if self.endless:
            chunk = self.chunks[0]
            self.pulled += len(chunk)
            return {"type": "http.request", "body": chunk, "more_body": True}
        if self.chunks:
            chunk = self.chunks.pop(0)
            self.pulled += len(chunk)
            return {"type": "http.request", "body": chunk, "more_body": bool(self.chunks)}
        return {"type": "http.disconnect"}

    async def send(self, message: MutableMapping[str, Any]) -> None:
        if self.receives_at_response is None:
            self.receives_at_response = self.receives
        self.sent.append(message)

    @property
    def status(self) -> int | None:
        return next((m["status"] for m in self.sent if m["type"] == "http.response.start"), None)

    @property
    def headers(self) -> dict[str, str]:
        start = next(m for m in self.sent if m["type"] == "http.response.start")
        return {k.decode().lower(): v.decode() for k, v in start["headers"]}

    @property
    def body(self) -> bytes:
        return b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")


async def run(wire: Wire, spy: Spy, sc: dict[str, Any] | None = None, rule: BodyRule = RULE) -> None:
    await BodyLimit(spy, [rule])(sc or scope(), wire.receive, wire.send)


async def test_a_body_at_the_limit_passes_intact_across_chunks() -> None:
    spy, wire = Spy(), Wire([b"a" * 40, b"b" * 40, b"c" * 20])
    await run(wire, spy)
    assert spy.calls == 1 and spy.body == b"a" * 40 + b"b" * 40 + b"c" * 20
    assert wire.status == 204


async def test_one_byte_over_the_limit_is_refused_and_never_reaches_the_app() -> None:
    spy, wire = Spy(), Wire([b"a" * 60, b"b" * 41])
    await run(wire, spy)
    assert spy.calls == 0 and wire.status == 413


async def test_a_declared_length_over_the_limit_is_refused_and_the_body_drained_first() -> None:
    body = [b"a" * 100] * 2  # 200 bytes: over the limit of 100, within the drain budget (2 x limit)
    spy, wire = Spy(), Wire(body)
    await run(wire, spy, scope(headers=[(b"content-length", b"200")]))
    assert spy.calls == 0 and wire.status == 413
    assert wire.pulled == 200 and wire.receives_at_response == 2  # all read and discarded before replying


async def test_draining_is_bounded_so_an_endless_sender_cannot_hold_the_connection() -> None:
    spy, wire = Spy(), Wire([b"z" * 30], endless=True)
    await run(wire, spy, scope(headers=[(b"content-length", b"999999999")]))
    assert spy.calls == 0 and wire.status == 413
    assert wire.pulled <= 2 * LIMIT + 30  # gave up at the drain budget and replied anyway


async def test_an_endless_chunked_body_is_aborted_not_drained() -> None:
    spy, wire = Spy(), Wire([b"z" * 30], endless=True)  # no Content-Length: like Transfer-Encoding: chunked
    await run(wire, spy)
    assert spy.calls == 0 and wire.status == 413
    assert wire.pulled <= LIMIT + 2 * LIMIT + 60  # the limit, one chunk, then the bounded drain


async def test_a_body_longer_than_its_declared_length_is_a_400() -> None:
    spy, wire = Spy(), Wire([b"a" * 50])
    await run(wire, spy, scope(headers=[(b"content-length", b"10")]))
    assert spy.calls == 0 and wire.status == 400


async def test_the_declaration_wins_over_a_tiny_actual_body() -> None:
    spy, wire = Spy(), Wire([b"a"])
    await run(wire, spy, scope(headers=[(b"content-length", b"5000")]))
    assert spy.calls == 0 and wire.status == 413


@pytest.mark.parametrize("value", [b"abc", b"-1", b"+5", b"1_000", b"1e3", b"", b" ", "²".encode("latin-1"), b"5, 5"])
async def test_a_malformed_content_length_is_a_400(value: bytes) -> None:
    spy, wire = Spy(), Wire([b"x"])
    await run(wire, spy, scope(headers=[(b"content-length", value)]))
    assert spy.calls == 0 and wire.status == 400 and wire.receives == 0


async def test_repeated_content_length_headers_are_a_400() -> None:
    spy, wire = Spy(), Wire([b"x"])
    await run(wire, spy, scope(headers=[(b"content-length", b"1"), (b"Content-Length", b"1")]))
    assert spy.calls == 0 and wire.status == 400


async def test_an_empty_body_without_content_length_passes() -> None:
    spy, wire = Spy(), Wire([b""])
    await run(wire, spy)
    assert spy.calls == 1 and spy.body == b""


@pytest.mark.parametrize(
    ("path", "method"), [("/mcp", "GET"), ("/mcp", "HEAD"), ("/health", "POST"), ("/mcpx", "POST")]
)
async def test_out_of_scope_requests_are_untouched(path: str, method: str) -> None:
    spy, wire = Spy(), Wire([b"a" * 500])
    await run(wire, spy, scope(path, method))
    assert spy.calls == 1 and spy.body == b"a" * 500


async def test_prefix_rules_match_below_the_prefix_only() -> None:
    rule = BodyRule("/ui/tools/", True, LIMIT)
    for path, refused in (("/ui/tools/dot", True), ("/ui/tools", False), ("/ui/static/x", False)):
        spy, wire = Spy(), Wire([b"a" * 500])
        await run(wire, spy, scope(path), rule)
        assert (spy.calls == 0) is refused, path


async def test_the_app_later_sees_the_real_disconnect() -> None:
    spy, wire = Spy(), Wire([b"hi"])
    await run(wire, spy)
    assert spy.after == {"type": "http.disconnect"}


async def test_a_disconnect_mid_body_ends_quietly() -> None:
    spy, wire = Spy(), Wire([b"a" * 10], disconnect_early=True)
    # first chunk says more_body=True would be needed; script one more_body chunk then disconnect
    wire.chunks = [b"a" * 10, b"b"]
    first = wire.receive

    async def receive() -> MutableMapping[str, Any]:
        m = await first()
        return {**m, "more_body": True} if m["type"] == "http.request" else m

    await BodyLimit(spy, [RULE])(scope(), receive, wire.send)
    assert spy.calls == 0 and wire.sent == []


async def test_rejections_are_json_for_mcp_and_close_the_connection() -> None:
    spy, wire = Spy(), Wire([b"a" * 500])
    await run(wire, spy)
    assert wire.headers["connection"] == "close" and wire.headers["content-type"].startswith("application/json")
    assert "too large" in json.loads(wire.body)["error"]


async def test_a_custom_responder_words_the_rejection() -> None:
    from starlette.responses import HTMLResponse

    seen: list[tuple[int, str]] = []

    def respond(status: int, message: str) -> HTMLResponse:
        seen.append((status, message))
        return HTMLResponse("<p>nope</p>", status_code=status)

    spy, wire = Spy(), Wire([b"a" * 500])
    await run(wire, spy, rule=BodyRule("/mcp", False, LIMIT, respond))
    assert wire.status == 413 and wire.body == b"<p>nope</p>" and seen[0][0] == 413


@pytest.mark.parametrize(
    ("raw", "expected"), [([], None), ([(b"Content-Length", b"12")], 12), ([(b"content-length", b"0")], 0)]
)
def test_declared_length(raw: list[tuple[bytes, bytes]], expected: int | None) -> None:
    assert declared_length(raw) == expected
