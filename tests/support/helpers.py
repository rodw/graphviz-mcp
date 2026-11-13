from __future__ import annotations

import base64
import struct

from mcp_types import CallToolResult


def text_of(result: CallToolResult) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def first_text(result: CallToolResult) -> str:
    return next(c.text for c in result.content if c.type == "text")


def image_bytes(result: CallToolResult) -> bytes:
    block = next(c for c in result.content if c.type == "image")
    return base64.b64decode(block.data)


def blob_bytes(result: CallToolResult) -> bytes:
    block = next(c for c in result.content if c.type == "resource")
    return base64.b64decode(block.resource.blob)  # type: ignore[union-attr]


def png_dims(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    return w, h
