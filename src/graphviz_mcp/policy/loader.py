"""Read the built-in defaults plus an optional operator policy file (TOML); fail startup if invalid."""

from __future__ import annotations

import logging
import re
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

from ..config import Settings
from .model import MODES, Constraint, PolicyConfig

LOG = logging.getLogger("graphviz_mcp.policy")
_FILE_KEYS = {"deny", "deny_add", "allow", "allow_add", "constraints"}
_CONSTRAINT_KEYS = {"min", "max", "enum", "regex"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:\-]{0,127}")


class PolicyError(ValueError):
    """Invalid policy configuration (the server refuses to start)."""


def _names(value: Any, where: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and _NAME.fullmatch(v) for v in value):
        raise PolicyError(f"{where} must be a list of attribute names")
    return frozenset(v.lower() for v in value)


def _constraint(name: str, raw: Any) -> Constraint:
    where = f"constraints.{name}"
    if not isinstance(raw, dict) or not raw:
        raise PolicyError(f"{where} must be a non-empty table")
    extra = set(raw) - _CONSTRAINT_KEYS
    if extra:
        raise PolicyError(f"{where}: unknown key(s) {sorted(extra)}")
    lo, hi = raw.get("min"), raw.get("max")
    for label, v in (("min", lo), ("max", hi)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, int | float)):
            raise PolicyError(f"{where}.{label} must be a number")
    if lo is not None and hi is not None and lo > hi:
        raise PolicyError(f"{where}: min is greater than max")
    enum = raw.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum or not all(isinstance(v, str) for v in enum)):
        raise PolicyError(f"{where}.enum must be a non-empty list of strings")
    regex = raw.get("regex")
    if regex is not None:
        if not isinstance(regex, str) or len(regex) > 500:
            raise PolicyError(f"{where}.regex must be a string of at most 500 characters")
        try:
            re.compile(regex)
        except re.error as exc:
            raise PolicyError(f"{where}.regex does not compile: {exc}") from None
    return Constraint(
        min=None if lo is None else float(lo),
        max=None if hi is None else float(hi),
        enum=None if enum is None else tuple(enum),
        regex=regex,
    )


def builtin_defaults() -> dict[str, Any]:
    return tomllib.loads(resources.files("graphviz_mcp.policy").joinpath("defaults.toml").read_text("utf-8"))


def build_policy(mode: str, user: dict[str, Any] | None = None) -> PolicyConfig:
    if mode not in MODES:
        raise PolicyError(f"unknown policy mode {mode!r}")
    base = builtin_defaults()
    deny = _names(base["deny"], "defaults deny")
    allow = _names(base["allow"], "defaults allow")
    constraints = {k.lower(): _constraint(k, v) for k, v in base.get("constraints", {}).items()}
    if user:
        extra = set(user) - _FILE_KEYS
        if extra:
            raise PolicyError(f"policy file: unknown key(s) {sorted(extra)}")
        if "deny" in user:
            deny = _names(user["deny"], "deny")
        if "deny_add" in user:
            deny |= _names(user["deny_add"], "deny_add")
        if "allow" in user:
            allow = _names(user["allow"], "allow")
        if "allow_add" in user:
            allow |= _names(user["allow_add"], "allow_add")
        raw_constraints = user.get("constraints", {})
        if not isinstance(raw_constraints, dict):
            raise PolicyError("constraints must be a table")
        for name, raw in raw_constraints.items():
            if not _NAME.fullmatch(name):
                raise PolicyError(f"constraints: bad attribute name {name!r}")
            constraints[name.lower()] = _constraint(name, raw)
    return PolicyConfig(mode=mode, deny=deny, allow=allow, constraints=constraints)


def load_policy(settings: Settings) -> PolicyConfig:
    user: dict[str, Any] | None = None
    if settings.attr_policy_file is not None:
        path = Path(settings.attr_policy_file)
        try:
            user = tomllib.loads(path.read_text("utf-8"))
        except OSError as exc:
            raise PolicyError(f"cannot read policy file: {exc.strerror}") from None
        except tomllib.TOMLDecodeError as exc:
            raise PolicyError(f"policy file is not valid TOML: {exc}") from None
    policy = build_policy(settings.attr_policy, user)
    if policy.mode == "unrestricted":
        LOG.warning(
            "attribute policy is UNRESTRICTED: no attribute name or value checks, file loading enabled. "
            "Use only for trusted local use."
        )
    return policy
