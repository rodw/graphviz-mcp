# Tool reference

Generated from `src/graphviz_mcp/tools/specs.py` by `scripts/gen_tool_docs.py`; do not edit by hand.

Every tool is named after a Graphviz program, and its parameters are named after the program's flags (the flag letter is the parameter name; long options keep their name). `G`, `N`, `E` and `A` are objects: `G: {"rankdir": "LR"}` is `-Grankdir=LR`. Tools whose binary is missing from the installed Graphviz build are not registered; `get_capabilities` lists what is available. Attribute names and values are subject to the [attribute policy](attribute-policy.md).

## Layout and rendering

### `dot`

Hierarchical (layered) layout of directed graphs. Use this by default for directed graphs: flowcharts, trees, dependency and organisation charts. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `neato`

Spring-model layout (Kamada-Kawai) of undirected graphs. Use for undirected networks of up to a few hundred nodes where distance should reflect connection. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `fdp`

Force-directed layout (Fruchterman-Reingold) of undirected graphs. Use instead of neato for undirected graphs with clusters. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `sfdp`

Scalable force-directed layout for large graphs. Use for large undirected graphs (thousands of nodes). Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `twopi`

Radial layout. Use for hierarchies drawn outward from a root node (set the `root` attribute). Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `circo`

Circular layout. Use for cyclic structures such as rings and telecom topologies. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `osage`

Array-based layout of clusters. Use to pack clusters into an array. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

### `patchwork`

Squarified treemap layout. Use for treemaps where node `area` shows size. Takes DOT text in `input` and returns the drawing in format `T` (svg by default; for example T=png). Example: input="digraph { a -> b }".

* Input: `input`: the graph in DOT language
* Output: the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `T` | `-T` | string (default `svg`) | Output format (-T). Accepts `format`, `format:renderer` or `format:renderer:formatter`, for example `svg`, `png`, `png:cairo`. The valid values are the ones the installed build reports (see get_capabilities). |
| `K` | `-K` | string | Layout engine override (-K); overrides the engine implied by the tool name. |
| `G` | `-G` | object | Graph attributes, object of name/value pairs (-Gname=value). See graphviz://attributes for the names. |
| `N` | `-N` | object | Node attributes, object of name/value pairs (-Nname=value). See graphviz://attributes for the names. |
| `E` | `-E` | object | Edge attributes, object of name/value pairs (-Ename=value). See graphviz://attributes for the names. |
| `A` | `-A` | object | Attributes set on graph, nodes and edges at once (-Aname=value). See graphviz://attributes. |
| `s` | `-s` | number (0.001..100000) | Scale input coordinates by this factor (-s, default 72). |
| `n` | `-n` | integer (one of `1`, `2`) | No-layout mode for neato-style input with positions (-n1 or -n2). |
| `x` | `-x` | boolean | Reduce graph (-x). |
| `y` | `-y` | boolean | Invert the y coordinate in output (-y). |
| `q` | `-q` | integer (0..10) | Message suppression level (-q[l]; 1 when given without a value). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `Lg` | `-Lg` | boolean | fdp: do not use grid (-Lg). |
| `LO` | `-LO` | boolean | fdp: use old attractive force (-LO). |
| `Ln` | `-Ln` | integer (1..1e+06) | fdp: number of iterations (-Ln). |
| `LU` | `-LU` | integer (0..1e+06) | fdp: unscaled factor (-LU). |
| `LC` | `-LC` | number (0..1e+06) | fdp: overlap expansion factor (-LC). |
| `Lm` | `-Lm` | number (0..1e+06) | fdp: m-limit (-Lm). |
| `LT` | `-LT` | string (pattern `\*?[0-9]+(\.[0-9]+)?`) | fdp: temperature factor, optionally prefixed with `*` (-LT). |

Flags not exposed: `-V` (version is available through get_capabilities); `-l` (loads external libraries from the server); `-o` (writes to the server filesystem; output is returned as MCP content); `-O` (writes to the server filesystem; output is returned as MCP content); `-P` (writes a plugin graph to the server filesystem); `-c` (writes the plugin configuration; done once at image build time); `-?` (usage text; see docs/graphviz-tools.md).

