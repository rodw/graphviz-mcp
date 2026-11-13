"""For each tool, the Web UI output equals the MCP output for the same input, against the Docker image."""

from __future__ import annotations

import html
import json
import re
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

import httpx2
import pytest

from graphviz_mcp.tools.specs import PROGRAMS
from tests.support.cases import CASE_NAMES, GRAPHML, MM, cases
from tests.support.helpers import text_of

pytestmark = pytest.mark.docker_image
FORM = {"content-type": "application/x-www-form-urlencoded"}
SRC = "digraph G { rankdir=LR; a -> b -> c; a -> c [label=x] }"


@pytest.fixture
async def web(docker_image_server: Any) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(base_url=docker_image_server.base, follow_redirects=False, timeout=60) as c:
        yield c


@pytest.fixture(scope="module")
def case_table(docker_image_server: Any) -> dict[str, tuple[str, dict[str, Any], list[str], str]]:
    return cases(docker_image_server.cli)


def to_form(tool: str, args: dict[str, Any]) -> dict[str, str]:
    prog = PROGRAMS.get(tool)
    types = {p.name: p.ptype for p in prog.params} if prog else {}
    out: dict[str, str] = {}
    for k, v in args.items():
        t = types.get(k)
        if t == "bool":
            if v:
                out[k] = "on"
        elif t == "kv":
            out[k] = "\n".join(f"{a}={b}" for a, b in v.items())
        elif t == "strlist":
            out[k] = "\n".join(v)
        else:
            out[k] = str(v)
    return out


def ui_outputs(page: str) -> dict[int, tuple[str, str]]:
    found: dict[int, tuple[str, str]] = {}
    for m in re.finditer(r'<pre id="output-(\d+)" data-kind="text">(.*?)</pre>', page, re.S):
        found[int(m.group(1))] = ("text", html.unescape(m.group(2)))
    for m in re.finditer(r'<img id="output-(\d+)" data-kind="image" src="data:[^;]+;base64,([^"]+)"', page):
        found[int(m.group(1))] = ("image", m.group(2))
    for m in re.finditer(r'<p id="output-(\d+)" data-kind="blob">.*?href="data:[^;]+;base64,([^"]+)"', page, re.S):
        found[int(m.group(1))] = ("blob", m.group(2))
    for m in re.finditer(r'<pre class="stderr" id="stderr-(\d+)" data-kind="stderr">(.*?)</pre>', page, re.S):
        found[int(m.group(1))] = ("stderr", html.unescape(m.group(2)))
    return found


def mcp_outputs(result: Any) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    for i, c in enumerate(result.content):
        if c.type == "image":
            out[i] = ("image", c.data)
        elif c.type == "resource":
            out[i] = ("blob", c.resource.blob)
        elif c.text.startswith("[stderr]"):
            out[i] = ("stderr", c.text.removeprefix("[stderr]").strip())
        else:
            out[i] = ("text", c.text)
    return out


async def both(web: Any, client: Any, tool: str, args: dict[str, Any]) -> tuple[Any, Any]:
    mcp = await client.call_tool(tool, args)
    ui = await web.post(f"/ui/tools/{tool}", content=urlencode(to_form(tool, args)), headers=FORM)
    return mcp, ui


def assert_same(mcp: Any, ui: Any) -> None:
    assert not mcp.is_error, mcp.content[0].text
    assert ui.status_code == 200, ui.text[:500]
    got, want = ui_outputs(ui.text), mcp_outputs(mcp)
    got = {k: (kind, v.strip() if kind in ("text", "stderr") else v) for k, (kind, v) in got.items()}
    want = {k: (kind, v.strip() if kind in ("text", "stderr") else v) for k, (kind, v) in want.items()}
    assert got == want


async def assert_parity(web: Any, client: Any, tool: str, args: dict[str, Any], attempts: int = 1) -> None:
    """Cairo stamps PDFs with the current time, so two renders can straddle a second boundary: retry those only."""
    for attempt in range(attempts):
        mcp, ui = await both(web, client, tool, args)
        try:
            assert_same(mcp, ui)
            return
        except AssertionError:
            if attempt == attempts - 1:
                raise


