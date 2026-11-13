from __future__ import annotations

import pytest

from graphviz_mcp.policy import AttrUse, PolicyViolation, build_policy
from graphviz_mcp.policy.engine import PolicyEngine


def test_denylist_classification() -> None:
    cfg = build_policy("denylist")
    assert cfg.classify("image").state == "denied"
    assert cfg.classify("totally_unknown_attr").state == "ok"
    capped = cfg.classify("dpi")
    assert capped.state == "ok" and capped.constraint is not None and capped.constraint.max == 300


def test_allowlist_classification() -> None:
    cfg = build_policy("allowlist")
    assert cfg.classify("shape").state == "ok"
    assert cfg.classify("lhead").state == "ok"
    assert cfg.classify("totally_unknown_attr").state == "not_allowed"
    assert cfg.classify("image").state == "not_allowed"


def test_unrestricted_classification_has_no_constraints() -> None:
    cfg = build_policy("unrestricted")
    assert cfg.classify("image").state == "ok"
    assert cfg.classify("dpi").constraint is None


def test_names_match_case_insensitively_like_enforcement() -> None:
    cfg = build_policy("denylist")
    assert cfg.classify("IMAGE").state == "denied"
    assert build_policy("allowlist").classify("K").state == "ok"  # Graphviz's K is stored as the key "k"


@pytest.mark.parametrize("mode", ["denylist", "allowlist"])
def test_evaluate_agrees_with_classify(mode: str) -> None:
    cfg = build_policy(mode)
    engine = PolicyEngine(cfg, runner=None, max_pixels=50_000_000, preflight=True)  # type: ignore[arg-type]
    for name in ("image", "shape", "dpi", "lhead", "totally_unknown_attr", "svgid", "_background"):
        try:
            engine.evaluate([AttrUse(name, "1", 1)])
            rejected = False
        except PolicyViolation:
            rejected = True
        assert rejected == (cfg.classify(name).state != "ok"), name


def test_as_dict_reports_allow_list_only_when_enforced() -> None:
    assert build_policy("denylist").as_dict()["allow"] == []
    assert "shape" in build_policy("allowlist").as_dict()["allow"]  # type: ignore[operator]
    assert "accepted except" in str(build_policy("denylist").as_dict()["rule"])
