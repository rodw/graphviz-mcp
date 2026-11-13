from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
from importlib import resources
from pathlib import Path
from types import ModuleType

import pytest

from graphviz_mcp.attributes import build_view, master_names, render_markdown
from graphviz_mcp.policy import build_policy

ROOT = Path(__file__).resolve().parents[2]
# Policy names the Graphviz documentation does not list: svgid is read by the SVG renderer, html:img is a pseudo-attribute.
UNLISTED_POLICY_NAMES = {"svgid", "html:img"}
# Master attributes deliberately left out of both the starter allow list and the deny list (none today).
DELIBERATELY_UNCLASSIFIED: set[str] = set()


def _gen_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_attribute_list", ROOT / "scripts" / "gen_attribute_list.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _row(mode: str, name: str) -> list[str]:
    for line in render_markdown(build_view(build_policy(mode))).splitlines():
        cells = [c.strip() for c in line.strip("|").split(" | ")]
        if line.startswith("| ") and cells[0] == name:
            return cells
    raise AssertionError(f"no row for {name} in {mode} mode")


def test_master_list_covers_current_attributes() -> None:
    names = master_names()
    assert len(names) >= 170
    assert {"penwidth", "newrank", "xlabel", "_background", "K", "Damping", "lhead"} <= names


def test_every_master_attribute_is_classified() -> None:
    allow = build_policy("allowlist").allow
    deny = build_policy("denylist").deny
    missing = {n for n in master_names() if n.lower() not in allow | deny} - DELIBERATELY_UNCLASSIFIED
    assert not missing, (
        f"classify these in policy/defaults.toml (allow or deny), or list them as skipped: {sorted(missing)}"
    )


def test_every_policy_name_is_a_master_attribute() -> None:
    cfg = build_policy("allowlist")
    known = {n.lower() for n in master_names()} | UNLISTED_POLICY_NAMES
    stray = (cfg.allow | build_policy("denylist").deny | frozenset(cfg.constraints)) - known
    assert not stray, f"policy names that Graphviz does not document: {sorted(stray)}"


def _described() -> dict[str, str]:
    text = resources.files("graphviz_mcp").joinpath("data", "attribute-descriptions.toml").read_text("utf-8")
    entries: dict[str, str] = tomllib.loads(text)["description"]
    return entries


def test_every_attribute_has_a_description() -> None:
    gen = _gen_module()
    missing, _legacy = gen.compare_descriptions(sorted(master_names()), list(_described()))
    assert not missing, f"add these to data/attribute-descriptions.toml: {missing}"


def test_descriptions_are_not_empty() -> None:
    assert all(text.strip() for text in _described().values())


def test_compare_descriptions_reports_missing_and_legacy() -> None:
    gen = _gen_module()
    assert gen.compare_descriptions(["a", "b", "c"], ["b", "c", "old"]) == (["a"], ["old"])
    assert gen.compare_descriptions(["a"], ["a"]) == ([], [])


def test_check_fails_on_a_missing_description_and_only_warns_on_a_legacy_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gen = _gen_module()
    listing = tmp_path / "list.toml"
    descs = tmp_path / "descs.toml"
    listing.write_text(
        f'graphviz_release = "{gen.GRAPHVIZ_RELEASE}"\nsource_sha = "{gen.SOURCE_SHA}"\n'
        '[[attribute]]\nname = "a"\n[[attribute]]\nname = "b"\n'
    )
    monkeypatch.setattr(gen, "OUTPUT", listing)
    monkeypatch.setattr(gen, "DESCRIPTIONS", descs)
    descs.write_text('[description]\na = "x"\nold = "y"\n')
    assert gen.check() == 1
    err = capsys.readouterr().err
    assert "FAIL" in err and "'b'" in err and "WARNING" in err and "'old'" in err
    descs.write_text('[description]\na = "x"\nb = "y"\nold = "z"\n')
    assert gen.check() == 0
    assert "WARNING" in capsys.readouterr().err


def test_view_status_in_denylist_mode() -> None:
    assert _row("denylist", "image")[5] == "denied"
    assert _row("denylist", "dpi")[5] == "capped (min=0, max=300)"
    assert _row("denylist", "lhead")[5] == "ok"
    assert _row("denylist", "html:img")[5] == "denied"
    assert _row("denylist", "svgid")[5] == "ok"


def test_view_status_in_allowlist_and_unrestricted_modes() -> None:
    assert _row("allowlist", "image")[5] == "not on allow list"
    assert _row("allowlist", "rankdir")[5] == "ok"
    assert _row("unrestricted", "image")[5] == "ok"
    assert _row("unrestricted", "dpi")[5] == "ok"


def test_view_carries_structure_from_the_list() -> None:
    k = _row("denylist", "K")
    assert k[1] == "GC" and k[2] == "fdp, sfdp" and k[3] == "double"
    assert _row("denylist", "label")[2] == "all"


def test_markdown_header_states_mode_release_and_official_link() -> None:
    text = render_markdown(build_view(build_policy("allowlist")))
    assert "**allowlist**" in text and "Graphviz 16.1.0" in text and "https://graphviz.org/doc/info/attrs.html" in text
    assert "Only attributes on the allow list are accepted" in text


def test_front_matter_parser_handles_the_page_shapes() -> None:
    gen = _gen_module()
    page = (
        "---\ndefaults:\n- default: forward\n  for: (directed)\n- default: none\n  for: (undirected)\nflags:\n- dot\n"
        "minimums: []\ntitle: dir\ntypes:\n- dirType\nused_by: E\ndescription: x\n---\nbody: ignored\n"
    )
    entry = gen.entry_from_page("dir", page)
    assert entry["default"] == "forward (directed); none (undirected)"
    assert entry["engines"] == ["dot"] and entry["applies"] == "E"
    quoted = "---\ndefaults:\n- '\"Times-Roman\"'\nflags: []\nminimums: []\ntitle: fontname\ntypes:\n- string\nused_by: ENGC\n---\n"
    assert gen.entry_from_page("fontname", quoted)["default"] == '"Times-Roman"'
    assert gen.entry_from_page("fontname", quoted)["applies"] == "GCNE"
    with pytest.raises(ValueError):
        gen.entry_from_page("x", "---\ntitle: x\nused_by: Z\n---\n")


def test_attribute_list_is_consistent_with_the_pinned_release() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_attribute_list.py"), "--check"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
