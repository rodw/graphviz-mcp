"""Validate tool arguments against the flag table and build the argv list.

No string is built for a shell. Every value ends up either attached to its flag
(``-Tsvg``: it cannot start a new option) or after a flag that takes a separate value. Values that
could be mistaken for an option are rejected.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .specs import NAME_RE, Param, Program

MAX_VALUE_LEN = 4096
_NAME = re.compile(NAME_RE)
_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")


class ArgError(ValueError):
    """The arguments do not fit the tool's parameters (reported as a tool error)."""


class Dynamic(Protocol):
    def valid_format(self, spec: str) -> bool: ...
    def valid_engine(self, name: str) -> bool: ...


def _clean(label: str, value: str, *, allow_newline: bool = False) -> str:
    if len(value) > MAX_VALUE_LEN:
        raise ArgError(f"{label}: value is longer than {MAX_VALUE_LEN} characters")
    for ch in value:
        if ch == "\x00" or (ord(ch) < 0x20 and not (allow_newline and ch in "\t\n\r")) or ord(ch) == 0x7F:
            raise ArgError(f"{label}: control characters are not allowed")
    return value


def _number(p: Param, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ArgError(f"{p.name}: expected a number")
    if p.ptype == "int":
        if isinstance(value, float):
            if not value.is_integer():
                raise ArgError(f"{p.name}: expected an integer")
            value = int(value)
    elif not math.isfinite(value):
        raise ArgError(f"{p.name}: must be finite")
    if p.choices is not None and value not in p.choices:
        raise ArgError(f"{p.name}: must be one of {list(p.choices)}")
    if p.minimum is not None and value < p.minimum:
        raise ArgError(f"{p.name}: must be >= {p.minimum:g}")
    if p.maximum is not None and value > p.maximum:
        raise ArgError(f"{p.name}: must be <= {p.maximum:g}")
    result: int | float = value
    return result


def _fmt_number(value: int | float) -> str:
    return str(value) if isinstance(value, int) else format(value, ".10g")


def _string(p: Param, value: Any, caps: Dynamic | None) -> str:
    if not isinstance(value, str):
        raise ArgError(f"{p.name}: expected a string")
    value = _clean(p.name, value)
    if value == "" and p.style in ("attached", "separate", "long", "positional", "multi"):
        raise ArgError(f"{p.name}: must not be empty")
    if p.style in ("separate", "positional") and value.startswith("-") and not _NUMBER.fullmatch(value):
        raise ArgError(f"{p.name}: must not start with '-'")
    if p.choices is not None and value not in p.choices:
        raise ArgError(f"{p.name}: must be one of {list(p.choices)}")
    if p.pattern is not None and re.fullmatch(p.pattern, value) is None:
        raise ArgError(f"{p.name}: value {value[:40]!r} has an invalid form")
    if caps is not None and p.dynamic == "format" and not caps.valid_format(value):
        raise ArgError(
            f"{p.name}: {value[:40]!r} is not an output format of this Graphviz build (see get_capabilities)"
        )
    if caps is not None and p.dynamic == "engine" and not caps.valid_engine(value):
        raise ArgError(f"{p.name}: {value[:40]!r} is not a layout engine of this Graphviz build (see get_capabilities)")
    text: str = value
    return text


def _kv(p: Param, value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        raise ArgError(f"{p.name}: expected an object of name/value pairs")
    out: list[str] = []
    for k, v in value.items():
        if not isinstance(k, str) or _NAME.fullmatch(k) is None:
            raise ArgError(f"{p.name}: invalid attribute name {str(k)[:40]!r}")
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, int | float):
            v = _fmt_number(v)
        if not isinstance(v, str):
            raise ArgError(f"{p.name}.{k}: value must be a string or number")
        out.append(f"{p.flag}{k}={_clean(f'{p.name}.{k}', v, allow_newline=True)}")
    return out


def build_argv(program: Program, args: Mapping[str, Any], caps: Dynamic | None = None) -> list[str]:
    """Return the flag/positional argv (without the program name and without any input file)."""
    known = {p.name: p for p in program.params}
    unknown = sorted(set(args) - set(known) - {"input"})
    if unknown:
        raise ArgError(f"unknown parameter(s) for {program.name}: {', '.join(unknown)}")
    flags: list[str] = []
    positionals: list[str] = []
    for p in program.params:
        value = args.get(p.name)
        if value is None:
            if p.required:
                raise ArgError(f"{p.name}: required")
            continue
        if p.ptype == "bool":
            if not isinstance(value, bool):
                raise ArgError(f"{p.name}: expected true or false")
            if value:
                flags.append(p.flag)
        elif p.ptype == "kv":
            flags.extend(_kv(p, value))
        elif p.ptype == "strlist":
            if not isinstance(value, Sequence) or isinstance(value, str):
                raise ArgError(f"{p.name}: expected a list of strings")
            flags.extend(f"{p.flag}{_string(p, v, caps)}" for v in value)
        elif p.ptype in ("int", "float"):
            text = _fmt_number(_number(p, value))
            _append(p, text, flags)
        else:
            text = _string(p, value, caps)
            if p.style == "positional":
                positionals.append(text)
            else:
                _append(p, text, flags)
    return [*flags, *positionals]


def _append(p: Param, text: str, flags: list[str]) -> None:
    if p.style == "attached" or (p.style == "long" and p.flag.endswith("=")):
        flags.append(f"{p.flag}{text}")
    elif p.style == "long":
        flags.append(f"{p.flag}={text}")
    elif p.style == "separate":
        flags.extend([p.flag, text])
    else:  # pragma: no cover - table error
        raise AssertionError(f"{p.name}: cannot place a value with style {p.style}")
