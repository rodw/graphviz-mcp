# Security policy

graphviz-mcp is meant for one operator on a trusted machine or private network. It has no TLS, authentication or rate limiting, so don't expose the port or the Web UI to the internet. Input is treated as untrusted, because the caller is often an AI model working on content it did not write.

## Supported versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Older releases | No |

Security fixes go into the most recent release only. If you hit a problem on an older image, upgrade first and check whether it still happens.

## Reporting a vulnerability

Please don't open a public issue for a suspected vulnerability. Use GitHub's private vulnerability reporting instead: [report it here](https://github.com/rodw/graphviz-mcp/security/advisories/new), or open the repository's Security tab and choose "Report a vulnerability".

A useful report includes the image tag or version, the tool and parameters involved, the input that triggers the problem, and what an attacker gains. Reports are handled on a best-effort basis.

Anything that gets around the attribute policy, the resource limits or the container hardening described below is in scope. The behavior listed under [Known limitations](#known-limitations) is documented and is not a vulnerability by itself.

## Threats and controls

| Threat | Control |
|---|---|
| Reading server files through Graphviz (`image=`, `shapefile=`, `<IMG SRC>`, `stylesheet`, `fontpath`) | Attribute policy on parameters and on the DOT text (parsed by Graphviz's own `nop`), plus Graphviz server mode (`SERVER_NAME`), which refuses all file loads. Details in [attribute-security-policy.md](docs/attribute-security-policy.md). |
| Writing files or running programs | No `-o/-O/-l/-P/-c`; `gvpr` is not exposed; argv lists only, never a shell; fixed program allowlist; per-call temp dir removed afterwards. |
| Option injection through values | Values are validated against the flag table; free-form strings need a pattern; attached flag values (`-Tsvg`) cannot start a new option; separate values may not start with `-`; NUL and control characters are rejected; `T` and `K` are checked against the set the running Graphviz reports. |
| CPU, memory or disk exhaustion | Timeout, `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_FSIZE`, input cap, streamed output cap, stderr cap, raster pixel budget, bounded concurrency with a bounded queue. |
| A runaway call affecting others | Each call runs in its own process group. A timeout or cancellation sends SIGTERM, then SIGKILL, to that group and leaves other calls alone. |
| Browser-based attacks on a localhost service | DNS rebinding: a `Host` allow-list on every route (the SDK's own check covers only `/mcp`). CSRF: `Origin` and `Sec-Fetch-Site` checks on form posts, urlencoded forms only (no multipart), no cookies. XSS: all output escaped; results shown through `<img src="data:...">`; CSP `default-src 'none'; img-src data:; style-src 'self'; form-action 'self'`. |
| Information leakage in errors | Graphviz stderr is trimmed and server paths are replaced by `<graphviz>` and `<tmp>`. Policy rejections name only the attribute and the rule. |
| Supply chain | Base image pinned by digest; Graphviz source pinned by SHA-256; Python dependencies pinned in `requirements.lock`; CI license check; SBOM and provenance attestations on release. |

## Running it safely

The image runs as user 10001, supports a read-only root filesystem and needs no network or Linux capabilities. This command turns all of that on:

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --cap-drop=ALL --security-opt no-new-privileges \
  --pids-limit 512 --memory 2g \
  ghcr.io/rodw/graphviz-mcp:latest
```

* Publish to `127.0.0.1` only. Inside a container the server has to listen on `0.0.0.0` to be reachable through a published port, so the host-side `-p 127.0.0.1:...` is what keeps it local. Outside Docker the default bind is `127.0.0.1`.
* Pin an image tag such as `X.Y.Z` instead of `latest` when you want the same image every time.
* With the stdio transport, add `--network=none`. The server needs no network at all.
* `--memory` is the real memory ceiling. `GVMCP_MEMORY_MB` (`RLIMIT_AS`) is a per-process safety net that limits address space, so keep it generous or pango and cairo mappings will fail spuriously.
* Prefer `GVMCP_ATTR_POLICY=allowlist` for anything beyond personal use. `unrestricted` turns file loading back on. [attribute-security-policy.md](docs/attribute-security-policy.md) explains how to choose.
* To serve other host names (a reverse proxy, a LAN name), add them to `GVMCP_ALLOWED_HOSTS`. Without that, requests with an unknown `Host` header get a 421.

## Known limitations

* No TLS, authentication, rate limiting or per-client quotas.
* `denylist` lets through attributes nobody has classified. Server mode narrows the gap for file loading only.
* Concurrency limits apply per process, so several replicas each apply their own.
* The image contains LGPL and MPL system libraries (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
* A very large graph can use its full timeout and memory allowance. Those limits bound it, not any attempt to predict its cost.

## Logging

Logs are JSON lines on stderr, because stdout is the protocol channel in stdio mode. Each tool call logs one record with the tool, the surface (`mcp` or `ui`), the status, the duration, the input and output sizes in bytes, and the rejection reason if there was one. Graph contents are never logged.
