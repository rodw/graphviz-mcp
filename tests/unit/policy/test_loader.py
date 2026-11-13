from __future__ import annotations

from pathlib import Path

import pytest

from graphviz_mcp.config import Settings
from graphviz_mcp.policy import PolicyError, build_policy, load_policy


def settings(tmp_path: Path, mode: str = "denylist", file: str | None = None) -> Settings:
    p = None
    if file is not None:
        p = tmp_path / "policy.toml"
        p.write_text(file)
    return Settings(graphviz_bin=tmp_path, attr_policy=mode, attr_policy_file=p)


def test_builtin_defaults_load() -> None:
    p = build_policy("denylist")
    assert {"image", "shapefile", "imagepath", "fontpath", "stylesheet", "html:img"} <= p.deny
    assert "shape" in p.allow and "image" not in p.allow  # starter allow list never contains denied names


def test_file_overrides(tmp_path: Path) -> None:
    p = load_policy(settings(tmp_path, file='deny_add=["label"]\n[constraints.dpi]\nmax=100\n'))
    assert "label" in p.deny and p.constraints["dpi"].max == 100


@pytest.mark.parametrize(
    "content",
    [
        "not toml [",
        "unknown_key = 1",
        'deny = "image"',
        'deny = ["bad name"]',
        "[constraints.dpi]\nmin = 5\nmax = 1",
        "[constraints.dpi]\nbogus = 1",
        '[constraints.dpi]\nregex = "("',
        "[constraints.dpi]",
        '[constraints.dpi]\nmax = "x"',
        "[constraints.dpi]\nenum = []",
        "constraints = 3",
    ],
)
def test_invalid_policy_files_fail(tmp_path: Path, content: str) -> None:
    with pytest.raises(PolicyError):
        load_policy(settings(tmp_path, file=content))


def test_missing_policy_file_fails(tmp_path: Path) -> None:
    s = Settings(graphviz_bin=tmp_path, attr_policy_file=tmp_path / "nope.toml")
    with pytest.raises(PolicyError, match="cannot read"):
        load_policy(s)


def test_unrestricted_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="graphviz_mcp.policy"):
        load_policy(settings(tmp_path, "unrestricted"))
    assert "UNRESTRICTED" in caplog.text
