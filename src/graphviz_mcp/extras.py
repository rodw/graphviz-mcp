"""MCP-only extensions: validate_dot, get_capabilities, resources, prompts."""

from __future__ import annotations

import json
import platform
import re
from importlib import metadata, resources
from typing import Annotated, Any

from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from .app import App
from .attributes import ATTRS_RESOURCE, ATTRS_URL, DOT_LANGUAGE_RESOURCE, build_view, render_markdown
from .meta import package_version
from .policy import PolicyViolation
from .runner import RunnerError, scrub
from .tools import catalog
from .tools.service import ToolFailure

_ANNOT = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
_LINE = re.compile(r"syntax error in line (\d+)(?: near (.*))?", re.I)


def _data(name: str) -> str:
    return resources.files("graphviz_mcp").joinpath("data", name).read_text("utf-8")


def parse_nop_diagnostics(stderr: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn ``nop -p`` stderr into structured errors and warnings (line when Graphviz gives one)."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for raw in stderr.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind, _, rest = line.partition(": ")
        if kind not in ("Error", "Warning"):
            if errors or warnings:
                (errors if errors and not warnings else warnings)[-1]["message"] += " " + line
            continue
        rest = rest.replace("<stdin>: ", "")
        item: dict[str, Any] = {"message": rest}
        if m := _LINE.search(rest):
            item["line"] = int(m.group(1))
            if m.group(2):
                item["near"] = m.group(2).strip()
        (errors if kind == "Error" else warnings).append(item)
    return errors, warnings


def capabilities_document(app: App) -> dict[str, Any]:
    s = app.settings
    cat = {
        "exposed": sorted(app.caps.programs),
        "not_in_this_build": list(app.caps.missing),
        "excluded": {e.name: e.reason for e in catalog.CATALOG.values() if e.status == "excluded"},
    }
    return {
        "server": {
            "name": "graphviz-mcp",
            "version": package_version(),
            "python": platform.python_version(),
            "mcp_sdk": _sdk_version(),
        },
        **app.caps.as_dict(),
        "catalog": cat,
        "attribute_policy": app.service.policy.config.as_dict(),
        "documentation": {
            "attributes_resource": ATTRS_RESOURCE,
            "dot_language_resource": DOT_LANGUAGE_RESOURCE,
            "official_attributes": ATTRS_URL,
        },
        "limits": {
            "timeout_seconds": s.timeout_s,
            "max_input_bytes": s.max_input_bytes,
            "max_output_bytes": s.max_output_bytes,
            "max_stderr_bytes": s.max_stderr_bytes,
            "memory_mb": s.memory_mb,
            "concurrency": s.concurrency,
            "queue_size": s.queue_size,
            "queue_wait_seconds": s.queue_wait_s,
            "max_raster_pixels": s.max_raster_pixels,
            "raster_preflight": s.raster_preflight,
        },
    }


def _sdk_version() -> str:
    try:
        return metadata.version("mcp")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


def _json_result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data, indent=2))], structured_content=data)


async def validate_document(app: App, text: str) -> dict[str, Any]:
    """Shared by the MCP tool and the Web UI. Raises ToolFailure for bad input, busy, timeout."""
    if not text.strip():
        raise ToolFailure("args", "input is required")
    if len(text.encode("utf-8")) > app.settings.max_input_bytes:
        raise ToolFailure("too_large", f"input exceeds the {app.settings.max_input_bytes}-byte limit")
    try:
        async with app.runner.call_slot(), app.runner.workdir() as wd:
            res = await app.runner.run("nop", ["-p"], text.encode("utf-8"), workdir=wd)
            err = scrub(res.stderr, app.runner.scrubber(wd))
            policy_ok, violation = True, None
            if res.returncode == 0:
                try:
                    await app.service.policy.check([text])
                except PolicyViolation as exc:
                    policy_ok, violation = False, str(exc)
    except RunnerError as exc:
        raise ToolFailure(exc.kind if exc.kind in ("busy", "timeout") else "internal", str(exc)) from None
    errors, warnings = parse_nop_diagnostics(err)
    valid = res.returncode == 0 and not errors
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "policy_ok": policy_ok if valid else None,
        "policy_violation": violation,
    }


