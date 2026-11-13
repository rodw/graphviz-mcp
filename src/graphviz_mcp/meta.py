"""Static facts about the service: what it tells clients about itself, and its installed version.

A leaf module (it imports nothing from this package), so anything may import it.
"""

from __future__ import annotations

from importlib import metadata

INSTRUCTIONS = (
    "Graphviz as MCP tools: draw, check, analyse and convert graphs written in the DOT language. Each tool is named "
    "after a Graphviz program and its parameters are the program's command-line flag letters (T is -T, G is -G).\n\n"
    "Which tool:\n"
    "- Draw or render a diagram: `dot` (layered; the usual choice for directed graphs, flowcharts, trees and "
    "dependencies), `neato`, `fdp` or `sfdp` (network-style layouts of undirected graphs; `sfdp` for large ones), "
    "`circo` (circular), `twopi` (radial), `osage` (clusters), `patchwork` (treemap). Pass the DOT text in `input` and "
    "the output format in `T` (default svg; others such as png or pdf are listed by `get_capabilities`).\n"
    "- Check DOT syntax without drawing: `validate_dot` (returns line numbers, and whether the attribute policy "
    "accepts the graph). Use `nop` to pretty-print DOT.\n"
    "- Analyse a graph: `gc` (counts), `ccomps`, `bcomps` and `sccmap` (components), `dijkstra` (distances), "
    "`tred` (transitive reduction), `acyclic`, `prune`. `unflatten` improves the aspect ratio of `dot` layouts.\n"
    "- Convert formats: `graphml2gv`, `gml2gv`, `gxl2dot` and `mm2gv` produce DOT; `gv2gml` and `dot2gxl` read DOT. "
    "Generate a sample graph with `gvgen`.\n\n"
    "Attributes (color, shape, rankdir, splines, ...) go in the DOT text or in the `G`, `N`, `E` and `A` parameters. "
    "Read the `graphviz://attributes` resource for every Graphviz attribute with where it applies, its type and "
    "default, and whether this server's attribute policy accepts it (some, such as `image`, are rejected); "
    "`graphviz://dot-language` is a DOT primer; the official reference is https://graphviz.org/doc/info/attrs.html . "
    "`get_capabilities` reports the installed Graphviz version, formats, fonts, limits and the active policy."
)


def package_version() -> str:
    try:
        return metadata.version("graphviz-mcp")
    except metadata.PackageNotFoundError:  # pragma: no cover - running from a source tree
        return "0.0.0"
