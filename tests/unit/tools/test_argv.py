from __future__ import annotations

from typing import Any

import pytest

from graphviz_mcp.tools.argv import ArgError, build_argv
from graphviz_mcp.tools.specs import PROGRAMS


class Caps:
    def valid_format(self, spec: str) -> bool:
        return spec in {"svg", "png", "png:cairo", "png:cairo:cairo", "plain"}

    def valid_engine(self, name: str) -> bool:
        return name in {"dot", "neato"}


def argv(program: str, **kw: Any) -> list[str]:
    return build_argv(PROGRAMS[program], kw, Caps())


def test_layout_flags_become_cli_flags() -> None:
    assert argv("dot", T="png", G={"rankdir": "LR", "dpi": "144"}, N={"shape": "box"}, E={"color": "red"}, A={"fontname": "x"},
                s=2, n=2, x=True, y=True, q=1, v=True, K="neato") == [
        "-Tpng", "-Kneato", "-Grankdir=LR", "-Gdpi=144", "-Nshape=box", "-Ecolor=red", "-Afontname=x",
        "-s2", "-n2", "-x", "-y", "-q1", "-v",
    ]  # fmt: skip


def test_renderer_combinations_pass_through() -> None:
    assert argv("neato", T="png:cairo") == ["-Tpng:cairo"]
    assert argv("neato", T="png:cairo:cairo") == ["-Tpng:cairo:cairo"]


def test_false_and_none_omit_flags() -> None:
    assert argv("dot", x=False, y=None) == []


@pytest.mark.parametrize(
    "bad",
    ["svg -o/etc/x", "svg\n-o/x", "png:cairo -o/x", "nope", "png:nope", "", "-oevil", "svg\x00", " svg", "svg "],
)
def test_format_injection_rejected(bad: str) -> None:
    with pytest.raises(ArgError):
        argv("dot", T=bad)


@pytest.mark.parametrize("bad", ["dot -o/x", "unknown", "", "dot\n", "-Kdot"])
def test_engine_injection_rejected(bad: str) -> None:
    with pytest.raises(ArgError):
        argv("dot", K=bad)


@pytest.mark.parametrize("bad_name", ["a=b", "a b", "", "-x", "a\nb", "a\x00", "x" * 200, "é-"[:0] + "1abc", "=x"])
def test_attribute_names_conservative(bad_name: str) -> None:
    with pytest.raises(ArgError):
        argv("dot", G={bad_name: "v"})


def test_attribute_values_may_contain_equals_and_spaces_but_not_nul() -> None:
    assert argv("dot", G={"label": "a=b c \\n d"}) == ["-Glabel=a=b c \\n d"]
    assert argv("dot", G={"label": "line1\nline2"}) == ["-Glabel=line1\nline2"]
    assert argv("dot", G={"size": 7, "center": True}) == ["-Gsize=7", "-Gcenter=true"]
    for bad in ("a\x00b", "a\x07b", "x" * 5000):
        with pytest.raises(ArgError):
            argv("dot", G={"label": bad})


def test_value_starting_with_dash_cannot_start_an_option() -> None:
    assert argv("dot", G={"label": "-o/etc/x"}) == ["-Glabel=-o/etc/x"]  # stays inside one argv element
    with pytest.raises(ArgError):
        argv("dijkstra", node="-o")


def test_type_and_range_checks() -> None:
    for kw in (
        {"s": "2"},
        {"s": 0},
        {"s": float("nan")},
        {"s": True},
        {"n": 3},
        {"q": -1},
        {"x": "yes"},
        {"G": ["a"]},
        {"Ln": 1.5},
    ):
        with pytest.raises(ArgError):
            argv("dot", **kw)
    assert argv("dot", Ln=3.0) == ["-Ln3"]


def test_unknown_parameters_rejected() -> None:
    with pytest.raises(ArgError, match="unknown parameter"):
        argv("dot", o="/etc/x")
    with pytest.raises(ArgError, match="unknown parameter"):
        argv("dot", Tt="svg")


def test_excluded_flags_are_not_parameters() -> None:
    for flag in ("o", "O", "l", "P", "c", "V"):
        with pytest.raises(ArgError, match="unknown parameter"):
            argv("dot", **{flag: "x"})


def test_separate_value_flags() -> None:
    assert argv("unflatten", f=True, l=3, c=2) == ["-f", "-l", "3", "-c", "2"]
    assert argv("cluster", C=5, c=1) == ["-C", "5", "-c", "1"]
    assert argv("mingle", T="simple", a=40.5) == ["-a", "40.5", "-T", "simple"]


def test_positional_and_repeatable() -> None:
    assert argv("dijkstra", p=True, node="a") == ["-p", "a"]
    with pytest.raises(ArgError, match="required"):
        argv("dijkstra", p=True)
    assert argv("prune", n=["a", "b"], N=["color=red"]) == ["-na", "-nb", "-Ncolor=red"]
    assert argv("prune", n=[]) == []
    with pytest.raises(ArgError):
        argv("prune", n="a")


def test_long_options() -> None:
    assert argv("edgepaint", accuracy=0.01, angle=15, random_seed=-3, color_scheme="lab", share_endpoint=True) == [
        "--accuracy=0.01", "--angle=15", "--random_seed=-3", "--color_scheme=lab", "--share_endpoint",
    ]  # fmt: skip
    assert argv("gvmap", c_opacity="7f", highlight=2, c=3) == ["-c", "3", "-c_opacity=7f", "-highlight=2"]
    with pytest.raises(ArgError):
        argv("edgepaint", color_scheme="lab --evil")


def test_gvpack_attached_and_kv() -> None:
    assert argv("gvpack", array="_c3", m=4, s="root", G={"a": "b"}) == ["-m4", "-sroot", "-Ga=b", "-array_c3"]
    with pytest.raises(ArgError):
        argv("gvpack", array="; rm -rf")


def test_gvgen_bounds_and_patterns() -> None:
    assert argv("gvgen", k=5, d=True) == ["-k5", "-d"]
    assert argv("gvgen", g="f3,4", T="3,3,1,2") == ["-gf3,4", "-T3,3,1,2"]
    for kw in ({"k": 100000}, {"c": 0}, {"g": "3x4"}, {"g": "3,4; rm"}, {"n": "a b"}, {"N": "x y"}, {"h": 99}):
        with pytest.raises(ArgError):
            argv("gvgen", **kw)


def test_empty_string_for_attached_flag_rejected() -> None:
    with pytest.raises(ArgError):
        argv("dot", T="")
    with pytest.raises(ArgError):
        argv("gml2gv", g="")
