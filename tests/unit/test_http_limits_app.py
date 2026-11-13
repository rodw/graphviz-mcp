"""The real http_app() with a stub App: oversized bodies must not reach the SDK or the tool service."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import Response

from graphviz_mcp.app import App
from graphviz_mcp.capabilities import Capabilities
from graphviz_mcp.config import Settings
from graphviz_mcp.extras import register_extras
from graphviz_mcp.policy import PolicyEngine, load_policy
from graphviz_mcp.runner import Runner
from graphviz_mcp.security import BodyLimit
from graphviz_mcp.server import http_app
from graphviz_mcp.tools.registry import register_tools
from graphviz_mcp.tools.service import ToolFailure, ToolService

N = 1000
FORM = {"content-type": "application/x-www-form-urlencoded"}
JSON = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


@dataclass
class Spies:
    service_calls: int = 0
    validate_calls: int = 0
    sdk_calls: int = 0
    sdk_bodies: list[int] = field(default_factory=list)


@dataclass
class Stack:
    app: App
    starlette: Starlette
    client: httpx2.AsyncClient
    spies: Spies


def make_stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, max_input: int) -> Stack:
    spies = Spies()
    settings = Settings(graphviz_bin=Path("/nonexistent"), tmp_dir=tmp_path / "tmp", max_input_bytes=max_input)
    dot = Path("/nonexistent/dot")
    caps = Capabilities(
        version="0", version_line="dot - graphviz version 0", bin_dir=dot.parent, formats=("svg", "dot", "plain"),
        combos={}, default_device={}, engines=("dot",), programs={"dot": dot, "nop": dot}, missing=(), unclassified=(),
    )  # fmt: skip
    runner = Runner(settings, caps.programs)
    service = ToolService(
        settings, caps, runner, PolicyEngine(load_policy(settings), runner, max_pixels=1, preflight=False)
    )
    server = MCPServer("graphviz-mcp")
    app = App(settings, caps, runner, service, server)
    register_tools(server, service)
    register_extras(app)

    async def call(self: Any, *a: Any, **k: Any) -> Any:
        spies.service_calls += 1
        raise ToolFailure("args", "tool service reached")

    async def validate(*a: Any, **k: Any) -> Any:
        spies.validate_calls += 1
        raise ToolFailure("args", "validate_document reached")

    async def handle(self: Any, scope: Any, receive: Any, send: Any) -> None:
        # Coupled to a private SDK method on purpose: "does not reach the SDK" is exactly the claim under test.
        spies.sdk_calls += 1
        size = 0
        while True:
            m = await receive()
            size += len(m.get("body", b""))
            if not m.get("more_body"):
                break
        spies.sdk_bodies.append(size)
        await Response("sdk reached", status_code=202)(scope, receive, send)

    monkeypatch.setattr(ToolService, "call", call)
    monkeypatch.setattr("graphviz_mcp.web.routes.validate_document", validate)
    monkeypatch.setattr(StreamableHTTPSessionManager, "_handle_request", handle)  # before http_app() binds it
    starlette = http_app(app)
    transport = httpx2.ASGITransport(app=starlette)
    client = httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000")
    return Stack(app, starlette, client, spies)


@pytest.fixture
async def stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Stack]:
    s = make_stack(monkeypatch, tmp_path, N)
    async with s.client:
        yield s


def chunks(total: int, size: int = 4096) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b"a" * n


async def stream(total: int) -> AsyncIterator[bytes]:
    for c in chunks(total):
        yield c


async def test_oversized_chunked_form_is_refused_before_the_tool_service(stack: Stack) -> None:
    r = await stack.client.post(
        "/ui/tools/dot", content=stream(stack.app.settings.max_form_body_bytes + 5000), headers=FORM
    )
    assert r.status_code == 413 and "text/html" in r.headers["content-type"] and "too large" in r.text.lower()
    assert stack.spies.service_calls == 0 and stack.spies.validate_calls == 0


async def test_a_small_form_still_reaches_the_tool_service(stack: Stack) -> None:
    r = await stack.client.post("/ui/tools/validate_dot", content="input=digraph%7Ba%7D", headers=FORM)
    assert stack.spies.validate_calls == 1 and r.status_code == 422


async def test_oversized_chunked_mcp_post_is_refused_before_the_sdk(stack: Stack) -> None:
    r = await stack.client.post("/mcp", content=stream(stack.app.settings.max_mcp_body_bytes + 5000), headers=JSON)
    assert r.status_code == 413 and r.json()["error"]
    assert stack.spies.sdk_calls == 0 and stack.spies.service_calls == 0


async def test_a_small_mcp_post_reaches_the_sdk(stack: Stack) -> None:
    r = await stack.client.post("/mcp", content=b'{"jsonrpc":"2.0"}', headers=JSON)
    assert r.status_code == 202 and stack.spies.sdk_calls == 1


async def test_the_mcp_envelope_covers_worst_case_json_escaping(stack: Stack) -> None:
    limit = stack.app.settings.max_mcp_body_bytes
    assert (await stack.client.post("/mcp", content=b"x" * limit, headers=JSON)).status_code == 202
    assert (await stack.client.post("/mcp", content=b"x" * (limit + 1), headers=JSON)).status_code == 413
    assert stack.spies.sdk_bodies == [limit]
    assert limit == N * 6 + 64_000  # 6x: a control byte escapes to \u00XX


async def test_a_raised_input_cap_is_not_cut_short_by_the_sdk_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    s = make_stack(monkeypatch, tmp_path, 5_000_000)
    async with s.client:
        r = await s.client.post("/mcp", content=b"x" * 4_500_000, headers=JSON)  # over the SDK's 4 MiB default
        assert r.status_code == 202 and s.spies.sdk_calls == 1


async def test_bad_content_length_is_a_400_not_a_500(stack: Stack) -> None:
    for path, headers in (("/mcp", JSON), ("/ui/tools/dot", FORM)):
        r = await stack.client.post(path, content=b"x", headers={**headers, "content-length": "x"})
        assert r.status_code == 400, path
    assert stack.spies.sdk_calls == 0 and stack.spies.service_calls == 0


async def test_a_disallowed_host_is_refused_before_the_body_limit(stack: Stack) -> None:
    r = await stack.client.post(
        "/mcp", content=b"x", headers={**JSON, "host": "evil.example", "content-length": "99999999"}
    )
    assert r.status_code == 421


async def test_every_route_that_accepts_a_body_is_covered_by_a_rule(stack: Stack) -> None:
    layer = next(m for m in stack.starlette.user_middleware if cast(Any, m.cls) is BodyLimit)
    rules: Any = layer.kwargs["rules"]
    uncovered = []
    for route in stack.starlette.routes:
        methods: set[str] = set(cast(Any, getattr(route, "methods", None)) or ()) - {"GET", "HEAD", "OPTIONS"}
        path = getattr(route, "path", "")
        if methods and not any(r.matches(path.replace("{name}", "dot")) for r in rules):
            uncovered.append((path, sorted(methods)))
    assert not uncovered


def test_the_sdk_limit_is_the_repos_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    s = make_stack(monkeypatch, tmp_path, N)
    manager = s.app.server._lowlevel_server._session_manager
    assert manager is not None and manager.max_request_body_size == s.app.settings.max_mcp_body_bytes
