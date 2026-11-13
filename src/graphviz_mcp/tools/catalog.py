"""Classification of every executable Graphviz installs.

Every executable Graphviz installs is listed here; the Docker image tests fail if one is missing.
``exposed`` programs become MCP tools
when their binary exists in the installed build.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["exposed", "excluded"]


@dataclass(frozen=True)
class Entry:
    name: str
    status: Status
    group: str  # layout | processing | generator | converter | image | alias | gui | other
    reason: str


def _e(name: str, status: Status, group: str, reason: str = "") -> Entry:
    return Entry(name, status, group, reason)


_ENTRIES: tuple[Entry, ...] = (
    *(_e(n, "exposed", "layout") for n in ("dot", "neato", "fdp", "sfdp", "twopi", "circo", "osage", "patchwork")),
    *(
        _e(n, "exposed", "processing")
        for n in (
            "acyclic",
            "bcomps",
            "ccomps",
            "sccmap",
            "tred",
            "unflatten",
            "gc",
            "nop",
            "cluster",
            "dijkstra",
            "gvcolor",
            "gvpack",
            "mingle",
            "prune",
            "edgepaint",
            "gvmap",
        )
    ),
    _e("gvgen", "exposed", "generator"),
    *(_e(n, "exposed", "converter") for n in ("dot2gxl", "gxl2dot", "gml2gv", "gv2gml", "graphml2gv", "mm2gv")),
    _e("gvpr", "excluded", "processing", "deferred; can read files and run programs"),
    _e("gv2gxl", "excluded", "alias", "same binary as dot2gxl; alias names are not registered"),
    _e("gxl2gv", "excluded", "alias", "same binary as gxl2dot; alias names are not registered"),
    _e("dot_builtins", "excluded", "other", "variant of dot with built-in plugins; redundant with dot"),
    _e("dot_sandbox", "excluded", "other", "variant of dot; blocks -o but not image=/file reads, so it adds nothing"),
    _e(
        "gvmap.sh",
        "excluded",
        "other",
        "shell pipeline (sfdp | gvmap | neato); shell scripts are not exposed",
    ),
    *(
        _e(n, "excluded", "gui", "interactive GUI program")
        for n in ("smyrna", "lefty", "lneato", "dotty", "gvedit", "vimdot")
    ),
)

CATALOG: dict[str, Entry] = {e.name: e for e in _ENTRIES}
EXPOSED: tuple[str, ...] = tuple(e.name for e in _ENTRIES if e.status == "exposed")


def classify(names: set[str] | frozenset[str]) -> tuple[list[str], list[str]]:
    """Return (unclassified installed programs, exposed programs missing from the install)."""
    unclassified = sorted(n for n in names if n not in CATALOG)
    missing = sorted(n for n in EXPOSED if n not in names)
    return unclassified, missing
