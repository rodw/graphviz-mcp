"""Policy data model (immutable)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MODES = ("denylist", "allowlist", "unrestricted")
HTML_IMG = "html:img"
RULES = {
    "denylist": "Every attribute is accepted except those on the deny list, and so are attribute names Graphviz does "
    "not document. Value constraints are enforced.",
    "allowlist": "Only attributes on the allow list are accepted. Value constraints are enforced.",
    "unrestricted": "No attribute or value checks, and Graphviz file loading is enabled.",
}


class PolicyViolation(Exception):
    """A request was rejected by the attribute policy (HTTP 403 on plain routes)."""

    def __init__(self, attribute: str, rule: str) -> None:
        self.attribute = attribute
        self.rule = rule
        super().__init__(f"attribute policy violation: {attribute}: {rule}")


@dataclass(frozen=True)
class Constraint:
    min: float | None = None
    max: float | None = None
    enum: tuple[str, ...] | None = None
    regex: str | None = None

    def describe(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f"min={self.min:g}")
        if self.max is not None:
            parts.append(f"max={self.max:g}")
        if self.enum is not None:
            parts.append("enum=" + "|".join(self.enum))
        if self.regex is not None:
            parts.append(f"regex={self.regex}")
        return ", ".join(parts)

    def check(self, value: str) -> str | None:
        """Return a human-readable reason if ``value`` violates the constraint, else None."""
        if self.min is not None or self.max is not None:
            try:
                number = float(value.strip())
            except ValueError:
                return f"value must be a number ({self.describe()})"
            if self.min is not None and number < self.min:
                return f"value {value[:40]!r} is below the minimum ({self.describe()})"
            if self.max is not None and number > self.max:
                return f"value {value[:40]!r} exceeds the maximum ({self.describe()})"
        if self.enum is not None and value not in self.enum:
            return f"value {value[:40]!r} is not one of the allowed values ({self.describe()})"
        if self.regex is not None and re.fullmatch(self.regex, value) is None:
            return f"value {value[:40]!r} does not match the required pattern ({self.describe()})"
        return None


@dataclass(frozen=True)
class AttrStatus:
    """How the active policy treats an attribute name.

    ``state`` is ``ok`` (accepted), ``denied`` (on the deny list, denylist mode) or ``not_allowed`` (missing from the
    allow list, allowlist mode). ``constraint`` is the value constraint that applies when the attribute is accepted;
    unrestricted mode has none.
    """

    state: str
    constraint: Constraint | None = None


@dataclass(frozen=True)
class PolicyConfig:
    mode: str = "denylist"
    deny: frozenset[str] = frozenset()
    allow: frozenset[str] = frozenset()
    constraints: dict[str, Constraint] = field(default_factory=dict)

    def classify(self, name: str) -> AttrStatus:
        """Classify an attribute name under this policy; the single decision path used by enforcement and reports.

        Names are matched case-insensitively, as enforcement always has: the policy keys are lower-case, although
        Graphviz itself treats ``K`` and ``k`` as different attributes.
        """
        if self.mode == "unrestricted":
            return AttrStatus("ok")
        key = name.lower()
        constraint = self.constraints.get(key)
        if self.mode == "denylist" and key in self.deny:
            return AttrStatus("denied", constraint)
        if self.mode == "allowlist" and key not in self.allow:
            return AttrStatus("not_allowed", constraint)
        return AttrStatus("ok", constraint)

    def as_dict(self) -> dict[str, object]:
        """Shape reported by ``get_capabilities`` and the Web UI.

        The allow list is only reported in allowlist mode, the one mode where it is enforced; in denylist mode
        everything not denied is accepted, so listing it would suggest other names are forbidden.
        """
        return {
            "mode": self.mode,
            "rule": RULES[self.mode],
            "deny": sorted(self.deny),
            "allow": sorted(self.allow) if self.mode == "allowlist" else [],
            "constraints": {k: v.describe() for k, v in sorted(self.constraints.items())},
        }
