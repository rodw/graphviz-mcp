# Configuration

graphviz-mcp is configured through environment variables with the `GVMCP_` prefix, read once at startup. An invalid value stops the server with an error at launch. Unset or empty variables use the default value.

## Using them

Within Docker, pass environment variables with the [the `--env` parameter](https://docs.docker.com/reference/cli/docker/container/run/#env) to the `docker run` command, e.g.:

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  -e GVMCP_TIMEOUT_S=60 \
  -e GVMCP_LOG_LEVEL=DEBUG \
  ghcr.io/rodw/graphviz-mcp:latest
```

Outside of Docker, export them before starting the server:

```bash
GVMCP_TIMEOUT_S=60 GVMCP_LOG_LEVEL=DEBUG graphviz-mcp
```

To see the values a running server is using, open `/ui/status/current-env` in the [web UI](web-ui.md#status). It lists every variable below with its current value and its default.

## Configuration Parameters

### Network

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_HOST` | `127.0.0.1` (`0.0.0.0` in the Docker image) | HTTP bind address |
| `GVMCP_PORT` | `8000` | HTTP port (1-65535) |
| `GVMCP_ALLOWED_HOSTS` | (localhost names only) | Extra Host header values to accept, comma separated (`name`, `name:port` or `name:*`) |

Binding to a non-localhost name requires adding that name to `GVMCP_ALLOWED_HOSTS`, otherwise requests with that Host header are refused.

In the Docker image the server listens on 0.0.0.0 inside the container; publish the port on 127.0.0.1 (e.g., `-p 127.0.0.1:8000:8000`) to keep it local.

### Limits

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_TIMEOUT_S` | `30` | Wall-clock limit per Graphviz run, in seconds |
| `GVMCP_MAX_INPUT_BYTES` | `1000000` | Largest accepted input |
| `GVMCP_MAX_OUTPUT_BYTES` | `20000000` | Output is cut off and the run killed beyond this |
| `GVMCP_MAX_STDERR_BYTES` | `64000` | Stderr kept per run |
| `GVMCP_MEMORY_MB` | `4096` | Address-space limit per Graphviz process; `0` disables. |
| `GVMCP_CONCURRENCY` | CPU count | Simultaneous active Graphviz calls allowed |
| `GVMCP_QUEUE_SIZE` | 4x concurrency | Calls allowed to wait for a free slot; beyond this the server responds with HTTP 503 |
| `GVMCP_QUEUE_WAIT_S` | `30` | How long a queued request may wait before the server answers "busy" |
| `GVMCP_MAX_RASTER_PIXELS` | `50000000` | Pixel budget for raster output |
| `GVMCP_RASTER_PREFLIGHT` | `true` | Run a layout pre-flight that enforces the raster budget before rendering |

### Attribute policy

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_ATTR_POLICY` | `denylist` | Policy mode: `denylist`, `allowlist` or `unrestricted` |
| `GVMCP_ATTR_POLICY_FILE` | (not set) | TOML file of policy overrides |

See [attribute-security-policy.md](attribute-security-policy.md) for more information.


### Runtime

| Variable | Default | Meaning |
|---|---|---|
| `GVMCP_GRAPHVIZ_BIN` | (found on PATH; `/opt/graphviz/bin` in the Docker image) | Directory containing the Graphviz programs |
| `GVMCP_TMP_DIR` | (system temp dir) | Scratch directory for Graphviz runs |
| `GVMCP_LOG_LEVEL` | `INFO` | Server log level: `DEBUG`, `INFO`, `WARNING` or `ERROR` |

All server logs are reported to stderr since stdout is reserved for the MCP protocol when the STDIO transport mode is used.

## Also See

 * [SECURITY.md](../SECURITY.md)
 * [attibute-security-policy.md](attribute-security-policy.md)