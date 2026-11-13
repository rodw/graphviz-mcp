"""Web UI helpers: form generation from the flag table, form parsing, result presentation, headers."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp_types import BlobResourceContents, EmbeddedResource, ImageContent, TextContent

from ..formats import base_format, describe
from ..tools.argv import MAX_VALUE_LEN
from ..tools.service import ToolResult
from ..tools.specs import Param, Program

if TYPE_CHECKING:
    from ..server import App

SAMPLE_DOT = 'digraph G {\n  rankdir=LR;\n  a -> b -> c;\n  a -> c [label="shortcut"];\n}\n'
CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'self'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
}


class FormError(ValueError):
    """The submitted form could not be turned into tool arguments (HTTP 422)."""


@dataclass
class FieldView:
    name: str
    label: str
    control: str  # checkbox | number | text | select | textarea | datalist-text
    help: str
    required: bool = False
    value: str = ""
    checked: bool = False
    options: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    rows: int = 3
    flag: str = ""


def _help(p: Param) -> str:
    return p.doc


def build_fields(
    prog: Program, app: App, values: dict[str, str] | None = None, checked: set[str] | None = None
) -> list[FieldView]:
    """One field per MCP parameter, in table order."""
    values = values or {}
    checked = checked or set()
    fields: list[FieldView] = []
    if prog.input in ("dot", "text", "file"):
        sample = SAMPLE_DOT if prog.input == "dot" else ""
        fields.append(
            FieldView(
                "input",
                "input",
                "textarea",
                prog.input_doc,
                required=True,
                value=values.get("input", sample),
                rows=14,
                flag="input",
            )
        )
    for p in prog.params:
        v = values.get(p.name, "" if p.default is None else str(p.default))
        fv = FieldView(p.name, p.name, "text", _help(p), required=p.required, value=v, flag=p.cli)
        if p.ptype == "bool":
            fv.control, fv.checked = "checkbox", p.name in checked
        elif p.ptype in ("int", "float"):
            fv.control = "number"
            fv.attrs["step"] = "1" if p.ptype == "int" else "any"
            if p.minimum is not None:
                fv.attrs["min"] = f"{p.minimum:g}"
            if p.maximum is not None:
                fv.attrs["max"] = f"{p.maximum:g}"
            if p.choices:
                fv.control, fv.options = "select", [str(c) for c in p.choices]
        elif p.ptype == "kv":
            fv.control, fv.rows = "textarea", 3
            fv.help += " One `name=value` per line."
        elif p.ptype == "strlist":
            fv.control, fv.rows = "textarea", 3
            fv.help += " One value per line."
        elif p.choices:
            fv.control, fv.options = "select", [str(c) for c in p.choices]
        elif p.dynamic == "format":
            fv.control = "datalist-text"
            fv.options = sorted({*app.caps.formats, *app.caps.valid_specs})
        elif p.dynamic == "engine":
            fv.control, fv.options = "select", list(app.caps.engines)
        else:
            fv.attrs["maxlength"] = str(MAX_VALUE_LEN)
        fields.append(fv)
    return fields


def parse_form(prog: Program, form: dict[str, str]) -> dict[str, Any]:
    """Turn submitted fields into the same argument object an MCP client would send."""
    args: dict[str, Any] = {}
    if "input" in form and form["input"].strip():
        args["input"] = form["input"].replace("\r\n", "\n")
    known = {p.name for p in prog.params} | {"input"}
    stray = sorted(set(form) - known)
    if stray:
        raise FormError(f"unknown form field(s): {', '.join(stray)}")
    for p in prog.params:
        raw = form.get(p.name)
        if raw is None or (raw.strip() == "" and p.ptype != "bool"):
            continue
        try:
            if p.ptype == "bool":
                if raw.lower() in ("on", "true", "1"):
                    args[p.name] = True
            elif p.ptype == "int":
                args[p.name] = int(raw)
            elif p.ptype == "float":
                args[p.name] = float(raw)
            elif p.ptype == "kv":
                args[p.name] = _parse_kv(p.name, raw)
            elif p.ptype == "strlist":
                args[p.name] = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            else:
                args[p.name] = raw.strip()
        except ValueError:
            raise FormError(f"{p.name}: expected {'an integer' if p.ptype == 'int' else 'a number'}") from None
    return args


def _parse_kv(name: str, raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise FormError(f"{name}: each line must look like name=value (got {line[:40]!r})")
        out[key.strip()] = value.strip()
    return out


def _data_uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def present(prog: Program, result: ToolResult) -> list[dict[str, Any]]:
    """Result blocks for the template: images render via <img src=data:>, text is shown with a download link."""
    fmt = str(result.meta.get("format", ""))
    blocks: list[dict[str, Any]] = []
    for i, c in enumerate(result.content):
        if isinstance(c, ImageContent):
            blocks.append(
                {
                    "kind": "image",
                    "src": f"data:{c.mime_type};base64,{c.data}",
                    "mime": c.mime_type,
                    "index": i,
                    "filename": f"result-{i}.{c.mime_type.split('/')[-1]}",
                }
            )
        elif isinstance(c, TextContent) and c.text.startswith("[stderr]"):
            blocks.append({"kind": "stderr", "text": c.text.removeprefix("[stderr]").strip(), "index": i})
        elif isinstance(c, TextContent):
            info = describe(fmt) if fmt else None
            block: dict[str, Any] = {
                "kind": "text",
                "text": c.text,
                "index": i,
                "filename": f"result-{i}.{info.ext if info else 'txt'}",
                "download": _data_uri((info.mime if info else "text/plain") + ";charset=utf-8", c.text.encode()),
            }
            if fmt and base_format(fmt) in ("svg", "svg_inline"):
                block["image"] = _data_uri("image/svg+xml", c.text.encode())
            blocks.append(block)
        elif isinstance(c, EmbeddedResource) and isinstance(c.resource, BlobResourceContents):
            res = c.resource
            mime = res.mime_type or "application/octet-stream"
            blocks.append(
                {
                    "kind": "blob",
                    "mime": mime,
                    "index": i,
                    "href": f"data:{mime};base64,{res.blob}",
                    "filename": str(res.uri).rsplit("/", 1)[-1],
                    "size": len(res.blob) * 3 // 4,
                }
            )
    return blocks
