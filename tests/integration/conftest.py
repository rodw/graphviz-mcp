from __future__ import annotations

import pytest

from tests.support import docker_image_ctl
from tests.support.clients import PerCallClient


@pytest.fixture(scope="session")
def docker_image_server():  # type: ignore[no-untyped-def]
    """One hardened container with default settings for the whole session."""
    c = docker_image_ctl.start()
    yield c
    c.remove()


@pytest.fixture
def container_factory():  # type: ignore[no-untyped-def]
    """Start containers with custom env/mounts; all are removed afterwards."""
    made = []

    def make(**kw):  # type: ignore[no-untyped-def]
        c = docker_image_ctl.start(**kw)
        made.append(c)
        return c

    yield make
    for c in made:
        c.remove()


@pytest.fixture
def docker_image_client(docker_image_server):  # type: ignore[no-untyped-def]
    return PerCallClient(docker_image_server.mcp_url)
