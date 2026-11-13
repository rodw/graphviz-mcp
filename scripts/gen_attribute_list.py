#!/usr/bin/env python3
"""Generate src/graphviz_mcp/data/attribute-list.toml, the master list of Graphviz attributes.

The list holds structured facts only (name, applies-to, engines, type, default, minimum). Upstream prose is not
copied: descriptions come from our own overlay, data/attribute-descriptions.toml.

Source: the Graphviz website repo (gitlab.com/graphviz/graphviz.gitlab.io), content/en/docs/attrs/*.md, read at the
pinned commit below. Graphviz has no command that lists its attributes, and the schema/attributes.xml shipped with
the install is stale (it lacks penwidth, newrank, xlabel, ...), so a pinned snapshot is the reference.

Usage:
    python scripts/gen_attribute_list.py            # fetch at the pinned commit and (re)write the list
    python scripts/gen_attribute_list.py --source DIR   # read the *.md files from a local directory instead
    python scripts/gen_attribute_list.py --check    # offline: fail if the list, this script and the Dockerfile disagree,
                                                    # or an attribute has no description (a stale description only warns)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "graphviz_mcp" / "data"
OUTPUT = DATA / "attribute-list.toml"
DESCRIPTIONS = DATA / "attribute-descriptions.toml"

# Bump these together with GV_VERSION in the Dockerfile (audit.attribute-list enforces the release).
GRAPHVIZ_RELEASE = "16.1.0"
SOURCE_SHA = "aad25bebc73f1f25fa7f853a564f9efadcbfbd62"  # website commit just before the 16.1.0 release (2026-09-03)

_PROJECT = "graphviz%2Fgraphviz.gitlab.io"
_PATH = "content/en/docs/attrs"
_TREE = f"https://gitlab.com/api/v4/projects/{_PROJECT}/repository/tree"
_RAW = f"https://gitlab.com/graphviz/graphviz.gitlab.io/-/raw/{SOURCE_SHA}/{_PATH}/"

ENGINES = ("circo", "dot", "fdp", "neato", "osage", "patchwork", "sfdp", "twopi")
APPLIES_ORDER = "GCSNE"
_KEY = re.compile(r"^([A-Za-z_]+):(?: (.*))?$")


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        inner = text[1:-1]
        return inner.replace("''", "'") if text[0] == "'" else json.loads(text)
    return text


def parse_front_matter(text: str) -> dict[str, object]:
    """Parse the small YAML subset used in the attribute pages; raise ValueError on anything else."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing front matter")
    end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), None)
    if end is None:
        raise ValueError("unterminated front matter")
    data: dict[str, object] = {}
    key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if m := _KEY.match(line):
            key, value = m.group(1), m.group(2)
            if value is None:
                data[key] = []
            elif value.strip() == "[]":
                data[key] = []
            else:
                data[key] = _scalar(value)
            continue
        if key is None or not isinstance(data.get(key), list):
            raise ValueError(f"unexpected line: {line!r}")
        items: list[object] = data[key]  # type: ignore[assignment]
        if line.startswith("- "):
            body = line[2:]
            if m := _KEY.match(body):
                items.append({m.group(1): _scalar(m.group(2) or "")})
            else:
                items.append(_scalar(body))
        elif line.startswith("  ") and items and isinstance(items[-1], dict) and (m := _KEY.match(line.strip())):
            items[-1][m.group(1)] = _scalar(m.group(2) or "")
        else:
            raise ValueError(f"unexpected line: {line!r}")
    return data


def _join(values: list[object]) -> str:
    parts = []
    for v in values:
        if isinstance(v, dict):
            value = str(v.get("default", v.get("minimum", "")))
            parts.append(f"{value} {v['for']}" if v.get("for") else value)
        else:
            parts.append(str(v))
    return "; ".join(parts)


def entry_from_page(stem: str, text: str) -> dict[str, object]:
    """Build one list entry; the attribute name is the page title (background.md documents ``_background``)."""
    fm = parse_front_matter(text)
    name = str(fm.get("title", ""))
    if name.lstrip("_") != stem:
        raise ValueError(f"{stem}: title {name!r} does not match the file name")
    used_by = str(fm.get("used_by", ""))
    if not used_by or set(used_by) - set(APPLIES_ORDER):
        raise ValueError(f"{name}: unexpected used_by {used_by!r}")
    flags = [str(f) for f in fm.get("flags", [])]  # type: ignore[attr-defined]
    return {
        "name": name,
        "applies": "".join(c for c in APPLIES_ORDER if c in used_by),
        "type": ", ".join(str(t) for t in fm.get("types", [])),  # type: ignore[attr-defined]
        "default": _join(fm.get("defaults", [])),  # type: ignore[arg-type]
        "minimum": _join(fm.get("minimums", [])),  # type: ignore[arg-type]
        "engines": [f for f in flags if f in ENGINES],
        "flags": [f for f in flags if f not in ENGINES],
    }