LAYOUT_CASES: list[tuple[str, dict[str, Any]]] = [
    ("dot", {"input": SRC}), ("dot", {"input": SRC, "T": "png"}), ("dot", {"input": SRC, "T": "pdf"}),
    ("dot", {"input": SRC, "T": "plain"}), ("dot", {"input": SRC, "T": "json"}), ("dot", {"input": SRC, "T": "jpg"}),
    ("neato", {"input": SRC, "T": "svg", "G": {"overlap": "false"}, "N": {"shape": "box"}, "y": True}),
    ("fdp", {"input": SRC, "Ln": 5, "s": 1.5}), ("sfdp", {"input": SRC}), ("twopi", {"input": SRC, "K": "circo"}),
    ("circo", {"input": SRC, "T": "png:cairo"}), ("osage", {"input": SRC}), ("patchwork", {"input": SRC}),
    ("dot", {"input": 'digraph { a [shape=nosuchshape] }'}),
]  # fmt: skip


@pytest.mark.parametrize(
    "tool,args", LAYOUT_CASES, ids=[f"{t}-{a.get('T', 'svg')}-{i}" for i, (t, a) in enumerate(LAYOUT_CASES)]
)
async def test_layout_parity(web: Any, docker_image_client: Any, tool: str, args: dict[str, Any]) -> None:
    await assert_parity(web, docker_image_client, tool, args, attempts=3 if args.get("T") == "pdf" else 1)


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_processing_parity(web: Any, docker_image_client: Any, case_table: dict[str, Any], name: str) -> None:
    tool, args, _, src = case_table[name]
    if tool not in {t.name for t in (await docker_image_client.list_tools()).tools}:
        pytest.skip(f"{tool} not in this build")
    if tool == "gvmap":
        pytest.skip("gvmap output is randomized between runs")
    await assert_parity(web, docker_image_client, tool, {"input": src, **args})


@pytest.mark.parametrize("args", [{"k": 4}, {"c": 5, "d": True}, {"g": "2,3"}, {"T": "3,3"}, {"p": 4, "n": "v"}])
async def test_gvgen_parity(web: Any, docker_image_client: Any, args: dict[str, Any]) -> None:
    await assert_parity(web, docker_image_client, "gvgen", args)


async def test_converter_parity(web: Any, docker_image_client: Any) -> None:
    for tool, args in (
        ("gxl2dot", None),
        ("gml2gv", None),
        ("graphml2gv", {"input": GRAPHML}),
        ("mm2gv", {"input": MM, "u": True}),
    ):
        if args is None:
            first = "gv2gml" if tool == "gml2gv" else "dot2gxl"
            src = (await docker_image_client.call_tool(first, {"input": SRC})).content[0].text
            args = {"input": src}
        await assert_parity(web, docker_image_client, tool, args)


async def test_validate_dot_parity(web: Any, docker_image_client: Any) -> None:
    for src in ("digraph { a -> b }", "digraph {\n a ->\n}", 'digraph { a [image="x"] }'):
        mcp = await docker_image_client.call_tool("validate_dot", {"input": src})
        ui = await web.post("/ui/tools/validate_dot", content=urlencode({"input": src}), headers=FORM)
        m = re.search(r'<pre id="output-0" data-kind="text">(.*?)</pre>', ui.text, re.S)
        assert m and json.loads(html.unescape(m.group(1))) == json.loads(mcp.content[0].text)


async def test_error_parity(web: Any, docker_image_client: Any) -> None:
    for tool, args in (("dot", {"input": 'digraph { a [image="x"] }'}), ("dot", {"input": "digraph {"}),
                       ("dot", {"input": SRC, "T": "nonsense"}), ("dijkstra", {"input": "digraph{a}", "node": "-x"})):  # fmt: skip
        mcp, ui = await both(web, docker_image_client, tool, args)
        assert mcp.is_error and ui.status_code in (403, 422), text_of(mcp)[:200]
        msg = mcp.content[0].text.split(": ", 1)[1]
        assert html.unescape(msg) in html.unescape(ui.text).replace("\n", " ") or msg[:30] in html.unescape(ui.text)
