"""Malicious input against the built Docker image: policy bypasses, resource exhaustion, error hygiene."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp.types import EmbeddedResource

from tests.support.cases import HOSTILE
from tests.support.docker_image_ctl import Container
from tests.support.helpers import first_text, text_of

pytestmark = pytest.mark.docker_image
LEAKS = ("/opt/graphviz", "/opt/venv", "/tmp/gvmcp-", "/usr/lib", "/usr/share", "/home/", "/root", "site-packages")
ERRORS: list[str] = []


def note(r: Any) -> None:
    if r.is_error:
        ERRORS.append(text_of(r))


async def settle(c: Container, seconds: float = 6.0) -> list[str]:
    """Wait until no Graphviz process is left in the container (or the time is up)."""
    end = time.monotonic() + seconds
    while True:
        left = c.graphviz_processes()
        if not left or time.monotonic() > end:
            return left
        await asyncio.sleep(0.25)


@pytest.mark.parametrize("name", list(HOSTILE))
async def test_hostile_dot_is_stopped_in_the_docker_image(docker_image_client: Any, name: str) -> None:
    r = await docker_image_client.call_tool("dot", {"input": HOSTILE[name]})
    note(r)
    assert r.is_error and any(k in text_of(r) for k in ("policy", "invalid input")), text_of(r)[:200]


async def test_hostile_dot_through_every_dot_input_tool(docker_image_client: Any) -> None:
    bad = 'digraph { a [image="/etc/passwd"]; b [label=<<IMG SRC="/etc/passwd"/>>] }'
    for tool, extra in (("neato", {}), ("fdp", {}), ("sfdp", {}), ("circo", {}), ("twopi", {}), ("osage", {}), ("patchwork", {}),
                        ("nop", {}), ("acyclic", {}), ("tred", {}), ("gvpack", {}), ("dijkstra", {"node": "a"}), ("gv2gml", {}),
                        ("dot2gxl", {}), ("unflatten", {}), ("ccomps", {}), ("gc", {})):  # fmt: skip
        r = await docker_image_client.call_tool(tool, {"input": bad, **extra})
        note(r)
        assert r.is_error and "policy" in text_of(r), tool


async def test_oversized_raster_requests_are_refused_quickly(docker_image_client: Any) -> None:
    started = time.monotonic()
    for src, extra in (('digraph { size="1000,1000!"; dpi=300; a }', {}), ("digraph { a }", {"G": {"dpi": "100000"}}),
                       ('digraph { size="500,500!"; a }', {"G": {"dpi": "300"}}), ('digraph { pad=500; a }', {"G": {"dpi": "300"}})):  # fmt: skip
        r = await docker_image_client.call_tool("dot", {"input": src, "T": "png", **extra})
        note(r)
        assert r.is_error, src
    assert time.monotonic() - started < 15


async def test_deep_nesting_and_long_labels_do_not_hurt_the_server(
    docker_image_client: Any, docker_image_server: Container
) -> None:
    deep = "digraph { " + "subgraph s { " * 400 + "a" + " }" * 400 + " }"
    r = await docker_image_client.call_tool("dot", {"input": deep})
    note(r)
    assert r.content  # either rendered or a clean error; never a hang or crash
    long_label = 'digraph { a [label="' + "x" * 900_000 + '"] }'
    r = await docker_image_client.call_tool("dot", {"input": long_label})
    note(r)
    assert r.content
    assert httpx2.get(f"{docker_image_server.base}/ready").status_code == 200


async def test_input_over_the_cap_is_rejected_without_running_graphviz(docker_image_client: Any) -> None:
    r = await docker_image_client.call_tool("dot", {"input": "digraph{" + "a;" * 600_000 + "}"})
    note(r)
    assert r.is_error and "limit" in text_of(r)


async def test_nul_and_control_characters_rejected(docker_image_client: Any) -> None:
    for kw in (
        {"input": "digraph{a}\x00"},
        {"input": "digraph{a}", "G": {"label": "x\x00y"}},
        {"input": "digraph{a}", "N": {"a\nb": "c"}},
    ):
        r = await docker_image_client.call_tool("dot", kw)
        note(r)
        assert r.is_error


async def test_timeout_kills_graphviz_and_server_recovers(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_TIMEOUT_S": "3"})
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        k60 = first_text(await mcp.call_tool("gvgen", {"k": 60}))
        started = time.monotonic()
        r = await mcp.call_tool("dot", {"input": k60})
        note(r)
        assert r.is_error and "timeout" in text_of(r) and time.monotonic() - started < 15
        assert await settle(c) == []
        ok = await mcp.call_tool("dot", {"input": "digraph { a -> b }"})
        assert not ok.is_error


async def test_output_flood_is_capped_and_process_killed(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_MAX_OUTPUT_BYTES": "20000"})
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        big = first_text(await mcp.call_tool("gvgen", {"g": "30,30"}))
        r = await mcp.call_tool("dot", {"input": big})
        note(r)
        assert r.is_error and "limit" in text_of(r)
        assert await settle(c) == []
        ok = await mcp.call_tool("dot", {"input": "digraph { a -> b }"})
        assert not ok.is_error


def emulated_docker_image() -> bool:
    """True when the Docker image architecture differs from the host's (Rosetta/QEMU need address space of their own)."""
    import platform

    from tests.support.docker_image_ctl import DOCKER_IMAGE, docker

    arch = docker("image", "inspect", "-f", "{{.Architecture}}", DOCKER_IMAGE).stdout.decode().strip()
    host = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(platform.machine().lower())
    return arch != host


