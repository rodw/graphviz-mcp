"""Concurrent mixed workloads, queue limits and cancellation under load, against the Docker image."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
import pytest
from mcp import Client

from tests.support.docker_image_ctl import Container
from tests.support.helpers import first_text, text_of

pytestmark = pytest.mark.docker_image


async def call(url: str, tool: str, args: dict[str, Any]) -> Any:
    async with Client(url) as c:
        return await c.call_tool(tool, args)


async def settle(c: Container, seconds: float = 8.0) -> list[str]:
    end = time.monotonic() + seconds
    while True:
        left = c.graphviz_processes()
        if not left or time.monotonic() > end:
            return left
        await asyncio.sleep(0.25)


async def test_mixed_fast_and_medium_calls_run_in_parallel(container_factory: Any) -> None:
    docker_image_server = container_factory(env={"GVMCP_QUEUE_SIZE": "200"})
    url = docker_image_server.mcp_url
    medium = first_text(await call(url, "gvgen", {"g": "35,35"}))
    jobs = [call(url, "dot", {"input": f"digraph {{ a{i} -> b{i} }}"}) for i in range(30)]
    jobs += [call(url, "dot", {"input": medium, "T": "svg"}) for _ in range(10)]
    jobs += [call(url, "neato", {"input": f"graph {{ x{i} -- y{i} -- z{i} }}", "T": "png"}) for i in range(10)]
    started = time.monotonic()
    results = await asyncio.gather(*jobs)
    elapsed = time.monotonic() - started
    assert all(not r.is_error for r in results), [text_of(r)[:100] for r in results if r.is_error]
    assert elapsed < 60
    assert await settle(docker_image_server) == []


async def test_results_are_not_mixed_up_between_concurrent_calls(container_factory: Any) -> None:
    url = container_factory(env={"GVMCP_QUEUE_SIZE": "200"}).mcp_url
    results = await asyncio.gather(
        *(call(url, "dot", {"input": f'digraph {{ "unique_{i}" -> "other_{i}" }}'}) for i in range(25))
    )
    for i, r in enumerate(results):
        assert f"unique_{i}" in first_text(r) and f"unique_{(i + 1) % 25}" not in first_text(r)


async def test_queue_full_gives_fast_busy_errors_and_recovers(container_factory: Any) -> None:
    c = container_factory(
        env={"GVMCP_CONCURRENCY": "1", "GVMCP_QUEUE_SIZE": "1", "GVMCP_TIMEOUT_S": "4", "GVMCP_QUEUE_WAIT_S": "30"}
    )
    k60 = first_text(await call(c.mcp_url, "gvgen", {"k": 60}))
    started = time.monotonic()
    times: list[float] = []

    async def timed() -> Any:
        r = await call(c.mcp_url, "dot", {"input": k60})
        times.append(time.monotonic() - started)
        return r

    results = await asyncio.gather(*(timed() for _ in range(6)))
    texts = [text_of(r) for r in results]
    busy = [t for t in texts if "server busy" in t]
    timeouts = [t for t in texts if "timeout" in t]
    assert len(busy) >= 3 and len(timeouts) >= 1, texts
    assert sorted(times)[0] < 3, "busy rejections must be immediate, not wait for the running call"
    assert await settle(c) == []
    ok = await call(c.mcp_url, "dot", {"input": "digraph { a -> b }"})
    assert not ok.is_error
    assert httpx2.get(f"{c.base}/ready").json()["queued_calls"] == 0


async def test_cancelling_a_call_kills_only_that_calls_processes(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_TIMEOUT_S": "120", "GVMCP_CONCURRENCY": "4"})
    k60 = first_text(await call(c.mcp_url, "gvgen", {"k": 60}))
    async with Client(c.mcp_url) as slow_client, Client(c.mcp_url) as other:
        slow = asyncio.create_task(slow_client.call_tool("dot", {"input": k60}))
        await asyncio.sleep(1.5)
        first = {p.split()[0] for p in c.graphviz_processes()}
        assert len(first) == 1, c.graphviz_processes()
        survivor = asyncio.create_task(other.call_tool("dot", {"input": k60}))  # a second, equally slow call
        await asyncio.sleep(1.5)
        both = {p.split()[0] for p in c.graphviz_processes()}
        assert len(both) == 2 and first < both
        slow.cancel()
        with pytest.raises(asyncio.CancelledError):
            await slow
        end = time.monotonic() + 10
        while time.monotonic() < end and {p.split()[0] for p in c.graphviz_processes()} != both - first:
            await asyncio.sleep(0.25)
        assert {p.split()[0] for p in c.graphviz_processes()} == both - first, (
            "cancel must kill exactly that call's process"
        )
        assert not survivor.done()
        survivor.cancel()
    assert await settle(c) == []


async def test_client_disconnect_does_not_leave_processes(container_factory: Any) -> None:
    c = container_factory(env={"GVMCP_TIMEOUT_S": "120"})
    k60 = first_text(await call(c.mcp_url, "gvgen", {"k": 60}))
    async with Client(c.mcp_url) as cl:
        t = asyncio.create_task(cl.call_tool("dot", {"input": k60}))
        await asyncio.sleep(1.5)
        assert c.graphviz_processes()
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    assert await settle(c, 10) == [], "Graphviz kept running after its caller went away"


async def test_stress_leaves_no_processes_and_server_ready(container_factory: Any) -> None:
    docker_image_server = container_factory(env={"GVMCP_QUEUE_SIZE": "500"})
    url = docker_image_server.mcp_url
    jobs = [call(url, ("dot", "neato", "fdp", "circo", "twopi")[i % 5], {"input": f"digraph {{ a{i} -> b{i} -> c{i} }}", "T": ("svg", "png", "plain")[i % 3]})
            for i in range(120)]  # fmt: skip
    results = await asyncio.gather(*jobs)
    assert all(not r.is_error for r in results), [text_of(r)[:100] for r in results if r.is_error][:3]
    assert await settle(docker_image_server) == []
    procs = docker_image_server.processes()
    # the server alone; its command line reads `graphviz-mcp` normally, `python -m coverage run ... graphviz_mcp` when instrumented
    assert len(procs) == 1 and ("graphviz-mcp" in procs[0] or "graphviz_mcp" in procs[0]), procs
    assert httpx2.get(f"{docker_image_server.base}/ready").status_code == 200
