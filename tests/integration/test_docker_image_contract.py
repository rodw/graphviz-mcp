"""The built Docker image honors its contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from graphviz_mcp.tools import catalog
from tests.support import docker_image_ctl
from tests.support.docker_image_ctl import DOCKER_IMAGE, HARDENING, coverage_args, docker
from tests.support.helpers import first_text

pytestmark = pytest.mark.docker_image
ROOT = Path(__file__).resolve().parents[2]


def sh(script: str, *flags: str) -> subprocess.CompletedProcess[bytes]:
    return docker("run", "--rm", *flags, "--entrypoint", "sh", DOCKER_IMAGE, "-c", script, check=False)


def test_pinned_graphviz_version_matches_dockerfile() -> None:
    pinned = re.search(r"ARG GV_VERSION=(\S+)", (ROOT / "Dockerfile").read_text())
    assert pinned
    out = sh("/opt/graphviz/bin/dot -V 2>&1").stdout.decode()
    assert f"graphviz version {pinned.group(1)} " in out
    labels = json.loads(docker("inspect", "-f", "{{json .Config.Labels}}", DOCKER_IMAGE).stdout)
    assert (
        labels["io.github.rodw.graphviz-mcp.graphviz.version"] == pinned.group(1)
        and labels["org.opencontainers.image.licenses"] == "MIT"
    )


def test_base_docker_image_is_pinned_by_tag_and_digest() -> None:
    first = re.search(r"ARG DEBIAN_IMAGE_BASENAME=(\S+)", (ROOT / "Dockerfile").read_text())
    assert first and re.fullmatch(r"debian:trixie-slim", first.group(1))
    second = re.search(r'ARG DEBIAN_IMAGE="?(\S+?)"?\s*$', (ROOT / "Dockerfile").read_text(), re.MULTILINE)
    pinned = re.escape("${DEBIAN_IMAGE_BASENAME}") + r"@sha256:[0-9a-f]{64}"
    assert second and re.fullmatch(pinned, second.group(1))
    assert re.search(r"ARG GV_SHA256=[0-9a-f]{64}", (ROOT / "Dockerfile").read_text())


def test_runs_as_non_root_user() -> None:
    assert sh("id -u").stdout.decode().strip() == "10001"
    assert json.loads(docker("inspect", "-f", "{{json .Config.User}}", DOCKER_IMAGE).stdout) == "10001:10001"


def test_no_compilers_dev_packages_or_package_manager_caches() -> None:
    out = sh("command -v gcc cc c++ make pkg-config cmake; dpkg -l | awk '{print $2}' | grep -E -- '-dev(:|$)'; "
             "ls /var/lib/apt/lists | grep -v '^partial$' | wc -l; ls /root/.cache 2>&1 | head -1").stdout.decode()  # fmt: skip
    assert "gcc" not in out and "-dev" not in out and "make" not in out
    assert out.strip().splitlines()[0] == "0" or "No such file" in out


def test_plugin_config_generated_at_build_time() -> None:
    assert sh("test -s /opt/graphviz/lib/graphviz/config8").returncode == 0


def test_fonts_map_to_metric_compatible_families() -> None:
    out = sh("HOME=/tmp fc-match Helvetica; HOME=/tmp fc-match Times; HOME=/tmp fc-match Courier; HOME=/tmp fc-match 'DejaVu Sans'",
             "--tmpfs", "/tmp").stdout.decode()  # fmt: skip
    assert (
        '"Liberation Sans"' in out
        and '"Liberation Serif"' in out
        and '"Liberation Mono"' in out
        and '"DejaVu Sans"' in out
    )


def test_licenses_and_notices_are_in_the_docker_image() -> None:
    script = ("test -s /usr/share/doc/graphviz-mcp/LICENSE && test -s /usr/share/doc/graphviz-mcp/THIRD_PARTY_NOTICES.md && "
              "test -s /opt/graphviz/share/licenses/COPYING && test -s /opt/graphviz/share/licenses/cpl1.0.txt && "
              "test -s /usr/share/doc/fonts-dejavu-core/copyright && test -s /usr/share/doc/fonts-liberation/copyright && "
              "test -s /usr/share/doc/libcairo2/copyright && grep -q 'Eclipse Public License' /opt/graphviz/share/licenses/COPYING && grep -q 'Common Public License' /opt/graphviz/share/licenses/cpl1.0.txt")  # fmt: skip
    r = sh(script)
    assert r.returncode == 0, r.stderr.decode()
    assert b"MIT License" in sh("cat /usr/share/doc/graphviz-mcp/LICENSE").stdout


def test_every_installed_graphviz_executable_is_classified() -> None:
    names = set(sh("ls /opt/graphviz/bin").stdout.decode().split())
    assert {"dot", "nop", "ccomps", "gvgen", "mingle", "edgepaint", "gvmap"} <= names
    unclassified, missing = catalog.classify(names)
    assert unclassified == [], f"classify these in tools/catalog.py: {unclassified}"
    assert missing == [], f"expected no missing tools in tools/catalog.py, found {missing}"


def test_healthcheck_is_defined_and_passes() -> None:
    hc = json.loads(docker("inspect", "-f", "{{json .Config.Healthcheck}}", DOCKER_IMAGE).stdout)
    assert hc and "/health" in " ".join(hc["Test"])
    c = docker_image_ctl.start()
    try:
        r = c.exec("python3", ["-c", " ".join(hc["Test"][1:]) if hc["Test"][0] == "CMD-SHELL" else hc["Test"][-1]])
        assert r.returncode == 0, r.stderr.decode()
    finally:
        c.remove()


def test_docker_image_size_is_reasonable() -> None:
    unpacked_kb = int(sh("du -skx / 2>/dev/null | cut -f1").stdout)
    print(f"unpacked filesystem: {unpacked_kb / 1000:.0f} MB")
    assert unpacked_kb < 450_000  # about 300 MB measured; the README reports the number


def test_server_works_with_readonly_rootfs_dropped_caps_and_no_network() -> None:
    """stdio mode under the documented hardened flags: --read-only --cap-drop=ALL --network=none."""
    import asyncio

    async def run() -> None:
        params = StdioServerParameters(
            command="docker",
            args=["run", "-i", "--rm", "--network=none", *HARDENING, *coverage_args(), DOCKER_IMAGE, "--stdio"],
        )  # fmt: skip
        async with Client(params) as c:
            r = await c.call_tool("dot", {"input": "digraph { a -> b }", "T": "png"})
            assert not r.is_error and r.content[0].type == "image"
            r = await c.call_tool("get_capabilities", {})
            assert json.loads(first_text(r))["graphviz_version"] == "16.1.0"

    asyncio.run(run())


def test_http_default_is_reachable_through_a_localhost_publish(docker_image_server: docker_image_ctl.Container) -> None:
    import httpx2

    assert httpx2.get(f"{docker_image_server.base}/health").json()["status"] == "ok"
    ports = docker("port", docker_image_server.name).stdout.decode()
    assert "127.0.0.1:" in ports and "0.0.0.0" not in ports  # host-side publish keeps it on localhost


def test_container_never_runs_as_root_and_has_no_writable_root(docker_image_server: docker_image_ctl.Container) -> None:
    assert docker_image_server.exec("id", ["-u"]).stdout.decode().strip() == "10001"
    r = docker_image_server.exec("sh", ["-c", "touch /opt/should-fail 2>&1; touch /etc/should-fail 2>&1"])
    assert b"Read-only file system" in r.stdout or b"Permission denied" in r.stdout


def test_logs_are_json_lines_on_stderr(docker_image_server: docker_image_ctl.Container) -> None:
    lines = [ln for ln in docker_image_server.logs().splitlines() if ln.strip()]
    assert lines and all(json.loads(ln)["level"] for ln in lines if ln.startswith("{"))


def test_invalid_policy_file_stops_the_container(tmp_path: Path) -> None:
    bad = tmp_path / "policy.toml"
    bad.write_text("this = is not [valid")
    r = docker(
        "run",
        "--rm",
        "-v",
        f"{bad}:/policy.toml:ro",
        "-e",
        "GVMCP_ATTR_POLICY_FILE=/policy.toml",
        *coverage_args(),
        DOCKER_IMAGE,
        "--http",
        check=False,
    )
    assert r.returncode == 2 and b"policy file is not valid TOML" in r.stderr


def test_python_version_documented() -> None:
    out = sh("python3 --version").stdout.decode()
    assert out.startswith("Python 3.13") and sys.version_info >= (3, 13)
