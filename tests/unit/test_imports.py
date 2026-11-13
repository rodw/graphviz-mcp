"""Every module must import on its own, whatever else was imported first (no import cycles)."""

from __future__ import annotations

import subprocess
import sys

import pytest

MODULES = [
    "graphviz_mcp.meta",
    "graphviz_mcp.app",
    "graphviz_mcp.extras",
    "graphviz_mcp.http_ops",
    "graphviz_mcp.web.routes",
    "graphviz_mcp.web.render",
    "graphviz_mcp.server",
]


def run_python(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_in_a_fresh_interpreter(module: str) -> None:
    r = run_python(f"import {module}")
    assert r.returncode == 0, r.stderr


def test_meta_is_a_leaf() -> None:
    r = run_python(
        "import sys, graphviz_mcp.meta\n"
        "bad = [m for m in ('uvicorn', 'mcp', 'graphviz_mcp.server') if m in sys.modules]\n"
        "sys.exit(1 if bad else 0)"
    )
    assert r.returncode == 0
