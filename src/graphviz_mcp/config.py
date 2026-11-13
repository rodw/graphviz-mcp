"""Typed settings read from ``GVMCP_*`` environment variables, validated at startup."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

ENV_PREFIX = "GVMCP_"
POLICY_MODES = ("denylist", "allowlist", "unrestricted")


class ConfigError(ValueError):
    """Raised when the environment holds an invalid setting (the server refuses to start)."""


@dataclass(frozen=True)
class Settings:
    graphviz_bin: Path
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_hosts: tuple[str, ...] = ()
    timeout_s: float = 30.0
    max_input_bytes: int = 1_000_000
    max_output_bytes: int = 20_000_000
    max_stderr_bytes: int = 64_000
    memory_mb: int = 4096
    concurrency: int = field(default_factory=lambda: max(1, os.cpu_count() or 1))
    queue_size: int = 0
    queue_wait_s: float = 30.0
    log_level: str = "INFO"
    attr_policy: str = "denylist"
    attr_policy_file: Path | None = None
    raster_preflight: bool = True
    max_raster_pixels: int = 50_000_000
    tmp_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.queue_size <= 0:
            object.__setattr__(self, "queue_size", 4 * self.concurrency)

    @property
    def cpu_limit_s(self) -> int:
        return int(self.timeout_s) + 5


def _get(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(ENV_PREFIX + name)
    return None if value is None or value.strip() == "" else value.strip()


def _num(env: Mapping[str, str], name: str, default: float, *, minimum: float, integer: bool) -> float:
    raw = _get(env, name)
    if raw is None:
        return default
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ConfigError(
            f"{ENV_PREFIX}{name} must be {'an integer' if integer else 'a number'}, got {raw!r}"
        ) from None
    if value < minimum:
        raise ConfigError(f"{ENV_PREFIX}{name} must be >= {minimum}, got {raw!r}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _get(env, name)
    if raw is None:
        return default
    low = raw.lower()
    if low in ("1", "true", "yes", "on"):
        return True
    if low in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{ENV_PREFIX}{name} must be a boolean, got {raw!r}")


def find_graphviz_bin(env: Mapping[str, str]) -> Path:
    raw = _get(env, "GRAPHVIZ_BIN")
    if raw is not None:
        path = Path(raw)
    else:
        dot = shutil.which("dot", path=env.get("PATH"))
        if dot is None:
            raise ConfigError(f"Graphviz not found: set {ENV_PREFIX}GRAPHVIZ_BIN to the directory holding 'dot'")
        path = Path(dot).resolve().parent
    if not (path / "dot").is_file():
        raise ConfigError(f"{ENV_PREFIX}GRAPHVIZ_BIN={str(path)!r} does not contain 'dot'")
    return path


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    policy = (_get(env, "ATTR_POLICY") or "denylist").lower()
    if policy not in POLICY_MODES:
        raise ConfigError(f"{ENV_PREFIX}ATTR_POLICY must be one of {POLICY_MODES}, got {policy!r}")
    policy_file = _get(env, "ATTR_POLICY_FILE")
    level = (_get(env, "LOG_LEVEL") or "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ConfigError(f"{ENV_PREFIX}LOG_LEVEL must be DEBUG/INFO/WARNING/ERROR, got {level!r}")
    tmp = _get(env, "TMP_DIR")
    hosts = tuple(h.strip() for h in (_get(env, "ALLOWED_HOSTS") or "").split(",") if h.strip())
    port = int(_num(env, "PORT", 8000, minimum=1, integer=True))
    if port > 65535:
        raise ConfigError(f"{ENV_PREFIX}PORT must be <= 65535")
    concurrency = int(_num(env, "CONCURRENCY", max(1, os.cpu_count() or 1), minimum=1, integer=True))
    return Settings(
        graphviz_bin=find_graphviz_bin(env),
        host=_get(env, "HOST") or "127.0.0.1",
        port=port,
        allowed_hosts=hosts,
        timeout_s=_num(env, "TIMEOUT_S", 30.0, minimum=0.1, integer=False),
        max_input_bytes=int(_num(env, "MAX_INPUT_BYTES", 1_000_000, minimum=1, integer=True)),
        max_output_bytes=int(_num(env, "MAX_OUTPUT_BYTES", 20_000_000, minimum=1, integer=True)),
        max_stderr_bytes=int(_num(env, "MAX_STDERR_BYTES", 64_000, minimum=0, integer=True)),
        memory_mb=int(_num(env, "MEMORY_MB", 4096, minimum=0, integer=True)),
        concurrency=concurrency,
        queue_size=int(_num(env, "QUEUE_SIZE", 0, minimum=0, integer=True)),
        queue_wait_s=_num(env, "QUEUE_WAIT_S", 30.0, minimum=0.0, integer=False),
        log_level=level,
        attr_policy=policy,
        attr_policy_file=Path(policy_file) if policy_file else None,
        raster_preflight=_bool(env, "RASTER_PREFLIGHT", True),
        max_raster_pixels=int(_num(env, "MAX_RASTER_PIXELS", 50_000_000, minimum=1, integer=True)),
        tmp_dir=Path(tmp) if tmp else None,
    )
