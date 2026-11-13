from __future__ import annotations

import re

from graphviz_mcp.tools.catalog import CATALOG
from graphviz_mcp.tools.specs import LAYOUT, PROGRAMS
from graphviz_mcp.web.render import SAMPLE_DOT


def test_every_program_is_cataloged_as_exposed() -> None:
    for name in PROGRAMS:
        assert CATALOG[name].status == "exposed", name


def test_every_exposed_catalog_entry_has_a_spec_unless_deliberately_absent() -> None:
    exposed = {n for n, e in CATALOG.items() if e.status == "exposed"}
    assert exposed - set(PROGRAMS) == set(), "an exposed program has no entry in tools/specs.py"
    for e in CATALOG.values():
        assert e.status == "exposed" or e.reason, f"{e.name}: excluded entries need a reason"


def test_param_names_unique_and_wellformed() -> None:
    for prog in PROGRAMS.values():
        names = [p.name for p in prog.params]
        assert len(names) == len(set(names)), prog.name
        assert "input" not in names, f"{prog.name}: 'input' is reserved for the graph text"
        for p in prog.params:
            assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p.name), (prog.name, p.name)
            assert p.doc, (prog.name, p.name)
            if p.style in ("switch",):
                assert p.ptype == "bool"
            if p.style == "kv":
                assert p.ptype == "kv"
            if p.style == "multi":
                assert p.ptype == "strlist"
            if p.style in ("attached", "separate", "long"):
                assert p.flag and p.ptype in ("int", "float", "str"), (prog.name, p.name)
            if p.minimum is not None and p.maximum is not None:
                assert p.minimum <= p.maximum
            if p.pattern:
                re.compile(p.pattern)
            if p.ptype == "str" and p.style in ("attached", "separate", "long") and not p.choices:
                assert p.pattern or p.dynamic, f"{prog.name}.{p.name}: free-form string values need a pattern"


def test_filesystem_and_process_flags_are_never_exposed() -> None:
    for prog in PROGRAMS.values():
        assert all(p.flag != "-o" for p in prog.params), f"{prog.name}: -o writes to the server filesystem"
    for prog in LAYOUT:
        tokens = {p.token for p in prog.params}
        assert tokens.isdisjoint({"-o", "-O", "-l", "-P", "-c", "-V"}), prog.name
        assert {t for t, _ in prog.excluded} >= {"-o", "-O", "-l", "-P", "-c", "-V"}


def test_every_exclusion_has_a_reason() -> None:
    for prog in PROGRAMS.values():
        for token, reason in prog.excluded:
            assert token.startswith("-") and reason, (prog.name, token)


def test_layout_engines_share_one_parameter_set() -> None:
    sets = {tuple(p.name for p in prog.params) for prog in LAYOUT}
    assert len(sets) == 1 and {"T", "K", "G", "N", "E", "A", "s", "n", "x", "y", "q", "v"} <= set(next(iter(sets)))


def test_sample_input_is_valid_dot_for_the_forms() -> None:
    assert "digraph" in SAMPLE_DOT and PROGRAMS["dot"].input == "dot"
