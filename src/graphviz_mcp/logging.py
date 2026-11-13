"""JSON-lines logging to stderr (stdout is the protocol channel in stdio mode)."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

LOGGER = logging.getLogger("graphviz_mcp")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Route all logging (ours, uvicorn's, the SDK's) to stderr as JSON lines."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True


def log_call(
    tool: str,
    status: str,
    started: float,
    *,
    input_bytes: int = 0,
    output_bytes: int = 0,
    reason: str | None = None,
    surface: str = "mcp",
) -> None:
    """One structured record per tool call."""
    LOGGER.info(
        "call",
        extra={
            "event": "call",
            "tool": tool,
            "status": status,
            "surface": surface,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
            "input_bytes": input_bytes,
            "output_bytes": output_bytes,
            "reason": reason,
        },
    )
