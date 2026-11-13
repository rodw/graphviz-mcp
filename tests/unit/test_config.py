from __future__ import annotations

from pathlib import Path

import pytest

from graphviz_mcp.config import ConfigError, load_settings


def env(tmp_path: Path, **kw: str) -> dict[str, str]:
    (tmp_path / "dot").write_text("#!/bin/sh\n")
    return {"GVMCP_GRAPHVIZ_BIN": str(tmp_path), **{f"GVMCP_{k}": v for k, v in kw.items()}}


def test_defaults(tmp_path: Path) -> None:
    s = load_settings(env(tmp_path))
    assert s.host == "127.0.0.1" and s.port == 8000
    assert s.attr_policy == "denylist"
    assert s.queue_size == 4 * s.concurrency
    assert s.cpu_limit_s == 35


def test_overrides(tmp_path: Path) -> None:
    s = load_settings(
        env(
            tmp_path,
            HOST="0.0.0.0",
            PORT="9000",
            TIMEOUT_S="2.5",
            CONCURRENCY="3",
            ATTR_POLICY="AllowList",
            ALLOWED_HOSTS="a.example:*, b.example",
            RASTER_PREFLIGHT="off",
        )
    )
    assert (s.host, s.port, s.timeout_s, s.concurrency) == ("0.0.0.0", 9000, 2.5, 3)
    assert s.attr_policy == "allowlist" and s.allowed_hosts == ("a.example:*", "b.example")
    assert s.raster_preflight is False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PORT", "abc"),
        ("PORT", "0"),
        ("PORT", "70000"),
        ("TIMEOUT_S", "-1"),
        ("CONCURRENCY", "0"),
        ("ATTR_POLICY", "yolo"),
        ("LOG_LEVEL", "LOUD"),
        ("RASTER_PREFLIGHT", "maybe"),
        ("MAX_INPUT_BYTES", "1.5"),
    ],
)
def test_bad_values_rejected(tmp_path: Path, key: str, value: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(env(tmp_path, **{key: value}))


def test_missing_graphviz(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not contain 'dot'"):
        load_settings({"GVMCP_GRAPHVIZ_BIN": str(tmp_path)})
    with pytest.raises(ConfigError, match="not found"):
        load_settings({"PATH": str(tmp_path)})


def test_http_body_limits_follow_the_input_cap(tmp_path: Path) -> None:
    s = load_settings(env(tmp_path))
    assert s.max_mcp_body_bytes == 6 * 1_000_000 + 64_000
    assert s.max_form_body_bytes == 4 * 1_000_000 + 64_000
    big = load_settings(env(tmp_path, MAX_INPUT_BYTES="5000000"))
    assert big.max_mcp_body_bytes > 4 * 1024 * 1024 and big.max_mcp_body_bytes > s.max_mcp_body_bytes
