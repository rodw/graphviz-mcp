"""The hardened `docker run` limits must agree everywhere they appear, and leave room for the server's own defaults.

`GVMCP_MEMORY_MB` is a per-process address-space cap; the container's `--memory` is the ceiling for everything in it,
including the RAM-backed /tmp. If `--memory` is not above the cap plus that overhead, the kernel OOM-kills a runaway
call before the cap can fail it cleanly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from graphviz_mcp.config import Settings
from tests.support.docker_image_ctl import HARDENING

ROOT = Path(__file__).resolve().parents[2]
TMPFS_MB = 256  # the /tmp:...size=256m tmpfs in every hardened command
HEADROOM_MB = 256  # the server's own use (about 150 MB) plus a margin
DOCS = ("README.md", "SECURITY.md", "docs/attribute-security-policy.md")
LAUNCH_TARGETS = ("run-http", "run-stdio", "start")


def megabytes(size: str) -> int:
    m = re.fullmatch(r"(\d+)([mg])", size.lower())
    assert m, f"unrecognised size {size!r}"
    return int(m.group(1)) * (1024 if m.group(2) == "g" else 1)


def flag_values(text: str, flag: str) -> list[str]:
    """Every value given to `--flag value` or `--flag=value` (also the quoted JSON form `"--flag=value"`)."""
    return re.findall(rf"--{flag}(?:[ =]|\", \")(\w+)", text) + re.findall(rf"--{flag}[ =](\w+)", text)


def harness_value(flag: str) -> str:
    return HARDENING[HARDENING.index(f"--{flag}") + 1]


def make_default(name: str) -> str:
    m = re.search(rf"^{name} \?= (\w+)\s*$", (ROOT / "Makefile").read_text(), re.M)
    assert m, f"{name} default not found in the Makefile"
    return m.group(1)


def sources(flag: str, makefile_name: str) -> dict[str, set[str]]:
    found = {doc: set(flag_values((ROOT / doc).read_text(), flag)) for doc in DOCS}
    found["tests/support/docker_image_ctl.py"] = {harness_value(flag)}
    found["Makefile"] = {make_default(makefile_name)}
    return found


@pytest.mark.parametrize(("flag", "var"), [("memory", "SERVICE_MEMORY"), ("pids-limit", "SERVICE_PIDS_LIMIT")])
def test_each_limit_has_one_value_everywhere(flag: str, var: str) -> None:
    found = sources(flag, var)
    assert all(found.values()), f"--{flag} missing from: {[k for k, v in found.items() if not v]}"
    assert len(set().union(*found.values())) == 1, found


def test_swap_equals_memory_wherever_it_is_given() -> None:
    memory = make_default("SERVICE_MEMORY")
    assert harness_value("memory-swap") == memory
    for doc in DOCS:
        swaps = set(flag_values((ROOT / doc).read_text(), "memory-swap"))
        assert swaps <= {memory}, (doc, swaps)
    assert re.search(r"^SERVICE_MEMORY_SWAP \?= \$\(SERVICE_MEMORY\)\s*$", (ROOT / "Makefile").read_text(), re.M)


def test_the_container_memory_limit_leaves_room_for_the_default_per_process_cap() -> None:
    floor = Settings(graphviz_bin=Path("/nonexistent")).memory_mb + TMPFS_MB + HEADROOM_MB
    assert megabytes(make_default("SERVICE_MEMORY")) >= floor, f"--memory must be at least {floor} MB"


@pytest.mark.parametrize("target", LAUNCH_TARGETS)
def test_every_make_launch_path_applies_the_limits(target: str) -> None:
    text = (ROOT / "Makefile").read_text()
    m = re.search(rf"^{re.escape(target)}:.*?(?=^\S)", text, re.M | re.S)
    assert m, f"target {target} not found"
    assert "$(SERVICE_RESOURCE_ARGS)" in m.group(0)
