#!/usr/bin/env python3
"""Fail if any installed runtime dependency has a non-permissive license.

Usage: python scripts/check_licenses.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib import metadata

from packaging.requirements import Requirement

ALLOWED = re.compile(
    r"\b(MIT|MIT-0|BSD|BSD-2-Clause|BSD-3-Clause|Apache|Apache-2\.0|ISC|PSF|Python Software Foundation|"
    r"Unlicense|0BSD|CC0|HPND|Zlib)\b",
    re.I,
)
FORBIDDEN = re.compile(r"\b(GPL|AGPL|LGPL|GNU|MPL|EPL|CDDL|SSPL)\b", re.I)


def runtime_closure(root: str = "graphviz-mcp") -> set[str]:
    seen: set[str] = set()
    todo = [root]
    while todo:
        name = todo.pop().lower().replace("_", "-")
        if name in seen:
            continue
        seen.add(name)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                continue
            todo.append(req.name)
    seen.discard(root)
    return seen


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--from=mixed", "--format=json", "--with-system"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    table = {r["Name"].lower().replace("_", "-"): r["License"] for r in json.loads(out)}
    bad = 0
    names = runtime_closure()
    for name in sorted(names):
        lic = table.get(name, "UNKNOWN")
        if FORBIDDEN.search(lic) or not ALLOWED.search(lic):
            print(f"FAIL {name}: {lic}", file=sys.stderr)
            bad += 1
    print(f"checked {len(names)} runtime packages, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
