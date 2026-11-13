#!/usr/bin/env python3
"""Refresh the generated Python dependency table inside THIRD_PARTY_NOTICES.md.

python scripts/gen_notices.py          # rewrite the section between the markers
python scripts/gen_notices.py --check  # exit 1 if it is stale
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_licenses  # noqa: E402

BEGIN, END = "<!-- BEGIN PYTHON DEPENDENCIES -->", "<!-- END PYTHON DEPENDENCIES -->"


def table() -> str:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--from=mixed", "--format=json", "--with-urls"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    rows = {r["Name"].lower().replace("_", "-"): r for r in json.loads(out)}
    lines = ["| Package | Version | License | Home page |", "|---|---|---|---|"]
    for name in sorted(check_licenses.runtime_closure()):
        r = rows.get(name)
        if r:
            lines.append(f"| {r['Name']} | {r['Version']} | {r['License']} | {r['URL']} |")
    return "\n".join(lines)


def main() -> int:
    path = ROOT / "THIRD_PARTY_NOTICES.md"
    text = path.read_text()
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    new = f"{head}{BEGIN}\n{table()}\n{END}{tail}"
    if "--check" in sys.argv:
        return 0 if new == text else 1
    path.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
