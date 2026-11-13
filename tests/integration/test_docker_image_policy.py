"""Attribute-policy red-team and false-positive sets, against the Docker image (the real Graphviz parser behind `nop`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mcp import Client

from graphviz_mcp.policy import scan_canonical
from tests.support import docker_image_ctl
from tests.support.cases import BENIGN, HOSTILE, SCAN_SRC
from tests.support.clients import PerCallClient
from tests.support.helpers import text_of

pytestmark = pytest.mark.docker_image


@pytest.fixture(scope="module")
def allowlist_client() -> Iterator[PerCallClient]:
    """One container in allowlist mode shared by the module (the session container runs the default denylist)."""
    c = docker_image_ctl.start(env={"GVMCP_ATTR_POLICY": "allowlist"})
    try:
        yield PerCallClient(c.mcp_url)
    finally:
        c.remove()


@pytest.mark.parametrize("name", list(HOSTILE))
async def test_hostile_dot_is_stopped_in_allowlist_mode(allowlist_client: Any, name: str) -> None:
    r = await allowlist_client.call_tool("dot", {"input": HOSTILE[name]})
    assert r.is_error and any(k in text_of(r) for k in ("policy", "invalid input")), text_of(r)[:200]


@pytest.mark.parametrize("scope", ["G", "N", "E", "A"])
@pytest.mark.parametrize("attr", ["image", "Image", "shapefile", "imagepath", "fontpath", "stylesheet"])
async def test_hostile_parameter_is_refused(docker_image_client: Any, scope: str, attr: str) -> None:
    r = await docker_image_client.call_tool("dot", {"input": "digraph{a}", scope: {attr: "/etc/passwd"}})
    assert r.is_error and "policy" in text_of(r), text_of(r)[:200]


@pytest.mark.parametrize("name", list(BENIGN))
async def test_benign_dot_is_not_flagged(docker_image_client: Any, name: str) -> None:
    r = await docker_image_client.call_tool("dot", {"input": BENIGN[name]})
    assert not r.is_error, text_of(r)[:200]


async def test_allowed_parameters_pass(docker_image_client: Any) -> None:
    args = {"input": "digraph{a [shape=box]}", "G": {"rankdir": "LR"}, "N": {"color": "red"}}
    r = await docker_image_client.call_tool("dot", args)
    assert not r.is_error, text_of(r)[:200]


async def test_syntax_error_is_invalid_input_not_a_policy_violation(docker_image_client: Any) -> None:
    r = await docker_image_client.call_tool("dot", {"input": "digraph { a -> "})
    assert r.is_error and "invalid input" in text_of(r) and "policy" not in text_of(r), text_of(r)[:200]


async def test_unlisted_file_attribute_is_the_documented_denylist_gap(
    docker_image_client: Any, allowlist_client: Any
) -> None:
    """Denylist fails open for unclassified names; allowlist is the secure mode."""
    src = "digraph { a [somefuturefileattr=x] }"
    assert not (await docker_image_client.call_tool("dot", {"input": src})).is_error
    r = await allowlist_client.call_tool("dot", {"input": src})
    assert r.is_error and "allow list" in text_of(r), text_of(r)[:200]


async def test_unrestricted_mode_skips_the_policy_entirely(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_ATTR_POLICY": "unrestricted"})
    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("dot", {"input": "digraph{a}", "G": {"image": "x"}})
        assert not r.is_error, text_of(r)[:200]
        r = await mcp.call_tool("dot", {"input": "this is not dot"})  # nothing parses it first: Graphviz itself fails
        assert r.is_error and "policy" not in text_of(r)


def test_scan_extracts_everything_from_real_nop_output(docker_image_server: Any) -> None:
    out = docker_image_server.cli("nop", [], SCAN_SRC)
    assert out.returncode == 0, out.stderr.decode()
    scan = scan_canonical(out.stdout.decode())
    names = {(u.name, u.depth) for u in scan.uses}
    assert ("image", 1) in names  # "ima"+"ge" is folded by Graphviz's own parser
    assert {"Image", "Shapefile", "style", "stylesheet", "label", "fontpath", "shape", "color"} <= {
        u.name for u in scan.uses
    }
    assert next(u for u in scan.uses if u.name == "stylesheet").depth == 2
    assert scan.html_img == 1