def register_extras(app: App) -> None:
    server = app.server

    async def validate_dot(
        input: Annotated[str, Field(description="The graph in DOT language to check; nothing is laid out.")],
    ) -> CallToolResult:
        """Check DOT syntax without laying the graph out (uses `nop -p`). MCP extension, not a Graphviz program.

        Use this before rendering a graph you wrote or edited, or to find why a render failed.
        Returns {valid, errors[{line, message, near}], warnings[], policy_ok, policy_violation}. Graphviz reports
        the line of a syntax error but no column. `policy_ok` says whether the active attribute policy would accept it.
        Example: input="digraph { a -> b }".
        """
        from .tools.registry import failure_text

        try:
            return _json_result(await validate_document(app, input))
        except ToolFailure as exc:
            return CallToolResult(content=[TextContent(type="text", text=failure_text(exc))], is_error=True)

    async def get_capabilities() -> CallToolResult:
        """Report the Graphviz version, layout engines, output formats and renderers, available tools, fonts,
        limits and the active attribute policy (mode, rule, deny list, value constraints).

        Use this to learn which output formats `T` accepts and what the server limits are. The resource
        graphviz://attributes lists every attribute with its status under the policy."""
        return _json_result(capabilities_document(app))

    server.add_tool(
        validate_dot, name="validate_dot", title="validate_dot", annotations=_ANNOT, structured_output=False
    )
    server.add_tool(get_capabilities, name="get_capabilities", title="get_capabilities", annotations=_ANNOT,
                    structured_output=False)  # fmt: skip
    from .tools.registry import harden

    harden(server, "validate_dot")
    harden(server, "get_capabilities")

    @server.resource("graphviz://capabilities", name="capabilities", mime_type="application/json",
                     description="Mirrors the get_capabilities tool: version, formats, limits, policy.")  # fmt: skip
    def capabilities_resource() -> str:
        return json.dumps(capabilities_document(app), indent=2)

    @server.resource("graphviz://attributes", name="attributes", mime_type="text/markdown",
                     description="Every Graphviz attribute: applies-to, type, default, policy status.")  # fmt: skip
    def attributes_resource() -> str:
        return render_attributes(app)

    @server.resource("graphviz://dot-language", name="dot-language", mime_type="text/markdown",
                     description="A short guide to the DOT language.")  # fmt: skip
    def dot_language_resource() -> str:
        return _data("dot-language.md")

    register_prompts(app)


def render_attributes(app: App) -> str:
    return render_markdown(build_view(app.service.policy.config))


def register_prompts(app: App) -> None:
    server = app.server

    @server.prompt(name="visualize_data_as_graph", description="Turn described data into a DOT graph and render it.")
    def visualize_data_as_graph(data: str, layout: str = "dot", format: str = "svg") -> str:
        return (
            f"Here is some data:\n\n{data}\n\n"
            "Model it as a graph: decide what the nodes and edges are, then write DOT. Keep node ids simple "
            "and put readable text in `label`. Call `validate_dot` on your DOT, fix any errors, then render it "
            f'with the `{layout}` tool using T="{format}". Briefly explain the layout you chose.'
        )

    @server.prompt(name="explain_dot", description="Explain what a DOT graph describes and how it will be laid out.")
    def explain_dot(dot: str) -> str:
        return (
            f"Explain this DOT graph: what the nodes and edges represent, which attributes change its look "
            f"or layout, and anything that looks wrong or could be improved.\n\n```dot\n{dot}\n```\n\n"
            "Use `validate_dot` first if you are unsure it is valid."
        )

    @server.prompt(name="fix_dot", description="Repair a DOT graph that fails to parse or renders badly.")
    def fix_dot(dot: str, problem: str = "") -> str:
        extra = f"\nReported problem: {problem}\n" if problem else ""
        return (
            f"Fix this DOT graph.{extra}\n```dot\n{dot}\n```\n\n"
            "Run `validate_dot`, correct the errors it reports (it gives line numbers), and show the corrected "
            "graph. Then render it to confirm."
        )
