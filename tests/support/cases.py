"""Shared test inputs: Graphviz source texts and tool cases, used by the Docker image tests and the unit tests."""

from __future__ import annotations

import re
from typing import Any

from graphviz_mcp.dotsplit import split_graphs
from graphviz_mcp.tools.specs import PROGRAMS
from tests.support.helpers import text_of

CYCLE = "digraph { a -> b -> c -> a; c -> d }"
TWO = "graph { a -- b -- c; c -- a; d -- e }"
FANOUT = "digraph { r -> a; r -> b; r -> c; r -> d; x; y; z }"


def laid_out(engine: str, src: str, run: Any, *flags: str) -> str:
    out: str = run(engine, ["-Tdot", *flags], src).stdout.decode()
    return out


def cases(run: Any) -> dict[str, tuple[str, dict[str, Any], list[str], str]]:
    crossing = laid_out("dot", "digraph { a -> d; b -> c; a -> c; b -> d; a -> b }", run)
    pos2 = laid_out("neato", "graph { a -- b -- c -- a }", run)
    pos3 = laid_out("neato", "graph { x -- y -- z }", run)
    big = laid_out("sfdp", "graph { a -- b -- c -- d -- a; c -- e; e -- f; f -- g; g -- e }", run, "-Goverlap=prism")
    return {
        "acyclic": ("acyclic", {}, [], CYCLE),
        "acyclic -n": ("acyclic", {"n": True}, ["-n"], CYCLE),
        "bcomps": ("bcomps", {}, [], TWO),
        "bcomps -t": ("bcomps", {"t": True}, ["-t"], TWO),
        "ccomps": ("ccomps", {}, [], TWO),
        "ccomps -zv": ("ccomps", {"z": True}, ["-z"], TWO),
        "ccomps -x": ("ccomps", {"x": True}, ["-x"], TWO),
        "sccmap": ("sccmap", {}, [], CYCLE),
        "sccmap -s": ("sccmap", {"s": True}, ["-s"], CYCLE),
        "tred": ("tred", {}, [], "digraph { a -> b -> c; a -> c }"),
        "unflatten": ("unflatten", {"f": True, "l": 2}, ["-f", "-l", "2"], FANOUT),
        "unflatten -c": ("unflatten", {"c": 3}, ["-c", "3"], FANOUT),
        "gc": ("gc", {}, [], TWO),
        "gc -a": ("gc", {"a": True}, ["-a"], TWO),
        "gc -nc": ("gc", {"n": True, "c": True}, ["-n", "-c"], TWO),
        "nop": ("nop", {}, [], "digraph{a->b [color=red]}"),
        "nop -p": ("nop", {"p": True}, ["-p"], "digraph{a->b}"),
        "cluster": ("cluster", {"C": 2}, ["-C", "2"], "graph { a -- b -- c -- a; d -- e -- f -- d; c -- d }"),
        "dijkstra": ("dijkstra", {"node": "a"}, ["a"], "digraph { a -> b -> c; a -> c }"),
        "dijkstra -p": ("dijkstra", {"node": "a", "p": True}, ["-p", "a"], "graph { a -- b -- c }"),
        "gvcolor": ("gvcolor", {}, [], laid_out("dot", "digraph { a [color=red]; a -> b -> c }", run)),
        "gvpack": ("gvpack", {"array": "_c2"}, ["-array_c2"], pos2 + "\n" + pos3),
        "gvpack -u": ("gvpack", {"u": True}, ["-u"], pos2 + "\n" + pos3),
        "mingle": ("mingle", {}, [], crossing),
        "prune": ("prune", {"n": ["b"]}, ["-nb"], "digraph { a -> b -> c; a -> d }"),
        "prune -N": (
            "prune",
            {"n": ["b"], "N": ["color=red"]},
            ["-nb", "-Ncolor=red"],
            "digraph { a -> b -> c; a -> d }",
        ),
        "edgepaint": ("edgepaint", {"angle": 20}, ["--angle=20"], crossing),
        "edgepaint seed": (
            "edgepaint",
            {"random_seed": 7, "color_scheme": "rgb"},
            ["--random_seed=7", "--color_scheme=rgb"],
            crossing,
        ),
        "gvmap": ("gvmap", {"c": 2}, ["-c", "2"], big),
        "gvmap -e": ("gvmap", {"e": True, "b": 1}, ["-e", "-b", "1"], big),
        "dot2gxl": ("dot2gxl", {}, [], "digraph { a -> b }"),
        "gv2gml": ("gv2gml", {}, [], "digraph { a -> b }"),
        "gv2gml -y": ("gv2gml", {"y": True}, ["-y"], "digraph { a -> b }"),
    }


