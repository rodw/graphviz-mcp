from __future__ import annotations

import stat
from pathlib import Path

import pytest

from graphviz_mcp.capabilities import (
    Capabilities,
    CapabilityError,
    parse_default_device,
    parse_use_one_of,
    parse_version,
    probe,
)
from graphviz_mcp.config import Settings
from graphviz_mcp.tools import catalog

# Samples in the exact shape Graphviz prints them; the real programs are checked in the Docker image tests.
VERSION_LINE = "dot - graphviz version 16.1.0 (20260904.0139)\n"
FORMATS = 'Format: "?" not recognized. Use one of: canon cmap dot eps gif jpg json pdf plain png ps svg svgz webp xdot xdot_json\n'
ENGINES = 'There is no layout engine support for "?"\n Use one of: circo dot fdp neato nop nop1 nop2 osage patchwork sfdp twopi\n'
COMBOS = 'Format: "png:nope" not recognized. Use one of: png:cairo:cairo png:cairo:gd png:gd:gd\n'


def test_parse_version() -> None:
    assert parse_version(VERSION_LINE) == "16.1.0"
    with pytest.raises(CapabilityError):
        parse_version("garbage")


def test_parse_formats_and_engines() -> None:
    formats = parse_use_one_of(FORMATS)
    assert {"svg", "png", "pdf", "dot", "plain", "webp", "svgz", "xdot_json"} <= set(formats)
    assert "?" not in formats
    assert parse_use_one_of(ENGINES) == (
        "circo", "dot", "fdp", "neato", "nop", "nop1", "nop2", "osage", "patchwork", "sfdp", "twopi",
    )  # fmt: skip


def test_parse_renderer_combinations() -> None:
    assert parse_use_one_of(COMBOS) == ("png:cairo:cairo", "png:cairo:gd", "png:gd:gd")
    assert parse_use_one_of("nothing here") == ()


def test_parse_default_device() -> None:
    assert parse_default_device("Using render: cairo:cairo\nUsing device: png:cairo:cairo\n") == "png:cairo:cairo"
    assert parse_default_device("") is None


def make_caps() -> Capabilities:
    return Capabilities(
        version="16.1.0", version_line="dot - graphviz version 16.1.0", bin_dir=Path("/x"),
        formats=("svg", "png", "jpg"),
        combos={"svg": ("svg:svg:core", "svg:cairo:cairo"), "png": ("png:cairo:cairo", "png:gd:gd"), "jpg": ("jpg:gd:gd",)},
        default_device={"png": "png:cairo:cairo"}, engines=("dot", "neato"), programs={}, missing=(), unclassified=(),
    )  # fmt: skip


@pytest.mark.parametrize(
    ("spec", "ok"),
    [
        ("svg", True), ("png", True), ("png:cairo", True), ("png:gd", True), ("png:cairo:cairo", True),
        ("png:gd:gd", True), ("svg:cairo", True), ("svg:svg:core", True),
        ("png:nope", False), ("png:cairo:gd", False), ("pdf", False), ("svg:cairo -o/x", False),
        ("svg -o/x", False), ("", False), ("png:", False), (":cairo", False), ("PNG", False),
    ],
)  # fmt: skip
def test_valid_format_is_membership_in_discovered_set(spec: str, ok: bool) -> None:
    assert make_caps().valid_format(spec) is ok


def test_valid_engine() -> None:
    caps = make_caps()
    assert caps.valid_engine("neato") and not caps.valid_engine("sfdp") and not caps.valid_engine("dot -o/x")


def test_as_dict_derives_mime_from_base_format() -> None:
    d = make_caps().as_dict()
    png = next(f for f in d["output_formats"] if f["format"] == "png")
    assert png["mime"] == "image/png" and png["renderers"] == ["png:cairo:cairo", "png:gd:gd"]


def test_catalog_classification() -> None:
    unclassified, missing = catalog.classify({"dot", "neato", "mystery"})
    assert unclassified == ["mystery"] and "ccomps" in missing and "dot" not in missing


def stub_bin(tmp_path: Path, names: dict[str, str]) -> Path:
    for name, body in names.items():
        f = tmp_path / name
        f.write_text("#!/bin/sh\n" + body)
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    return tmp_path


async def test_probe_fails_without_baseline(tmp_path: Path) -> None:
    only_nop = stub_bin(tmp_path, {"nop": "exit 0\n"})
    with pytest.raises(CapabilityError, match="'dot' not found"):
        await probe(Settings(graphviz_bin=only_nop, tmp_dir=tmp_path / "t"))


async def test_probe_with_stub_registers_only_present_tools(tmp_path: Path) -> None:
    stub = (
        'case "$1" in\n -V) echo "dot - graphviz version 9.9.9 (stub)" >&2;;\n'
        " -T\\?) echo 'Format: \"?\" not recognized. Use one of: svg dot plain' >&2; exit 1;;\n"
        " -K\\?) echo 'There is no layout engine support for \"?\"\n Use one of: dot neato' >&2; exit 1;;\n"
        " -T*:x) echo 'Format: \"x\" not recognized. Use one of: svg:svg:core' >&2; exit 1;;\n esac\nexit 0\n"
    )
    bin_dir = stub_bin(tmp_path, {"dot": stub, "nop": "exit 0\n", "neato": "exit 0\n", "mystery": "exit 0\n"})
    caps, runner = await probe(Settings(graphviz_bin=bin_dir, tmp_dir=tmp_path / "t"))
    assert caps.version == "9.9.9" and set(caps.programs) == {"dot", "nop", "neato"}
    assert "ccomps" in caps.missing and caps.unclassified == ("mystery",)
    assert "mystery" not in runner.programs and "ccomps" not in runner.programs
