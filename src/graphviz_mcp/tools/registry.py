"""Turn the flag table plus the probed capabilities into registered MCP tools."""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from .argv import MAX_VALUE_LEN
from .service import ToolFailure, ToolService
from .specs import PROGRAMS, Param, Program

_ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


def failure_text(exc: ToolFailure) -> str:
    label = {"policy": "attribute policy violation", "busy": "server busy", "timeout": "timeout",
             "too_large": "limit exceeded", "args": "invalid arguments", "input": "invalid input",
             "graphviz": "graphviz error"}.get(exc.kind, "error")  # fmt: skip
    return f"{label}: {exc.message}"


def _annotation(p: Param) -> Any:
    extra: dict[str, Any] = {}
    if p.choices is not None:
        extra["enum"] = list(p.choices)
    base: Any
    if p.ptype == "bool":
        base = bool
    elif p.ptype == "int":
        base = Annotated[int, Field(ge=p.minimum, le=p.maximum, json_schema_extra=extra or None)]
    elif p.ptype == "float":
        base = Annotated[float, Field(ge=p.minimum, le=p.maximum)]
    elif p.ptype == "str":
        base = Annotated[str, Field(pattern=p.pattern, max_length=MAX_VALUE_LEN, json_schema_extra=extra or None)]
    elif p.ptype == "kv":
        base = dict[str, str | int | float | bool]
    else:
        base = list[str]
    if not p.required:
        base = base | None
    return Annotated[base, Field(description=p.doc)]


def build_signature(prog: Program) -> inspect.Signature:
    params: list[inspect.Parameter] = []
    kw = inspect.Parameter.KEYWORD_ONLY
    if prog.input in ("dot", "text", "file"):
        params.append(inspect.Parameter("input", kw, annotation=Annotated[str, Field(description=prog.input_doc)]))
    for p in prog.params:
        default = inspect.Parameter.empty if p.required else p.default
        params.append(inspect.Parameter(p.name, kw, default=default, annotation=_annotation(p)))
    return inspect.Signature(params, return_annotation=CallToolResult)


def describe_tool(prog: Program, policy_line: str) -> str:
    lines = [prog.summary]
    if prog.group == "layout":
        lines.append("Parameter names are the flag letters of the Graphviz command line (T is -T, G is -G, ...).")
        lines.append(
            "Attribute names and whether this server accepts them: resource graphviz://attributes "
            "(official reference https://graphviz.org/doc/info/attrs.html); DOT syntax: graphviz://dot-language."
        )
    else:
        lines.append(
            f"Parameters mirror the flags of the `{prog.name}` command; the parameter name is the flag letter."
        )
    if prog.input == "dot":
        lines.append(policy_line)
    return " ".join(lines)


def make_handler(prog: Program, service: ToolService) -> Any:
    async def handler(**kwargs: Any) -> CallToolResult:
        args = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = await service.call(prog.name, args)
        except ToolFailure as exc:
            return CallToolResult(content=[TextContent(type="text", text=failure_text(exc))], is_error=True)
        return CallToolResult(content=list(result.content))

    sig = build_signature(prog)
    handler.__signature__ = sig  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in sig.parameters.values()} | {"return": CallToolResult}
    handler.__name__ = prog.name
    return handler


def harden(server: MCPServer, name: str) -> None:
    """Make the tool reject unknown arguments (the SDK silently drops them by default)."""
    tool = server._tool_manager.get_tool(name)
    if tool is None:
        raise RuntimeError(f"tool {name} not registered")
    model = tool.fn_metadata.arg_model
    model.model_config["extra"] = "forbid"
    model.model_rebuild(force=True)
    tool.parameters["additionalProperties"] = False


def policy_line(service: ToolService) -> str:
    mode = service.policy.config.mode
    return {
        "denylist": "Attribute policy: denylist (file-reading attributes such as image, shapefile, imagepath, "
        "fontpath, stylesheet and HTML <IMG> are rejected; see graphviz://attributes).",
        "allowlist": "Attribute policy: allowlist (only listed attributes are accepted; see graphviz://attributes).",
        "unrestricted": "Attribute policy: unrestricted.",
    }[mode]


def register_tools(server: MCPServer, service: ToolService) -> list[str]:
    registered: list[str] = []
    line = policy_line(service)
    for name, prog in PROGRAMS.items():
        if name not in service.caps.programs:
            continue
        server.add_tool(
            make_handler(prog, service), name=name, title=name, description=describe_tool(prog, line),
            annotations=_ANNOTATIONS, structured_output=False,
        )  # fmt: skip
        harden(server, name)
        registered.append(name)
    return registered
