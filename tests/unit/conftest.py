from __future__ import annotations

from pathlib import Path

import pytest

from graphviz_mcp.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings for unit tests; no Graphviz is ever started from them (the Docker image tests cover real programs)."""
    return Settings(
        graphviz_bin=Path("/nonexistent"),
        tmp_dir=tmp_path / "tmp",
        timeout_s=10,
        concurrency=4,
        queue_size=8,
        queue_wait_s=5,
    )
