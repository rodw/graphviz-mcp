# Security

The server is intended for a **single operator on a trusted machine or private network**. Input is treated as untrusted; the caller is often an AI model acting on content it did not write.

## Assets and threats

| Threat | Control |
|---|---|
| Reading server files through Graphviz (`image=`, `shapefile=`, `<IMG SRC>`, `stylesheet`, `fontpath`) | Attribute policy on parameters **and** DOT text (parsed by Graphviz's own `nop`), plus Graphviz server mode (`SERVER_NAME`) which refuses all file loads. Details in [attribute-policy.md](attribute-policy.md). |
| Writing files or running programs | No `-o/-O/-l/-P/-c`; `gvpr` is not exposed; argv lists only, never a shell; fixed program allowlist; per-call temp dir removed afterwards. |
| Option injection through values | Values are validated against the flag table; free-form strings need a pattern; attached flag values (`-Tsvg`) cannot start a new option; separate values may not start with `-`; NUL and control characters are rejected; `T` and `K` are checked against the set the running Graphviz reports. |
| CPU / memory / disk exhaustion | Timeout, `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, input cap, streamed output cap, stderr cap, raster pixel budget, bounded concurrency with a bounded queue. |
| A runaway call affecting others | Each call runs in its own process group; timeout or cancellation sends SIGTERM then SIGKILL to the group; other calls are untouched. |
| Browser-based attacks on a localhost service | DNS-rebinding: `Host` allow-list on every route (the SDK's own check covers only `/mcp`). CSRF: `Origin`/`Sec-Fetch-Site` checks on form posts, urlencoded forms only (no multipart), no cookies. XSS: all output escaped; results shown through `<img src="data:...">`; CSP `default-src 'none'; img-src data:; style-src 'self'; form-action 'self'`. |
| Information leakage in errors | Graphviz stderr is trimmed and server paths are replaced by `<graphviz>` / `<tmp>`; policy rejections name the attribute and rule only. |
| Supply chain | Base image pinned by digest; Graphviz source pinned by SHA-256; Python dependencies pinned in `requirements.lock`; CI license check; SBOM attestation on release. |

## Running it safely

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop=ALL --security-opt no-new-privileges \
  --pids-limit 512 --memory 2g \
  graphviz-mcp:dev
```

* **Publish to `127.0.0.1` only.** Inside a container the server must listen on `0.0.0.0` to be reachable through a published port, so the host-side `-p 127.0.0.1:...` is what keeps it local. Outside Docker the default bind is `127.0.0.1`.
* Use `--network=none` with the stdio transport: the server needs no network at all.
* `--memory` is the real memory ceiling. `GVMCP_MEMORY_MB` (`RLIMIT_AS`) is a per-process safety net; it limits address space, so keep it generous or pango/cairo mappings will fail spuriously.
* Prefer `GVMCP_ATTR_POLICY=allowlist` for anything beyond personal use. `unrestricted` re-enables file loading.
* To serve other host names (a reverse proxy, a LAN name), add them to `GVMCP_ALLOWED_HOSTS`; without that, requests with an unknown `Host` header get 421.

## Known limitations

* No TLS, authentication, rate limiting or per-client quotas.
* `denylist` fails open for attributes nobody has classified; server mode narrows the gap for file loading only.
* Concurrency limits are per process; several replicas each apply their own.
* The image contains LGPL/MPL system libraries (see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)).
* A very large graph can use its full timeout and memory allowance; those limits, not prediction, bound it.

## Logging

JSON lines on stderr (stdout is the protocol channel in stdio mode). Each tool call logs one record: tool, surface (`mcp` or `ui`), status, duration, input and output bytes, and the rejection reason. Graph contents are never logged.
