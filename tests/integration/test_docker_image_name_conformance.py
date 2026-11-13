"""Tool and parameter names must match the real programs' flags, checked against the Docker image.

The usage text of every Graphviz program is read live from the image (`<program> -?`), so there is no snapshot to go
stale. Any flag Graphviz prints that is neither in the table nor in the explicit exclusion list fails the test, which
forces a decision whenever the pinned Graphviz is upgraded.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from graphviz_mcp.tools.specs import PROGRAMS, Program
from tests.support.docker_image_ctl import Container

pytestmark = pytest.mark.docker_image
_IMPLICIT = ("-?",)  # every program prints its usage with -?

# Runs inside the container: `./name -?` from the bin directory, so usage texts do not embed an install path.
_COLLECT = """
import json, os, subprocess
b = "/opt/graphviz/bin"
out = {}
for n in sorted(os.listdir(b)):
    p = os.path.join(b, n)
    if n == "gvmap.sh" or not os.path.isfile(p) or not os.access(p, os.X_OK):
        continue
    r = subprocess.run(["./" + n, "-?"], cwd=b, capture_output=True, input=b"", timeout=20, check=False)
    out[n] = (r.stdout + r.stderr).decode("utf-8", "replace")
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def usage(docker_image_server: Container) -> dict[str, str]:
    r = docker_image_server.exec("python3", ["-c", _COLLECT])
    assert r.returncode == 0, r.stderr.decode()[:300]
    texts: dict[str, str] = json.loads(r.stdout)
    assert texts, "no Graphviz programs found in the image"
    return texts


def usage_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*(-[^\s,:]+)", text))


def known_prefixes(prog: Program) -> set[str]:
    out = {p.token for p in prog.params if p.token.startswith("-")}
    out |= {t for t, _ in prog.excluded}
    out |= set(_IMPLICIT)
    return out


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_flags_in_usage_are_all_decided(usage: dict[str, str], name: str) -> None:
    if name not in usage:
        pytest.skip(f"{name} is absent from the pinned build")
    tokens = usage_tokens(usage[name])
    assert tokens, f"no flags parsed from the {name} usage text"
    prefixes = known_prefixes(PROGRAMS[name])
    undecided = sorted(t for t in tokens if not any(t.startswith(p) for p in prefixes))
    assert not undecided, f"{name}: flags in usage neither exposed nor excluded: {undecided}"


@pytest.mark.parametrize("name", list(PROGRAMS))
def test_table_flags_exist_in_usage(usage: dict[str, str], name: str) -> None:
    if name not in usage:
        pytest.skip(f"{name} is absent from the pinned build")
    tokens = usage_tokens(usage[name])
    ghosts = sorted(
        p for p in known_prefixes(PROGRAMS[name]) if p not in _IMPLICIT and not any(t.startswith(p) for t in tokens)
    )
    assert not ghosts, f"{name}: table lists flags the program does not print: {ghosts}"


def test_layout_engine_usage_is_identical_across_engines(usage: dict[str, str]) -> None:
    texts: dict[str, Any] = {
        n: usage[n].replace(f"./{n}", "PROG")
        for n in ("dot", "neato", "fdp", "sfdp", "twopi", "circo", "osage", "patchwork")
    }
    assert len(set(texts.values())) == 1