## Graph processing and analysis

### `acyclic`

Make a directed graph acyclic by reversing edges. Use this to break cycles before a layered layout.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph
* Exit statuses treated as success: 0, 1

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `n` | `-n` | boolean | Do not output the graph (-n); only the exit status reports cycles. |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `bcomps`

Decompose a graph into biconnected components.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph
* Exit statuses treated as success: 0, 1

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `s` | `-s` | boolean | Do not print components (-s). |
| `t` | `-t` | boolean | Emit the block-cutpoint tree (-t). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `x` | `-x` | boolean | External (-x). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `ccomps`

Decompose a graph into connected components. Use this to find or split disconnected parts, or to extract one with -X.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph
* Exit statuses treated as success: 0, 1

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `s` | `-s` | boolean | Silent (-s). |
| `x` | `-x` | boolean | External (-x). |
| `X` | `-X` | string (pattern `[#%][^\s]{1,200}`) | Extract a component: `#n`, `%name` and an optional `-f` suffix (-X). |
| `C` | `-C` | boolean | Use clusters (-C). |
| `e` | `-e` | boolean | Do not induce edges (-e). |
| `n` | `-n` | boolean | Do not induce subgraphs (-n). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `z` | `-z` | boolean | Sort components by size, largest first (-z). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `sccmap`

Decompose a directed graph into strongly connected components and a map of them.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph
* Exit statuses treated as success: 0, 1

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `s` | `-s` | boolean | Only produce statistics (-s). |
| `S` | `-S` | boolean | Silent (-S). |
| `d` | `-d` | boolean | Allow degenerate components (-d). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `tred`

Transitive reduction of a directed graph. Use this to drop redundant edges and make a dependency graph easier to read.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `r` | `-r` | boolean | Print removed edges to stderr (-r). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `unflatten`

Adjust directed graphs to improve the aspect ratio of dot layouts. Use this on wide graphs with many leaves or roots.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `f` | `-f` | boolean | Adjust immediate fanout chains (-f). |
| `l` | `-l` | integer (1..1000) | Stagger the length of leaf edges between 1 and this value (-l). |
| `c` | `-c` | integer (1..1000) | Put disconnected nodes in chains of this length (-c). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `gc`

Count nodes, edges, connected components and clusters of graphs. Use this to size up a graph; returns text.

* Input: `input`: the graph in DOT language
* Output: text

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `n` | `-n` | boolean | Print number of nodes (-n). |
| `e` | `-e` | boolean | Print number of edges (-e). |
| `c` | `-c` | boolean | Print number of connected components (-c). |
| `C` | `-C` | boolean | Print number of clusters (-C). |
| `a` | `-a` | boolean | Print all counts (-a). |
| `D` | `-D` | boolean | Only directed graphs (-D). |
| `U` | `-U` | boolean | Only undirected graphs (-U). |
| `r` | `-r` | boolean | Recursively analyze subgraphs (-r). |
| `s` | `-s` | boolean | Silent (-s). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

### `nop`

Pretty-print a DOT graph (and, with -p, check that it is valid DOT). Use this to reformat DOT; use validate_dot to get line numbers.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `p` | `-p` | boolean | Check for valid DOT only (-p). |

### `cluster`

Find clusters in a graph and add them as subgraphs.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `C` | `-C` | integer (0..100000) | Generate no more than this many clusters; 0 for no limit (-C). |
| `c` | `-c` | integer (one of `0`, `1`) | Clustering method: 0 modularity, 1 modularity quality (-c). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `dijkstra`

Single-source distances in a graph.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `a` | `-a` | boolean | For nodes in a different component, set the distance very large (-a). |
| `d` | `-d` | boolean | Use forward directed edges (-d). |
| `p` | `-p` | boolean | Attach shortest path information (-p). |
| `node` | `<node>` | string (required) | Name of the source node. |

### `gvcolor`

Flow colors through a graph.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

### `gvpack`

