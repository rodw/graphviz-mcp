#!/usr/bin/env python3
"""Write docs/graphviz-tools.md from the flag table in tools/specs.py.

python scripts/gen_tool_docs.py          # rewrite docs/graphviz-tools.md
python scripts/gen_tool_docs.py --check  # exit 1 if the file is stale
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from graphviz_mcp.tools import catalog  # noqa: E402
from graphviz_mcp.tools.specs import PROGRAMS, Param, Program  # noqa: E402

TITLES = {
    "layout": "Layout and rendering",
    "processing": "Graph processing and analysis",
    "generator": "Generators",
    "converter": "Converters",
}
INPUTS = {
    "dot": "`input`: the graph in DOT language",
    "text": "`input`: the graph in the converter's source format",
    "file": "`input`: the file contents (written to a temporary file for the program)",
    "none": "none (the parameters select what is generated)",
}
OUTPUTS = {
    "format": "the rendering in format `T`: text, MCP image content or an embedded blob, by MIME type",
    "graphs": "DOT text; programs that emit several graphs return one string per graph",
    "text": "text",
}


def kind(p: Param) -> str:
    base = {
        "bool": "boolean",
        "int": "integer",
        "float": "number",
        "str": "string",
        "kv": "object",
        "strlist": "list of strings",
    }[p.ptype]
    extras = []
    if p.choices:
        extras.append("one of " + ", ".join(f"`{c}`" for c in p.choices))
    if p.minimum is not None or p.maximum is not None:
        lo = "" if p.minimum is None else f"{p.minimum:g}"
        hi = "" if p.maximum is None else f"{p.maximum:g}"
        extras.append(f"{lo}..{hi}")
    if p.pattern and not p.dynamic:
        extras.append(f"pattern `{p.pattern}`")
    if p.required:
        extras.append("required")
    if p.default is not None:
        extras.append(f"default `{p.default}`")
    return base + (f" ({'; '.join(extras)})" if extras else "")


def program_section(prog: Program) -> str:
    out = [f"### `{prog.name}`", "", prog.summary, ""]
    out.append(f"* Input: {INPUTS[prog.input]}")
    out.append(f"* Output: {OUTPUTS[prog.output]}")
    if prog.ok_returncodes != (0,):
        out.append(f"* Exit statuses treated as success: {', '.join(map(str, prog.ok_returncodes))}")
    out.append("")
    if prog.params:
        out += ["| Parameter | Flag | Type | Meaning |", "|---|---|---|---|"]
        for p in prog.params:
            out.append(f"| `{p.name}` | `{p.cli}` | {kind(p)} | {p.doc.replace('|', chr(92) + '|')} |")
        out.append("")
    if prog.excluded:
        out.append("Flags not exposed: " + "; ".join(f"`{t}` ({r})" for t, r in prog.excluded) + ".")
        out.append("")
    return "\n".join(out)


def build() -> str:
    lines = [
        "# Tool reference",
        "",
        "Generated from `src/graphviz_mcp/tools/specs.py` by `scripts/gen_tool_docs.py`; do not edit by hand.",
        "",
        "Every tool is named after a Graphviz program, and its parameters are named after the program's flags "
        "(the flag letter is the parameter name; long options keep their name). `G`, `N`, `E` and `A` are objects: "
        '`G: {"rankdir": "LR"}` is `-Grankdir=LR`. Tools whose binary is missing from the installed Graphviz build '
        "are not registered; `get_capabilities` lists what is available. Attribute names and values are subject to the "
        "[attribute policy](attribute-policy.md).",
        "",
    ]
    for key, title in TITLES.items():
        members = [p for p in PROGRAMS.values() if p.group == key]
        if not members:
            continue
        lines += [f"## {title}", ""]
        lines += [program_section(p) for p in members]
    lines += [
        "## MCP extensions",
        "",
        "These have no Graphviz counterpart and are named distinctly.",
        "",
        "### `validate_dot`",
        "",
        "Checks DOT syntax without laying the graph out (it runs `nop -p`; Graphviz has no `null` output format). "
        "Returns `{valid, errors[{line, message, near}], warnings[], policy_ok, policy_violation}`. Graphviz reports the "
        "line of a syntax error but no column.",
        "",
        "### `get_capabilities`",
        "",
        "Graphviz version, layout engines, output formats with MIME types and renderer combinations, available tools, "
        "fonts, limits and the active attribute policy. The same document is the resource `graphviz://capabilities`.",
        "",
        "## Resources and prompts",
        "",
        "* `graphviz://capabilities`, `graphviz://attributes` (curated attribute reference), `graphviz://dot-language`.",
        "* Prompts: `visualize_data_as_graph`, `explain_dot`, `fix_dot`.",
        "",
        "## Program catalog",
        "",
        "Every executable in the Graphviz bin directory is classified; the Docker image test fails on an unclassified one.",
        "",
        "| Program | Status | Reason |",
        "|---|---|---|",
    ]
    for e in sorted(catalog.CATALOG.values(), key=lambda e: (e.status, e.name)):
        lines.append(f"| `{e.name}` | {e.status} | {e.reason or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    target = ROOT / "docs" / "graphviz-tools.md"
    text = build()
    if "--check" in sys.argv:
        if not target.exists() or target.read_text() != text:
            print("docs/graphviz-tools.md is stale: run python scripts/gen_tool_docs.py", file=sys.stderr)
            return 1
        return 0
    target.write_text(text)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
