"""Web UI, HTTP endpoints, MCP extras and validate_dot, against the Docker image (real Graphviz behind them)."""

from __future__ import annotations

import asyncio
import html
import json
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx2
import pytest
from mcp import Client

from graphviz_mcp.web.render import SAMPLE_DOT
from tests.support.docker_image_ctl import DOCKER_IMAGE, HARDENING, coverage_args, docker
from tests.support.helpers import first_text, text_of

pytestmark = pytest.mark.docker_image
FORM = {"content-type": "application/x-www-form-urlencoded"}


@pytest.fixture
async def ui(docker_image_server: Any) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(base_url=docker_image_server.base, follow_redirects=False, timeout=60) as c:
        yield c


async def post(ui: Any, tool: str, data: dict[str, str], headers: dict[str, str] | None = None) -> Any:
    return await ui.post(f"/ui/tools/{tool}", content=urlencode(data), headers={**FORM, **(headers or {})})


async def capabilities(client: Any) -> dict[str, Any]:
    return json.loads(first_text(await client.call_tool("get_capabilities", {})))  # type: ignore[no-any-return]


def field_names(page: str) -> set[str]:
    form = page[page.index('<form method="post"') :]
    return set(re.findall(r'<(?:input|textarea|select)[^>]*\bname="([^"]+)"', form))


# --- the Web UI ----------------------------------------------------------------------------------------------
async def test_index_lists_exactly_the_mcp_tools(ui: Any, docker_image_client: Any) -> None:
    page = (await ui.get("/ui/tools")).text
    listed = set(re.findall(r'href="/ui/tools/([^"]+)"', page))
    assert listed == {t.name for t in (await docker_image_client.list_tools()).tools}


async def test_home_page_has_server_instructions(ui: Any) -> None:
    r = await ui.get("/ui")
    assert r.status_code == 200 and "<h1>graphviz-mcp</h1>" in r.text and "Which tool:" in r.text


UI_PAGES = (
    "/ui", "/ui/tools", "/ui/capabilities", "/ui/resources", "/ui/resources/dot-language", "/ui/resources/attributes",
    "/ui/resources/capabilities", "/ui/status", "/ui/status/current-env", "/ui/docs", "/ui/docs/env-vars",
    "/ui/docs/attribute-security-policy", "/ui/legal", "/ui/legal/license", "/ui/legal/third-party-notices",
)  # fmt: skip


async def test_every_ui_page_is_served_with_its_content(ui: Any) -> None:
    expect = {
        "/ui/resources/dot-language": "The DOT Language",
        "/ui/resources/attributes": "Graphviz attributes",
        "/ui/resources/capabilities": "graphviz://capabilities",
        "/ui/status": "/ui/status/current-env",
        "/ui/docs": "/ui/docs/env-vars",
        "/ui/docs/attribute-security-policy": "Attribute Security Policy",
        "/ui/legal": "/ui/legal/third-party-notices",
        "/ui/legal/license": "MIT License",
        "/ui/legal/third-party-notices": "primer/octicons",
    }
    for path in UI_PAGES:
        r = await ui.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"], path
        assert expect.get(path, "") in r.text, path
        assert 'rel="icon" href="/favicon.ico"' in r.text and "View on GitHub" in r.text, path


async def test_status_links_the_operational_endpoints(ui: Any) -> None:
    page = (await ui.get("/ui/status")).text
    for link in ("/health", "/ready", "/version", "/ui/status/current-env"):
        assert f'href="{link}"' in page


async def test_env_var_pages_cover_every_setting(ui: Any) -> None:
    source = (Path(__file__).parents[2] / "src/graphviz_mcp/config.py").read_text()
    names = {f"GVMCP_{n}" for n in re.findall(r'\b_(?:get|num|bool)\(env, "([A-Z_]+)"', source)}
    assert len(names) >= 18
    for path in ("/ui/status/current-env", "/ui/docs/env-vars"):
        page = (await ui.get(path)).text
        assert {n for n in names if f"<code>{n}</code>" not in page} == set(), path


async def test_favicon_is_served_at_the_default_path(ui: Any) -> None:
    r = await ui.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon" and r.content[:4] == b"\x00\x00\x01\x00"


async def test_forms_have_exactly_the_mcp_parameters(ui: Any, docker_image_client: Any) -> None:
    for tool in (await docker_image_client.list_tools()).tools:
        r = await ui.get(f"/ui/tools/{tool.name}")
        if tool.name == "get_capabilities":
            assert r.status_code == 200 and "Capabilities" in r.text
            continue
        assert r.status_code == 200, tool.name
        assert field_names(r.text) == set(tool.input_schema["properties"]), tool.name


