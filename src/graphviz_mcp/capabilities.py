"""Probe the installed Graphviz once at startup; the result drives tool registration and validation."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .runner import Runner
from .tools import catalog

REQUIRED_PROGRAMS = ("dot", "nop")
REQUIRED_FORMATS = ("svg", "dot", "plain")
REQUIRED_ENGINES = ("dot", "neato")
_VERSION = re.compile(r"graphviz version (\S+)")
_USE_ONE_OF = re.compile(r"Use one of:\s*(.+)", re.DOTALL)
_PLUGIN_LINE = re.compile(r"^\s+(render|layout|textlayout|device|loadimage)\s*:\s*(.*)$", re.M)
_DEVICE = re.compile(r"Using device:\s*(\S+)")


class CapabilityError(RuntimeError):
    """The installed Graphviz does not meet the required baseline (the server refuses to start)."""


def parse_version(text: str) -> str:
    m = _VERSION.search(text)
    if not m:
        raise CapabilityError(f"cannot parse 'dot -V' output: {text.strip()[:200]!r}")
    return m.group(1)


def parse_use_one_of(text: str) -> tuple[str, ...]:
    """Parse the ``Use one of: a b c`` tail of Graphviz's 'not recognized' messages."""
    m = _USE_ONE_OF.search(text)
    if not m:
        return ()
    return tuple(m.group(1).split())


def parse_plugins(text: str) -> dict[str, tuple[str, ...]]:
    """Plugin kinds and names from the ``dot -v`` configuration dump."""
    return {m.group(1): tuple(m.group(2).split()) for m in _PLUGIN_LINE.finditer(text)}


def parse_default_device(text: str) -> str | None:
    m = _DEVICE.search(text)
    return m.group(1) if m else None


@dataclass(frozen=True)
class Capabilities:
    version: str
    version_line: str
    bin_dir: Path
    formats: tuple[str, ...]
    combos: Mapping[str, tuple[str, ...]]
    default_device: Mapping[str, str]
    engines: tuple[str, ...]
    programs: Mapping[str, Path]
    missing: tuple[str, ...]
    unclassified: tuple[str, ...]
    fonts: tuple[str, ...] = ()
    plugins: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    valid_specs: frozenset[str] = field(init=False, default=frozenset())

    def __post_init__(self) -> None:
        specs: set[str] = set(self.formats)
        for combos in self.combos.values():
            for full in combos:
                specs.add(full)
                parts = full.split(":")
                if len(parts) >= 2:
                    specs.add(":".join(parts[:2]))
        object.__setattr__(self, "valid_specs", frozenset(specs))

    def valid_format(self, spec: str) -> bool:
        return spec in self.valid_specs

    def valid_engine(self, name: str) -> bool:
        return name in self.engines

    def as_dict(self) -> dict[str, Any]:
        from .formats import describe

        return {
            "graphviz_version": self.version,
            "graphviz_version_line": self.version_line,
            "layout_engines": list(self.engines),
            "output_formats": [
                {
                    "format": f,
                    "mime": describe(f).mime,
                    "result": describe(f).kind,
                    "renderers": list(self.combos.get(f, ())),
                    "default": self.default_device.get(f),
                }
                for f in self.formats
            ],
            "tools": sorted(self.programs),
            "tools_missing": list(self.missing),
            "unclassified_programs": list(self.unclassified),
            "fonts": list(self.fonts),
            "plugins": {k: list(v) for k, v in self.plugins.items()},
        }


def _executables(bin_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for entry in sorted(bin_dir.iterdir()):
        if entry.is_file() and os.access(entry, os.X_OK):
            out[entry.name] = entry
    return out


async def probe(settings: Settings) -> tuple[Capabilities, Runner]:
    """Run the capability gate. Returns the capabilities and the Runner restricted to the allowlist."""
    installed = _executables(settings.graphviz_bin)
    unclassified, missing = catalog.classify(set(installed))
    programs = {n: installed[n] for n in catalog.EXPOSED if n in installed}
    for required in REQUIRED_PROGRAMS:
        if required not in programs:
            raise CapabilityError(f"required Graphviz program {required!r} not found in {settings.graphviz_bin}")
    helpers = dict(programs)
    if fc := shutil.which("fc-list"):
        helpers["fc-list"] = Path(fc)
    runner = Runner(settings, helpers)

    gate = asyncio.Semaphore(max(1, settings.concurrency))  # the startup burst must not trip the busy limit

    async def run(prog: str, args: list[str], stdin: bytes | None = None) -> tuple[str, str, int]:
        async with gate, runner.workdir() as wd:
            r = await runner.run(prog, args, stdin, workdir=wd, timeout_s=20)
        return r.stdout.decode("utf-8", "replace"), r.stderr, r.returncode

    _, err, _ = await run("dot", ["-V"])
    version = parse_version(err)
    version_line = err.strip().splitlines()[0]
    _, err, _ = await run("dot", ["-T?"])
    formats = parse_use_one_of(err)
    _, err, _ = await run("dot", ["-K?"])
    engines = parse_use_one_of(err)
    for need, have, label in (
        (REQUIRED_FORMATS, formats, "output format"),
        (REQUIRED_ENGINES, engines, "layout engine"),
    ):
        for item in need:
            if item not in have:
                raise CapabilityError(f"required {label} {item!r} not reported by this Graphviz build")

    async def combos(fmt: str) -> tuple[str, tuple[str, ...]]:
        _, e, _ = await run("dot", [f"-T{fmt}:x"], b"digraph{}")
        return fmt, parse_use_one_of(e) or (fmt,)

    plugins: dict[str, tuple[str, ...]] = {}

    async def device(fmt: str) -> tuple[str, str | None]:
        _, e, _ = await run("dot", ["-v", f"-T{fmt}"], b"digraph{}")
        if not plugins:
            plugins.update(parse_plugins(e))
        return fmt, parse_default_device(e)

    combo_list, device_list = await asyncio.gather(
        asyncio.gather(*(combos(f) for f in formats)), asyncio.gather(*(device(f) for f in formats))
    )
    fonts: tuple[str, ...] = ()
    if "fc-list" in helpers:
        out, _, rc = await run("fc-list", [":", "family"])
        if rc == 0:
            fonts = tuple(sorted({line.split(",")[0].strip() for line in out.splitlines() if line.strip()}))
    caps = Capabilities(
        version=version,
        version_line=version_line,
        bin_dir=settings.graphviz_bin,
        formats=formats,
        combos={f: c for f, c in combo_list},
        default_device={f: d for f, d in device_list if d},
        engines=engines,
        programs=programs,
        missing=tuple(missing),
        unclassified=tuple(unclassified),
        fonts=fonts,
        plugins=plugins,
    )
    # The runner keeps fc-list out of the tool surface: it is only reachable from this module.
    return caps, runner
