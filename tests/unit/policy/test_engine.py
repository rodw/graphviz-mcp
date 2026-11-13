from __future__ import annotations

import pytest

from graphviz_mcp.policy import AttrUse, PolicyViolation, build_policy
from graphviz_mcp.policy.engine import PolicyEngine


def engine(mode: str = "denylist", user: dict | None = None) -> PolicyEngine:  # type: ignore[type-arg]
    return PolicyEngine(build_policy(mode, user), runner=None, max_pixels=50_000_000, preflight=True)  # type: ignore[arg-type]


def uses(**kw: str) -> list[AttrUse]:
    return [AttrUse(k, v, 1) for k, v in kw.items()]


def test_denylist_allows_unknown_and_denies_listed() -> None:
    engine().evaluate(uses(shape="box", totally_unknown_attr="x"))
    for bad in ("image", "Image", "SHAPEFILE", "imagepath", "fontpath", "stylesheet"):
        with pytest.raises(PolicyViolation, match="deny list"):
            engine().evaluate(uses(**{bad: "/etc/passwd"}))


def test_allowlist_rejects_unknown_and_listed_denied() -> None:
    engine("allowlist").evaluate(uses(shape="box", rankdir="LR", K="1"))
    with pytest.raises(PolicyViolation, match="not on the allow list"):
        engine("allowlist").evaluate(uses(totally_unknown_attr="x"))
    with pytest.raises(PolicyViolation):
        engine("allowlist").evaluate(uses(image="x"))


def test_unrestricted_skips_everything() -> None:
    engine("unrestricted").evaluate(uses(image="/etc/passwd", dpi="99999"), html_img=3)


def test_html_img() -> None:
    with pytest.raises(PolicyViolation, match="IMG"):
        engine().evaluate([], html_img=1)
    with pytest.raises(PolicyViolation, match="IMG"):
        engine("allowlist").evaluate([], html_img=1)
    engine("allowlist", {"allow_add": ["html:img"]}).evaluate([], html_img=1)


@pytest.mark.parametrize(("attr", "value", "ok"), [
    ("dpi", "96", True), ("dpi", "300", True), ("dpi", "301", False), ("dpi", "abc", False),
    ("resolution", "5000", False), ("mclimit", "11", False), ("nslimit", "2", True),
    ("maxiter", "1000000", False), ("fontsize", "1e9", False), ("peripheries", "3", True),
])  # fmt: skip
def test_default_constraints(attr: str, value: str, ok: bool) -> None:
    if ok:
        engine().evaluate(uses(**{attr: value}))
    else:
        with pytest.raises(PolicyViolation):
            engine().evaluate(uses(**{attr: value}))


def test_constraints_apply_in_allowlist_mode_too() -> None:
    with pytest.raises(PolicyViolation, match="maximum"):
        engine("allowlist").evaluate(uses(dpi="9999"))


def test_user_constraints_enum_regex_override() -> None:
    user = {
        "constraints": {"splines": {"enum": ["line", "true"]}, "label": {"regex": "[a-z ]{0,10}"}, "dpi": {"max": 150}}
    }
    e = engine(user=user)
    e.evaluate(uses(splines="line", label="hello"))
    with pytest.raises(PolicyViolation, match="allowed values"):
        e.evaluate(uses(splines="ortho"))
    with pytest.raises(PolicyViolation, match="pattern"):
        e.evaluate(uses(label="HELLO"))
    with pytest.raises(PolicyViolation, match="maximum"):
        e.evaluate(uses(dpi="200"))


def test_user_lists_replace_and_add() -> None:
    e = engine(user={"deny": ["color"]})
    e.evaluate(uses(image="x"))  # replaced: image no longer denied
    with pytest.raises(PolicyViolation):
        e.evaluate(uses(color="red"))
    e2 = engine(user={"deny_add": ["label"]})
    with pytest.raises(PolicyViolation):
        e2.evaluate(uses(label="x"))
    with pytest.raises(PolicyViolation):
        e2.evaluate(uses(image="x"))


def test_invalid_attribute_names_rejected() -> None:
    for bad in ("a b", "x\ny", "", "a" * 200, "=x"):
        with pytest.raises(PolicyViolation, match="valid attribute name"):
            engine().evaluate([AttrUse(bad, "v", 1)])


def test_violation_message_names_attribute_and_leaks_no_paths() -> None:
    with pytest.raises(PolicyViolation) as ei:
        engine().evaluate(uses(image="/srv/secret/file.png"))
    assert "image" in str(ei.value) and "/srv" not in str(ei.value)


def test_as_dict_reports_lists_and_constraints() -> None:
    d = build_policy("denylist").as_dict()
    assert d["mode"] == "denylist" and "image" in d["deny"] and "dpi" in d["constraints"]  # type: ignore[operator]
