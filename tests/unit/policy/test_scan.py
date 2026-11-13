from __future__ import annotations


def test_scan_canonical_handles_bare_names_html_and_depth() -> None:
    """Hand-written text (no Graphviz needed): the tokenizer must survive anything and fail closed."""
    from graphviz_mcp.policy import scan_canonical

    scan = scan_canonical('digraph { a [image, color=red, label=<<IMG SRC="x"/>>]; b [<x>]; subgraph { size="1,1" } }')
    names = [(u.name, u.value, u.depth) for u in scan.uses]
    assert ("image", "", 1) in names and ("color", "red", 1) in names
    assert scan.html_img >= 1
    assert scan.values("size") == ["1,1"] and scan.values("size", root_only=True) == []
    top = scan_canonical('graph { size="2,2"; <<IMG SRC="y"/>> = z }')
    assert top.values("size", root_only=True) == ["2,2"] and top.html_img == 1
