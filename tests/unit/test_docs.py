from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tool_reference_is_generated_from_the_table_and_fresh() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_tool_docs.py"), "--check"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr


def test_every_program_is_documented() -> None:
    from graphviz_mcp.tools.specs import PROGRAMS

    text = (ROOT / "docs" / "graphviz-tools.md").read_text()
    for name in PROGRAMS:
        assert f"### `{name}`" in text
    assert "### `validate_dot`" in text and "### `get_capabilities`" in text
