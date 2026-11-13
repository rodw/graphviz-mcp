from __future__ import annotations

import pytest

from graphviz_mcp.dotsplit import DotLexError, merge_concatenation, split_graphs, tokenize


def kinds(text: str) -> list[tuple[str, str]]:
    return [(t.kind, t.value) for t in merge_concatenation(tokenize(text))]


def test_basic_statement() -> None:
    assert kinds('digraph G { a -> b [label="x"]; }') == [
        ("id", "digraph"), ("id", "G"), ("op", "{"), ("id", "a"), ("op", "->"), ("id", "b"),
        ("op", "["), ("id", "label"), ("op", "="), ("str", "x"), ("op", "]"), ("op", ";"), ("op", "}"),
    ]  # fmt: skip


def test_quoted_escapes_and_continuation() -> None:
    assert kinds(
        r'"a\"b" "c\\d" "line\
joined"'
    ) == [("str", 'a"b'), ("str", r"c\\d"), ("str", "linejoined")]


def test_string_concatenation() -> None:
    assert kinds('"ima" + "ge" = "x"') == [("str", "image"), ("op", "="), ("str", "x")]


def test_html_nesting() -> None:
    toks = kinds("label=<<TABLE><TR><TD>a &gt; b</TD></TR></TABLE>>;")
    assert toks[2] == ("html", "<TABLE><TR><TD>a &gt; b</TD></TR></TABLE>")


def test_comments_and_preprocessor_lines() -> None:
    src = '# preprocessor "line\n// c1 "x"\n/* c2 \n "y" */ a /* inline */ b'
    assert kinds(src) == [("id", "a"), ("id", "b")]


def test_hash_only_a_comment_at_line_start() -> None:
    # '#' is only a comment marker at the start of a line; elsewhere it is a stray operator
    assert kinds("a [color=#ff0000]; x") == [
        ("id", "a"), ("op", "["), ("id", "color"), ("op", "="), ("op", "#"), ("id", "ff0000"), ("op", "]"),
        ("op", ";"), ("id", "x"),
    ]  # fmt: skip


def test_numerals_and_edge_ops() -> None:
    assert kinds("a -- b -1 .5 3.") == [
        ("id", "a"), ("op", "--"), ("id", "b"), ("id", "-1"), ("id", ".5"), ("id", "3."),
    ]  # fmt: skip


def test_unicode_ids_and_ports() -> None:
    assert kinds("é:p:n") == [("id", "é"), ("op", ":"), ("id", "p"), ("op", ":"), ("id", "n")]


@pytest.mark.parametrize("bad", ['"open', "<a<b>", "/* open"])
def test_unterminated(bad: str) -> None:
    with pytest.raises(DotLexError):
        tokenize(bad)


def test_split_graphs() -> None:
    text = 'digraph a { x -> y }\n\nstrict graph "b c" { subgraph s { q } r }\ndigraph { "}" }'
    parts = split_graphs(text)
    assert parts == ["digraph a { x -> y }", 'strict graph "b c" { subgraph s { q } r }', 'digraph { "}" }']


def test_split_ignores_braces_in_strings_html_comments() -> None:
    text = 'digraph { a [label="}{"]; b [label=<{x}>]; /* } */ // }\n}'
    assert split_graphs(text) == [text]
