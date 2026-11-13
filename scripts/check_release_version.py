#!/usr/bin/env python3
"""Fail if the project's release version is not used consistently

The version in pyproject.toml is the single source of truth. This checks that:

* the git release tag (when there is one) is ``v<version>``;
* the Dockerfile takes ``APP_VERSION`` as a build arg without a hardcoded default;
* the Makefile and every ``docker/build-push-action`` step in .github/workflows pass ``APP_VERSION``;
* version-pinned image references (``graphviz-mcp:X.Y.Z``) and ``docker build`` commands in the docs agree.

Usage: python scripts/check_release_version.py [--tag vX.Y.Z] [--require-tag]

The tag is taken from ``--tag``, else ``RELEASE_TAG``, else ``GITHUB_REF_NAME`` when ``GITHUB_REF_TYPE`` is ``tag``,
else ``git describe --exact-match --tags HEAD``. With no tag (or no git) the tag check is skipped with a notice,
unless ``--require-tag`` is given.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
IMAGE_REF = re.compile(r"graphviz-mcp:(\d+\.\d+\.\d+[0-9A-Za-z.-]*)")
DOC_FILES = ["README.md", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md"))]


def project_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def find_tag(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if os.environ.get("RELEASE_TAG"):
        return os.environ["RELEASE_TAG"]
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and os.environ.get("GITHUB_REF_NAME"):
        return os.environ["GITHUB_REF_NAME"]
    try:
        out = subprocess.run(
            ["git", "describe", "--exact-match", "--tags", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def workflow_steps(text: str) -> list[str]:
    """Split a workflow file into its ``- `` list items (steps), by indentation."""
    steps: list[list[str]] = []
    for line in text.splitlines():
        if re.match(r"^\s*- \w+:", line):
            steps.append([line])
        elif steps:
            steps[-1].append(line)
    return ["\n".join(s) for s in steps]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="release tag to check against (default: autodetect)")
    parser.add_argument("--require-tag", action="store_true", help="fail, rather than skip, if there is no tag")
    args = parser.parse_args()

    failures: list[str] = []
    version = project_version()
    if not SEMVER.match(version):
        failures.append(f"pyproject.toml version {version!r} is not X.Y.Z[-prerelease]")

    tag = find_tag(args.tag)
    if tag is None:
        if args.require_tag:
            failures.append("no release tag found (and --require-tag was given)")
        else:
            print("NOTE: no git tag at HEAD (or no git); tag check skipped", file=sys.stderr)
    elif tag != f"v{version}":
        failures.append(f"git tag {tag!r} does not match pyproject.toml version {version!r} (expected 'v{version}')")

    dockerfile = (ROOT / "Dockerfile").read_text()
    if not re.search(r"^ARG APP_VERSION\s*$", dockerfile, re.M):
        failures.append("Dockerfile: expected a bare `ARG APP_VERSION` (no default value)")
    if re.search(r"^\s*ARG APP_VERSION=", dockerfile, re.M):
        failures.append("Dockerfile: APP_VERSION must not have a hardcoded default")

    if "--build-arg APP_VERSION=" not in (ROOT / "Makefile").read_text():
        failures.append("Makefile: no `--build-arg APP_VERSION=` found")

    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for step in workflow_steps(wf.read_text()):
            if "docker/build-push-action" in step and "APP_VERSION=" not in step:
                first = step.splitlines()[0].strip()
                failures.append(
                    f"{wf.relative_to(ROOT)}: build-push-action step without build-args APP_VERSION ({first})"
                )

    for name in DOC_FILES:
        text = (ROOT / name).read_text()
        for n, line in enumerate(text.splitlines(), 1):
            for ref in IMAGE_REF.findall(line):
                if ref != version:
                    failures.append(f"{name}:{n}: image reference graphviz-mcp:{ref} != {version}")
            if (
                re.search(r"\bdocker build\b", line)
                and "Dockerfile.test-coverage" not in line
                and "APP_VERSION" not in line
            ):
                failures.append(f"{name}:{n}: `docker build` without --build-arg APP_VERSION")

    for f in failures:
        print(f"FAIL {f}", file=sys.stderr)
    if not failures:
        print(f"release version {version}: consistent" + (f" (tag {tag})" if tag else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
