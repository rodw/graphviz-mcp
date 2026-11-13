"""One implementation of every tool call, shared by the MCP surface and the Web UI.

Raises :class:`ToolFailure` with a ``kind`` that each surface maps to its own error form (MCP tool
error with ``isError``; HTTP 400/403/413/422/429/504).
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..capabilities import Capabilities
from ..config import Settings
from ..dotsplit import DotLexError, split_graphs
from ..formats import ContentBlock, base_format, build_content, stderr_block
from ..logging import log_call
from ..policy import InputError, PolicyEngine, PolicyViolation
from ..runner import Busy, OutputTooLarge, Runner, RunnerError, TimedOut, scrub
from .argv import ArgError, build_argv
from .specs import PROGRAMS, Program

from mcp_types import TextContent  # isort: skip

HTTP_STATUS = {
    "args": 422, "input": 422, "graphviz": 422, "policy": 403, "busy": 429, "timeout": 504, "too_large": 413,
    "unknown_tool": 404, "internal": 500,
}  # fmt: skip


class ToolFailure(Exception):
    """An anticipated failure (bad arguments, policy rejection, busy, timeout, Graphviz error)."""

    def __init__(self, kind: str, message: str, *, rule: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.rule = rule

    @property
    def status(self) -> int:
        return HTTP_STATUS.get(self.kind, 500)


@dataclass
class ToolResult:
    content: list[ContentBlock]
    output_bytes: int = 0
    stderr: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.content if isinstance(b, TextContent))


def _attr_params(prog: Program, args: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Attribute-style parameters the policy must see (G/N/E/A, gvpack's G, prune's -N specs)."""
    out: dict[str, dict[str, str]] = {}
    for p in prog.params:
        value = args.get(p.name)
        if value is None:
            continue
        if p.ptype == "kv":
            out[p.name] = {str(k): (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in value.items()}
        elif prog.name == "prune" and p.name == "N":
            specs: dict[str, str] = {}
            for item in value:
                name, _, val = str(item).partition("=")
                specs[name] = val
            out["N"] = specs
    return out


class ToolService:
    def __init__(self, settings: Settings, caps: Capabilities, runner: Runner, policy: PolicyEngine) -> None:
        self.settings = settings
        self.caps = caps
        self.runner = runner
        self.policy = policy

    def program(self, name: str) -> Program:
        prog = PROGRAMS.get(name)
        if prog is None or name not in self.caps.programs:
            raise ToolFailure("unknown_tool", f"unknown tool {name!r}")
        return prog

    async def call(self, name: str, args: Mapping[str, Any], *, surface: str = "mcp") -> ToolResult:
        started = time.monotonic()
        prog = self.program(name)
        in_bytes = len(str(args.get("input", "")).encode("utf-8", "replace"))
        try:
            result = await self._dispatch(prog, dict(args))
        except ToolFailure as exc:
            log_call(name, exc.kind, started, input_bytes=in_bytes, reason=exc.message[:200], surface=surface)
            raise
        log_call(name, "ok", started, input_bytes=in_bytes, output_bytes=result.output_bytes, surface=surface)
        return result

    # ------------------------------------------------------------------------------------------
    async def _dispatch(self, prog: Program, args: dict[str, Any]) -> ToolResult:
        try:
            async with self.runner.call_slot():
                return await self._run(prog, args)
        except ToolFailure:
            raise
        except ArgError as exc:
            raise ToolFailure("args", str(exc)) from None
        except PolicyViolation as exc:
            raise ToolFailure("policy", f"{exc.attribute}: {exc.rule}", rule=exc.rule) from None
        except InputError as exc:
            raise ToolFailure("input", f"invalid input: {exc}") from None
        except DotLexError as exc:
            raise ToolFailure("input", f"invalid input: {exc}") from None
        except Busy as exc:
            raise ToolFailure("busy", str(exc)) from None
        except TimedOut as exc:
            raise ToolFailure("timeout", str(exc)) from None
        except OutputTooLarge as exc:
            raise ToolFailure("too_large", str(exc)) from None
        except RunnerError as exc:
            raise ToolFailure("internal", str(exc)) from None

    def _input_text(self, prog: Program, args: Mapping[str, Any]) -> str | None:
        if prog.input not in ("dot", "text", "file"):
            return None
        text = args.get("input")
        if not isinstance(text, str) or not text.strip():
            raise ArgError("input: required, must be a non-empty string")
        if "\x00" in text:
            raise ArgError("input: NUL characters are not allowed")
        if len(text.encode("utf-8")) > self.settings.max_input_bytes:
            raise ToolFailure("too_large", f"input exceeds the {self.settings.max_input_bytes}-byte limit")
        return text

    async def _run(self, prog: Program, args: dict[str, Any]) -> ToolResult:
        if prog.group == "layout" and args.get("T") is None:
            args["T"] = "svg"
        text = self._input_text(prog, args)
        argv = build_argv(prog, {k: v for k, v in args.items() if k != "input"}, self.caps)
        scan = await self.policy.check([text] if prog.input == "dot" and text else [], _attr_params(prog, args))
        async with self.runner.workdir() as wd:
            fmt = str(args["T"]) if prog.group == "layout" else ""
            if prog.group == "layout" and text is not None:
                plain = [a for a in argv if not a.startswith("-T")]
                await self.policy.check_raster(base_format(fmt), prog.name, plain, text, scan, wd)
            stdin = text.encode("utf-8") if text is not None and prog.input != "file" else None
            if prog.input == "file" and text is not None:
                (wd / "input.mtx").write_text(text, encoding="utf-8")
                argv = [*argv, "input.mtx"]
            res = await self.runner.run(prog.name, argv, stdin, workdir=wd)
            err = scrub(res.stderr, self.runner.scrubber(wd))
        if res.returncode not in prog.ok_returncodes:
            tail = (err.strip() or "no error output")[-2000:]
            raise ToolFailure("graphviz", f"{prog.name} failed (exit status {res.returncode}): {tail}")
        if not res.stdout.strip() and re.search(r"(?m)^Error:", err):
            # some tools exit 1 on success, so an "Error:" line with no output is what marks a failure
            raise ToolFailure("graphviz", f"{prog.name} failed: {err.strip()[-2000:]}")
        return self._shape(prog, fmt, res.stdout, err)

    def _shape(self, prog: Program, fmt: str, stdout: bytes, err: str) -> ToolResult:
        if prog.output == "format":
            content = build_content(fmt, stdout, err)
            return ToolResult(content, len(stdout), err, {"format": fmt})
        text = stdout.decode("utf-8", "replace")
        blocks: list[ContentBlock] = []
        if prog.output == "graphs" and text.strip():
            try:
                parts: Sequence[str] = split_graphs(text) or [text]
            except DotLexError:
                parts = [text]
            blocks.extend(TextContent(type="text", text=p) for p in parts)
        elif text.strip() or not err.strip():
            blocks.append(TextContent(type="text", text=text if text.strip() else "(no output)"))
        if err.strip():
            blocks.append(stderr_block(err))
        return ToolResult(blocks, len(stdout), err, {"graphs": len(blocks) - (1 if err.strip() else 0)})
