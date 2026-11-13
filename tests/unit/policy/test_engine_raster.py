"""The raster-size check's early exits and static path. None of them starts a Graphviz process (no runner needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from graphviz_mcp.policy import AttrUse, PolicyViolation, build_policy
from graphviz_mcp.policy.engine import PolicyEngine
from graphviz_mcp.policy.scan import Scan

WORKDIR = Path("/nonexistent")


def engine(mode: str = "denylist", *, max_pixels: int = 50_000_000, preflight: bool = True) -> PolicyEngine:
    return PolicyEngine(build_policy(mode, None), runner=None, max_pixels=max_pixels, preflight=preflight)  # type: ignore[arg-type]


async def test_vector_formats_are_never_checked() -> None:
    text = 'digraph { size="400,400!"; a -> b }'
    scan = Scan(uses=[AttrUse("size", "400,400!", 1)])
    assert await engine().check_raster("svg", "dot", [], text, scan, WORKDIR) is None


async def test_unrestricted_mode_skips_the_check() -> None:
    text = 'digraph { size="400,400!"; a -> b }'
    scan = Scan(uses=[AttrUse("size", "400,400!", 1)])
    assert await engine("unrestricted").check_raster("png", "dot", [], text, scan, WORKDIR) is None


async def test_without_preflight_the_static_bound_is_enforced() -> None:
    text = 'digraph { size="40,40!"; dpi=300; a }'
    scan = Scan(uses=[AttrUse("size", "40,40!", 1), AttrUse("dpi", "300", 1)])
    with pytest.raises(PolicyViolation, match="megapixels"):
        await engine(max_pixels=1_000_000, preflight=False).check_raster("png", "dot", [], text, scan, WORKDIR)


async def test_without_preflight_and_without_size_nothing_can_be_proved() -> None:
    # defers to the timeout and the output cap
    assert await engine(preflight=False).check_raster("png", "dot", [], "digraph { a }", Scan(), WORKDIR) is None
