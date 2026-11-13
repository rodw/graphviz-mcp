# graphviz-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants access to Graphviz: the layout engines (`dot`, `neato`, `fdp`, and the rest) and the graph-processing utilities (`ccomps`, `tred`, `gvpack`, and so on).

It ships as a single Docker image with Graphviz 16.1.0 built from source, so nothing needs to be installed on the host. A given image tag always has the same engines, output formats and fonts, which keeps rendered output reproducible from one machine to the next.

## Overview

Each Graphviz program is one MCP tool with the same name, and its parameters are named after the command-line flags. `T` is `-T`, `G` is `-G`, and so on. If you already know Graphviz, you know the API.

Calls are stateless. The graph goes in as a string and the result comes back as MCP content: text for formats like SVG and DOT, image content for PNG, JPEG, GIF and WebP, and an embedded blob for everything else (PDF, for example). The server never reads or writes files on a caller's behalf.

Because the caller is often a model working on text it didn't write, the defaults are strict. There's an attribute policy, limits on time, memory and output size, no shell, a non-root user and a read-only root filesystem. See [Security](#security) before you change any of that.

The server speaks Streamable HTTP and stdio. The HTTP mode also serves a small form-based Web UI and a few health endpoints. The image is built for linux/amd64 and linux/arm64.

## Getting started

### Prerequisites

* Docker with a running daemon
* `make` (optional, but the targets below save typing)

### Build and run

There's no published image yet for a fresh clone, so build one:

```bash
docker build --build-arg APP_VERSION=0.1.0 -t graphviz-mcp:dev .
```

Then start the HTTP server, published to localhost only:

```bash
docker run --rm -p 127.0.0.1:8000:8000 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop=ALL --security-opt no-new-privileges graphviz-mcp:dev
```

That gives you:

* the MCP endpoint at `http://127.0.0.1:8000/mcp`
* the Web UI at <http://127.0.0.1:8000/ui>
* `/health`, `/ready` and `/version`

The `127.0.0.1:` part of `-p` matters. Inside the container the server listens on `0.0.0.0`, so the published address is what keeps it off your network.

From a checkout, the Makefile wraps the same thing: `make start`, `make status`, `make logs`, `make stop`, `make restart`, `make run-http` (foreground) and `make run-stdio`. Set `SERVICE_IMAGE_TAG` to pick an image (default `dev`) and `HTTP_PORT` to change the host port (default 8000). `make help` lists the rest.

The release workflow publishes a multi-arch image to `ghcr.io/<owner>/graphviz-mcp` when a version tag is pushed, so once a release exists you can pull that instead of building.

### Connect a client

Claude Code, over HTTP:

```bash
claude mcp add --transport http graphviz http://127.0.0.1:8000/mcp
```

Claude Code, over stdio, which needs no open port at all:

```bash
claude mcp add graphviz -- docker run -i --rm --network=none --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop=ALL --security-opt no-new-privileges graphviz-mcp:dev --stdio
```

Claude Desktop (stdio) in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "graphviz": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network=none", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
               "--cap-drop=ALL", "--security-opt", "no-new-privileges", "graphviz-mcp:dev", "--stdio"]
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

Everything is an environment variable, and an invalid value stops the server at startup. The command line also accepts `--http` (the default), `--stdio`, `--host`, `--port` and `--version`.

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

## Security

This is meant for one operator on a trusted machine or private network. It has no TLS, authentication or rate limiting, so don't expose the port or the Web UI to the internet.

The main controls:

* No shell. Programs run from argv lists against a fixed allowlist, and the flags that touch the server's filesystem or processes (`-o`, `-O`, `-l`, `-P`, `-c`) aren't exposed.
* The attribute policy (`GVMCP_ATTR_POLICY`) is `denylist` by default, which rejects `image`, `shapefile`, `imagepath`, `fontpath`, `stylesheet` and HTML `<IMG>`. `allowlist` permits only listed attributes and is the better choice beyond local use. `unrestricted` turns the checks off. The policy applies to the `G`/`N`/`E`/`A` parameters and to every attribute inside the DOT text. [docs/attribute-security-policy.md](docs/attribute-security-policy.md) explains how to choose.
* Each call has limits on time, input size, output size, memory, CPU and raster pixels, and a bounded queue. A timed-out or canceled call kills its own process group and nothing else.
* The container runs as user 10001 with a read-only root filesystem and all capabilities dropped, and it needs no network.
* Host and Origin checks guard against DNS rebinding and cross-site form posts. The Web UI sets a strict CSP and no cookies.

The threat model and a recommended hardened `docker run` command are in [SECURITY.md](SECURITY.md).

## Project structure

```
src/graphviz_mcp/
  tools/        tool specs, catalog, argv builder, registry, service layer
  policy/       attribute policy engine, loader, defaults, raster budget
  web/          Web UI rendering and static assets
  data/         attribute lists and descriptions, DOT language reference
  runner.py     the only place a process is spawned
  server.py     MCP and HTTP server wiring
  extras.py     validate_dot, get_capabilities
  config.py     GVMCP_* settings
docs/           generated tool reference, attribute policy guide
scripts/        doc generators, license check, prerequisite check
tests/          unit tests, Docker image integration tests, golden fixtures
```

[specs.py](src/graphviz_mcp/tools/specs.py) is the single source of truth for flags, types and limits. The MCP schemas, the argv builder, the Web UI forms, the docs and the name-conformance tests are all generated from it.

## Development

You need Python 3.12 or newer with `venv`, Docker, and `make`. `make audit.prereqs` checks them.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
.venv/bin/pytest
```

The unit tests need neither Graphviz nor Docker. Tests that depend on the pinned Graphviz (golden SVGs, renderers, security, concurrency) run against the built image:

```bash
docker build --build-arg APP_VERSION=0.1.0 -t graphviz-mcp:dev . && .venv/bin/pytest -m docker_image
```

Coverage and housekeeping:

```bash
make test-coverage.docker-image      # Docker image tests with coverage of the code inside the containers
make test-coverage                   # unit and image tests, one combined report
.venv/bin/python scripts/gen_tool_docs.py     # regenerate docs/graphviz-tools.md
.venv/bin/python scripts/check_licenses.py    # dependency license policy
```

CI (`.github/workflows/ci.yml`) runs lint, type checks, unit tests and the license check, then builds the image on amd64 and arm64 and runs the image tests on each. In the Dockerfile the base image is pinned by digest and the Graphviz source by SHA-256, and the final stage has no compiler.

## Contributing

Issues and pull requests are welcome. Before opening one, run ruff, mypy and the unit tests, and run the Docker image tests if you touched anything that affects Graphviz behavior. If you change a tool spec, regenerate `docs/graphviz-tools.md`.

## License

MIT, see [LICENSE](LICENSE). Graphviz (EPL-1.0) and the system libraries and fonts in the image keep their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
