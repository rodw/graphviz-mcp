"""Hard-coded combined raster-size check (enforced in every mode except ``unrestricted``).

Pixel size depends on several things at once: the layout's own bounding box, ``size`` (scale-down
or, with ``!``, scale-up), ``pad`` and ``dpi``. Checked against Graphviz (see
tests/test_raster.py):  width_px = (layout_w * scale + 2 * pad) * dpi  (same for height), where
``layout_w`` and ``scale`` are what ``-Tplain`` reports.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .scan import Scan

DEFAULT_DPI = 96.0
DEFAULT_PAD_IN = 4 / 72  # 4 points
SAFETY = 1.05  # margin so rounding and rotation never make us under-estimate
_NUM = re.compile(r"\s*([0-9]*\.?[0-9]+)")

# Base formats whose output is a pixel image whose size scales with dpi.
RASTER_FORMATS = frozenset(
    {
        "png", "jpg", "jpeg", "jpe", "gif", "webp", "wbmp", "bmp", "ico", "tif", "tiff", "tga",
        "gd", "gd2", "jp2", "pict", "kitty", "kittyz",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Estimate:
    pixels: float
    exact: bool  # True when derived from a layout pre-flight, False for a static bound


def _numbers(value: str) -> list[float]:
    out: list[float] = []
    for part in value.split(","):
        m = _NUM.match(part)
        if m:
            out.append(float(m.group(1)))
    return out


def _max_dpi(scan: Scan) -> float:
    best = DEFAULT_DPI
    for name in ("dpi", "resolution"):
        for v in scan.values(name):
            nums = _numbers(v)
            if nums:
                best = max(best, nums[0])
    return best


def _max_pad(scan: Scan) -> float:
    best = DEFAULT_PAD_IN
    for v in scan.values("pad"):
        nums = _numbers(v)
        if nums:
            best = max(best, *nums)
    return best


def static_bound(scan: Scan) -> Estimate | None:
    """Upper bound from ``size`` alone, or None when ``size`` is not set on the root graph."""
    sizes = scan.values("size", root_only=True)
    if not sizes:
        return None
    w = h = 0.0
    for v in sizes:
        nums = _numbers(v)
        if not nums:
            return None
        w = max(w, nums[0])
        h = max(h, nums[-1])
    dpi, pad = _max_dpi(scan), _max_pad(scan)
    px = math.ceil((w + 2 * pad) * dpi) * math.ceil((h + 2 * pad) * dpi)
    return Estimate(px * SAFETY, exact=False)


def from_plain(plain_header: str, scan: Scan) -> Estimate:
    """Estimate from the first line of ``-Tplain`` output (``graph <scale> <w> <h>``)."""
    parts = plain_header.split()
    if len(parts) < 4 or parts[0] != "graph":
        raise ValueError("unexpected -Tplain output")
    scale, w, h = float(parts[1]), float(parts[2]), float(parts[3])
    dpi, pad = _max_dpi(scan), _max_pad(scan)
    px = math.ceil((w * scale + 2 * pad) * dpi) * math.ceil((h * scale + 2 * pad) * dpi)
    return Estimate(px * SAFETY, exact=True)
