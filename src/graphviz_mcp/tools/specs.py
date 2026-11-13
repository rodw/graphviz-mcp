"""The declarative program/flag table: the single source of truth.

From it we generate the MCP tool schemas, the argv builder, the Web UI forms, the generated docs and
the name-conformance test. Tool names equal Graphviz program names; parameter names equal
the flag letters (or long option names) of the program.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Style = Literal["switch", "attached", "separate", "long", "kv", "multi", "positional"]
PType = Literal["bool", "int", "float", "str", "kv", "strlist"]
Dynamic = Literal["format", "engine"]
Input = Literal["dot", "text", "file", "none"]
Output = Literal["format", "graphs", "text"]

NAME_RE = r"[A-Za-z_][A-Za-z0-9_.:\-]{0,127}"


@dataclass(frozen=True)
class Param:
    name: str  # MCP parameter name
    token: str  # how the program's usage text spells it, e.g. "-G", "--accuracy", "<node>"
    ptype: PType
    style: Style
    doc: str
    flag: str = ""  # CLI spelling emitted ("-x", "-K", "--accuracy")
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[int | str, ...] | None = None
    pattern: str | None = None
    dynamic: Dynamic | None = None
    required: bool = False
    default: Any = None

    @property
    def cli(self) -> str:
        """Human-readable flag, used in descriptions."""
        return self.flag or self.token


@dataclass(frozen=True)
class Program:
    name: str
    group: str
    summary: str
    input: Input
    output: Output
    params: tuple[Param, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()  # (usage token prefix, reason it is not exposed)
    ok_returncodes: tuple[int, ...] = (0,)
    input_doc: str = "The graph in DOT language."
    tokens_extra: tuple[str, ...] = field(default=())


# --------------------------------------------------------------------------- constructors
def sw(letter: str, doc: str) -> Param:
    return Param(letter, f"-{letter}", "bool", "switch", doc, flag=f"-{letter}")


def att(letter: str, ptype: PType, doc: str, **kw: Any) -> Param:
    return Param(letter, f"-{letter}", ptype, "attached", doc, flag=f"-{letter}", **kw)


def sep(letter: str, ptype: PType, doc: str, **kw: Any) -> Param:
    return Param(letter, f"-{letter}", ptype, "separate", doc, flag=f"-{letter}", **kw)


def kv(letter: str, doc: str) -> Param:
    return Param(letter, f"-{letter}", "kv", "kv", doc, flag=f"-{letter}")


def longopt(name: str, ptype: PType, doc: str, **kw: Any) -> Param:
    return Param(name, f"--{name}", ptype, "long", doc, flag=f"--{name}", **kw)


def switch_long(name: str, doc: str) -> Param:
    return Param(name, f"--{name}", "bool", "switch", doc, flag=f"--{name}")


def positional(name: str, doc: str, **kw: Any) -> Param:
    return Param(name, f"<{name}>", "str", "positional", doc, **kw)


V = sw("v", "Verbose messages on stderr (-v).")

# --------------------------------------------------------------------------- layout engines
_NUM = r"[0-9]+(\.[0-9]+)?"
LAYOUT_PARAMS: tuple[Param, ...] = (
    att(
        "T",
        "str",
        "Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, "
        "for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports "
        "(see get_capabilities).",
        dynamic="format",
        default="svg",
    ),
    att("K", "str", "Layout engine override (-K); overrides the engine implied by the tool name.", dynamic="engine"),
    kv("G", "Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names."),
    kv("N", "Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names."),
    kv("E", "Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names."),
    kv("A", "Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes."),
    att("s", "float", "Scale input coordinates by this factor (-s, default 72).", minimum=0.001, maximum=100000),
    att("n", "int", "No-layout mode for neato-style input with positions (-n1 or -n2).", choices=(1, 2)),
    sw("x", "Reduce graph (-x)."),
    sw("y", "Invert the y coordinate in output (-y)."),
    att("q", "int", "Message suppression level (-q[l]; 1 when given without a value).", minimum=0, maximum=10),
    V,
    sw("Lg", "fdp: do not use grid (-Lg)."),
    sw("LO", "fdp: use old attractive force (-LO)."),
    att("Ln", "int", "fdp: number of iterations (-Ln).", minimum=1, maximum=1_000_000),
    att("LU", "int", "fdp: unscaled factor (-LU).", minimum=0, maximum=1_000_000),
    att("LC", "float", "fdp: overlap expansion factor (-LC).", minimum=0, maximum=1_000_000),
    att("Lm", "float", "fdp: m-limit (-Lm).", minimum=0, maximum=1_000_000),
    att("LT", "str", "fdp: temperature factor, optionally prefixed with `*` (-LT).", pattern=r"\*?" + _NUM),
)
LAYOUT_EXCLUDED: tuple[tuple[str, str], ...] = (
    ("-V", "version is available through get_capabilities"),
    ("-l", "loads external libraries from the server"),
    ("-o", "writes to the server filesystem; output is returned as MCP content"),
    ("-O", "writes to the server filesystem; output is returned as MCP content"),
    ("-P", "writes a plugin graph to the server filesystem"),
    ("-c", "writes the plugin configuration; done once at image build time"),
    ("-?", "usage text; see docs/graphviz-tools.md"),
)
_ENGINE_USE = {
    "dot": "Use this by default for directed graphs: flowcharts, trees, dependency and organisation charts.",
    "neato": "Use for undirected networks of up to a few hundred nodes where distance should reflect connection.",
    "fdp": "Use instead of neato for undirected graphs with clusters.",
    "sfdp": "Use for large undirected graphs (thousands of nodes).",
    "twopi": "Use for hierarchies drawn outward from a root node (set the `root` attribute).",
    "circo": "Use for cyclic structures such as rings and telecom topologies.",
    "osage": "Use to pack clusters into an array.",
    "patchwork": "Use for treemaps where node `area` shows size.",
}
_ENGINE_SUMMARY = {
    "dot": "Hierarchical (layered) layout of directed graphs.",
    "neato": "Spring-model layout (Kamada-Kawai) of undirected graphs.",
    "fdp": "Force-directed layout (Fruchterman-Reingold) of undirected graphs.",
    "sfdp": "Scalable force-directed layout for large graphs.",
    "twopi": "Radial layout.",
    "circo": "Circular layout.",
    "osage": "Array-based layout of clusters.",
    "patchwork": "Squarified treemap layout.",
}
LAYOUT = tuple(
    Program(
        n,
        "layout",
        f"{s} {_ENGINE_USE[n]} Takes DOT text in `input` and returns the drawing in format `T` "
        '(svg by default; for example T=png). Example: input="digraph { a -> b }".',
        "dot",
        "format",
        LAYOUT_PARAMS,
        LAYOUT_EXCLUDED,
        tokens_extra=("-L",),
    )
    for n, s in _ENGINE_SUMMARY.items()
)


# --------------------------------------------------------------------------- processing tools
def _proc(name: str, summary: str, params: tuple[Param, ...] = (), *, output: Output = "graphs", **kw: Any) -> Program:
    excluded = kw.pop("excluded", ())
    return Program(name, "processing", summary, kw.pop("input", "dot"), output, params, excluded, **kw)


_O_EXCL = ("-o", "writes to the server filesystem; output is returned as MCP content")

PROCESSING: tuple[Program, ...] = (
    _proc(
        "acyclic",
        "Make a directed graph acyclic by reversing edges. Use this to break cycles before a layered layout.",
        (sw("n", "Do not output the graph (-n); only the exit status reports cycles."), V),
        excluded=(_O_EXCL,),
        ok_returncodes=(0, 1),
    ),
    _proc(
        "bcomps",
        "Decompose a graph into biconnected components.",
        (
            sw("s", "Do not print components (-s)."),
            sw("t", "Emit the block-cutpoint tree (-t)."),
            V,
            sw("x", "External (-x)."),
        ),
        excluded=(_O_EXCL,),
        ok_returncodes=(0, 1),  # exits 1 on a normal run
    ),
    _proc(
        "ccomps",
        "Decompose a graph into connected components. "
        "Use this to find or split disconnected parts, or to extract one with -X.",
        (
            sw("s", "Silent (-s)."),
            sw("x", "External (-x)."),
            att(
                "X",
                "str",
                "Extract a component: `#n`, `%name` and an optional `-f` suffix (-X).",
                pattern=r"[#%][^\s]{1,200}",
            ),
            sw("C", "Use clusters (-C)."),
            sw("e", "Do not induce edges (-e)."),
            sw("n", "Do not induce subgraphs (-n)."),
            V,
            sw("z", "Sort components by size, largest first (-z)."),
        ),
        excluded=(_O_EXCL,),
        ok_returncodes=(0, 1),
    ),
    _proc(
        "sccmap",
        "Decompose a directed graph into strongly connected components and a map of them.",
        (
            sw("s", "Only produce statistics (-s)."),
            sw("S", "Silent (-S)."),
            sw("d", "Allow degenerate components (-d)."),
            V,
        ),
        excluded=(_O_EXCL,),
        ok_returncodes=(0, 1),
    ),
    _proc(
        "tred",
        "Transitive reduction of a directed graph. "
        "Use this to drop redundant edges and make a dependency graph easier to read.",
        (V, sw("r", "Print removed edges to stderr (-r).")),
        excluded=(_O_EXCL,),
    ),
    _proc(
        "unflatten",
        "Adjust directed graphs to improve the aspect ratio of dot layouts. "
        "Use this on wide graphs with many leaves or roots.",
        (
            sw("f", "Adjust immediate fanout chains (-f)."),
            sep("l", "int", "Stagger the length of leaf edges between 1 and this value (-l).", minimum=1, maximum=1000),
            sep("c", "int", "Put disconnected nodes in chains of this length (-c).", minimum=1, maximum=1000),
        ),
        excluded=(_O_EXCL,),
    ),
    _proc(
        "gc",
        "Count nodes, edges, connected components and clusters of graphs. Use this to size up a graph; returns text.",
        (
            sw("n", "Print number of nodes (-n)."),
            sw("e", "Print number of edges (-e)."),
            sw("c", "Print number of connected components (-c)."),
            sw("C", "Print number of clusters (-C)."),
            sw("a", "Print all counts (-a)."),
            sw("D", "Only directed graphs (-D)."),
            sw("U", "Only undirected graphs (-U)."),
            sw("r", "Recursively analyze subgraphs (-r)."),
            sw("s", "Silent (-s)."),
            V,
        ),
        output="text",
    ),
    _proc(
        "nop",
        "Pretty-print a DOT graph (and, with -p, check that it is valid DOT). "
        "Use this to reformat DOT; use validate_dot to get line numbers.",
        (sw("p", "Check for valid DOT only (-p)."),),
    ),
    _proc(
        "cluster",
        "Find clusters in a graph and add them as subgraphs.",
        (
            sep(
                "C", "int", "Generate no more than this many clusters; 0 for no limit (-C).", minimum=0, maximum=100000
            ),
            sep("c", "int", "Clustering method: 0 modularity, 1 modularity quality (-c).", choices=(0, 1)),
            V,
        ),
        excluded=(_O_EXCL,),
    ),
    _proc(
        "dijkstra",
        "Single-source distances in a graph.",
        (
            sw("a", "For nodes in a different component, set the distance very large (-a)."),
            sw("d", "Use forward directed edges (-d)."),
            sw("p", "Attach shortest path information (-p)."),
            positional("node", "Name of the source node.", required=True),
        ),
    ),
    _proc("gvcolor", "Flow colors through a graph.", ()),
    _proc(
        "gvpack",
        "Merge and pack disjoint graphs (graphs with positions).",
        (
            sw("n", "Use node granularity (-n)."),
            sw("g", "Use graph granularity (-g)."),
            sw("u", "No packing; just combine graphs (-u)."),
            V,
            att("m", "int", "Margin in points (-m).", minimum=0, maximum=10000),
            att("s", "str", "Name for the root graph (-s).", pattern=NAME_RE),
            kv("G", "Attributes attached to the output graph (-Gname=value)."),
            Param(
                "array",
                "-array",
                "str",
                "attached",
                "Pack as an array of graphs: `[_rc][n]`, for example `_c3` (-array).",
                flag="-array",
                pattern=r"(_[A-Za-z]+)?[0-9]*",
            ),
        ),
        excluded=(_O_EXCL,),
    ),
    _proc(
        "mingle",
        "Edge bundling for graphs with positions.",
        (
            sep("a", "float", "Maximum turning angle, 0-180 (-a).", minimum=0, maximum=180),
            sep("c", "int", "Compatibility measure: 0 distance, 1 full (-c).", choices=(0, 1)),
            sep("i", "int", "Number of outer iterations (-i).", minimum=0, maximum=100),
            sep("k", "int", "Neighbors in the nearest-neighbor graph (-k).", minimum=1, maximum=1000),
            sep("K", "float", "The force constant (-K).", minimum=0, maximum=1e6),
            sep(
                "m",
                "int",
                "Method: 0 force directed, 1 agglomerative ink saving, 2 cluster+ink saving (-m).",
                choices=(0, 1, 2),
            ),
            sep("p", "float", "Balance for avoiding sharp angles (-p).", minimum=0, maximum=1e6),
            sep("r", "int", "Maximum recursion level (-r).", minimum=0, maximum=10000),
            sep("T", "str", "Output format: gv (default) or simple (-T).", choices=("gv", "simple")),
            V,
        ),
        excluded=(_O_EXCL,),
    ),
    _proc(
        "prune",
        "Prune the graph around the given nodes.",
        (
            Param("n", "-n", "strlist", "multi", "Name of a node to prune; repeatable (-n).", flag="-n"),
            Param(
                "N",
                "-N",
                "strlist",
                "multi",
                "Attribute specification applied to pruned nodes; repeatable (-N).",
                flag="-N",
            ),
            V,
        ),
        excluded=(("-h", "usage text"),),
    ),
    _proc(
        "edgepaint",
        "Color edges so that edges crossing at small angles differ. Input needs 2D positions.",
        (
            longopt(
                "accuracy",
                "float",
                "Accuracy of the maximally different coloring (--accuracy).",
                minimum=1e-9,
                maximum=1,
            ),
            longopt(
                "angle",
                "float",
                "Edges crossing at less than this angle get different colors (--angle).",
                minimum=0,
                maximum=180,
            ),
            longopt(
                "random_seed",
                "int",
                "Random seed; negative runs several seeds (--random_seed).",
                minimum=-1000,
                maximum=1_000_000,
            ),
            longopt(
                "color_scheme",
                "str",
                "rgb, gray, lab, a comma-separated list of #rrggbb colors, or a Brewer scheme name (--color_scheme).",
                pattern=r"[A-Za-z0-9#,_]{1,500}",
            ),
            longopt(
                "lightness",
                "str",
                "LAB scheme only: `l1,l2` with 0<=l1<=l2<=100 (--lightness).",
                pattern=r"[0-9]{1,3},[0-9]{1,3}",
            ),
            switch_long(
                "share_endpoint", "Edges sharing an endpoint are not in conflict if nearly opposite (--share_endpoint)."
            ),
            V,
        ),
        excluded=(("-o", "writes to the server filesystem; output is returned as MCP content"),),
    ),
    _proc(
        "gvmap",
        "Draw a map-like picture of a graph with positions, sizes and clusters.",
        (
            sep("a", "int", "Average number of artificial points along label boxes (-a).", minimum=-1, maximum=1000),
            sep("b", "float", "Polygon line width; negative for no line (-b).", minimum=-1, maximum=100),
            sep("c", "int", "Polygon color scheme 0-10 (-c).", minimum=0, maximum=10),
            Param(
                "c_opacity",
                "-c_opacity=",
                "str",
                "long",
                "Two hex digits of polygon opacity (-c_opacity=xx).",
                flag="-c_opacity=",
                pattern=r"[0-9A-Fa-f]{2}",
            ),
            sep("C", "int", "Generate at most this many clusters (-C).", minimum=0, maximum=100000),
            sep("d", "int", "Seed for the Fiedler vector used in coloring (-d).", minimum=0, maximum=1_000_000),
            sw("D", "Use top-level cluster subgraphs as the clustering (-D)."),
            sw("e", "Show edges (-e)."),
            sep("h", "int", "Artificial points added to keep bridges (-h).", minimum=0, maximum=1000),
            Param(
                "highlight",
                "-highlight=",
                "int",
                "long",
                "Only draw cluster k (-highlight=k).",
                flag="-highlight=",
                minimum=0,
                maximum=100000,
            ),
            sw("k", "Increase randomness of the boundary (-k)."),
            sep("m", "float", "Bounding box margin (-m).", minimum=0, maximum=1000),
            sw("O", "Do not optimize color assignment (-O)."),
            sep("r", "int", "Random points defining sea and lake boundaries (-r).", minimum=0, maximum=100000),
            sep("s", "float", "Depth of sea and lake shores in points (-s).", minimum=-1, maximum=1000),
            sep("t", "int", "Improve contiguity up to n times (-t).", minimum=0, maximum=1000),
            V,
            sep("z", "str", "Polygon line color (-z).", pattern=r"[A-Za-z0-9#_]{1,40}"),
        ),
        excluded=(_O_EXCL,),
    ),
)

# --------------------------------------------------------------------------- generator, converters, image
_POS = r"[0-9]{1,4}"
GENERATORS: tuple[Program, ...] = (
    Program(
        "gvgen",
        "generator",
        "Generate a graph of a chosen family (cycle, grid, tree, random, ...).",
        "none",
        "graphs",
        (
            att("c", "int", "Cycle with this many nodes (-c).", minimum=1, maximum=5000),
            att("C", "str", "Cylinder `x,y` (-C).", pattern=rf"{_POS},{_POS}"),
            att("g", "str", "Grid `h,w`; prefix `f` for a folded grid (-g).", pattern=rf"f?{_POS},{_POS}"),
            att("G", "str", "Partial grid `h,w`; prefix `f` for folded (-G).", pattern=rf"f?{_POS},{_POS}"),
            att("h", "int", "Hypercube of this dimension (-h).", minimum=1, maximum=12),
            att("k", "int", "Complete graph with this many nodes (-k).", minimum=1, maximum=1500),
            att("b", "str", "Complete bipartite graph `x,y` (-b).", pattern=rf"{_POS},{_POS}"),
            att("B", "str", "Ball `x,y` (-B).", pattern=rf"{_POS},{_POS}"),
            att("i", "int", "Random graph with this many nodes (-i).", minimum=1, maximum=5000),
            att("m", "int", "Triangular mesh (-m).", minimum=1, maximum=500),
            att("M", "str", "Moebius strip `x,y` (-M).", pattern=rf"{_POS},{_POS}"),
            att("n", "str", "Prefix for node names (-n).", pattern=r"[A-Za-z0-9_]{1,50}"),
            att("N", "str", "Name of the graph (-N).", pattern=NAME_RE),
            att("p", "int", "Path with this many nodes (-p).", minimum=1, maximum=5000),
            att("r", "str", "Random graph `x,n` (-r).", pattern=rf"{_POS},{_POS}"),
            att("R", "int", "Random rooted tree on this many vertices (-R).", minimum=1, maximum=5000),
            att("s", "int", "Star with this many nodes (-s).", minimum=1, maximum=5000),
            att("S", "str", "Sierpinski graph `x` or `x,d` (-S).", pattern=rf"{_POS}(,[23])?"),
            att("t", "str", "Binary tree `x` or n-ary tree `x,n` (-t).", pattern=rf"{_POS}(,{_POS})?"),
            att(
                "T", "str", "Torus `x,y` or twisted torus `x,y,t1,t2` (-T).", pattern=rf"{_POS},{_POS}(,{_POS},{_POS})?"
            ),
            att("u", "int", "Seed for random number generation (-u).", minimum=0, maximum=2**31 - 1),
            att("w", "int", "Wheel with this many nodes (-w).", minimum=1, maximum=5000),
            sw("d", "Directed graph (-d)."),
            V,
        ),
        (_O_EXCL,),
        input_doc="",
    ),
)


def _conv(
    name: str,
    summary: str,
    params: tuple[Param, ...],
    *,
    output: Output,
    input_: Input = "text",
    input_doc: str = "",
    **kw: Any,
) -> Program:
    return Program(
        name, "converter", summary, input_, output, params, kw.pop("excluded", ()), input_doc=input_doc, **kw
    )


_GD = (sw("g", "Convert to GXL (-g)."), sw("d", "Convert to GV/DOT (-d)."))
CONVERTERS: tuple[Program, ...] = (
    _conv(
        "dot2gxl",
        "Convert DOT to GXL.",
        _GD,
        output="text",
        input_="dot",
        input_doc="The graph in DOT language.",
        excluded=(("-o", "writes to the server filesystem; output is returned as MCP content"),),
    ),
    _conv(
        "gxl2dot",
        "Convert GXL to DOT.",
        _GD,
        output="graphs",
        input_doc="The graph in GXL (XML) format.",
        excluded=(("-o", "writes to the server filesystem; output is returned as MCP content"),),
    ),
    _conv(
        "gml2gv",
        "Convert GML to DOT.",
        (V, att("g", "str", "Template for graph names (-g).", pattern=NAME_RE)),
        output="graphs",
        input_doc="The graph in GML format.",
        excluded=(_O_EXCL,),
    ),
    _conv(
        "gv2gml",
        "Convert DOT to GML.",
        (sw("y", "Output the yWorks.com GML variant (-y)."),),
        output="text",
        input_="dot",
        input_doc="The graph in DOT language.",
        excluded=(_O_EXCL,),
    ),
    _conv(
        "graphml2gv",
        "Convert GraphML to DOT.",
        (att("g", "str", "Template for graph names (-g).", pattern=NAME_RE), V),
        output="graphs",
        input_doc="The graph in GraphML (XML) format.",
        excluded=(_O_EXCL,),
    ),
    _conv(
        "mm2gv",
        "Convert a Matrix Market file to DOT.",
        (
            sw("u", "Make the graph undirected (-u)."),
            sep(
                "U",
                "int",
                "Treat a non-square matrix as a bipartite graph: 0 never, 1 if pattern unsymmetric, "
                "2 if matrix unsymmetric, 3 always (-U).",
                choices=(0, 1, 2, 3),
            ),
            V,
            sw("c", "Assign color and weight to edges (-c)."),
            sw("l", "Add labels (-l)."),
        ),
        output="graphs",
        input_="file",
        input_doc="The matrix in Matrix Market format; only element type `real` is accepted.",
        excluded=(("-o", "writes to the server filesystem; output is returned as MCP content"),),
    ),
)

PROGRAMS: dict[str, Program] = {p.name: p for p in (*LAYOUT, *PROCESSING, *GENERATORS, *CONVERTERS)}
