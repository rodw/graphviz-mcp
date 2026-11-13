"""validate_dot's own input checks. They run before any Graphviz process is started, so no Graphviz is needed."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graphviz_mcp.config import Settings
from graphviz_mcp.extras import parse_nop_diagnostics, validate_document
from graphviz_mcp.tools.service import ToolFailure


def app_with_cap(cap: int) -> Any:
    return SimpleNamespace(settings=Settings(graphviz_bin=Path("/nonexistent"), max_input_bytes=cap), runner=None)


async def test_input_over_the_cap_is_rejected_before_graphviz_runs() -> None:
    with pytest.raises(ToolFailure) as ei:
        await validate_document(app_with_cap(10), "x" * 11)
    assert ei.value.kind == "too_large" and "10-byte limit" in ei.value.message


async def test_the_cap_counts_bytes_not_characters() -> None:
    with pytest.raises(ToolFailure) as ei:
        await validate_document(app_with_cap(10), "é" * 6)  # 6 characters, 12 bytes
    assert ei.value.kind == "too_large"


async def test_input_exactly_at_the_cap_passes_the_size_check() -> None:
    with pytest.raises(AttributeError):  # got past the cap and reached the (absent) runner
        await validate_document(app_with_cap(10), "x" * 10)


async def test_blank_input_is_an_argument_error() -> None:
    with pytest.raises(ToolFailure) as ei:
        await validate_document(app_with_cap(10), "   ")
    assert ei.value.kind == "args"


def test_parse_diagnostics() -> None:
    errors, warnings = parse_nop_diagnostics(
        "Error: <stdin>: syntax error in line 3 near ']'\nWarning: something odd\n"
    )
    assert errors == [{"message": "syntax error in line 3 near ']'", "line": 3, "near": "']'"}]
    assert warnings == [{"message": "something odd"}]
    assert parse_nop_diagnostics("") == ([], [])
