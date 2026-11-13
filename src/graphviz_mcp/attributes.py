"""The effective attribute view: the master list of Graphviz attributes filtered by the live policy.

``data/attribute-list.toml`` (generated, structured facts) is the superset. ``data/attribute-descriptions.toml``
supplies our own short descriptions. Each row gets its status from ``PolicyConfig.classify``, the same decision path
enforcement uses.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from .policy.model import HTML_IMG, RULES, PolicyConfig

ATTRS_URL = "https://graphviz.org/doc/info/attrs.html"
ATTRS_RESOURCE = "graphviz://attributes"
DOT_LANGUAGE_RESOURCE = "graphviz://dot-language"

_UNLISTED = "Not in the Graphviz attribute documentation."


@dataclass(frozen=True)
class AttrRow:
    name: str
    applies: str
    engines: tuple[str, ...]
    type: str
    default: str
    minimum: str
    status: str
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "applies_to": self.applies,
            "engines": list(self.engines),
            "type": self.type,
            "default": self.default,
            "minimum": self.minimum,
            "status": self.status,
            "description": self.description,
        }


@dataclass(frozen=True)
class AttrView:
    mode: str
    rule: str
    graphviz_release: str
    source_sha: str
    rows: tuple[AttrRow, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rule": self.rule,
            "graphviz_release": self.graphviz_release,
            "documentation": ATTRS_URL,
            "attributes": [r.as_dict() for r in self.rows],
        }


@cache
def _load() -> tuple[str, str, tuple[dict[str, Any], ...], dict[str, str]]:
    data = resources.files("graphviz_mcp").joinpath("data")
    master = tomllib.loads(data.joinpath("attribute-list.toml").read_text("utf-8"))
    descriptions: dict[str, str] = tomllib.loads(data.joinpath("attribute-descriptions.toml").read_text("utf-8"))[
        "description"
    ]
    return master["graphviz_release"], master["source_sha"], tuple(master["attribute"]), descriptions


def master_names() -> frozenset[str]:
    """Every attribute name in the master list (exact case)."""
    return frozenset(e["name"] for e in _load()[2])


def status_text(config: PolicyConfig, name: str) -> str:
    st = config.classify(name)
    if st.state == "denied":
        return "denied"
    if st.state == "not_allowed":
        return "not on allow list"
    if st.constraint is not None:
        return f"capped ({st.constraint.describe()})"
    return "ok"


def build_view(config: PolicyConfig) -> AttrView:
    release, sha, entries, descriptions = _load()
    rows = [
        AttrRow(
            name=e["name"],
            applies=e["applies"],
            engines=tuple(e["engines"]),
            type=e["type"],
            default=e["default"],
            minimum=e["minimum"],
            status=status_text(config, e["name"]),
            description=descriptions.get(e["name"], ""),
        )
        for e in entries
    ]
    # Names the policy classifies that the documentation does not list (e.g. the undocumented svgid) and the
    # <IMG> pseudo-attribute are still shown, so the view and the policy cannot drift apart silently.
    known = {r.name.lower() for r in rows}
    for key in sorted((config.deny | config.allow | frozenset(config.constraints)) - known):
        note = "HTML-like label <IMG> elements." if key == HTML_IMG else _UNLISTED
        rows.append(AttrRow(key, "-", (), "-", "", "", status_text(config, key), note))
    rows.sort(key=lambda r: (r.name.lower(), r.name))
    return AttrView(config.mode, RULES[config.mode], release, sha, tuple(rows))


def render_markdown(view: AttrView) -> str:
    lines = [
        "# Graphviz attributes and this server's attribute policy",
        "",
        f"Attribute policy: **{view.mode}**. {view.rule}",
        "",
        "Status per attribute: `ok` is accepted; `denied` and `not on allow list` are rejected; `capped (...)` is "
        "accepted only while the value stays within the stated limit. Attribute names are matched "
        "case-insensitively.",
        "",
        f"The list follows the Graphviz {view.graphviz_release} documentation; Graphviz cannot list its own "
        f"attributes, so a different installed version may differ. Official reference: {ATTRS_URL} . "
        "Descriptions are short summaries; follow the link for full semantics. "
        f"For the DOT language itself see `{DOT_LANGUAGE_RESOURCE}`; for limits call `get_capabilities`.",
        "",
        "Applies to: G root graph, C cluster, S subgraph, N node, E edge.",
        "",
        "| Attribute | Applies to | Engines | Type | Default | Status | Description |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in view.rows:
        cells = [
            r.name,
            r.applies,
            ", ".join(r.engines) or "all",
            r.type or "-",
            r.default or "-",
            r.status,
            r.description,
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"