Merge and pack disjoint graphs (graphs with positions).

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `n` | `-n` | boolean | Use node granularity (-n). |
| `g` | `-g` | boolean | Use graph granularity (-g). |
| `u` | `-u` | boolean | No packing; just combine graphs (-u). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `m` | `-m` | integer (0..10000) | Margin in points (-m). |
| `s` | `-s` | string (pattern `[A-Za-z_][A-Za-z0-9_.:\-]{0,127}`) | Name for the root graph (-s). |
| `G` | `-G` | object | Attributes attached to the output graph (-Gname=value). |
| `array` | `-array` | string (pattern `(_[A-Za-z]+)?[0-9]*`) | Pack as an array of graphs: `[_rc][n]`, for example `_c3` (-array). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `mingle`

Edge bundling for graphs with positions.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `a` | `-a` | number (0..180) | Maximum turning angle, 0-180 (-a). |
| `c` | `-c` | integer (one of `0`, `1`) | Compatibility measure: 0 distance, 1 full (-c). |
| `i` | `-i` | integer (0..100) | Number of outer iterations (-i). |
| `k` | `-k` | integer (1..1000) | Neighbors in the nearest-neighbor graph (-k). |
| `K` | `-K` | number (0..1e+06) | The force constant (-K). |
| `m` | `-m` | integer (one of `0`, `1`, `2`) | Method: 0 force directed, 1 agglomerative ink saving, 2 cluster+ink saving (-m). |
| `p` | `-p` | number (0..1e+06) | Balance for avoiding sharp angles (-p). |
| `r` | `-r` | integer (0..10000) | Maximum recursion level (-r). |
| `T` | `-T` | string (one of `gv`, `simple`) | Output format: gv (default) or simple (-T). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `prune`

