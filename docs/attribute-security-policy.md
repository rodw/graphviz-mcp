# Attribute Security Policy

This guide explains how to choose and configure graphviz-mcp's "attribute security policy" which determines which Graphviz attributes are permitted within graph source files and tool parameters.

## Background

Graphviz uses name-value pairs called [attributes](https://graphviz.org/doc/info/attrs.html) to control how nodes, edges, graphs, subgraphs, and clusters are laid out and rendered. 

These attributes can be defined within the graph source code itself. For example, in the following DOT source listing:

```gv
graph G {
  rankdir=LR
  node [style=filled fillcolor=lightblue]
  edge [color=red arrowhead=normal]
  A -- B [label="An edge from A to B"]
  B -- C
}
```

the `rankdir`, `style`, `fillcolor`, `color`, `arrowhead` and `label` properties are all examples of attributes.

You can also set (or override) attributes by passing command-line parameters (such as `-G`, `-N`, `-E`) when you invoke an individual tool. For example, in the command:

```bash
dot -Grankdir=LR -Nshape=rect input.dot -o output.svg
```

the graph `rankdir` and node `shape` attributes are being set.

Most of these attributes are fairly harmless, but a few of them ask Graphviz to do something potentially dangerous. For example:
 
 - The node attributes `image` and `shapefile` tell Graphviz to load custom images from another file on the local file system. They might be used to access sensitive files on the graphviz-mcp server.

 - The graph attribute `dpi` sets the dots-per-inch value for raster images formats like PNG. A parameter like `-Gdpi=1000000` could be used to set the image resolution to a million pixels per inch, asking the server to generate an image of an absurd size.

Since the requests made to this service may contain data that comes from an untrusted source, graphviz-mcp allows the administrator to decide which attributes iot should will accept. That decision is the *attribute security policy*.

The attribute security policy can be used to permit (allowlist) or restrict (denylist) specific attributes by name. It can also be used to constraint specific attributes to a sensible range of values.

## Choosing a mode

The attribute security policy is primarily controlled by the environment variable `GVMCP_ATTR_POLICY`, passed to the graphviz-mcp server Docker container on launch. It can be set to one of three values:

| Mode | What it does | Use it when |
|---|---|---|
| `denylist` (the default) | Accepts every attribute except the ones on a short deny list. The built-in list covers the attributes that read files: `image`, `shapefile`, `imagepath`, `fontpath`, `stylesheet`, and `<IMG>` elements in HTML-like labels. | You are running the server for yourself, or for people you trust, and want the least friction. |
| `allowlist` | Accepts only the attributes on an allow list. The default allowlist covers the common layout, styling, font, and label attributes. Anything else, including attribute names Graphviz does not document, is rejected. | The server is shared, or reachable by anyone you do not fully trust. This is the safer choice. |
| `unrestricted` | Performs no attribute checks at all and allows Graphviz to read files from the server. | Only for a throwaway setup on your own machine where you know exactly what is being sent. The server logs a warning at startup. |

In `denylist` and `allowlist` modes the server also applies specific attribute-value range limits as described later in this guide. In `unrestricted` those range limits are not applied. 

In all cases, the server's other security and resource limit (time, memory, input size and output size) configuration settings always apply. 

To set the mode, pass the variable to the container using the `-e` parameter to the `docker run` call. E.g., you might use something like:

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  -e GVMCP_ATTR_POLICY=allowlist \
  graphviz-mcp:dev
```

When no `GVMCP_ATTR_POLICY` value is explicitly set, the attribute policy defaults to `denylist`.

### A second layer of protection

When the `denylist` or `allowlist` modes are active, graphviz-mcp also runs every Graphviz process in the Graphviz's built in "web server" mode, in which file loading is strictly prohibited. Even if some attribute slips past the lists, Graphviz itself still declines to open files.

The `unrestricted` is truly unrestricted. File loading _is_ allowed when the attribute policy is set to `unrestricted`.

## What gets checked

The policy looks at every attribute in a request, wherever it appears in the `G`, `N`, `E` and `A` parameters or anywhere in the DOT source cod3e. That includes graph, subgraph, node, and edge defaults, individual node and edge attribute lists, and `<IMG>` elements inside HTML-like labels. Writing the name in unusual ways (for example `"ima" + "ge"`) does not work around these constraints.

Attribute names are compared without regard to upper or lower case, so a rule for `Label` also covers `label` and
`LABEL`. Graphviz itself treats a few names that differ only by case (such as `K` and `k`) as different attributes,
but the policy does not. A rule for one of them will apply to both.

## What you will see an prohibited attribute is used

graphviz-mcp will refuse to process any request that includes prohibited attributes. A request that violates the attribute security policy is refused before any drawing starts. Nothing is partly processed, the request is rejected outright.

MCP clients will receive a tool error that names the attribute and the rule it violated. For example:

```text
attribute policy violation: image: attribute is on the deny list (graph text)
attribute policy violation: fancyattr: attribute is not on the allow list (request parameter)
attribute policy violation: dpi: value '150' exceeds the maximum (max=100)
```

The text in parentheses tells you whether the offending attribute came from the DOT text or from a request parameter.

When an invalid request is submitted via the Web UI forms, you will receive a similar message and an HTTP 403 status code.

Each rejection is also written to the server log.

A graph that is not a valid DOT document is reported as a syntax error, not a policy error, and that syntax check happens first.

## Reviewing the current policy

You can ask the running server what the current attribute policy is, and so can any assistant using it via MCP.

* **`get_capabilities`** returns, among other things, an `attribute_policy` section indicating the `mode`, a one-line `rule` describing it, the `deny` list, the `allow` list (if active), and any additional `constraints`, which are the value limits.
* **`graphviz://attributes`** is a resource that lists every documented Graphviz attribute together with its type, default, and its status under the current policy: `ok`, `denied`, `not on allow list`, or `capped` along with the limit. The Web UI shows the same information.
* **`validate_dot`** checks a graph's syntax and reports in `policy_ok` and `policy_violation` whether the policy would accept it, without drawing anything.

## Customizing with a policy file

The built-in lists suit many situations, but you can adjust them with a small configuration file. Write it in TOML, a plain-text format of `key = value` lines and `[table]` headings.

Point the server to the file via the environment variable  `GVMCP_ATTR_POLICY_FILE`. It works with both `denylist` and `allowlist` modes. The policy file is ignored when the `unrestricted` mode is active.

Note that the policy file is read once, when the server starts. If you make changes to the file you must restart the server to see them take effect.

Since the server runs in a container, mount the file into it, read-only, and give the path as seen from inside:

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop=ALL \
  --security-opt no-new-privileges \
  -e GVMCP_ATTR_POLICY=allowlist \
  -e GVMCP_ATTR_POLICY_FILE=/policy.toml \
  -v "$PWD/my-policy.toml:/policy.toml:ro" \
  graphviz-mcp:dev
```

The file may contain any of these keys, and nothing else:

| Key | Meaning | Applies in |
|---|---|---|
| `deny_add` | Names to add to the built-in deny list. | `denylist` mode |
| `deny` | Names to use as the deny list instead of the built-in one. | `denylist` mode |
| `allow_add` | Names to add to the built-in allow list. | `allowlist` mode |
| `allow` | Names to use as the allow list instead of the built-in one. | `allowlist` mode |
| `[constraints.NAME]` | A limit on the values of the attribute `NAME`. | both modes |

Each list is an array of attribute names in quotes. The special name `html:img` stands for `<IMG>` elements in HTML-like labels, which are not attributes in the usual sense but are controlled the same way.

If a key is in the file but the other mode is active, it is accepted and has no effect. Setting `deny_add` while running in `allowlist` mode, for example, changes nothing. In `allowlist` mode, to forbid an attribute you leave it out of the allow list.

### Example: also block some attributes (denylist mode)

Suppose you want to keep everything the default configuration blocks, and also stop requests from setting `URL`, `href` and `tooltip`, because the graphs you render are shown on a page where links should not appear. You can use this within your policy TOML file:

```toml
deny_add = ["URL", "href", "tooltip"]
```

### Example: permit a few more attributes (allowlist mode)

The built-in allow list is a starting point. Graphviz lets you invent your own attribute names, and some people use them to carry extra information through a graph. In `allowlist` mode those are refused until you list them explicitly. 

For eaxample, the following TOML configuration permits a custom attribute called `data_owner`, and also permits `<IMG>` elements, which the built-in list does not:

```toml
allow_add = ["data_owner", "html:img"]
```

Remember that this only lets the request past the policy screen. Graphviz will still refuse to load an image file unless the server runs in `unrestricted` mode.

### Example: a short, strict allow list (allowlist mode)

If you know exactly what your users should be able to do, replace the built-in list rather than extending it. The list must then include every attribute you want to permit, including the basic ones such as `label`:

```toml
allow = [
  "label", "shape", "style", "color", "fillcolor", "fontname", "fontsize",
  "rankdir", "nodesep", "ranksep", "arrowhead", "dir",
]
```

With this file, a graph that sets `splines=ortho` is refused, because `splines` is not on the list.

### Example: change a numeric limit

The server ships with upper limits for a number of attributes that can make Graphviz use a lot of time or memory, such as `dpi`, `fontsize`, `penwidth`, `peripheries`, and `maxiter`. Use a `constraints` table to tighten or loosen one. This configuration lowers the largest allowed `dpi` to 150 and sets a minimum for it too:

```toml
[constraints.dpi]
min = 36
max = 150
```

An attribute constraint table can use these keys, alone or together. A value must satisfy all of them.

| Key | Meaning |
|---|---|
| `min`, `max` | The value must be a number, and not below `min` or above `max`. |
| `enum` | The value must exactly match one of the listed strings (case matters). |
| `regex` | The whole value must match the given regular expression, up to 500 characters long. |

You can also add limits to attributes that have none. This configuration allows only three edge styles for `splines`, and only the top-to-bottom and left-to-right directions for `rankdir`:

```toml
[constraints.splines]
enum = ["line", "polyline", "true"]

[constraints.rankdir]
regex = "TB|LR"
```

A table for an attribute replaces the built-in table for that attribute entirely; the two are not merged. If you want to keep the built-in `max` and only add a `min`, repeat the `max` in your table. To effectively remove a built-in limit, set a very large `max`.

A limit only matters when the attribute itself is accepted. A constraint on an attribute that is denied, or missing from the allow list, never gets the chance to apply.

### Example: start from the built-in defaults

To work from the complete built-in lists, open the file `src/graphviz_mcp/policy/defaults.toml` in the project repo, copy the parts you want into your own file, and edit them. Because `deny` and `allow` replace the built-in lists, this is how you take full control of one of them. For example, a copy of the deny list with the `stylesheet` entry removed:

```toml
deny = ["image", "shapefile", "imagepath", "fontpath", "html:img"]
```

That file is the authoritative record of the defaults, including the reasons for each deny-list entry. This guide does not repeat them, so check the file for current contents. If you are running a published image and do not have the source, run `get_capabilities` against it (see above) to read the active deny list, allow list, and limits.

## The image-size limit

Asking for a PNG or other bitmap format at a large `size`, `dpi` or `pad` can produce an enormous image. In `denylist` and `allowlist` modes, the server estimates the pixel count of such a result before producing it and refuses requests above 50 million pixels, with a message that suggests reducing `size` or `dpi`, or choosing a vector format such as SVG. The estimate is slightly generous, so a request very close to the limit may be refused.

Two addtional settings adjust this behavior:

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_MAX_RASTER_PIXELS` | `50000000` | The largest image, in pixels, that the server will produce. |
| `GVMCP_RASTER_PREFLIGHT` | `true` | When `true`, the server runs a quick layout to measure the true size. When `false`, it relies on the graph's `size` attribute alone, which is faster but less precise. |

## Troubleshooting

**The server will not start and mentions the policy.** The server checks its configuration at startup and exits with a message if something is wrong. Typical causes are a `GVMCP_ATTR_POLICY` value other than the three modes, a policy file path that cannot be read (often a missing `-v` mount), a file that is not valid TOML, a key the file may not contain, an attribute name with characters that cannot appear in one, or a constraint that is empty, has an empty `enum`, or has a `min` larger than its `max`.

**A change to my policy file had no effect.** Restart the server, since the file is only read at startup. Then check whether you used a list that belongs to the other mode (`deny` and `deny_add` for `denylist`; `allow` and `allow_add` for `allowlist`), and compare against `get_capabilities`.

**An ordinary attribute is being refused in `allowlist` mode.** The built-in list is not exhaustive. Add the attribute with `allow_add`. If it is refused with "not a valid attribute name", the name is malformed rather than unlisted.

**A request is refused even though the attribute is allowed.** Look at the message. If it mentions a maximum, minimum, allowed values, or pattern, a value limit rejected it rather than the lists. If it mentions megapixels, it is the image-size limit.
