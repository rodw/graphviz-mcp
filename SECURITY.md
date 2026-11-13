# Security Policy

By default, graphviz-mcp treats all input as untrusted and enforces a strict access policy. However the server is NOT hardened for deployment on the public internet. It has no TLS or authentication, and only limited request throttling support. It is designed for use on a single machine or within a private network.

## Supported versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Older releases | No |

Security fixes are generally only maintained for the most recent stable release. Please upgrade to the latest version before reporting an issue.

## Reporting a vulnerability

Please do not open a public GitHub issue for suspected vulnerabilities.

Use the [private vulnerability reporting for this repository](https://github.com/rodw/graphviz-mcp/security/advisories/new) instead.

## Running it safely

The service runs as a non-root user, supports a read-only root filesystem and needs no network or Linux capabilities. This command turns all of that on:

```bash
docker run \
    --rm -p 127.0.0.1:8000:8000 \
    --read-only --cap-drop=ALL \
    --tmpfs /tmp:rw,noexec,nosuid,size=256m \
    --security-opt no-new-privileges \
    --pids-limit 512 \
    --memory 2g \
    ghcr.io/rodw/graphviz-mcp:latest
```

* Publish to `127.0.0.1` only.
* Pin an image tag such as `X.Y.Z` instead of `latest` when you want the same image every time.
* With the stdio transport, add `--network=none`. The server needs no network at all.
* `--memory` is the real (container-level) memory ceiling. `GVMCP_MEMORY_MB` is a per-process safety net that limits address space per internal Graphviz call.
* Prefer `GVMCP_ATTR_POLICY=allowlist` for anything beyond personal use. See [attribute-security-policy.md](docs/attribute-security-policy.md) for details.
* To serve other host names (a reverse proxy, a LAN name), add them to `GVMCP_ALLOWED_HOSTS`.

See [docs/configuration.md](docs/configuration.md) for more information on the `GVMCP_*` configuration parameters.

## Threats and controls

| Threat | Control |
|---|---|
| Reading server files through Graphviz (`image=`, `shapefile=`, `<IMG SRC>`, `stylesheet`, `fontpath`) | Attribute policy on parameters and on the DOT text (parsed by Graphviz's own `nop`), plus Graphviz server mode (`SERVER_NAME`), which refuses all file loads. Details in [attribute-security-policy.md](docs/attribute-security-policy.md). |
| Writing files or running programs | No `-o/-O/-l/-P/-c`; `gvpr` is not exposed; argv lists only, never a shell; fixed program allowlist; per-call temp dir removed afterwards. |
| Option injection through values | Values are validated against the flag table; free-form strings need a pattern; attached flag values (`-Tsvg`) cannot start a new option; separate values may not start with `-`; NUL and control characters are rejected; `T` and `K` are checked against the set the running Graphviz reports. |
| CPU, memory or disk exhaustion | Timeout, `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, input cap, streamed output cap, stderr cap, raster pixel budget, bounded concurrency with a bounded queue. |
| HTTP request-body flood | A body cap on `/mcp` and Web UI form posts, derived from the input cap (see `GVMCP_MAX_INPUT_BYTES`). It is enforced before the body is buffered, parsed or routed: chunked bodies are counted and aborted at the cap, an over-large `Content-Length` is refused without reading anything, and malformed or repeated `Content-Length` values are rejected. It bounds size, not time or connection count. |
| A runaway call affecting others | Each call runs in its own process group. A timeout or cancellation sends SIGTERM, then SIGKILL, to that group and leaves other calls alone. |
| Browser-based attacks on a localhost service | DNS rebinding: a `Host` allow-list on every route (the SDK's own check covers only `/mcp`). CSRF: `Origin` and `Sec-Fetch-Site` checks on form posts, urlencoded forms only (no multipart), no cookies. XSS: all output escaped; results shown through `<img src="data:...">`; CSP `default-src 'none'; img-src data:; style-src 'self'; form-action 'self'`. |
| Information leakage in errors | Graphviz stderr is trimmed and server paths are replaced by `<graphviz>` and `<tmp>`. Policy rejections name only the attribute and the rule. |
| Supply chain | Base image pinned by digest; Graphviz source pinned by SHA-256; Python dependencies pinned in `requirements.lock`; CI license check; SBOM and provenance attestations on release. |

## Logging

Logs are JSON lines on stderr, because stdout is the protocol channel in stdio mode. Each tool call logs one record with the tool, the surface (`mcp` or `ui`), the status, the duration, the input and output sizes in bytes, and the rejection reason if there was one. Graph contents are never logged.
