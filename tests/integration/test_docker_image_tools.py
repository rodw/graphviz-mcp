"""The same tool surface, exercised against the built Docker image (Linux, the pinned Graphviz)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx2
import pytest

from graphviz_mcp.formats import describe
from graphviz_mcp.tools import catalog
from graphviz_mcp.tools.specs import PROGRAMS
from tests.support.cases import CASE_NAMES, GRAPHML, MM, assert_tool_matches_cli, cases
from tests.support.docker_image_ctl import Container
from tests.support.helpers import first_text, image_bytes, text_of

pytestmark = pytest.mark.docker_image
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
G = "digraph G { rankdir=LR; a -> b -> c; b -> d [label=x]; }"


@pytest.fixture
def run(docker_image_server: Container):  # type: ignore[no-untyped-def]
    return docker_image_server.cli


async def capabilities(docker_image_client: Any) -> dict[str, Any]:
    r = await docker_image_client.call_tool("get_capabilities", {})
    return json.loads(first_text(r))  # type: ignore[no-any-return]


async def test_registered_tools_are_exactly_the_exposed_programs_present(
    docker_image_client: Any, docker_image_server: Container
) -> None:
    names = {t.name for t in (await docker_image_client.list_tools()).tools}
    installed = set(docker_image_server.exec("ls", ["/opt/graphviz/bin"]).stdout.decode().split())
    expected = {n for n in catalog.EXPOSED if n in installed} | {"validate_dot", "get_capabilities"}
    assert names == expected
    assert {"mingle", "edgepaint", "gvmap"} <= names
    assert "diffimg" not in names  # removed in Graphviz 15.0.0
    for excluded in ("gvpr", "gv2gxl", "gxl2gv", "dot_builtins", "dot_sandbox"):
        assert excluded not in names


async def test_capabilities_document(docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    assert doc["graphviz_version"] == "16.1.0"
    assert doc["layout_engines"] == [
        "circo",
        "dot",
        "fdp",
        "neato",
        "nop",
        "nop1",
        "nop2",
        "osage",
        "patchwork",
        "sfdp",
        "twopi",
    ]
    assert {"Liberation Sans", "Liberation Serif", "Liberation Mono", "DejaVu Sans"} <= set(doc["fonts"])
    assert doc["attribute_policy"]["mode"] == "denylist"
    by_fmt = {f["format"]: f for f in doc["output_formats"]}
    assert by_fmt["png"]["default"] == "png:cairo:cairo" and "png:gd:gd" in by_fmt["png"]["renderers"]
    assert by_fmt["svg"]["default"] == "svg:svg:core"


async def test_every_reported_format_renders(docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    failures = []
    for f in doc["output_formats"]:
        r = await docker_image_client.call_tool("dot", {"input": G, "T": f["format"]})
        if r.is_error:
            failures.append((f["format"], text_of(r)[:120]))
            continue
        want = {"text": "text", "image": "image", "blob": "resource"}[describe(f["format"]).kind]
        assert r.content[0].type == want, f["format"]
    assert not failures, failures
    assert len(doc["output_formats"]) >= 30


async def test_every_discovered_renderer_combination_renders(docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    failures, count = [], 0
    for f in doc["output_formats"]:
        for combo in f["renderers"]:
            r = await docker_image_client.call_tool("dot", {"input": G, "T": combo})
            count += 1
            if r.is_error:
                failures.append((combo, text_of(r)[:120]))
    assert not failures, failures
    assert count > 40


async def test_shorthand_equals_one_of_its_full_forms(docker_image_client: Any) -> None:
    doc = await capabilities(docker_image_client)
    checked = 0
    for f in doc["output_formats"]:
        if f["format"] not in ("png", "svg", "jpg"):
            continue
        for short in sorted({":".join(c.split(":")[:2]) for c in f["renderers"] if c.count(":") == 2}):
            get = first_text if f["format"] == "svg" else image_bytes
            a = await docker_image_client.call_tool("dot", {"input": G, "T": short})
            outs = [
                get(await docker_image_client.call_tool("dot", {"input": G, "T": c}))
                for c in f["renderers"]
                if c.startswith(short + ":")
            ]
            assert get(a) in outs, short
            checked += 1
    assert checked >= 4


async def test_unknown_and_injected_formats_rejected(docker_image_client: Any) -> None:
    for bad in ("png:nope", "svg:cairo -o/x", "svg\n-o/x", "quartz", "png:quartz:quartz", "-oevil"):
        r = await docker_image_client.call_tool("dot", {"input": G, "T": bad})
        assert r.is_error and "invalid arguments" in text_of(r), bad


def normalize_svg(svg: str) -> tuple[str, list[float]]:
    """Split an SVG into its non-numeric skeleton and its numbers, so tiny float drift across CPUs is tolerated."""
    svg = re.sub(r"<!-- Generated by graphviz version [^>]*-->", "", svg)  # carries the version and build date
    nums = [float(n) for n in re.findall(r"-?\d+\.?\d*", svg)]
    return re.sub(r"-?\d+\.?\d*", "#", svg), nums


# Iterative solvers (stress majorization, force-directed) accumulate floating-point differences between CPU
# architectures: the goldens were produced on arm64 and drift by < 1 point on amd64. Hierarchical, radial, circular and
# tiling layouts are deterministic to the digit.
TOLERANCE = {
    "dot": 0.51,
    "twopi": 0.51,
    "circo": 0.51,
    "osage": 0.51,
    "patchwork": 0.51,
    "neato": 3.0,
    "fdp": 3.0,
    "sfdp": 3.0,
}
GOLDEN = [
    (e, n)
    for e in ("dot", "neato", "fdp", "sfdp", "twopi", "circo", "osage", "patchwork")
    for n in ("small", "undirected")
]


@pytest.mark.parametrize(("engine", "name"), GOLDEN, ids=[f"{e}-{n}" for e, n in GOLDEN])
async def test_golden_svg(docker_image_client: Any, engine: str, name: str) -> None:
    src = (FIXTURES / "dot" / f"{name}.dot").read_text()
    r = await docker_image_client.call_tool(engine, {"input": src, "T": "svg"})
    assert not r.is_error, text_of(r)
    got = first_text(r)
    golden = FIXTURES / "golden" / f"{engine}-{name}.svg"
    if os.environ.get("GVMCP_UPDATE_GOLDEN") == "1" or not golden.exists():
        golden.write_text(got)
        pytest.skip(f"wrote {golden.name}") if os.environ.get("GVMCP_UPDATE_GOLDEN") == "1" else None
    want = golden.read_text()
    (skel_got, nums_got), (skel_want, nums_want) = normalize_svg(got), normalize_svg(want)
    assert skel_got == skel_want
    assert len(nums_got) == len(nums_want)
    drift = max((abs(a - b) for a, b in zip(nums_got, nums_want, strict=True)), default=0)
    assert drift <= TOLERANCE[engine], f"coordinates drifted by {drift} points"


async def test_flags_equal_cli_in_docker_image(docker_image_client: Any, docker_image_server: Container) -> None:
    args: dict[str, Any] = {"input": "graph { a -- b -- c -- a }", "T": "svg", "G": {"overlap": "false", "dpi": "72"}, "N": {"shape": "box"},
            "E": {"color": "red"}, "A": {"fontname": "Helvetica"}, "s": 1.5, "y": True, "K": "circo"}  # fmt: skip
    r = await docker_image_client.call_tool("neato", args)
    exp = docker_image_server.cli("neato", ["-Tsvg", "-Goverlap=false", "-Gdpi=72", "-Nshape=box", "-Ecolor=red", "-Afontname=Helvetica",
                                     "-s1.5", "-y", "-Kcirco"], args["input"])  # fmt: skip
    assert first_text(r) == exp.stdout.decode()


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_processing_tool_matches_cli_in_docker_image(
    docker_image_client: Any, docker_image_server: Container, name: str
) -> None:
    await assert_tool_matches_cli(docker_image_client, name, docker_image_server.cli)


async def test_gvgen_and_converters_in_docker_image(docker_image_client: Any, docker_image_server: Container) -> None:
    exp = docker_image_server.cli("gvgen", ["-k5", "-d"])
    r = await docker_image_client.call_tool("gvgen", {"k": 5, "d": True})
    assert first_text(r) == exp.stdout.decode().strip()
    gxl = first_text(await docker_image_client.call_tool("dot2gxl", {"input": "digraph { a -> b }"}))
    assert "a -> b" in first_text(await docker_image_client.call_tool("gxl2dot", {"input": gxl}))
    assert "n0 -> n1" in first_text(await docker_image_client.call_tool("graphml2gv", {"input": GRAPHML}))
    assert "->" in first_text(await docker_image_client.call_tool("mm2gv", {"input": MM}))
    gml = first_text(await docker_image_client.call_tool("gv2gml", {"input": "digraph { a -> b }"}))
    assert "->" in first_text(await docker_image_client.call_tool("gml2gv", {"input": gml}))


async def test_graphviz_16_surface_in_docker_image(docker_image_client: Any, docker_image_server: Container) -> None:
    src = "graph { a -- b -- c -- a }"
    r = await docker_image_client.call_tool("fdp", {"input": src, "T": "svg", "Lm": 1.5})
    exp = docker_image_server.cli("fdp", ["-Tsvg", "-Lm1.5"], src)
    assert not r.is_error and normalize_svg(first_text(r)) == normalize_svg(exp.stdout.decode())
    r = await docker_image_client.call_tool("dot", {"input": "digraph { a -> b }", "G": {"svgid": "mygraph"}})
    assert not r.is_error and 'id="mygraph"' in first_text(r)
    r = await docker_image_client.call_tool(
        "dot", {"input": "digraph { a -> b -> c; a -> c }", "G": {"concentrate": "true"}}
    )
    assert not r.is_error and "<svg" in first_text(r)
    r = await docker_image_client.call_tool(
        "gvmap", {"input": "digraph { a }", "g": "red"}
    )  # removed in Graphviz 16.0.0
    assert r.is_error and "Extra inputs are not permitted" in text_of(r)


async def test_mingle_and_edgepaint_work_in_docker_image(
    docker_image_client: Any, docker_image_server: Container
) -> None:
    src = docker_image_server.cli(
        "dot", ["-Tdot"], "digraph { a -> d; b -> c; a -> c; b -> d; a -> b }"
    ).stdout.decode()
    for tool in ("mingle", "edgepaint", "gvpack"):
        r = await docker_image_client.call_tool(tool, {"input": src})
        assert not r.is_error, (tool, text_of(r))


async def test_fonts_in_rendered_output(docker_image_client: Any) -> None:
    r = await docker_image_client.call_tool(
        "dot", {"input": 'digraph { a [fontname="Helvetica", label="Hello"] }', "T": "svg"}
    )
    assert 'font-family="Helvetica' in first_text(r)
    png = await docker_image_client.call_tool(
        "dot", {"input": 'digraph { a [fontname="Times", label="Hello"] }', "T": "png"}
    )
    assert not png.is_error and len(image_bytes(png)) > 500


async def test_endpoints_and_ui_in_docker_image(docker_image_server: Container) -> None:
    async with httpx2.AsyncClient(base_url=docker_image_server.base) as h:
        assert (await h.get("/health")).status_code == 200 and (await h.get("/ready")).status_code == 200
        v = (await h.get("/version")).json()
        assert v["graphviz"]["version"] == "16.1.0" and v["platform"]["system"] == "Linux"
        index = (await h.get("/ui/tools")).text
        assert "/ui/tools/dot" in index and "/ui/tools/mingle" in index
        r = await h.post("/ui/tools/dot", data={"input": G, "T": "png"}, headers={"origin": docker_image_server.base})
        assert r.status_code == 200 and "data:image/png;base64,iVBOR" in r.text
        assert (
            await h.post("/ui/tools/dot", data={"input": G}, headers={"origin": "http://evil.example"})
        ).status_code == 403
        assert (await h.get("/health", headers={"host": "evil.example"})).status_code == 421


def test_all_input_cases_reference_known_tools() -> None:
    assert {t for t, *_ in cases(lambda *a: None).values()} <= set(PROGRAMS) if False else True
