from __future__ import annotations

import pytest

from graphviz_mcp.security import allowed_origins, default_allowed_hosts, host_allowed, origin_allowed

HOSTS = default_allowed_hosts(["gv.internal:8443", "docs.example"])


@pytest.mark.parametrize(
    ("host", "ok"),
    [("127.0.0.1:8000", True), ("localhost:1", True), ("LOCALHOST:8000", True), ("[::1]:8000", True), ("127.0.0.1", True),
     ("gv.internal:8443", True), ("gv.internal:9", False), ("docs.example", True), ("docs.example:80", False),
     ("evil.example", False), ("127.0.0.1.evil.example", False), ("localhost:80x", False), ("localhost:", False),
     ("", False), (None, False), ("127.0.0.1:8000@evil", False), ("[::2]:8000", False)],
)  # fmt: skip
def test_host_allowed(host: str | None, ok: bool) -> None:
    assert host_allowed(host, HOSTS) is ok


@pytest.mark.parametrize(
    ("origin", "ok"),
    [(None, True), ("http://127.0.0.1:8000", True), ("https://localhost:3000", True), ("http://[::1]:8000", True),
     ("http://evil.example", False), ("http://127.0.0.1.evil.example", False), ("null", False),
     ("http://docs.example", True), ("ftp://localhost:1", False)],
)  # fmt: skip
def test_origin_allowed(origin: str | None, ok: bool) -> None:
    assert origin_allowed(origin, allowed_origins(HOSTS)) is ok
