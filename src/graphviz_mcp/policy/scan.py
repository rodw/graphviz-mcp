"""Extract the effective attribute set from DOT text.

The text given to :func:`scan_canonical` is the output of ``nop`` (Graphviz's own parser re-emitting
the graph), so quoting, string concatenation (``"ima"+"ge"``) and statement forms are already
normalized. The tokenizer is written to survive any DOT, so a mismatch fails closed.
The *original* text, never the canonical one, is what the layout engine later receives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..dotsplit import Token, merge_concatenation, tokenize

_IMG = re.compile(r"<\s*img\b", re.IGNORECASE)
_VALUE_KINDS = ("id", "str", "html")


@dataclass(frozen=True)
class AttrUse:
    name: str
    value: str
    depth: int  # 1 = body of the root graph (or a parameter); >1 = inside a subgraph
    source: str = "dot"  # "dot" or "param:G" / "param:N" / ...


@dataclass
class Scan:
    uses: list[AttrUse] = field(default_factory=list)
    html_img: int = 0

    def values(self, name: str, *, root_only: bool = False) -> list[str]:
        lowered = name.lower()
        return [u.value for u in self.uses if u.name.lower() == lowered and (u.depth <= 1 or not root_only)]


def scan_canonical(text: str) -> Scan:
    tokens = merge_concatenation(tokenize(text))
    scan = Scan()
    depth = 0
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if t.kind == "html" and _IMG.search("<" + t.value + ">"):
            scan.html_img += 1
        if t.is_op("{"):
            depth += 1
        elif t.is_op("}"):
            depth = max(0, depth - 1)
        elif t.is_op("["):
            i = _attr_list(tokens, i + 1, depth, scan)
            continue
        elif t.kind in ("id", "str") and i + 2 < n and tokens[i + 1].is_op("=") and tokens[i + 2].kind in _VALUE_KINDS:
            scan.uses.append(AttrUse(t.value, tokens[i + 2].value, max(depth, 1)))
            if tokens[i + 2].kind == "html" and _IMG.search("<" + tokens[i + 2].value + ">"):
                scan.html_img += 1
            i += 3
            continue
        i += 1
    return scan


def _attr_list(tokens: list[Token], i: int, depth: int, scan: Scan) -> int:
    """Parse ``name=value`` pairs until the closing ``]``; returns the index after it."""
    n = len(tokens)
    while i < n and not tokens[i].is_op("]"):
        t = tokens[i]
        if t.kind in ("id", "str"):
            if i + 2 < n and tokens[i + 1].is_op("=") and tokens[i + 2].kind in _VALUE_KINDS:
                v = tokens[i + 2]
                scan.uses.append(AttrUse(t.value, v.value, max(depth, 1)))
                if v.kind == "html" and _IMG.search("<" + v.value + ">"):
                    scan.html_img += 1
                i += 3
                continue
            # a bare name is not valid DOT; record it anyway so a deny rule cannot be dodged by it
            scan.uses.append(AttrUse(t.value, "", max(depth, 1)))
        elif t.kind == "html" and _IMG.search("<" + t.value + ">"):
            scan.html_img += 1
        i += 1
    return i + 1
