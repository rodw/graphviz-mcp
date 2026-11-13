from __future__ import annotations

import pytest

from graphviz_mcp.policy.raster import from_plain, static_bound
from graphviz_mcp.policy.scan import AttrUse, Scan


def scan_of(**kw: str) -> Scan:
    return Scan(uses=[AttrUse(k, v, 1) for k, v in kw.items()])


def test_static_bound_needs_root_size() -> None:
    assert static_bound(Scan()) is None
    nested = Scan(uses=[AttrUse("size", "1,1", 2)])  # size inside a subgraph is ignored by Graphviz
    assert static_bound(nested) is None


def test_static_bound_value() -> None:
    est = static_bound(scan_of(size="2,3", dpi="100"))
    assert est is not None and not est.exact
    assert 2 * 100 * 3 * 100 <= est.pixels <= 1.2 * (2.2 * 100) * (3.2 * 100)


def test_static_bound_takes_largest_values() -> None:
    small = static_bound(scan_of(size="1,1"))
    big = static_bound(Scan(uses=[AttrUse("size", "1,1", 1), AttrUse("size", "9,9", 1), AttrUse("dpi", "300", 1)]))
    assert small and big and big.pixels > 100 * small.pixels


def test_from_plain_math() -> None:
    est = from_plain("graph 0.5 4 8", scan_of(dpi="100"))
    assert est.exact and est.pixels > (4 * 0.5 * 100) * (8 * 0.5 * 100)
    with pytest.raises(ValueError, match="unexpected"):
        from_plain("nonsense", Scan())