Prune the graph around the given nodes.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `n` | `-n` | list of strings | Name of a node to prune; repeatable (-n). |
| `N` | `-N` | list of strings | Attribute specification applied to pruned nodes; repeatable (-N). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-h` (usage text).

### `edgepaint`

Color edges so that edges crossing at small angles differ. Input needs 2D positions.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `accuracy` | `--accuracy` | number (1e-09..1) | Accuracy of the maximally different coloring (--accuracy). |
| `angle` | `--angle` | number (0..180) | Edges crossing at less than this angle get different colors (--angle). |
| `random_seed` | `--random_seed` | integer (-1000..1e+06) | Random seed; negative runs several seeds (--random_seed). |
| `color_scheme` | `--color_scheme` | string (pattern `[A-Za-z0-9#,_]{1,500}`) | rgb, gray, lab, a comma-separated list of #rrggbb colors, or a Brewer scheme name (--color_scheme). |
| `lightness` | `--lightness` | string (pattern `[0-9]{1,3},[0-9]{1,3}`) | LAB scheme only: `l1,l2` with 0<=l1<=l2<=100 (--lightness). |
| `share_endpoint` | `--share_endpoint` | boolean | Edges sharing an endpoint are not in conflict if nearly opposite (--share_endpoint). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `gvmap`

Draw a map-like picture of a graph with positions, sizes and clusters.

* Input: `input`: the graph in DOT language
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `a` | `-a` | integer (-1..1000) | Average number of artificial points along label boxes (-a). |
| `b` | `-b` | number (-1..100) | Polygon line width; negative for no line (-b). |
| `c` | `-c` | integer (0..10) | Polygon color scheme 0-10 (-c). |
| `c_opacity` | `-c_opacity=` | string (pattern `[0-9A-Fa-f]{2}`) | Two hex digits of polygon opacity (-c_opacity=xx). |
| `C` | `-C` | integer (0..100000) | Generate at most this many clusters (-C). |
| `d` | `-d` | integer (0..1e+06) | Seed for the Fiedler vector used in coloring (-d). |
| `D` | `-D` | boolean | Use top-level cluster subgraphs as the clustering (-D). |
| `e` | `-e` | boolean | Show edges (-e). |
| `h` | `-h` | integer (0..1000) | Artificial points added to keep bridges (-h). |
| `highlight` | `-highlight=` | integer (0..100000) | Only draw cluster k (-highlight=k). |
| `k` | `-k` | boolean | Increase randomness of the boundary (-k). |
| `m` | `-m` | number (0..1000) | Bounding box margin (-m). |
| `O` | `-O` | boolean | Do not optimize color assignment (-O). |
| `r` | `-r` | integer (0..100000) | Random points defining sea and lake boundaries (-r). |
| `s` | `-s` | number (-1..1000) | Depth of sea and lake shores in points (-s). |
| `t` | `-t` | integer (0..1000) | Improve contiguity up to n times (-t). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `z` | `-z` | string (pattern `[A-Za-z0-9#_]{1,40}`) | Polygon line color (-z). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

## Generators

### `gvgen`

Generate a graph of a chosen family (cycle, grid, tree, random, ...).

* Input: none (the parameters select what is generated)
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `c` | `-c` | integer (1..5000) | Cycle with this many nodes (-c). |
| `C` | `-C` | string (pattern `[0-9]{1,4},[0-9]{1,4}`) | Cylinder `x,y` (-C). |
| `g` | `-g` | string (pattern `f?[0-9]{1,4},[0-9]{1,4}`) | Grid `h,w`; prefix `f` for a folded grid (-g). |
| `G` | `-G` | string (pattern `f?[0-9]{1,4},[0-9]{1,4}`) | Partial grid `h,w`; prefix `f` for folded (-G). |
| `h` | `-h` | integer (1..12) | Hypercube of this dimension (-h). |
| `k` | `-k` | integer (1..1500) | Complete graph with this many nodes (-k). |
| `b` | `-b` | string (pattern `[0-9]{1,4},[0-9]{1,4}`) | Complete bipartite graph `x,y` (-b). |
| `B` | `-B` | string (pattern `[0-9]{1,4},[0-9]{1,4}`) | Ball `x,y` (-B). |
| `i` | `-i` | integer (1..5000) | Random graph with this many nodes (-i). |
| `m` | `-m` | integer (1..500) | Triangular mesh (-m). |
| `M` | `-M` | string (pattern `[0-9]{1,4},[0-9]{1,4}`) | Moebius strip `x,y` (-M). |
| `n` | `-n` | string (pattern `[A-Za-z0-9_]{1,50}`) | Prefix for node names (-n). |
| `N` | `-N` | string (pattern `[A-Za-z_][A-Za-z0-9_.:\-]{0,127}`) | Name of the graph (-N). |
| `p` | `-p` | integer (1..5000) | Path with this many nodes (-p). |
| `r` | `-r` | string (pattern `[0-9]{1,4},[0-9]{1,4}`) | Random graph `x,n` (-r). |
| `R` | `-R` | integer (1..5000) | Random rooted tree on this many vertices (-R). |
| `s` | `-s` | integer (1..5000) | Star with this many nodes (-s). |
| `S` | `-S` | string (pattern `[0-9]{1,4}(,[23])?`) | Sierpinski graph `x` or `x,d` (-S). |
| `t` | `-t` | string (pattern `[0-9]{1,4}(,[0-9]{1,4})?`) | Binary tree `x` or n-ary tree `x,n` (-t). |
| `T` | `-T` | string (pattern `[0-9]{1,4},[0-9]{1,4}(,[0-9]{1,4},[0-9]{1,4})?`) | Torus `x,y` or twisted torus `x,y,t1,t2` (-T). |
| `u` | `-u` | integer (0..2.14748e+09) | Seed for random number generation (-u). |
| `w` | `-w` | integer (1..5000) | Wheel with this many nodes (-w). |
| `d` | `-d` | boolean | Directed graph (-d). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

## Converters

### `dot2gxl`

Convert DOT to GXL.

* Input: `input`: the graph in DOT language
* Output: text

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `g` | `-g` | boolean | Convert to GXL (-g). |
| `d` | `-d` | boolean | Convert to GV/DOT (-d). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `gxl2dot`

Convert GXL to DOT.

* Input: `input`: the graph in the converter's source format
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `g` | `-g` | boolean | Convert to GXL (-g). |
| `d` | `-d` | boolean | Convert to GV/DOT (-d). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `gml2gv`

Convert GML to DOT.

* Input: `input`: the graph in the converter's source format
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `g` | `-g` | string (pattern `[A-Za-z_][A-Za-z0-9_.:\-]{0,127}`) | Template for graph names (-g). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `gv2gml`

Convert DOT to GML.

* Input: `input`: the graph in DOT language
* Output: text

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `y` | `-y` | boolean | Output the yWorks.com GML variant (-y). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `graphml2gv`

Convert GraphML to DOT.

* Input: `input`: the graph in the converter's source format
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `g` | `-g` | string (pattern `[A-Za-z_][A-Za-z0-9_.:\-]{0,127}`) | Template for graph names (-g). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

### `mm2gv`

Convert a Matrix Market file to DOT.

* Input: `input`: the file contents (written to a temporary file for the program)
* Output: DOT text; programs that emit several graphs return one string per graph

| Parameter | Flag | Type | Meaning |
|---|---|---|---|
| `u` | `-u` | boolean | Make the graph undirected (-u). |
| `U` | `-U` | integer (one of `0`, `1`, `2`, `3`) | Treat a non-square matrix as a bipartite graph: 0 never, 1 if pattern unsymmetric, 2 if matrix unsymmetric, 3 always (-U). |
| `v` | `-v` | boolean | Verbose messages on stderr (-v). |
| `c` | `-c` | boolean | Assign color and weight to edges (-c). |
| `l` | `-l` | boolean | Add labels (-l). |

Flags not exposed: `-o` (writes to the server filesystem; output is returned as MCP content).

## MCP extensions

These have no Graphviz counterpart and are named distinctly.

### `validate_dot`

Checks DOT syntax without laying the graph out (it runs `nop -p`; Graphviz has no `null` output format). Returns `{valid, errors[{line, message, near}], warnings[], policy_ok, policy_violation}`. Graphviz reports the line of a syntax error but no column.

### `get_capabilities`

Graphviz version, layout engines, output formats with MIME types and renderer combinations, available tools, fonts, limits and the active attribute policy. The same document is the resource `graphviz://capabilities`.

## Resources and prompts

* `graphviz://capabilities`, `graphviz://attributes` (curated attribute reference), `graphviz://dot-language`.
* Prompts: `visualize_data_as_graph`, `explain_dot`, `fix_dot`.

## Program catalog

Every executable in the Graphviz bin directory is classified; the Docker image test fails on an unclassified one.

| Program | Status | Reason |
|---|---|---|
| `dot_builtins` | excluded | variant of dot with built-in plugins; redundant with dot |
| `dot_sandbox` | excluded | variant of dot; blocks -o but not image=/file reads, so it adds nothing |
| `dotty` | excluded | interactive GUI program |
| `gv2gxl` | excluded | same binary as dot2gxl; alias names are not registered |
| `gvedit` | excluded | interactive GUI program |
| `gvmap.sh` | excluded | shell pipeline (sfdp | gvmap | neato); shell scripts are not exposed |
| `gvpr` | excluded | deferred; can read files and run programs |
| `gxl2gv` | excluded | same binary as gxl2dot; alias names are not registered |
| `lefty` | excluded | interactive GUI program |
| `lneato` | excluded | interactive GUI program |
| `smyrna` | excluded | interactive GUI program |
| `vimdot` | excluded | interactive GUI program |
| `acyclic` | exposed | - |
| `bcomps` | exposed | - |
| `ccomps` | exposed | - |
| `circo` | exposed | - |
| `cluster` | exposed | - |
| `dijkstra` | exposed | - |
| `dot` | exposed | - |
| `dot2gxl` | exposed | - |
| `edgepaint` | exposed | - |
| `fdp` | exposed | - |
| `gc` | exposed | - |
| `gml2gv` | exposed | - |
| `graphml2gv` | exposed | - |
| `gv2gml` | exposed | - |
| `gvcolor` | exposed | - |
| `gvgen` | exposed | - |
| `gvmap` | exposed | - |
| `gvpack` | exposed | - |
| `gxl2dot` | exposed | - |
| `mingle` | exposed | - |
| `mm2gv` | exposed | - |
| `neato` | exposed | - |
| `nop` | exposed | - |
| `osage` | exposed | - |
| `patchwork` | exposed | - |
| `prune` | exposed | - |
| `sccmap` | exposed | - |
| `sfdp` | exposed | - |
| `tred` | exposed | - |
| `twopi` | exposed | - |
| `unflatten` | exposed | - |
