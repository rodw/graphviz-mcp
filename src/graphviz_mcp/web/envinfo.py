"""The ``GVMCP_*`` settings as shown in the Web UI: one metadata table, effective values from ``Settings``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import ENV_PREFIX, Settings


@dataclass(frozen=True)
class EnvVar:
    name: str  # without the GVMCP_ prefix
    field: str  # attribute of Settings
    group: str
    default: str
    meaning: str

    @property
    def env(self) -> str:
        return ENV_PREFIX + self.name


GROUPS = ("Network", "Limits", "Attribute policy", "Runtime")

# fmt: off
ENV_VARS: tuple[EnvVar, ...] = (
    EnvVar("HOST", "host", "Network", "127.0.0.1 (0.0.0.0 in the Docker image)", "HTTP bind address."),
    EnvVar("PORT", "port", "Network", "8000", "HTTP port (1-65535)."),
    EnvVar("ALLOWED_HOSTS", "allowed_hosts", "Network", "(localhost names only)",
           "Extra Host header values to accept, comma separated (name, name:port or name:*)."),
    EnvVar(
        "TIMEOUT_S", "timeout_s", "Limits", "30",
        "Wall-clock time limit per tool request, in seconds. Time spent waiting for a free slot is not counted.",
    ),
    EnvVar("MAX_INPUT_BYTES", "max_input_bytes", "Limits", "1000000", "Largest accepted input."),
    EnvVar("MAX_OUTPUT_BYTES", "max_output_bytes", "Limits", "20000000",
           "Output is cut off and the run killed beyond this."),
    EnvVar("MAX_STDERR_BYTES", "max_stderr_bytes", "Limits", "64000", "Stderr kept per run."),
    EnvVar("MEMORY_MB", "memory_mb", "Limits", "4096", "Address-space limit per Graphviz process; 0 disables."),
    EnvVar("CONCURRENCY", "concurrency", "Limits", "CPU count", "Simultaneous Graphviz calls."),
    EnvVar("QUEUE_SIZE", "queue_size", "Limits", "4 x concurrency", "Calls allowed to wait for a free slot."),
    EnvVar("QUEUE_WAIT_S", "queue_wait_s", "Limits", "30",
           "How long a call may wait before the server answers \"busy\"."),
    EnvVar("MAX_RASTER_PIXELS", "max_raster_pixels", "Limits", "50000000", "Pixel budget for raster output."),
    EnvVar("RASTER_PREFLIGHT", "raster_preflight", "Limits", "true",
           "Run a layout pre-flight that enforces the raster budget before rendering."),
    EnvVar("ATTR_POLICY", "attr_policy", "Attribute policy", "denylist",
           "Policy mode: denylist, allowlist or unrestricted."),
    EnvVar("ATTR_POLICY_FILE", "attr_policy_file", "Attribute policy", "(not set)", "TOML file of policy overrides."),
    EnvVar("GRAPHVIZ_BIN", "graphviz_bin", "Runtime", "(found on PATH; /opt/graphviz/bin in the Docker image)",
           "Directory containing the Graphviz programs."),
    EnvVar("TMP_DIR", "tmp_dir", "Runtime", "(system temp dir)", "Scratch directory for Graphviz runs."),
    EnvVar("LOG_LEVEL", "log_level", "Runtime", "INFO", "DEBUG, INFO, WARNING or ERROR (JSON lines on stderr)."),
)
# fmt: on


def display(value: Any) -> str:
    if value is None or value == () or value == "":
        return "(not set)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple | list):
        return ", ".join(str(v) for v in value)
    return str(value)


def rows(settings: Settings) -> list[dict[str, str]]:
    """Every variable with its effective value (what the server is running with, not the raw environment)."""
    return [
        {
            "group": v.group,
            "env": v.env,
            "value": display(getattr(settings, v.field)),
            "default": v.default,
            "meaning": v.meaning,
        }
        for v in ENV_VARS
    ]
