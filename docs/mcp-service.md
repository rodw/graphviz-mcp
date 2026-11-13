# MCP service overview

## Tools

There are 31 Graphviz binaries exposed as MCP tools, plus 2 additional [MCP-specific extensions](#mcp-extensions)

Not every program in Graphviz's bin directory is exposed. Aliases, GUI programs and shell scripts are excluded. [catalog.py](../src/graphviz_mcp/tools/catalog.py) records the reason for each exclusion.

For a complete description of each tool and the parameters it supports, see [graphviz-tools.md](graphviz-tools.md).

Each tool is also available as a form in the [web UI](web-ui.md#running-a-tool).

### Layout and rendering

| Tool | Use it for |
|---|---|
| `dot` | Layered layout of directed graphs: flowcharts, trees, dependency and organization charts |
| `neato` | Spring-model layout of undirected networks up to a few hundred nodes |
| `fdp` | Force-directed layout of undirected graphs, especially ones with clusters |
| `sfdp` | Force-directed layout for large undirected graphs |
| `twopi` | Radial layout, with a root node in the middle |
| `circo` | Circular layout for cyclic structures such as rings |
| `osage` | Array-based packing of clusters |
| `patchwork` | Squarified treemaps, where node `area` shows size |

### Graph processing and analysis

| Tool | Use it for |
|---|---|
| `acyclic` | Reversing edges to break cycles in a directed graph |
| `bcomps` | Splitting a graph into biconnected components |
| `ccomps` | Splitting a graph into connected components |
| `sccmap` | Strongly connected components of a directed graph, and a map of them |
| `tred` | Transitive reduction, which drops redundant edges |
| `unflatten` | Improving the aspect ratio of `dot` layouts for graphs with many leaves or roots |
| `gc` | Counting nodes, edges, connected components and clusters |
| `nop` | Pretty-printing DOT, and checking that it parses |
| `cluster` | Finding clusters and adding them as subgraphs |
| `dijkstra` | Single-source distances |
| `gvcolor` | Flowing colors through a graph |
| `gvpack` | Merging and packing disjoint graphs that have positions |
| `mingle` | Edge bundling for graphs with positions |
| `prune` | Pruning a graph around given nodes |
| `edgepaint` | Coloring edges so that edges crossing at small angles differ. Needs 2D positions |
| `gvmap` | Drawing a map-like picture of a graph with positions, sizes and clusters |

### Generators

| Tool | Use it for |
|---|---|
| `gvgen` | Generating a graph from a family such as a cycle, grid, tree or random graph |

### Converters

| Tool | Use it for |
|---|---|
| `dot2gxl` | DOT to GXL |
| `gxl2dot` | GXL to DOT |
| `gml2gv` | GML to DOT |
| `gv2gml` | DOT to GML |
| `graphml2gv` | GraphML to DOT |
| `mm2gv` | Matrix Market to DOT |

### MCP extensions

| Tool | Use it for |
|---|---|
| `validate_dot` | Checking DOT syntax without laying the graph out. It reports errors with line numbers and whether the attribute policy accepts the graph. |
| `get_capabilities` | Describes the tools, layout engines, output formats, renderers, and fonts that are available, as well as the current limits and the active attribute policy. |


## Resources

The server has 3 fixed resources. Each one is also shown as a page in the [web UI](web-ui.md#resources).

| URI | Type | Contents |
|---|---|---|
| `graphviz://capabilities` | `application/json` | The same report as the `get_capabilities` tool: version, formats, limits and policy. |
| `graphviz://attributes` | `text/markdown` | Every Graphviz attribute with where it applies, its type and default, and whether the active attribute policy accepts it. |
| `graphviz://dot-language` | `text/markdown` | A short guide to the DOT language. |

## Prompts

There are three prompts. Each one gives the model a ready-made request that refers to the tools above.

| Prompt | Arguments | What it asks the model to do |
|---|---|---|
| `visualize_data_as_graph` | `data`, optional `layout` (default `dot`) and `format` (default `svg`) | Decide what the nodes and edges are, write DOT, check it with `validate_dot`, render it with the chosen layout tool, and explain the layout. |
| `explain_dot` | `dot` | Describe what a DOT graph represents, which attributes shape its look and layout, and what looks wrong or could be better. |
| `fix_dot` | `dot`, optional `problem` | Run `validate_dot`, correct the reported errors, show the corrected graph and render it to confirm. |
