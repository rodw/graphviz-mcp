"""A small, forgiving DOT tokenizer and a "split concatenated graphs" helper.

Not a validating parser: syntax errors are Graphviz's job (``nop -p``). This module only has to
tokenize the *regular* output of ``nop`` (and, for graph splitting, Graphviz tools' output) in
exactly the way Graphviz's own lexer would, so no attribute can hide from the policy scan.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

Kind = Literal["id", "str", "html", "op"]

_ID_RE = re.compile(r"[A-Za-z_\x80-\U0010ffff][A-Za-z_0-9\x80-\U0010ffff]*")
_NUM_RE = re.compile(r"-?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)")
_KEYWORDS = {"strict", "graph", "digraph", "subgraph", "node", "edge"}


@dataclass(frozen=True)
class Token:
    kind: Kind
    value: str
    start: int
    end: int

    @property
    def keyword(self) -> str | None:
        if self.kind == "id" and self.value.lower() in _KEYWORDS:
            return self.value.lower()
        return None

    def is_op(self, op: str) -> bool:
        return self.kind == "op" and self.value == op


class DotLexError(ValueError):
    pass


def _skip_html(text: str, i: int) -> int:
    """Return the index just past the HTML string starting at ``text[i] == '<'`` (angle-bracket nesting)."""
    depth = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "<":
            depth += 1
        elif c == ">":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise DotLexError("unterminated HTML string")


def _read_quoted(text: str, i: int) -> tuple[str, int]:
    out: list[str] = []
    n = len(text)
    i += 1
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == '"':
                out.append('"')
                i += 2
                continue
            if nxt == "\n":
                i += 2
                continue
            if nxt == "\r" and text[i + 2 : i + 3] == "\n":
                i += 3
                continue
            out.append(c + nxt)
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise DotLexError("unterminated string")


def tokenize(text: str) -> list[Token]:
    return list(iter_tokens(text))


def iter_tokens(text: str) -> Iterator[Token]:
    i, n = 0, len(text)
    line_start = True
    while i < n:
        c = text[i]
        if c == "\n":
            line_start = True
            i += 1
            continue
        if c in " \t\r\f\v﻿":
            i += 1
            continue
        if c == "#" and line_start:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        line_start = False
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise DotLexError("unterminated comment")
            i = j + 2
            continue
        start = i
        if c == '"':
            value, i = _read_quoted(text, i)
            yield Token("str", value, start, i)
        elif c == "<":
            i = _skip_html(text, i)
            yield Token("html", text[start + 1 : i - 1], start, i)
        elif c == "-" and text[i + 1 : i + 2] in (">", "-"):
            i += 2
            yield Token("op", text[start:i], start, i)
        elif (m := _NUM_RE.match(text, i)) and (c.isdigit() or c in "-."):
            i = m.end()
            yield Token("id", m.group(), start, i)
        elif m := _ID_RE.match(text, i):
            i = m.end()
            yield Token("id", m.group(), start, i)
        else:
            i += 1
            yield Token("op", c, start, i)


def merge_concatenation(tokens: list[Token]) -> list[Token]:
    """Collapse ``"a" + "b"`` into one string token (DOT allows this for any ID position)."""
    out: list[Token] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.kind == "str":
            value, end = t.value, t.end
            while i + 2 < len(tokens) and tokens[i + 1].is_op("+") and tokens[i + 2].kind == "str":
                value += tokens[i + 2].value
                end = tokens[i + 2].end
                i += 2
            out.append(Token("str", value, t.start, end))
        else:
            out.append(t)
        i += 1
    return out


def split_graphs(text: str) -> list[str]:
    """Split a stream holding several graphs into one source string per top-level graph."""
    tokens = tokenize(text)
    graphs: list[str] = []
    depth = 0
    start: int | None = None
    for t in tokens:
        if depth == 0 and start is None and t.keyword in ("strict", "graph", "digraph"):
            start = t.start
        if t.is_op("{"):
            depth += 1
        elif t.is_op("}"):
            depth -= 1
            if depth == 0 and start is not None:
                graphs.append(text[start : t.end])
                start = None
    return graphs
