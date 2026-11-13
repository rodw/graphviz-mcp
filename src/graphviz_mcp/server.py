"""Assemble the MCP server (tools, resources, prompts, HTTP routes) and run it."""

from __future__ import annotations

import asyncio
import logging
from importlib import metadata

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .capabilities import Capabilities, probe
from .config import Settings
from .logging import configure_logging
from .policy import PolicyEngine, load_policy
from .runner import Runner
from .security import HostGuard, allowed_origins, default_allowed_hosts
from .tools.registry import register_tools
from .tools.service import ToolService

LOG = logging.getLogger("graphviz_mcp")
INSTRUCTIONS = (
    "Graphviz as MCP tools: draw, check, analyse and convert graphs written in the DOT language. Each tool is named "
    "after a Graphviz program and its parameters are the program's command-line flag letters (T is -T, G is -G).\n\n"
    "Which tool:\n"
    "- Draw or render a diagram: `dot` (layered; the usual choice for directed graphs, flowcharts, trees and "
    "dependencies), `neato`, `fdp` or `sfdp` (network-style layouts of undirected graphs; `sfdp` for large ones), "
    "`circo` (circular), `twopi` (radial), `osage` (clusters), `patchwork` (treemap). Pass the DOT text in `input` and "
    "the output format in `T` (default svg; others such as png or pdf are listed by `get_capabilities`).\n"
    "- Check DOT syntax without drawing: `validate_dot` (returns line numbers, and whether the attribute policy "
    "accepts the graph). Use `nop` to pretty-print DOT.\n"
    "- Analyse a graph: `gc` (counts), `ccomps`, `bcomps` and `sccmap` (components), `dijkstra` (distances), "
    "`tred` (transitive reduction), `acyclic`, `prune`. `unflatten` improves the aspect ratio of `dot` layouts.\n"
    "- Convert formats: `graphml2gv`, `gml2gv`, `gxl2dot` and `mm2gv` produce DOT; `gv2gml` and `dot2gxl` read DOT. "
    "Generate a sample graph with `gvgen`.\n\n"
    "Attributes (color, shape, rankdir, splines, ...) go in the DOT text or in the `G`, `N`, `E` and `A` parameters. "
    "Read the `graphviz://attributes` resource for every Graphviz attribute with where it applies, its type and "
    "default, and whether this server's attribute policy accepts it (some, such as `image`, are rejected); "
    "`graphviz://dot-language` is a DOT primer; the official reference is https://graphviz.org/doc/info/attrs.html . "
    "`get_capabilities` reports the installed Graphviz version, formats, fonts, limits and the active policy."
)


def package_version() -> str:
    try:
        return metadata.version("graphviz-mcp")
    except metadata.PackageNotFoundError:  # pragma: no cover - running from a source tree
        return "0.0.0"


class App:
    """Everything the transports need, built once at startup."""

    def __init__(self, settings: Settings, caps: Capabilities, runner: Runner, service: ToolService, server: MCPServer):
        self.settings = settings
        self.caps = caps
        self.runner = runner
        self.service = service
        self.server = server
        self.allowed_hosts = default_allowed_hosts(settings.allowed_hosts)


async def build_app(settings: Settings) -> App:
    caps, runner = await probe(settings)
    policy_cfg = load_policy(settings)
    engine = PolicyEngine(
        policy_cfg, runner, max_pixels=settings.max_raster_pixels, preflight=settings.raster_preflight
    )
    service = ToolService(settings, caps, runner, engine)
    server = MCPServer("graphviz-mcp", title="Graphviz", version=package_version(), instructions=INSTRUCTIONS)
    app = App(settings, caps, runner, service, server)
    names = register_tools(server, service)
    from .extras import register_extras  # late import: extras need the assembled App

    register_extras(app)
    if caps.missing:
        LOG.info("graphviz tools not in this build and not registered: %s", ", ".join(caps.missing))
    if caps.unclassified:
        LOG.warning("graphviz programs not in the catalog (not exposed): %s", ", ".join(caps.unclassified))
    LOG.info("ready", extra={"graphviz": caps.version, "tools": len(names), "policy": policy_cfg.mode})
    return app


def http_app(app: App):  # type: ignore[no-untyped-def]
    """Starlette app: MCP at /mcp plus the operational endpoints and Web UI."""
    from .http_ops import register_http_routes

    register_http_routes(app)
    hosts = app.allowed_hosts
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=allowed_origins(hosts)
    )
    starlette_app = app.server.streamable_http_app(host=app.settings.host, transport_security=security)
    starlette_app.add_middleware(HostGuard, hosts=hosts)
    return starlette_app


async def run_http(settings: Settings) -> None:
    app = await build_app(settings)
    config = uvicorn.Config(
        http_app(app), host=settings.host, port=settings.port, log_config=None, access_log=False, server_header=False
    )
    LOG.info("listening", extra={"host": settings.host, "port": settings.port})
    await uvicorn.Server(config).serve()


async def run_stdio(settings: Settings) -> None:
    app = await build_app(settings)
    await app.server.run_stdio_async()


def main_sync(settings: Settings, transport: str) -> None:
    configure_logging(settings.log_level)
    asyncio.run(run_http(settings) if transport == "http" else run_stdio(settings))
