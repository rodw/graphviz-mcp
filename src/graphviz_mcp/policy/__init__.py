"""Attribute policy: public API."""

from __future__ import annotations

from .engine import InputError, PolicyEngine
from .loader import PolicyError, build_policy, load_policy
from .model import HTML_IMG, AttrStatus, Constraint, PolicyConfig, PolicyViolation
from .scan import AttrUse, Scan, scan_canonical

__all__ = [
    "HTML_IMG",
    "AttrStatus",
    "AttrUse",
    "Constraint",
    "InputError",
    "PolicyConfig",
    "PolicyEngine",
    "PolicyError",
    "PolicyViolation",
    "Scan",
    "build_policy",
    "load_policy",
    "scan_canonical",
]
