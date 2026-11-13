from __future__ import annotations

import base64

import pytest

from graphviz_mcp.formats import base_format, build_content, describe


def test_base_format_and_mime_derive_from_base() -> None:
    assert base_format("png:cairo:gd") == "png"
    assert describe("png:cairo:gd").mime == "image/png"
    assert describe("svg:cairo").mime == "image/svg+xml" and describe("svg:cairo").kind == "text"


@pytest.mark.parametrize(
    ("fmt", "kind"),
    [("svg", "text"), ("dot", "text"), ("json", "text"), ("plain", "text"), ("xdot", "text"), ("png", "image"),
     ("jpg", "image"), ("jpeg", "image"), ("gif", "image"), ("webp", "image"), ("pdf", "blob"), ("svgz", "blob"),
     ("gd", "blob"), ("wbmp", "blob"), ("ps", "text"), ("totally_new", "blob")],
)  # fmt: skip
def test_kinds(fmt: str, kind: str) -> None:
    assert describe(fmt).kind == kind


def test_text_result_and_stderr_block() -> None:
    blocks = build_content("svg", b"<svg/>", "Warning: x\n")
    assert [b.type for b in blocks] == ["text", "text"]
    assert blocks[0].text == "<svg/>" and blocks[1].text.startswith("[stderr]")  # type: ignore[union-attr]


def test_image_result_is_base64() -> None:
    (block,) = build_content("png", b"\x89PNG....")
    assert block.type == "image" and block.mime_type == "image/png"
    assert base64.b64decode(block.data) == b"\x89PNG...."


def test_blob_result_is_embedded_resource() -> None:
    (block,) = build_content("pdf", b"%PDF-1.7")
    assert block.type == "resource" and block.resource.mime_type == "application/pdf"
    assert base64.b64decode(block.resource.blob) == b"%PDF-1.7"  # type: ignore[union-attr]


def test_undecodable_text_falls_back_to_blob() -> None:
    (block,) = build_content("ps", b"\xff\xfe binary")
    assert block.type == "resource"
