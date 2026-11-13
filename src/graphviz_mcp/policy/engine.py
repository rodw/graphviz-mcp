"""Policy evaluation: ``nop`` pre-pass, attribute rules, raster-size guard."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from ..runner import Runner, scrub
from . import raster
from .model import HTML_IMG, PolicyConfig, PolicyViolation
from .scan import AttrUse, Scan, scan_canonical

_NAME = re.compile(r"[A-Za-z_\x80-\U0010ffff][A-Za-z_0-9.:\-\x80-\U0010ffff]{0,127}")


class InputError(Exception):
    """The DOT input could not be parsed (reported with Graphviz's own message)."""


class PolicyEngine:
    def __init__(self, config: PolicyConfig, runner: Runner, *, max_pixels: int, preflight: bool) -> None:
        self.config = config
        self._runner = runner
        self._max_pixels = max_pixels
        self._preflight = preflight

    # -- rules ---------------------------------------------------------------------------------
    def evaluate(self, uses: Iterable[AttrUse], html_img: int = 0) -> None:
        cfg = self.config
        if cfg.mode == "unrestricted":
            return
        for use in uses:
            where = "request parameter" if use.source.startswith("param") else "graph text"
            if not _NAME.fullmatch(use.name):
                raise PolicyViolation(use.name[:40], f"not a valid attribute name ({where})")
            status = cfg.classify(use.name)
            if status.state == "denied":
                raise PolicyViolation(use.name, f"attribute is on the deny list ({where})")
            if status.state == "not_allowed":
                raise PolicyViolation(use.name, f"attribute is not on the allow list ({where})")
            if status.constraint is not None and (reason := status.constraint.check(use.value)) is not None:
                raise PolicyViolation(use.name, reason)
        if html_img:
            if cfg.mode == "denylist" and HTML_IMG in cfg.deny:
                raise PolicyViolation("<IMG>", "HTML-like label <IMG> elements are on the deny list")
            if cfg.mode == "allowlist" and HTML_IMG not in cfg.allow:
                raise PolicyViolation("<IMG>", "HTML-like label <IMG> elements are not on the allow list")

    # -- DOT -----------------------------------------------------------------------------------
    async def canonical(self, text: str) -> str:
        """Run ``nop`` (parse only: no layout, no file access) and return Graphviz's canonical text."""
        async with self._runner.workdir() as wd:
            result = await self._runner.run("nop", [], text.encode("utf-8"), workdir=wd)
            if result.returncode != 0:
                msg = scrub(result.stderr, self._runner.scrubber(wd)).strip().splitlines()
                raise InputError((msg[-1] if msg else "invalid DOT input")[:300].replace("<stdin>: ", ""))
            return result.stdout.decode("utf-8", "replace")

    async def check(self, dot_texts: Sequence[str] = (), params: Mapping[str, Mapping[str, str]] | None = None) -> Scan:
        """Reject (PolicyViolation) or return the effective attribute set of the request."""
        scan = Scan()
        if self.config.mode == "unrestricted":
            return scan
        for scope, mapping in (params or {}).items():
            for name, value in mapping.items():
                scan.uses.append(AttrUse(name, value, 1, f"param:{scope}"))
        self.evaluate(scan.uses)
        for text in dot_texts:
            sub = scan_canonical(await self.canonical(text))
            self.evaluate(sub.uses, sub.html_img)
            scan.uses.extend(sub.uses)
            scan.html_img += sub.html_img
        return scan

    # -- raster size ---------------------------------------------------------------------------
    async def check_raster(
        self, base_format: str, program: str, args: Sequence[str], text: str, scan: Scan, workdir: Path
    ) -> raster.Estimate | None:
        """Refuse requests whose raster output would exceed the pixel budget (all modes but unrestricted)."""
        if self.config.mode == "unrestricted" or base_format.lower() not in raster.RASTER_FORMATS:
            return None
        cap = self._max_pixels
        static = raster.static_bound(scan)
        if static is not None and static.pixels <= cap:
            return static
        if self._preflight:
            result = await self._runner.run(program, [*args, "-Tplain"], text.encode("utf-8"), workdir=workdir)
            if result.returncode == 0:
                header = result.stdout.split(b"\n", 1)[0].decode("ascii", "replace")
                try:
                    est = raster.from_plain(header, scan)
                except ValueError:
                    return static  # let the real run report the problem
                self._enforce(est, cap)
                return est
            return static
        if static is not None:
            self._enforce(static, cap)
        return static

    @staticmethod
    def _enforce(est: raster.Estimate, cap: int) -> None:
        if est.pixels > cap:
            raise PolicyViolation(
                "raster-size",
                f"estimated output of about {est.pixels / 1e6:.1f} megapixels exceeds the limit of "
                f"{cap / 1e6:.1f} megapixels; reduce 'size' or 'dpi', or use a vector format",
            )