CASE_NAMES = [
    "acyclic", "acyclic -n", "bcomps", "bcomps -t", "ccomps", "ccomps -zv", "ccomps -x", "sccmap", "sccmap -s", "tred",
    "unflatten", "unflatten -c", "gc", "gc -a", "gc -nc", "nop", "nop -p", "cluster", "dijkstra", "dijkstra -p",
    "gvcolor", "gvpack", "gvpack -u", "mingle", "prune", "prune -N", "edgepaint", "edgepaint seed", "gvmap", "gvmap -e",
    "dot2gxl", "gv2gml", "gv2gml -y",
]  # fmt: skip


async def assert_tool_matches_cli(client: Any, name: str, run: Any) -> None:
    """Run case `name` through the MCP tool and through the CLI (via `run`) and compare."""
    tool, args, cli_args, src = cases(run)[name]
    expected = run(tool, cli_args, src)
    assert expected.returncode in PROGRAMS[tool].ok_returncodes, (
        f"{name}: CLI exits {expected.returncode}: the table's ok_returncodes would reject a good run"
    )
    r = await client.call_tool(tool, {"input": src, **args})
    assert not r.is_error, text_of(r)
    stdout = expected.stdout.decode()
    stderr_shown = bool(expected.stderr.strip())
    got = [c.text for c in r.content if c.type == "text" and not c.text.startswith("[stderr]")]
    assert any(c.text.startswith("[stderr]") for c in r.content if c.type == "text") == stderr_shown
    if PROGRAMS[tool].output == "graphs":
        want = split_graphs(stdout) or ([stdout] if stdout.strip() else [])
    else:
        want = [stdout] if stdout.strip() else []
    if not want and not stderr_shown:
        want = ["(no output)"]
    if tool == "gvmap":  # gvmap draws random boundary points: compare shape, not bytes
        assert len(got) == len(want) and got[0].splitlines()[0] == want[0].splitlines()[0]
        assert sorted(re.findall(r"^\t(\w+)\s", got[0], re.M)) == sorted(re.findall(r"^\t(\w+)\s", want[0], re.M))
    else:
        assert got == want


GVGEN = [
    ({"k": 4}, ["-k4"]), ({"c": 5, "d": True}, ["-c5", "-d"]), ({"g": "3,3"}, ["-g3,3"]), ({"p": 6}, ["-p6"]),
    ({"t": "3,2"}, ["-t3,2"]), ({"r": "6,8", "u": 7}, ["-r6,8", "-u7"]), ({"s": 5, "n": "v", "N": "star"}, ["-s5", "-nv", "-Nstar"]),
    ({"T": "3,3"}, ["-T3,3"]), ({"w": 6}, ["-w6"]), ({"h": 3}, ["-h3"]), ({"b": "2,3"}, ["-b2,3"]),
]  # fmt: skip


GXL = "digraph G { a -> b; b -> c [label=x] }"


GRAPHML = (
    '<?xml version="1.0"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns">'
    '<graph id="G" edgedefault="directed"><node id="n0"/><node id="n1"/><edge source="n0" target="n1"/></graph></graphml>'
)


MM = "%%MatrixMarket matrix coordinate real general\n3 3 2\n1 2 1.0\n2 3 1.0\n"


