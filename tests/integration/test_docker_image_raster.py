"""The raster pre-flight against what the pinned Graphviz really renders (the real policy engine, Graphviz in the image)."""

from __future__ import annotations

from typing import Any

import pytest

from graphviz_mcp.policy import PolicyViolation, build_policy
from graphviz_mcp.policy.engine import PolicyEngine
from tests.support.cases import RASTER_CASES
from tests.support.docker_image_ctl import ContainerRunner
from tests.support.helpers import png_dims

pytestmark = pytest.mark.docker_image


def engine(container: Any, *, max_pixels: int = 50_000_000) -> tuple[PolicyEngine, ContainerRunner]:
    runner = ContainerRunner(container)
    return PolicyEngine(build_policy("denylist", None), runner, max_pixels=max_pixels, preflight=True), runner  # type: ignore[arg-type]


@pytest.mark.parametrize("name", list(RASTER_CASES))
async def test_preflight_estimate_covers_the_real_png(docker_image_server: Any, name: str) -> None:
    text = RASTER_CASES[name]
    eng, runner = engine(docker_image_server)
    scan = await eng.check([text])
    async with runner.workdir() as wd:
        est = await eng.check_raster("png", "dot", [], text, scan, wd)
        real = await runner.run("dot", ["-Tpng"], text.encode(), workdir=wd)
    assert est is not None
    w, h = png_dims(real.stdout)
    assert est.pixels >= w * h * 0.999, f"underestimate: {est.pixels} < {w * h}"
    if est.exact:  # layout pre-flight; the static size-based bound is allowed to be loose
        assert est.pixels <= w * h * 1.4, f"estimate is too loose: {est.pixels} vs {w * h}"


async def test_oversized_request_is_rejected_before_rendering(docker_image_server: Any) -> None:
    text = 'digraph { size="40,40!"; dpi=300; a -> b }'
    eng, runner = engine(docker_image_server, max_pixels=10_000_000)
    scan = await eng.check([text])
    async with runner.workdir() as wd:
        with pytest.raises(PolicyViolation, match="megapixels"):
            await eng.check_raster("png", "dot", [], text, scan, wd)
