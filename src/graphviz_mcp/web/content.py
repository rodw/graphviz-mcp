"""Markdown and static-document content for the Web UI (rendered once, with raw HTML disabled)."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from markdown_it import MarkdownIt
from markupsafe import Markup

# In the Docker image these files live together in DOC_DIR; from a source checkout they are in the repo.
DOC_DIR = Path("/usr/share/doc/graphviz-mcp")
_REPO = Path(__file__).resolve().parents[3]
_COMMENT = re.compile(r"<!--.*?-->\n?", re.DOTALL)

_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def render_markdown(text: str) -> Markup:
    """Markdown to HTML. Raw HTML in the source is escaped; HTML comments (generator markers) are dropped."""
    return Markup(_md.render(_COMMENT.sub("", text)))  # noqa: S704 (html=False: the renderer escapes raw HTML)


def _find(name: str, repo_subdir: str = "") -> Path:
    for candidate in (DOC_DIR / name, _REPO / repo_subdir / name):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{name} not found in {DOC_DIR} or {_REPO / repo_subdir}")


@cache
def read_doc(name: str, repo_subdir: str = "") -> str:
    """The text of a shipped document (LICENSE, THIRD_PARTY_NOTICES.md, attribute-security-policy.md)."""
    return _find(name, repo_subdir).read_text("utf-8")


@cache
def rendered_doc(name: str, repo_subdir: str = "") -> Markup:
    return render_markdown(read_doc(name, repo_subdir))
