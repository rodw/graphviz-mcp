"""Output format -> (MIME, kind) and construction of MCP result content."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Literal

from mcp_types import BlobResourceContents, EmbeddedResource, ImageContent, TextContent

Kind = Literal["text", "image", "blob"]
ContentBlock = TextContent | ImageContent | EmbeddedResource


@dataclass(frozen=True)
class FormatInfo:
    mime: str
    kind: Kind
    ext: str


_TEXT_DOT = "text/vnd.graphviz"
_TABLE: dict[str, FormatInfo] = {}


def _add(names: str, mime: str, kind: Kind, ext: str | None = None) -> None:
    for n in names.split():
        _TABLE[n] = FormatInfo(mime, kind, ext or n)


_add("canon gv dot xdot xdot1.2 xdot1.4", _TEXT_DOT, "text", "gv")
_add("json json0 dot_json xdot_json", "application/json", "text", "json")
_add("plain plain-ext", "text/plain", "text", "txt")
_add("svg svg_inline", "image/svg+xml", "text", "svg")
_add("cmap cmapx cmapx_np imap imap_np ismap", "text/html", "text", "html")
_add("fig pic pov tk", "text/plain", "text", "txt")
_add("vrml", "model/vrml", "text", "wrl")
_add("ps ps2", "application/postscript", "text", "ps")
_add("eps", "application/postscript", "text", "eps")
_add("kitty kittyz vt vt-24bit vt-4up vt-6up vt-8up", "text/plain", "text", "txt")
_add("png", "image/png", "image")
_add("jpg jpeg jpe", "image/jpeg", "image", "jpg")
_add("gif", "image/gif", "image")
_add("webp", "image/webp", "image")
_add("pdf", "application/pdf", "blob")
_add("svgz", "image/svg+xml", "blob", "svgz")  # gzip-compressed; shipped as a blob
_add("wbmp", "image/vnd.wap.wbmp", "blob")
_add("bmp", "image/bmp", "blob")
_add("ico", "image/vnd.microsoft.icon", "blob")
_add("tif tiff", "image/tiff", "blob", "tif")
_add("gd gd2", "image/x-gd", "blob")
_add("jp2", "image/jp2", "blob")
_add("tga", "image/x-tga", "blob")
_add("pict", "image/x-pict", "blob")


def base_format(spec: str) -> str:
    """``png:cairo:cairo`` -> ``png``."""
    return spec.split(":", 1)[0]


def describe(spec: str) -> FormatInfo:
    """Unknown formats are returned as opaque blobs; the MIME/kind derives from the base format only."""
    return _TABLE.get(base_format(spec), FormatInfo("application/octet-stream", "blob", "bin"))


def stderr_block(stderr: str) -> TextContent:
    return TextContent(type="text", text=f"[stderr]\n{stderr.strip()}")


def build_content(spec: str, data: bytes, stderr: str = "") -> list[ContentBlock]:
    info = describe(spec)
    blocks: list[ContentBlock] = []
    kind = info.kind
    text: str | None = None
    if kind == "text":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            kind = "blob"  # e.g. a PostScript variant with binary data
    if kind == "text" and text is not None:
        blocks.append(TextContent(type="text", text=text))
    elif kind == "image":
        blocks.append(ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mime_type=info.mime))
    else:
        mime = info.mime if info.kind != "text" else "application/octet-stream"
        uri = f"graphviz://output.{info.ext}"
        blocks.append(
            EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(uri=uri, mime_type=mime, blob=base64.b64encode(data).decode("ascii")),
            )
        )
    if stderr.strip():
        blocks.append(stderr_block(stderr))
    return blocks
