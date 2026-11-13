"""Assemble the MCP server (tools, resources, prompts, HTTP routes) and run it."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .app import App
from .capabilities import probe
from .config import Settings
from .extras import register_extras
from .http_ops import register_http_routes
from .logging import configure_logging
from .meta import INSTRUCTIONS, package_version
from .policy import PolicyEngine, load_policy
from .security import HostGuard, allowed_origins
from .tools.registry import register_tools
from .tools.service import ToolService

LOG = logging.getLogger("graphviz_mcp")


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
    register_extras(app)
    if caps.missing:
        LOG.info("graphviz tools not in this build and not registered: %s", ", ".join(caps.missing))
    if caps.unclassified:
        LOG.warning("graphviz programs not in the catalog (not exposed): %s", ", ".join(caps.unclassified))
    LOG.info("ready", extra={"graphviz": caps.version, "tools": len(names), "policy": policy_cfg.mode})
    return app


def http_app(app: App):  # type: ignore[no-untyped-def]
    """Starlette app: MCP at /mcp plus the operational endpoints and Web UI."""
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