async def test_memory_limit_contains_a_big_raster(container_factory: Any) -> None:
    if emulated_docker_image():  # evaluated lazily: collection must not need a docker executable
        pytest.skip("RLIMIT_AS cannot be tested under CPU emulation: the emulator itself needs address space")
    c = container_factory(env={"GVMCP_MEMORY_MB": "96"})
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("dot", {"input": 'digraph { size="30,30!"; a -> b }', "T": "png", "G": {"dpi": "200"}})
        note(r)
        assert r.is_error, "a ~36 megapixel png should not fit in 96 MB"
        assert await settle(c) == []
        assert not (await mcp.call_tool("dot", {"input": "digraph { a -> b }"})).is_error
        assert httpx2.get(f"{c.base}/ready").status_code == 200


async def test_svgz_output_is_bounded_by_the_output_cap(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_MAX_OUTPUT_BYTES": "30000"})
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool(
            "dot", {"input": "digraph { " + " ".join(f"n{i} -> n{i + 1};" for i in range(400)) + " }", "T": "svgz"}
        )
        item = r.content[0]
        assert r.is_error or (isinstance(item, EmbeddedResource) and item.resource.mime_type == "image/svg+xml")
        note(r)


async def test_file_loading_is_disabled_even_if_the_policy_lets_the_attribute_through(
    container_factory: Any, tmp_path: Path
) -> None:
    """Defense in depth: with an empty deny list the policy allows image=, Graphviz server mode still refuses to read it."""
    policy = tmp_path / "policy.toml"
    policy.write_text("deny = []\n")
    c = container_factory(env={"GVMCP_ATTR_POLICY_FILE": "/policy.toml"}, volumes={policy: "/policy.toml"})
    c.exec("sh", ["-c", "HOME=/tmp /opt/graphviz/bin/dot -Tpng > /tmp/pic.png"], "digraph{a}")
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        src = 'digraph { a [image="/tmp/pic.png", shape=box, label=""]; b [image="/etc/passwd"] }'
        r = await mcp.call_tool("dot", {"input": src})
        assert not r.is_error, text_of(r)
        assert "<image" not in first_text(r)
        assert "file loading is disabled" in text_of(r)


async def test_unrestricted_mode_does_load_files(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_ATTR_POLICY": "unrestricted"})
    c.exec("sh", ["-c", "HOME=/tmp /opt/graphviz/bin/dot -Tpng > /tmp/pic.png"], "digraph{a}")
    from mcp import Client

    async with Client(c.mcp_url) as mcp:
        r = await mcp.call_tool("dot", {"input": 'digraph { a [image="/tmp/pic.png", shape=box, label=""] }'})
        assert not r.is_error and "<image" in first_text(r)
    assert "UNRESTRICTED" in c.logs()


async def test_error_messages_leak_no_server_paths(docker_image_client: Any) -> None:
    for tool, args in (("dot", {"input": "digraph {"}), ("dot", {"input": "digraph { a [shape=nosuch] }", "T": "bogus"}),
                       ("dijkstra", {"input": "digraph{a}", "node": "-x"}), ("gxl2dot", {"input": "<not-gxl"}),
                       ("graphml2gv", {"input": "garbage"}),
                       ("mm2gv", {"input": "garbage"}), ("dot", {"input": 'digraph { a [image="x"] }'})):  # fmt: skip
        note(await docker_image_client.call_tool(tool, args))
    assert ERRORS, "no errors were collected"
    for text in ERRORS:
        assert not any(leak in text for leak in LEAKS), text[:300]


async def test_excluded_programs_are_not_callable(docker_image_client: Any) -> None:
    for name in (
        "gvpr",
        "gv2gxl",
        "gxl2gv",
        "dot_builtins",
        "dot_sandbox",
        "gvmap.sh",
        "sh",
        "bash",
        "ls",
    ):
        r = await docker_image_client.call_tool(name, {"input": "digraph{}"})
        assert r.is_error and "Unknown tool" in text_of(r), name


async def test_flags_that_touch_the_filesystem_are_not_parameters(docker_image_client: Any) -> None:
    for bad in ({"o": "/tmp/x"}, {"O": True}, {"l": "x"}, {"P": True}, {"c": True}, {"V": True}):
        r = await docker_image_client.call_tool("dot", {"input": "digraph{a}", **bad})
        assert r.is_error and "Extra inputs are not permitted" in text_of(r), bad
