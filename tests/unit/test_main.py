from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "graphviz_mcp", *args], capture_output=True, text=True, timeout=30)


def test_version_flag() -> None:
    expected = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    r = run_cli("--version")
    assert r.returncode == 0 and r.stdout.strip() == expected


def test_stdio_and_http_are_mutually_exclusive() -> None:
    r = run_cli("--stdio", "--http")
    assert r.returncode == 2 and "not allowed with" in r.stderr
