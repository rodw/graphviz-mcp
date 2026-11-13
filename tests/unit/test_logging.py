from __future__ import annotations

import logging

import pytest

from graphviz_mcp.logging import JsonFormatter, log_call


def test_json_formatter_output() -> None:
    import json

    rec = logging.LogRecord("graphviz_mcp", logging.INFO, "f", 1, "call", (), None)
    rec.tool = "dot"
    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "call" and data["tool"] == "dot" and data["level"] == "INFO"


def test_log_call_helper_fields(caplog: pytest.LogCaptureFixture) -> None:
    import time

    with caplog.at_level(logging.INFO, logger="graphviz_mcp"):
        log_call("gvgen", "ok", time.monotonic(), output_bytes=5, surface="ui")
    r = caplog.records[-1]
    assert r.tool == "gvgen" and r.surface == "ui" and r.output_bytes == 5  # type: ignore[attr-defined]