def fetch_pages() -> dict[str, str]:
    names: list[str] = []
    for page in range(1, 10):
        query = urllib.parse.urlencode({"path": _PATH, "ref": SOURCE_SHA, "per_page": 100, "page": page})
        with urllib.request.urlopen(f"{_TREE}?{query}", timeout=30) as resp:
            batch = json.load(resp)
        if not batch:
            break
        names += [e["name"] for e in batch if e["name"].endswith(".md") and e["name"] != "_index.md"]
    pages = {}
    for n in sorted(names):
        with urllib.request.urlopen(_RAW + urllib.parse.quote(n), timeout=30) as resp:
            pages[n[:-3]] = resp.read().decode("utf-8")
    return pages


def local_pages(directory: Path) -> dict[str, str]:
    return {p.stem: p.read_text("utf-8") for p in sorted(directory.glob("*.md")) if p.name != "_index.md"}


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def render(entries: list[dict[str, object]]) -> str:
    out = [
        "# Master list of Graphviz attributes",
        "# GENERATED by scripts/gen_attribute_list.py (make update.attribute-list). Do not edit.",
        f"# Source: graphviz.gitlab.io {_PATH} at {SOURCE_SHA}.",
        "",
        f"graphviz_release = {_q(GRAPHVIZ_RELEASE)}",
        f"source_sha = {_q(SOURCE_SHA)}",
        "",
    ]
    for e in sorted(entries, key=lambda e: str(e["name"]).lower() + str(e["name"])):
        out.append("[[attribute]]")
        for field in ("name", "applies", "type", "default", "minimum"):
            out.append(f"{field} = {_q(str(e[field]))}")
        for field in ("engines", "flags"):
            out.append(f"{field} = [{', '.join(_q(v) for v in e[field])}]")  # type: ignore[attr-defined]
        out.append("")
    return "\n".join(out)


def compare_descriptions(listed: list[str], described: list[str]) -> tuple[list[str], list[str]]:
    """Return (attributes with no description, descriptions for attributes not in the list)."""
    return sorted(set(listed) - set(described)), sorted(set(described) - set(listed))


def check() -> int:
    failures = []
    data = tomllib.loads(OUTPUT.read_text("utf-8"))
    if data.get("graphviz_release") != GRAPHVIZ_RELEASE:
        failures.append(
            f"{OUTPUT.name}: graphviz_release {data.get('graphviz_release')!r} != script {GRAPHVIZ_RELEASE!r}"
        )
    if data.get("source_sha") != SOURCE_SHA:
        failures.append(f"{OUTPUT.name}: source_sha differs from this script's SOURCE_SHA; regenerate the list")
    m = re.search(r"^ARG GV_VERSION=(\S+)", (ROOT / "Dockerfile").read_text(), re.M)
    if not m or m.group(1) != GRAPHVIZ_RELEASE:
        failures.append(
            f"Dockerfile GV_VERSION {m.group(1) if m else None!r} != attribute list release {GRAPHVIZ_RELEASE!r}"
        )
    if not data.get("attribute"):
        failures.append(f"{OUTPUT.name}: no attributes")
    described = list(tomllib.loads(DESCRIPTIONS.read_text("utf-8"))["description"])
    missing, legacy = compare_descriptions([e["name"] for e in data.get("attribute", [])], described)
    for name in missing:
        failures.append(f"{DESCRIPTIONS.name}: no description for attribute {name!r}")
    for name in legacy:  # a warning only: e.g. an attribute dropped from a newer Graphviz release
        print(f"WARNING {DESCRIPTIONS.name}: description for {name!r}, which is not in {OUTPUT.name}", file=sys.stderr)
    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    if not failures:
        print(f"attribute list: {len(data['attribute'])} attributes, Graphviz {GRAPHVIZ_RELEASE}, consistent")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="read the attribute *.md files from this directory")
    parser.add_argument("--check", action="store_true", help="offline consistency check; writes nothing")
    args = parser.parse_args()
    if args.check:
        return check()
    pages = local_pages(args.source) if args.source else fetch_pages()
    entries = [entry_from_page(stem, text) for stem, text in pages.items()]
    OUTPUT.write_text(render(entries), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(entries)} attributes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
