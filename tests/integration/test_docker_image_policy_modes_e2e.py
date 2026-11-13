"""All three attribute-policy modes end to end through MCP and the Web UI, against the Docker image."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp import Client

from tests.support.helpers import first_text, text_of

pytestmark = pytest.mark.docker_image
UNKNOWN = "digraph { a [somethingunknown=1] }"
COMMON = "digraph { rankdir=LR; a [shape=box, color=red, label=hi]; a -> b [arrowhead=vee] }"


async def post_ui(base: str, tool: str, data: dict[str, str]) -> Any:
    async with httpx2.AsyncClient(base_url=base) as h:
        return await h.post(f"/ui/tools/{tool}", data=data, headers={"origin": base})


async def test_denylist_default(docker_image_client: Any, docker_image_server: Any) -> None:
    assert not (await docker_image_client.call_tool("dot", {"input": UNKNOWN})).is_error  # unknown names pass
    r = await docker_image_client.call_tool("dot", {"input": 'digraph { a [image="x"] }'})
    assert r.is_error and "deny list" in text_of(r)
    assert (
        await post_ui(docker_image_server.base, "dot", {"input": 'digraph { a [stylesheet="x"] }'})
    ).status_code == 403


async def test_allowlist_mode(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_ATTR_POLICY": "allowlist"})
    async with Client(c.mcp_url) as mcp:
        assert not (await mcp.call_tool("dot", {"input": COMMON})).is_error
        r = await mcp.call_tool("dot", {"input": UNKNOWN})
        assert r.is_error and "allow list" in text_of(r) and "somethingunknown" in text_of(r)
        r = await mcp.call_tool("dot", {"input": "digraph{a}", "N": {"somethingunknown": "1"}})
        assert r.is_error
        doc = json.loads(first_text(await mcp.call_tool("get_capabilities", {})))
        assert doc["attribute_policy"]["mode"] == "allowlist" and "shape" in doc["attribute_policy"]["allow"]
    assert (await post_ui(c.base, "dot", {"input": UNKNOWN})).status_code == 403
    assert (await post_ui(c.base, "dot", {"input": COMMON})).status_code == 200


async def test_unrestricted_mode(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_ATTR_POLICY": "unrestricted"})
    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("dot", {"input": 'digraph { dpi=1000; a [image="/nonexistent.png"] }', "T": "svg"})
        assert not r.is_error
        doc = json.loads(first_text(await mcp.call_tool("get_capabilities", {})))
        assert doc["attribute_policy"]["mode"] == "unrestricted"
        # the always-on limits still apply
        big = await mcp.call_tool("dot", {"input": "digraph{" + "a;" * 600_000 + "}"})
        assert big.is_error
    page = (await httpx2.AsyncClient().get(f"{c.base}/ui/capabilities")).text
    assert "Unrestricted" in page and "UNRESTRICTED" in c.logs()


async def test_operator_policy_file(container_factory: Any, tmp_path: Path) -> None:
    policy = tmp_path / "policy.toml"
    policy.write_text(
        'deny_add = ["label"]\n[constraints.dpi]\nmax = 100\n[constraints.splines]\nenum = ["line", "true"]\n'
    )
    c = container_factory(env={"GVMCP_ATTR_POLICY_FILE": "/policy.toml"}, volumes={policy: "/policy.toml"})
    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("dot", {"input": 'digraph { a [label="x"] }'})
        assert r.is_error and "label" in text_of(r)
        r = await mcp.call_tool("dot", {"input": "digraph { a }", "G": {"dpi": "150"}})
        assert r.is_error and "maximum" in text_of(r)
        r = await mcp.call_tool("dot", {"input": "digraph { splines=ortho; a }"})
        assert r.is_error and "allowed values" in text_of(r)
        assert not (
            await mcp.call_tool("dot", {"input": "digraph { splines=line; a -> b }", "G": {"dpi": "100"}})
        ).is_error
        r = await mcp.call_tool("dot", {"input": 'digraph { a [image="x"] }'})
        assert r.is_error  # built-in deny list still applies (deny_add extends it)
        doc = json.loads(first_text(await mcp.call_tool("get_capabilities", {})))
        assert "label" in doc["attribute_policy"]["deny"] and doc["attribute_policy"]["constraints"]["dpi"] == "max=100"
