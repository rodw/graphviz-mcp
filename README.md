# graphviz-mcp

[![CI](https://github.com/rodw/graphviz-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/rodw/graphviz-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/rodw/graphviz-mcp)](https://github.com/rodw/graphviz-mcp/releases)
[![License: MIT](https://img.shields.io/github/license/rodw/graphviz-mcp)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants access to Graphviz: the layout engines (`dot`, `neato`, `fdp`, and the rest) and the graph-processing utilities (`ccomps`, `tred`, `gvpack`, and so on).

It ships as a single Docker image with Graphviz 16.1.0 built from source, so nothing needs to be installed on the host. A given image tag always has the same engines, output formats and fonts, which keeps rendered output reproducible from one machine to the next.

## Overview

Each Graphviz program is one MCP tool with the same name, and its parameters are named after the command-line flags. `T` is `-T`, `G` is `-G`, and so on. If you already know Graphviz, you know the API.

Calls are stateless. The graph goes in as a string and the result comes back as MCP content: text for formats like SVG and DOT, image content for PNG, JPEG, GIF and WebP, and an embedded blob for everything else (PDF, for example). The server never reads or writes files on a caller's behalf.

The server speaks Streamable HTTP and stdio. The HTTP mode also serves a small form-based Web UI and a few health endpoints. The image is built for linux/amd64 and linux/arm64, and Docker picks the right one for your machine.

## Getting started

You need Docker with a running daemon. Start the HTTP server, published to localhost only:

```bash
docker run --rm -p 127.0.0.1:8000:8000 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop=ALL --security-opt no-new-privileges ghcr.io/rodw/graphviz-mcp:latest
```

That gives you:

* the MCP endpoint at `http://127.0.0.1:8000/mcp`
* the Web UI at <http://127.0.0.1:8000/ui>
* `/health`, `/ready` and `/version`

The `127.0.0.1:` part of `-p` matters. Inside the container the server listens on `0.0.0.0`, so the published address is what keeps it off your network.

Images are tagged `X.Y.Z`, `X.Y` and `latest`. Use a full version tag if you want the same image every time. The [releases page](https://github.com/rodw/graphviz-mcp/releases) lists what changed in each one.

### Connect a client

Claude Code, over HTTP:

```bash
claude mcp add --transport http graphviz http://127.0.0.1:8000/mcp
```

Claude Code, over stdio, which needs no open port at all:

```bash
claude mcp add graphviz -- docker run -i --rm --network=none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop=ALL --security-opt no-new-privileges ghcr.io/rodw/graphviz-mcp:latest --stdio
```

Claude Desktop (stdio) in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "graphviz": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network=none", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
               "--cap-drop=ALL", "--security-opt", "no-new-privileges", "ghcr.io/rodw/graphviz-mcp:latest", "--stdio"]
    }
  }
}
```

Any other client that supports Streamable HTTP only needs the URL:

```json
{ "mcpServers": { "graphviz": { "url": "http://127.0.0.1:8000/mcp" } } }
```

## Usage

This is what a client sends for `dot -Tpng:cairo -Grankdir=LR`:

```json
{ "name": "dot", "arguments": { "input": "digraph { a -> b -> c }", "T": "png:cairo", "G": { "rankdir": "LR" } } }
```

A few details worth knowing:

* `T` takes `format`, `format:renderer` or `format:renderer:formatter`. Valid values are discovered from the running Graphviz at startup, and `get_capabilities` lists them.
* Graphviz warnings come back in an extra `[stderr]` block.
* Tools that emit several graphs, such as `ccomps -x` and `bcomps -x`, return one string per graph.
* `validate_dot` checks syntax and reports line numbers, which is handy before a long render.

### Tools

| Group | Tools |
|---|---|
| Layout and rendering | `dot` `neato` `fdp` `sfdp` `twopi` `circo` `osage` `patchwork` |
| Processing and analysis | `acyclic` `bcomps` `ccomps` `sccmap` `tred` `unflatten` `gc` `nop` `cluster` `dijkstra` `gvcolor` `gvpack` `mingle` `prune` `edgepaint` `gvmap` |
| Generators and converters | `gvgen` `dot2gxl` `gxl2dot` `gml2gv` `gv2gml` `graphml2gv` `mm2gv` |
| MCP extras | `validate_dot`, `get_capabilities` |

Every executable in Graphviz's bin directory is classified in [catalog.py](src/graphviz_mcp/tools/catalog.py) as either exposed or excluded with a reason (`gvpr`, aliases, GUI programs and shell scripts are excluded). If a program is missing from the build, its tool isn't registered. [docs/graphviz-tools.md](docs/graphviz-tools.md) lists every parameter and is generated from the same table the server uses.

### Web UI

`/ui/tools` shows the same tools MCP clients see. Each tool page is a plain HTML form built from the same table, with the flag letters as field names (`G`, `N`, `E` and `A` take `name=value` lines). Results render inline with the source and a download link. There's no JavaScript and no cookies.

`/health` is liveness. `/ready` returns 503 until the capability check has passed and a trivial `dot` run works. `/version` reports the service, Graphviz, Python and SDK versions as JSON.

## Configuration

The server is configured through environment variables. Invalid values stop the server at startup. The command line also accepts `--http` (the default), `--stdio`, `--host`, `--port` and `--version`.

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_HOST` / `GVMCP_PORT` | `127.0.0.1` (`0.0.0.0` in the image) / `8000` | HTTP bind address and port |
| `GVMCP_ALLOWED_HOSTS` | localhost names | Extra `Host` header values to accept, comma separated (`name`, `name:port` or `name:*`) |
| `GVMCP_TIMEOUT_S` | `30` | Wall-clock limit per Graphviz run |
| `GVMCP_MAX_INPUT_BYTES` | `1000000` | Largest accepted input |
| `GVMCP_MAX_OUTPUT_BYTES` | `20000000` | Output is cut off and the run killed beyond this |
| `GVMCP_MAX_STDERR_BYTES` | `64000` | stderr kept per run |
| `GVMCP_MEMORY_MB` | `4096` | `RLIMIT_AS` per Graphviz process (`0` disables) |
| `GVMCP_CONCURRENCY` | CPU count | Simultaneous Graphviz calls |
| `GVMCP_QUEUE_SIZE` / `GVMCP_QUEUE_WAIT_S` | 4 x concurrency / `30` | Calls allowed to wait, and for how long. Past that the server answers "server busy" |
| `GVMCP_ATTR_POLICY` / `GVMCP_ATTR_POLICY_FILE` | `denylist` / none | Attribute policy mode and TOML overrides |
| `GVMCP_MAX_RASTER_PIXELS` / `GVMCP_RASTER_PREFLIGHT` | `50000000` / `true` | Raster pixel budget and the layout pre-flight that enforces it |
| `GVMCP_LOG_LEVEL` | `INFO` | Logs are JSON lines on stderr, with one `call` record per tool call |

With Docker, pass them with `-e`, for example `-e GVMCP_TIMEOUT_S=60`.

## Security

The server is meant for one operator on a trusted machine or private network. It has no TLS, authentication or rate limiting, so keep the port and the Web UI off the internet. Because the caller is often a model working on text it didn't write, the defaults are strict: an attribute policy, limits on time, memory and output size, no shell, a non-root user and a read-only root filesystem.

[SECURITY.md](SECURITY.md) has the threat model, a hardened `docker run` command, the known limitations, and how to report a vulnerability. [docs/attribute-security-policy.md](docs/attribute-security-policy.md) explains how to choose an attribute policy.

## Contributing

Issues and pull requests are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the development setup, running the tests, building the image yourself, and the release process.

## License

MIT, see [LICENSE](LICENSE). Graphviz (EPL-1.0) and the system libraries and fonts in the image keep their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