async def test_every_tool_form_has_labels_and_help(ui: Any, docker_image_client: Any) -> None:
    for tool in (await docker_image_client.list_tools()).tools:
        if tool.name == "get_capabilities":
            continue
        page = (await ui.get(f"/ui/tools/{tool.name}")).text
        for name in tool.input_schema["properties"]:
            assert f'for="f-{name}"' in page and f'id="f-{name}"' in page and f'id="help-{name}"' in page, (
                tool.name,
                name,
            )
        assert "<h1>" in page and '<html lang="en">' in page


async def test_secure_headers_and_no_cookies(ui: Any) -> None:
    for path in (*UI_PAGES, "/ui/tools/dot", "/ui/static/style.css", "/ui/tools/nope"):
        r = await ui.get(path)
        csp = r.headers["content-security-policy"]
        assert "default-src 'none'" in csp and "img-src 'self' data:" in csp and "form-action 'self'" in csp
        assert "script-src" not in csp and "unsafe" not in csp
        assert r.headers["x-content-type-options"] == "nosniff" and "set-cookie" not in r.headers
    r = await ui.post("/ui/tools/dot", content=f"input={SAMPLE_DOT}", headers=FORM)
    assert "set-cookie" not in r.headers


async def test_pages_use_no_javascript(ui: Any) -> None:
    for path in (*UI_PAGES, "/ui/tools/dot"):
        text = (await ui.get(path)).text.lower()
        assert "<script" not in text and " onclick" not in text and "javascript:" not in text


async def test_root_redirects_to_ui(ui: Any) -> None:
    r = await ui.get("/")
    assert r.status_code == 302 and r.headers["location"] == "/ui"


async def test_svg_result_renders_as_img_with_source(ui: Any) -> None:
    r = await post(ui, "dot", {"input": SAMPLE_DOT, "T": "svg"})
    assert r.status_code == 200
    assert re.search(
        r'<img id="output-image-0" data-kind="svg" src="data:image/svg\+xml;base64,[A-Za-z0-9+/=]+"', r.text
    )
    assert "&lt;svg" in r.text and "download=" in r.text


async def test_png_result_renders_as_data_uri_image(ui: Any) -> None:
    r = await post(ui, "dot", {"input": SAMPLE_DOT, "T": "png"})
    assert r.status_code == 200 and re.search(r'src="data:image/png;base64,iVBOR', r.text)


async def test_pdf_result_is_a_download_link(ui: Any) -> None:
    r = await post(ui, "dot", {"input": SAMPLE_DOT, "T": "pdf"})
    assert r.status_code == 200 and 'data-kind="blob"' in r.text and "data:application/pdf;base64," in r.text


async def test_text_result_has_download_link(ui: Any) -> None:
    r = await post(ui, "nop", {"input": "digraph{a->b}"})
    assert r.status_code == 200 and 'data-kind="text"' in r.text and 'download="result-0.txt"' in r.text


async def test_errors_map_to_http_statuses(ui: Any) -> None:
    cases: list[tuple[dict[str, str], int, str]] = [
        ({"input": 'digraph{a [image="/etc/passwd"]}'}, 403, "attribute policy"),
        ({"input": "digraph{a", "T": "svg"}, 422, "syntax error"),
        ({"input": SAMPLE_DOT, "T": "bogus"}, 422, "not an output format"),
        ({"input": SAMPLE_DOT, "s": "abc"}, 422, "number"),
        ({"input": SAMPLE_DOT, "G": "no-equals-sign"}, 422, "name=value"),
        ({"input": SAMPLE_DOT, "bogusfield": "1"}, 422, "unknown form field"),
        ({"input": ""}, 422, "input"),
        ({"input": "digraph{a}", "G": "dpi=9999", "T": "png"}, 403, "dpi"),
    ]
    for data, status, needle in cases:
        r = await post(ui, "dot", data)
        assert r.status_code == status, (data, r.status_code)
        assert needle in html.unescape(r.text), (data, needle)
        assert 'id="error"' in r.text
    assert (await ui.get("/ui/tools/nope")).status_code == 404


async def test_policy_rejection_in_ui_is_403_with_policy_link(ui: Any) -> None:
    r = await post(ui, "neato", {"input": 'graph { a [label=<<IMG SRC="x"/>>] }'})
    assert r.status_code == 403 and "/ui/capabilities#policy" in r.text