HOSTILE = {
    "plain node attr": 'digraph { a [image="/etc/passwd"] }',
    "node default": 'digraph { node [image="/etc/passwd"]; a }',
    "edge default": 'digraph { edge [image="x"]; a -> b }',
    "graph statement": 'digraph { image="x"; a }',
    "graph [..]": 'digraph { graph [image="x"]; a }',
    "cluster default": 'digraph { subgraph cluster_x { node [shapefile="x"]; a } }',
    "nested subgraph": "digraph { subgraph a { subgraph b { subgraph c { z [image=x] } } } }",
    "quoted name": 'digraph { a ["image"="x"] }',
    "concatenated name": 'digraph { a ["ima"+"ge"="x"] }',
    "concatenation with comments": 'digraph { a ["ima" /* c */ + // c\n "ge" = x] }',
    "concatenated three": 'digraph { a ["i"+"m"+"age"=x] }',
    "line continuation in name": 'digraph { a ["ima\\\nge"=x] }',
    "uppercase": "digraph { a [IMAGE=x] }",
    "mixed case": "digraph { a [ShapeFile=x] }",
    "imagepath": 'digraph { imagepath="/etc"; a }',
    "fontpath": 'digraph { fontpath="/usr/share"; a }',
    "stylesheet": 'digraph { stylesheet="/etc/passwd"; a }',
    "html IMG upper": 'digraph { a [label=<<IMG SRC="/etc/passwd"/>>] }',
    "html img lower": "digraph { a [label=<<img src='/etc/passwd'/>>] }",
    "html img mixed": 'digraph { a [label=<<ImG SRC="x"/>>] }',
    "html in table": 'digraph { a [label=<<TABLE><TR><TD><IMG SRC="x"/></TD></TR></TABLE>>] }',
    "html deep nesting": 'digraph { a [label=<<TABLE><TR><TD><TABLE><TR><TD><FONT><IMG SRC="x"/></FONT></TD></TR></TABLE></TD></TR></TABLE>>] }',
    "html edge label": 'digraph { a -> b [label=<<IMG SRC="x"/>>] }',
    "html xlabel": 'digraph { a [xlabel=<<IMG SRC="x"/>>] }',
    "html headlabel": 'digraph { a -> b [headlabel=<<IMG SRC="x"/>>] }',
    "html graph label": 'digraph { label=<<IMG SRC="x"/>>; a }',
    "html cluster label": 'digraph { subgraph cluster_a { label=<<IMG SRC="x"/>>; a } }',
    "html default label": 'digraph { node [label=<<IMG SRC="x"/>>]; a }',
    "html as node id": 'digraph { <<IMG SRC="x"/>> }',
    "second graph in stream": "digraph a { x }\ndigraph b { y [image=z] }",
    "strict graph": "strict graph { a -- b [image=x] }",
    "edge chain": "digraph { a -> b -> c [image=x] }",
    "after many statements": "digraph {" + "".join(f"n{i}; " for i in range(2000)) + " z [image=x] }",
    "comments around tokens": 'digraph { a [/* x */ image /* y */ = /* z */ "f"] }',
    "statement after subgraph": 'digraph { subgraph { a } image="x" }',
    "port-like prefix": "digraph { a:image -> b [image=x] }",
    "self closing img": "digraph { a [label=<<IMG/>>] }",
    "multiple attrs, denied last": "digraph { a [color=red, shape=box, label=hi, image=x] }",
    "semicolons between attrs": "digraph { a [color=red; image=x] }",
    "numeric-looking value": "digraph { a [image=1.5] }",
    "unicode name next to denied": "digraph { é [image=x] }",
}


SCAN_SRC = """strict DiGraph "G" { "ima"+"ge"="x"; node [Image="/etc/passwd" Shapefile=y]; edge [style=dashed]
 subgraph cluster_a { graph [stylesheet="s.css"]; a [label=<<IMG SRC="a.png"/>>]; a:p:n -> b }
 b [ "shape"="box" ; fontpath = "/x" ] ; a -> b -> c [color=red] }
digraph H { x }"""


BENIGN = {
    "node named image": "digraph { image -> b }",
    "quoted node named image": 'digraph { "image" -> "shapefile" }',
    "label text mentions attr": 'digraph { a [label="image=/etc/passwd; shapefile=x"] }',
    "label value is word image": "digraph { a [label=image] }",
    "comment mentions attr": "digraph { /* image=x */ a // image=y\n }",
    "escaped quote in label": r'digraph { a [label="\" image=\"x"] }',
    "html without img": "digraph { a [label=<<TABLE><TR><TD>hi</TD></TR></TABLE>>] }",
    "html text about img": "digraph { a [label=<&lt;IMG SRC=x&gt;>] }",
    "ports": "digraph { a:n -> b:s [color=red] }",
    "empty image value is no file": 'digraph { a [image=""] }',  # Graphviz ignores it; nop drops it
    "plain": "digraph { rankdir=LR; a -> b -> c }",
}


RASTER_CASES = {
    "default": "digraph { a -> b -> c }",
    "dpi": "digraph { dpi=200; a -> b -> c -> d }",
    "size down": 'digraph { size="2,2"; a -> b -> c -> d -> e -> f }',
    "size up": 'digraph { size="6,6!"; a -> b }',
    "pad": "digraph { pad=1.5; a -> b }",
    "ratio": "digraph { ratio=2; a -> b }",
    "rotate": "digraph { rotate=90; a -> b -> c }",
    "cluster": "digraph { subgraph cluster_x { a -> b } c -> a }",
    "wide": "digraph { rankdir=LR; " + " -> ".join(f"n{i}" for i in range(30)) + " }",
}
