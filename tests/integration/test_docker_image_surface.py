"""The tool surface (parameters, errors, content shaping, CLI equivalence), against the Docker image."""

from __future__ import annotations

from typing import Any

import pytest

from graphviz_mcp.dotsplit import split_graphs
from graphviz_mcp.tools.specs import PROGRAMS
from tests.support.cases import CYCLE, GRAPHML, GVGEN, GXL, MM, TWO
from tests.support.helpers import blob_bytes, first_text, image_bytes, text_of

pytestmark = pytest.mark.docker_image
G = "digraph G { rankdir=LR; a -> b -> c; b -> d [label=x]; }"


async def call(client: Any, tool: str, **args: Any) -> Any:
    return await client.call_tool(tool, args)


# --- the tool table ------------------------------------------------------------------------------------------
async def test_tool_schemas_match_the_table(docker_image_client: Any) -> None:
    tools = {t.name: t for t in (await docker_image_client.list_tools()).tools}
    for name, tool in tools.items():
        if name not in PROGRAMS:
            continue  # MCP-only extras
        props = tool.input_schema["properties"]
        expected = {p.name for p in PROGRAMS[name].params}
        if PROGRAMS[name].input in ("dot", "text", "file"):
            expected.add("input")
        assert set(props) == expected, name
        assert tool.input_schema.get("additionalProperties") is False
        assert all("description" in v for v in props.values()), name


# --- layout tools --------------------------------------------------------------------------------------------
async def test_default_format_is_svg_and_matches_the_cli(docker_image_client: Any, docker_image_server: Any) -> None:
    r = await call(docker_image_client, "dot", input=G)
    assert first_text(r) == docker_image_server.cli("dot", ["-Tsvg"], G).stdout.decode()


async def test_numeric_attribute_values_are_accepted(docker_image_client: Any, docker_image_server: Any) -> None:
    r = await call(docker_image_client, "dot", input=G, G={"nodesep": 0.5, "center": True})
    expected = docker_image_server.cli("dot", ["-Tsvg", "-Gnodesep=0.5", "-Gcenter=true"], G)
    assert first_text(r) == expected.stdout.decode()


@pytest.mark.parametrize(
    ("scope", "attrs", "expected"),
    [
        ("G", {"bgcolor": "lightblue"}, 'fill="lightblue"'),
        ("N", {"fillcolor": "gold", "style": "filled"}, 'fill="gold"'),
        ("E", {"color": "crimson"}, 'stroke="crimson"'),
        ("A", {"fontname": "Courier"}, "Courier"),
    ],
)
async def test_each_attribute_scope_reaches_graphviz(
    docker_image_client: Any, scope: str, attrs: dict[str, str], expected: str
) -> None:
    """A dropped `-G`/`-N`/`-E`/`-A` option would be invisible to argument tests: look at what Graphviz drew."""
    r = await call(docker_image_client, "dot", input="digraph { a -> b }", T="svg", **{scope: attrs})
    assert not r.is_error, text_of(r)
    assert expected in first_text(r), (scope, first_text(r)[:300])


async def test_png_is_image_content_matching_the_cli(docker_image_client: Any, docker_image_server: Any) -> None:
    r = await call(docker_image_client, "dot", input=G, T="png")
    assert r.content[0].mime_type == "image/png"
    assert image_bytes(r) == docker_image_server.cli("dot", ["-Tpng"], G).stdout


async def test_pdf_is_an_embedded_blob(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input=G, T="pdf")
    assert r.content[0].resource.mime_type == "application/pdf" and blob_bytes(r).startswith(b"%PDF")


async def test_unknown_parameters_are_rejected(docker_image_client: Any) -> None:
    for extra in ({"o": "/tmp/x"}, {"O": True}, {"Tt": "svg"}, {"l": "x"}):
        r = await call(docker_image_client, "dot", input=G, **extra)
        assert r.is_error and "Extra inputs are not permitted" in text_of(r), extra


async def test_warnings_are_returned_alongside_the_result(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input="digraph { a [shape=nosuchshape] }")
    assert not r.is_error
    assert r.content[0].type == "text" and "<svg" in r.content[0].text
    assert any(c.type == "text" and c.text.startswith("[stderr]") for c in r.content)