async def test_cross_origin_post_rejected(ui: Any) -> None:
    for headers in ({"origin": "http://evil.example"}, {"origin": "https://127.0.0.1.evil.example"},
                    {"origin": "null"}, {"origin": "null", "sec-fetch-site": "cross-site"}, {"sec-fetch-site": "cross-site"}, {"sec-fetch-site": "same-site"}):  # fmt: skip
        r = await post(ui, "dot", {"input": SAMPLE_DOT}, headers)
        assert r.status_code == 403, headers
    for headers in (
        {"origin": "null", "sec-fetch-site": "same-origin"},  # what a browser sends for a same-origin form post
        {"origin": "http://127.0.0.1:8000"},
        {"origin": "http://localhost:3000"},
        {"sec-fetch-site": "same-origin"},
        {},
    ):
        r = await post(ui, "dot", {"input": SAMPLE_DOT}, headers)
        assert r.status_code == 200, headers


async def test_only_urlencoded_forms_accepted_no_multipart(ui: Any) -> None:
    body = '--b\r\nContent-Disposition: form-data; name="input"\r\n\r\ndigraph{a}\r\n--b--\r\n'
    r = await ui.post("/ui/tools/dot", content=body, headers={"content-type": "multipart/form-data; boundary=b"})
    assert r.status_code == 415
    r = await ui.post("/ui/tools/dot", content='{"input":"digraph{a}"}', headers={"content-type": "application/json"})
    assert r.status_code == 415


async def test_oversized_form_rejected(ui: Any, docker_image_client: Any) -> None:
    cap = (await capabilities(docker_image_client))["limits"]["max_input_bytes"]
    r = await ui.post("/ui/tools/dot", content="input=" + "a" * (cap * 4 + 100_000), headers=FORM)
    assert r.status_code == 413


