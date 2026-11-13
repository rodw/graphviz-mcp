from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    from tests.support.docker_image_ctl import DOCKER_IMAGE, docker_image_available

    if any("docker_image" in item.keywords for item in items) and not docker_image_available():
        reason = f"Docker image {DOCKER_IMAGE} is not available (is docker installed? docker build -t {DOCKER_IMAGE} .)"
        if os.environ.get("GVMCP_REQUIRE_DOCKER") == "1":  # `make test.docker-image`: never go green by skipping
            pytest.exit(reason, returncode=2)
        skip_img = pytest.mark.skip(reason=reason)
        for item in items:
            if "docker_image" in item.keywords:
                item.add_marker(skip_img)