async def test_syntax_error_is_a_tool_error_with_the_line(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input="digraph { a -> ")
    assert r.is_error and "syntax error" in text_of(r) and "line" in text_of(r)


async def test_policy_rejection_is_a_tool_error(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input='digraph { a [image="/etc/passwd"] }')
    assert r.is_error and "attribute policy violation" in text_of(r) and "image" in text_of(r)
    r = await call(docker_image_client, "dot", input="digraph { a }", N={"shapefile": "x"})
    assert r.is_error and "shapefile" in text_of(r)
    r = await call(docker_image_client, "dot", input='digraph { a [label=<<IMG SRC="x"/>>] }')
    assert r.is_error and "IMG" in text_of(r)


async def test_empty_input_is_rejected(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input="   ")
    assert r.is_error and "input" in text_of(r)


async def test_a_huge_raster_is_refused_before_rendering(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dot", input='digraph { size="100,100!"; dpi=300; a }', T="png")
    assert r.is_error and "megapixels" in text_of(r)
    r = await call(docker_image_client, "dot", input="digraph { a }", G={"dpi": "5000"}, T="png")
    assert r.is_error and "dpi" in text_of(r)


async def test_fdp_specific_flags(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "fdp", input="graph { a -- b -- c }", Ln=5, Lg=True, LT="0.5")
    assert not r.is_error, text_of(r)


async def test_no_layout_mode_with_positions_matches_the_cli(
    docker_image_client: Any, docker_image_server: Any
) -> None:
    pos = 'digraph { node [pos="1,1!"]; a [pos="0,0!"]; b [pos="2,1!"]; a -> b }'
    r = await call(docker_image_client, "neato", input=pos, n=2)
    expected = docker_image_server.cli("neato", ["-Tsvg", "-n2"], pos)
    assert not r.is_error and first_text(r) == expected.stdout.decode()


# --- processing tools ----------------------------------------------------------------------------------------
async def test_ccomps_returns_one_string_per_component(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "ccomps", input=TWO, x=True)
    graphs = [c.text for c in r.content if c.type == "text"]
    assert len(graphs) == 2 and all(g.lstrip().startswith(("graph", "strict")) or "{" in g for g in graphs)


async def test_bcomps_external_returns_one_string_per_block(docker_image_client: Any, docker_image_server: Any) -> None:
    r = await call(docker_image_client, "bcomps", input=TWO, x=True)
    graphs = [c.text for c in r.content if c.type == "text"]
    cli_graphs = split_graphs(docker_image_server.cli("bcomps", ["-x"], TWO).stdout.decode())
    assert len(graphs) >= 2 and graphs == cli_graphs


async def test_acyclic_exit_status_one_is_not_an_error(docker_image_client: Any, docker_image_server: Any) -> None:
    exp = docker_image_server.cli("acyclic", ["-n"], CYCLE)
    r = await call(docker_image_client, "acyclic", input=CYCLE, n=True)
    assert not r.is_error and exp.returncode in (0, 1)


async def test_processing_tool_stderr_is_returned_as_its_own_block(
    docker_image_client: Any, docker_image_server: Any
) -> None:
    assert docker_image_server.cli("sccmap", [], CYCLE).stderr.strip()  # sccmap reports its statistics on stderr
    r = await call(docker_image_client, "sccmap", input=CYCLE)
    assert not r.is_error and any(c.type == "text" and c.text.startswith("[stderr]") for c in r.content)


async def test_graphviz_failure_is_a_tool_error(docker_image_client: Any) -> None:
    r = await call(docker_image_client, "dijkstra", input="digraph { a ->", node="a")
    assert r.is_error and "invalid input" in text_of(r)


async def test_policy_applies_to_processing_tools(docker_image_client: Any) -> None:
    for tool, args in (("nop", {}), ("tred", {}), ("ccomps", {}), ("gvpack", {}), ("dijkstra", {"node": "a"})):
        r = await call(docker_image_client, tool, input='digraph { a [image="/etc/passwd"] }', **args)
        assert r.is_error and "policy" in text_of(r), tool
    r = await call(docker_image_client, "gvpack", input="digraph { a }", G={"image": "x"})
    assert r.is_error and "image" in text_of(r)
    r = await call(docker_image_client, "prune", input="digraph { a -> b }", n=["a"], N=["image=/etc/passwd"])
    assert r.is_error and "image" in text_of(r)


async def test_unknown_parameters_are_rejected_on_processing_tools(docker_image_client: Any) -> None:
    assert (await call(docker_image_client, "ccomps", input=TWO, o="/tmp/x")).is_error


async def test_dijkstra_requires_a_node(docker_image_client: Any) -> None:
    assert (await call(docker_image_client, "dijkstra", input="digraph{a->b}")).is_error


# --- generators and converters -------------------------------------------------------------------------------
@pytest.mark.parametrize(("args", "cli_args"), GVGEN, ids=[" ".join(c) for _, c in GVGEN])
async def test_gvgen_matches_the_cli(
    docker_image_client: Any, docker_image_server: Any, args: dict[str, Any], cli_args: list[str]
) -> None:
    exp = docker_image_server.cli("gvgen", cli_args)
    r = await call(docker_image_client, "gvgen", **args)
    assert not r.is_error, text_of(r)
    assert [c.text for c in r.content if not c.text.startswith("[stderr]")] == split_graphs(exp.stdout.decode())


async def test_gvgen_bounds_are_enforced(docker_image_client: Any) -> None:
    for args in ({"k": 100_000}, {"c": 10**9}, {"g": "9999,9999"}, {"k": 5, "o": "/tmp/x"}):
        assert (await call(docker_image_client, "gvgen", **args)).is_error, args


async def test_gvgen_has_no_input_parameter(docker_image_client: Any) -> None:
    tool = next(t for t in (await docker_image_client.list_tools()).tools if t.name == "gvgen")
    assert "input" not in tool.input_schema["properties"]


async def test_gxl_matches_the_cli_and_round_trips(docker_image_client: Any, docker_image_server: Any) -> None:
    gxl = await call(docker_image_client, "dot2gxl", input=GXL)
    assert not gxl.is_error and "<gxl" in first_text(gxl)
    back = await call(docker_image_client, "gxl2dot", input=first_text(gxl))
    assert not back.is_error and "a -> b" in first_text(back)
    assert first_text(gxl) == docker_image_server.cli("dot2gxl", [], GXL).stdout.decode()


async def test_gml_round_trips(docker_image_client: Any) -> None:
    gml = await call(docker_image_client, "gv2gml", input=GXL)
    assert not gml.is_error and "graph [" in first_text(gml)
    back = await call(docker_image_client, "gml2gv", input=first_text(gml), g="tmpl")
    assert not back.is_error and "->" in first_text(back)


async def test_graphml2gv_matches_the_cli(docker_image_client: Any, docker_image_server: Any) -> None:
    r = await call(docker_image_client, "graphml2gv", input=GRAPHML)
    assert not r.is_error and "n0 -> n1" in first_text(r)
    expected = split_graphs(docker_image_server.cli("graphml2gv", [], GRAPHML).stdout.decode())[0]
    assert first_text(r) == expected


async def test_mm2gv_matches_the_cli(docker_image_client: Any, docker_image_server: Any) -> None:
    exp = docker_image_server.exec("sh", ["-c", "cat > /tmp/m.mtx && /opt/graphviz/bin/mm2gv /tmp/m.mtx"], MM)
    r = await call(docker_image_client, "mm2gv", input=MM)
    assert not r.is_error and first_text(r) == split_graphs(exp.stdout.decode())[0]
    r = await call(docker_image_client, "mm2gv", input=MM, u=True)
    assert "--" in first_text(r)


async def test_converter_garbage_input_is_an_error(docker_image_client: Any) -> None:
    for tool in ("gxl2dot", "gml2gv", "graphml2gv", "mm2gv"):
        r = await call(docker_image_client, tool, input="this is not valid")
        assert r.is_error or "(no output)" in first_text(r), tool
