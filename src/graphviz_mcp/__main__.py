"""Command line: ``graphviz-mcp --http`` (default) or ``graphviz-mcp --stdio``."""

from __future__ import annotations

import argparse
import dataclasses
import sys

from .capabilities import CapabilityError
from .config import ConfigError, load_settings
from .policy import PolicyError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="graphviz-mcp", description="MCP server exposing the Graphviz suite")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--http", action="store_true", help="serve Streamable HTTP + Web UI (default)")
    mode.add_argument("--stdio", action="store_true", help="serve MCP over stdin/stdout")
    parser.add_argument("--host", help="bind address (default 127.0.0.1, or GVMCP_HOST)")
    parser.add_argument("--port", type=int, help="port (default 8000, or GVMCP_PORT)")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    args = parser.parse_args(argv)
    from .server import main_sync, package_version

    if args.version:
        print(package_version())
        return
    try:
        settings = load_settings()
        overrides = {k: v for k, v in (("host", args.host), ("port", args.port)) if v is not None}
        if overrides:
            settings = dataclasses.replace(settings, **overrides)
        main_sync(settings, "stdio" if args.stdio else "http")
    except (ConfigError, PolicyError, CapabilityError) as exc:
        print(f"graphviz-mcp: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