async def test_oversized_chunked_bodies_are_refused_and_the_server_stays_up(ui: Any, docker_image_client: Any) -> None:
    cap = (await capabilities(docker_image_client))["limits"]["max_input_bytes"]

    async def stream(total: int) -> AsyncIterator[bytes]:  # no Content-Length: sent chunked
        for _ in range(total // 65536 + 1):
            yield b"a" * 65536

    r = await ui.post("/ui/tools/dot", content=stream(cap * 4 + 200_000), headers=FORM)
    assert r.status_code == 413
    r = await ui.post("/mcp", content=stream(cap * 6 + 200_000), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert (await ui.get("/ready")).status_code == 200


async def test_the_http_envelope_admits_a_json_escaped_input_near_the_cap(docker_image_client: Any) -> None:
    cap = (await capabilities(docker_image_client))["limits"]["max_input_bytes"]
    body = "digraph{\n" + "\n" * (cap - 20) + "a}"  # every newline is 2 bytes once JSON-escaped
    r = await docker_image_client.call_tool("validate_dot", {"input": body})
    assert not r.is_error, text_of(r)[:200]


async def test_form_values_are_echoed_escaped(ui: Any) -> None:
    evil = 'digraph { a [label="</textarea><script>alert(1)</script>"] }'
    r = await post(ui, "dot", {"input": evil})
    assert "<script>alert" not in r.text and "&lt;/textarea&gt;&lt;script&gt;" in r.text


async def test_validate_dot_page(ui: Any) -> None:
    r = await post(ui, "validate_dot", {"input": "digraph {\n a -> \n}"})
    assert r.status_code == 200 and "Not valid DOT" in r.text and "line" in r.text
    r = await post(ui, "validate_dot", {"input": "digraph { a -> b }"})
    assert "Valid DOT" in r.text


async def test_capabilities_page(ui: Any, docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    r = await ui.get("/ui/capabilities")
    assert r.status_code == 200 and doc["graphviz_version"] in r.text
    assert "Attribute policy: denylist" in r.text and "image" in r.text and 'id="policy"' in r.text
    assert (await ui.get("/ui/tools/get_capabilities")).text == r.text


# --- operational endpoints -----------------------------------------------------------------------------------
async def test_health(ui: Any) -> None:
    r = await ui.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.headers["cache-control"] == "no-store"
    assert r.headers["content-type"].startswith("application/json")


async def test_ready(ui: Any) -> None:
    r = await ui.get("/ready")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ready" and body["graphviz"].startswith("16.")


async def test_version(ui: Any, docker_image_client: Any) -> None:
    body = (await ui.get("/version")).json()
    assert body["service"]["name"] == "graphviz-mcp" and body["service"]["version"]
    assert body["graphviz"]["version"] == (await capabilities(docker_image_client))["graphviz_version"]
    assert body["graphviz"]["version_line"].startswith("dot - graphviz version")
    assert "layout" in body["graphviz"]["plugins"] and "dot" in body["graphviz"]["plugins"]["layout"]
    assert body["python"]["version"] and body["mcp_sdk"]["version"] and body["platform"]["system"]


async def test_only_get_is_allowed_on_operational_endpoints(ui: Any) -> None:
    for path in ("/health", "/ready", "/version"):
        assert (await ui.post(path)).status_code == 405


async def test_host_header_must_be_allowed(ui: Any) -> None:
    assert (await ui.get("/health", headers={"host": "evil.example"})).status_code == 421
    assert (await ui.get("/ui", headers={"host": "evil.example:8000"})).status_code == 421
    assert (await ui.get("/health", headers={"host": "localhost:9999"})).status_code == 200
    assert (await ui.get("/health", headers={"host": "[::1]:8000"})).status_code == 200


# --- MCP extras ----------------------------------------------------------------------------------------------
async def test_get_capabilities_tool_and_resource_agree(docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    res = await docker_image_client.read_resource("graphviz://capabilities")
    assert json.loads(res.contents[0].text) == doc
    assert doc["graphviz_version"] == "16.1.0" and "dot" in doc["layout_engines"]
    assert doc["attribute_policy"]["mode"] == "denylist" and "image" in doc["attribute_policy"]["deny"]
    assert doc["attribute_policy"]["constraints"]["dpi"]
    assert doc["limits"]["timeout_seconds"] > 0
    assert any(f["format"] == "png" and f["mime"] == "image/png" and f["renderers"] for f in doc["output_formats"])
    assert {"gvpr", "gv2gxl"} <= set(doc["catalog"]["excluded"]) and "deferred" not in doc["catalog"]
    assert doc["fonts"] and {"dot", "nop", "ccomps"} <= set(doc["tools"])


async def test_resources_listed_and_readable(docker_image_client: Any) -> None:
    listed = {str(r.uri) for r in (await docker_image_client.list_resources()).resources}
    assert {"graphviz://capabilities", "graphviz://attributes", "graphviz://dot-language"} <= listed
    attrs = (await docker_image_client.read_resource("graphviz://attributes")).contents[0]
    assert attrs.mime_type == "text/markdown" and "| rankdir |" in attrs.text
    assert "| image |" in attrs.text and "| denied |" in attrs.text and "Graphviz 16.1.0" in attrs.text
    guide = (await docker_image_client.read_resource("graphviz://dot-language")).contents[0].text
    assert "subgraph" in guide and "digraph" in guide


async def test_prompts(docker_image_client: Any) -> None:
    names = {p.name for p in (await docker_image_client.list_prompts()).prompts}
    assert {"visualize_data_as_graph", "explain_dot", "fix_dot"} <= names
    r = await docker_image_client.get_prompt("visualize_data_as_graph", {"data": "A depends on B", "layout": "neato"})
    text = r.messages[0].content.text
    assert "A depends on B" in text and "neato" in text and "validate_dot" in text
    r = await docker_image_client.get_prompt("fix_dot", {"dot": "digraph {", "problem": "does not parse"})
    assert "does not parse" in r.messages[0].content.text


async def test_tool_descriptions_state_policy(docker_image_client: Any) -> None:
    tools = {t.name: t for t in (await docker_image_client.list_tools()).tools}
    assert "Attribute policy: denylist" in tools["dot"].description
    assert tools["dot"].annotations.read_only_hint is True


# --- validate_dot --------------------------------------------------------------------------------------------
async def validate(client: Any, text: str) -> dict[str, Any]:
    r = await client.call_tool("validate_dot", {"input": text})
    assert not r.is_error, text_of(r)
    data = json.loads(first_text(r))
    assert r.structured_content == data
    return data  # type: ignore[no-any-return]


async def test_validate_valid(docker_image_client: Any) -> None:
    d = await validate(docker_image_client, "digraph { a -> b }")
    assert d["valid"] is True and d["errors"] == [] and d["policy_ok"] is True


async def test_validate_invalid_reports_the_line(docker_image_client: Any) -> None:
    d = await validate(docker_image_client, "digraph {\n a -> b;\n c -> ;\n}")
    assert d["valid"] is False and d["errors"][0]["line"] == 3 and d["policy_ok"] is None


async def test_validate_valid_but_policy_rejected(docker_image_client: Any) -> None:
    d = await validate(docker_image_client, 'digraph { a [image="/etc/passwd"] }')
    assert d["valid"] is True and d["policy_ok"] is False and "image" in d["policy_violation"]


async def test_validate_empty_input_and_unknown_parameters_are_errors(docker_image_client: Any) -> None:
    assert (await docker_image_client.call_tool("validate_dot", {"input": "  "})).is_error
    assert (await docker_image_client.call_tool("validate_dot", {"input": "x", "extra": 1})).is_error


async def test_validate_performs_no_layout(docker_image_client: Any) -> None:
    # a graph whose layout would be refused or slow is still just parsed
    d = await validate(docker_image_client, 'digraph { size="100,100!"; dpi=300; a }')
    assert d["valid"] is True


async def test_validate_dot_enforces_the_input_cap(container_factory: Any) -> None:
    """validate_dot has its own size check (shared by the MCP tool and the Web UI), separate from the tools'."""
    c = container_factory(env={"GVMCP_MAX_INPUT_BYTES": "100"})
    big = "digraph { " + "a; " * 50 + "}"
    assert len(big.encode()) > 100
    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("validate_dot", {"input": big})
        assert r.is_error and "100-byte limit" in text_of(r), text_of(r)[:200]
        r = await mcp.call_tool("dot", {"input": big})
        assert r.is_error and "100-byte limit" in text_of(r), text_of(r)[:200]
        assert not (await mcp.call_tool("validate_dot", {"input": "digraph{a}"})).is_error
    async with httpx2.AsyncClient(base_url=c.base, timeout=60) as h:
        resp = await h.post("/ui/tools/validate_dot", data={"input": big}, headers={"origin": c.base})
        assert resp.status_code in (413, 422) and "100-byte limit" in html.unescape(resp.text), resp.status_code


# --- logging, stdio and startup ------------------------------------------------------------------------------
async def test_one_structured_log_record_per_call(container_factory: Any) -> None:
    c = container_factory()
    async with Client(c.mcp_url) as mcp:
        await mcp.call_tool("dot", {"input": "digraph { a -> b }"})
        await mcp.call_tool("dot", {"input": 'digraph { a [image="/etc/passwd"] }'})
        await mcp.call_tool("dot", {"input": "digraph { a ->"})
    deadline = time.monotonic() + 5
    calls: list[dict[str, Any]] = []
    while time.monotonic() < deadline and len(calls) < 3:
        records = [json.loads(ln) for ln in c.logs().splitlines() if ln.startswith("{")]
        calls = [r for r in records if r.get("event") == "call"]
        await asyncio.sleep(0.2)
    assert [r["status"] for r in calls] == ["ok", "policy", "input"]
    ok, rejected, _ = calls
    assert ok["tool"] == "dot" and ok["surface"] == "mcp" and ok["input_bytes"] > 0 and ok["output_bytes"] > 0
    assert "image" in rejected["reason"]
    assert "a -> b" not in c.logs()  # graph contents are never logged


def test_stdout_stays_clean_in_stdio_mode() -> None:
    """Only protocol frames may appear on stdout; logging goes to stderr as JSON lines."""
    msg = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}\n'
    r = docker(
        "run",
        "-i",
        "--rm",
        *HARDENING,
        *coverage_args(),
        "-e",
        "GVMCP_LOG_LEVEL=INFO",
        DOCKER_IMAGE,
        "--stdio",
        stdin=msg,
        check=False,
    )
    assert r.returncode == 0, r.stderr.decode()[:300]
    for line in r.stdout.decode().splitlines():
        assert json.loads(line)["jsonrpc"] == "2.0"
    for line in r.stderr.decode().splitlines():
        assert json.loads(line)["level"]
    assert b'"msg":"ready"' in r.stderr


@pytest.mark.parametrize(
    "env",
    [{"GVMCP_ATTR_POLICY": "bogus"}, {"GVMCP_PORT": "x"}, {"GVMCP_GRAPHVIZ_BIN": "/tmp"}],
    ids=["policy", "port", "bin"],
)
def test_startup_failure_is_reported_on_stderr(env: dict[str, str]) -> None:
    args = ["run", "--rm", *HARDENING, *coverage_args()]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    r = docker(*args, DOCKER_IMAGE, "--http", check=False, timeout=60)
    assert r.returncode == 2 and b"graphviz-mcp:" in r.stderr, r.stderr.decode()[:300]
