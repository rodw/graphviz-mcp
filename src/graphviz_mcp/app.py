"""The assembled application object that the transports and routes share."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .capabilities import Capabilities
from .config import Settings
from .runner import Runner
from .security import default_allowed_hosts
from .tools.service import ToolService


class App:
    """Everything the transports need, built once at startup."""

    def __init__(self, settings: Settings, caps: Capabilities, runner: Runner, service: ToolService, server: MCPServer):
        self.settings = settings
        self.caps = caps
        self.runner = runner
        self.service = service
        self.server = server
        self.allowed_hosts = default_allowed_hosts(settings.allowed_hosts)
