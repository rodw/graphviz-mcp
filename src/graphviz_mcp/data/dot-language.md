# The DOT Language

DOT is a text-based language for describing graphs.

A *graph* is a collection of *nodes* which may be connected by *edges*. Graphs are typically rendered as boxes (nodes) joined by lines (edges). DOT documents conventionally use the file extension `.dot` or `.gv`.

The [Graphviz](https://graphviz.org/) tool suite  contains dozens of programs that generate, render, transform, analyze or otherwise process DOT-format graphs. This service exposes those programs through a standard MCP interface.

This document covers some important features of the DOT language as a primer for agents and other systems that use the service. For a more authoritative reference, consult  [the official documentation](https://graphviz.org/documentation/).


## Graphs

A graph contains nodes, edges, and other graphs. Every node and edge belongs to a graph. The outermost layer of any DOT document always contains one or more graph declarations.

DOT has two kinds of graph:

**1. directed graphs** - keyword `digraph`; directional edges: `A -> B` is distinct from `B -> A`; example:

```gv
digraph G { A -> B }
```

**2. undirected graphs** - keyword `graph`; edges have no inherent direction: `A -- B` is equivalent to `B -- A`; example:

```gv
graph G { A -- B }
```

The graph identifier (`G`) is optional.

A `digraph` can only contain `->` edges. A `graph` can only contain `--` edges. Using the wrong edge operator is a syntax error.

## Nodes

A node is a "vertex" within the graph, to which edges may be attached.

To create a node, simply declare it:

```gv
graph {
  Foo // creates a node with the ID "Foo"
}
```

Node declarations are separated by semicolons or whitespace:

```gv
graph { Foo Bar }
```

```gv
graph { Foo; Bar; }
```

```gv
graph {
  Foo
  Bar
}
```

Every node must have a unique identifier. Using the same identifier in more than one declaration does not create additional nodes: `graph { Foo Foo Foo }` is the same as `graph { Foo }`.

## Edges

Edges connect two nodes. To declare an edge, put an edge operator between two node references: `graph { A -- B }` or `digraph { A -> B }`

You can declare the nodes first and later add an edge between them, or declare the nodes at the same time as you declare an edge. These two listings are equivalent:

```gv
digraph { A -> B }
```

```gv
digraph {
  A
  B
  A -> B
}
```

Edges can be chained together like `A -> B -> C` or listed one at a time like `A -> B; B -> C`. An edge can connect a node to itself, as in `A -> A`.

Edges do not need to be unique. Each declaration creates a new edge. This graph contains three distinct edges:

```gv
digraph {
  A -> B
  A -> B
  A -> B
}
```

Adding the keyword `strict` before a `graph` or `digraph` declaration will cause duplicate edges to be ignored:

```gv
strict digraph {
  A -> B
  A -> B
  A -> B
}
```

is equivalent to

```gv
digraph { A -> B }
```

## Subgraphs and Clusters

Graphs may contain other graphs, called subgraphs. Subgraphs are declared with a pair of curly braces (`{` `}`), optionally preceded by the keyword `subgraph`. Both of the following listings declare a subgraph containing the nodes `C` and `D`:

```gv
digraph G {
    a -> b
    { C -> D }
    e -> f
}
```

```gv
digraph G {
    a -> b
    subgraph S { C -> D }
    e -> f
}
```

The subgraph identifier (`S`) is optional.

Subgraphs may contain other subgraphs.

Grouping nodes within a subgraph typically does not change the way the graph is laid out or rendered; but when a subgraph identifier starts with the (case-sensitive) prefix `cluster`, nodes within the subgraph are grouped together in a rectangular region. Nodes from outside the subgraph are never placed within that region.

For example:

```gv
digraph G {
    subgraph clusterS { 
      label="The Cluster" 
      A -> C  
    }
    A -> B -> C 
}
```

will render nodes `A` and `C` inside a box labelled "The Cluster" with node `B` outside of that box.

Clusters are not part of the DOT language itself, but a convention respected by specific layout engines, including `dot`, `neato` and `osage`

## Attributes

DOT supports a large number of *attributes* that influence how nodes, edges, and graphs are rendered. 

Attributes are specified as name-value pairs, formatted `name=value` or `name="value"`, typically enclosed in square brackets (`[` `]`). Multiple attributes can be separated by whitespace, comma, or semicolon.

```gv
digraph G {
  rankdir=RL
  A [color=blue]
  B [shape=triangle label="Second Node"]
  A -> B [arrowhead=vee]
}
```

Graph (`graph`, `digraph`, or `subgraph`) attributes are a special case and can be declared "inline", without the square brackets, like `rankdir` in the line 2 above. That line could also have been written `graph [rankdir=RL]`.

An attribute list following the keywords `node`, `edge`, or `graph` sets default values used by all subsequent elements of that type (until changed or overridden). E.g.:

```gv
digraph G {
  node [shape=triangle color=blue]
  edge [style=dashed]
  A // a blue triangle node
  B // another
  A -> B // a dashed-line edge

  edge [style=dotted] // setting a new default edge style
  node [shape=""] // reverting to the original default shape (oval)
  C [color=""] // a default shape, default color node
  D [color=red] // a red node with default shape
  C -> D // a dotted-line edge
}
```

When an attribute is set to an empty string (`""`), the original default value is used.


Subgraphs define a "local scope" for attributes defaults. When default `node` or `edge` attributes are declared within a subgraph, they only remain in effect until the end of that subgraph declaration.


The `graphviz://attributes` resource lists currently supported attributes. More information may be found in the official documentation at https://graphviz.org/doc/info/attrs.html.

## Identifiers

Graph, subgraph, and node IDs can be expressed in several formats:

 - **Alphanumeric** - any combination of letters, numbers or underscores (`_`) provided the first character is not a digit. E.g.: `Foo`, `f00`, `foo_bar`

 - **Numeric** - any sequence of digits (`0` thru `9`) and at most one decimal point (`.`), optionally preceded a negative sign (`-`). Leading `0`, and both leading or trailing `.` are allowed. E.g.: `700`, `007`, `.95`, `-3.14`, `0123.`

 - **Quoted String** - any sequence of characters wrapped in double quotes. Some backslash escape sequences are allowed. E.g.: `"Foo Bar"`, `"π ≈ 3.14"`, `"Hello \"World!\""`.

Identifiers are untyped (`3` is the same as `"3"`) but case sensitive (`foo` is distinct from `Foo`).

## Comments

Inline comments start with `//` or `#` and extend to the end of the line.
 
Block comments begin with `/*`, end with `*/`, and may span multiple lines.
