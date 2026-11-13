# Contributing

Issues and pull requests are welcome. This guide covers setting up a development environment, how the repository is laid out, and how changes and releases move through the git-flow branches. If you think you have found a security problem, follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## Development setup

You need Docker with a running daemon, `make`, and Python 3.13 or newer with `venv`. `make audit.prereqs` checks that all three are there.

```bash
git clone https://github.com/rodw/graphviz-mcp.git
cd graphviz-mcp
make install      # create .venv and install the dev dependencies
make test.unit    # confirm the setup works
```

## Everyday tasks

Everything goes through `make`. `make help` lists the common targets and `make help-all` lists all of them.

```bash
make audit.python             # ruff (lint and format check) and mypy
make update.python.codestyle  # apply the formatting ruff wants
make test.unit                # unit tests
make test.docker-image        # image tests (builds the image first if it is stale)
make test                     # unit and image tests
make audit                    # licenses, release version, generated docs, Python lint and types, Dockerfile lint
make test-coverage.unit       # unit tests with a coverage report
make test-coverage.docker-image  # image tests with a coverage report (builds the coverage image first if it is stale)
make test-coverage            # unit and image tests with one combined coverage report
```

The coverage targets enforce minimum net line coverage of `src/graphviz_mcp`: 65% for the unit tests (`make test-coverage.unit`), 85% for the image tests (`make test-coverage.docker-image`) and 90% for the two combined (`make test-coverage`). They fail when coverage is lower. The limits are the `COVERAGE_MIN_UNIT`, `COVERAGE_MIN_DOCKER` and `COVERAGE_MIN_COMBINED` variables in the Makefile; override one on the command line (for example `make test-coverage.unit COVERAGE_MIN_UNIT=0 PYTEST_ARGS='-k runner'`) when you run only part of a suite.

The unit tests need neither Graphviz nor Docker. Tests that depend on the pinned Graphviz (golden SVGs, renderers, security, concurrency) are marked `docker_image` and run against the built image. If a change to the image or to the test inputs alters the golden SVGs, regenerate them with `make update.test-fixtures.golden`.

### Building and running the image

```bash
make build    # build graphviz-mcp:dev
make start    # run the HTTP server in the background on 127.0.0.1:8000
```

The Dockerfile requires an `APP_VERSION` build argument, so a bare `docker build .` fails. The `make` targets read the version from `pyproject.toml` and pass it for you.

`make status`, `make logs`, `make stop` and `make restart` manage the background server. `make run-http` and `make run-stdio` run it in the foreground. Set `SERVICE_IMAGE_TAG` to pick a different image tag (default `dev`) and `HTTP_PORT` to change the host port (default 8000).

### Generated files

`docs/graphviz-tools.md` and `THIRD_PARTY_NOTICES.md` are generated. After you change a tool spec, run `make update.docs.tools-md`. After you change dependencies, run `make update.docs.notices-md`. `make update` refreshes everything, and `make audit.docs` fails if a generated file is out of date. When `pyproject.toml` dependencies change, `make install.python.reinstall-deps` regenerates `requirements.lock`.

## Project structure

```
src/graphviz_mcp/
  tools/        tool specs, catalog, argv builder, registry, service layer
  policy/       attribute policy engine, loader, defaults, raster budget
  web/          Web UI rendering and static assets
  data/         attribute lists and descriptions, DOT language reference
  runner.py     the only place a process is spawned
  server.py     MCP and HTTP server wiring and startup
  app.py        the assembled App object (settings, capabilities, runner, service, MCP server)
  meta.py       server instructions text and package version
  extras.py     validate_dot, get_capabilities
  config.py     GVMCP_* settings
docs/
  mcp-service.md                tools, resources and prompts
  graphviz-tools.md             generated reference for every tool parameter
  web-ui.md                     the Web UI (screenshots are in docs/screenshots/)
  configuration.md              GVMCP_* environment variables
  attribute-security-policy.md  how to choose an attribute policy
scripts/        doc generators, license check, release version check, prerequisite check
tests/          unit tests, Docker image integration tests, golden fixtures
.github/        CI and release workflows, Dependabot and release notes configuration
```

[specs.py](src/graphviz_mcp/tools/specs.py) is the single source of truth for flags, types and limits. The MCP schemas, the argv builder, the Web UI forms, the docs and the name-conformance tests are all generated from it.

## Continuous integration

[ci.yml](.github/workflows/ci.yml) runs on pushes to `main`, `develop`, `release/**` and `hotfix/**`, and on every pull request. It runs lint, type checks, unit tests (with the unit coverage minimum) and the license check, then lints the Dockerfile. It also builds the image on amd64 and arm64 and runs the image tests, a Trivy scan and a size check on each. On amd64 it then re-runs the image tests against a coverage-instrumented image and enforces the image and combined coverage minimums.

The Dockerfile pins the base image by digest and the Graphviz source by SHA-256, and the final stage has no compiler. Dependabot opens its update pull requests against `develop`.

## Git branching model

The project follows git-flow.

* `develop` is the default branch, where finished work accumulates.
* `main` holds released code. Every release is a `vX.Y.Z` tag on `main`.
* `feature/*` branches start from `develop` and come back to it through a pull request.
* `release/*` branches start from `develop` to prepare a release. `hotfix/*` branches start from `main` for urgent fixes. Both are merged into `main`, then back into `develop`.

## Submitting changes

1. Branch from `develop` and keep the change focused on one thing.
2. Add or update tests. If the change affects Graphviz behavior, run the image tests too.
3. Run `make test` and `make audit`. At the least, `make audit.python` and `make test.unit` should pass.
4. Update the documentation when behavior a user can see changes, and regenerate the generated files (see above).
5. Open a pull request against `develop`. Say what changed and why, and give it a label from the next section.

## Pull request labels

Release notes are generated from the titles of merged pull requests and grouped by label, using [.github/release.yml](.github/release.yml). A pull request lands in the first section below that matches one of its labels.

| Label | Section in the release notes |
|---|---|
| `breaking` | Breaking changes |
| `enhancement`, `feature` | New features |
| `bug`, `fix` | Bug fixes |
| `dependencies` | Dependencies (Dependabot adds this label itself) |
| `documentation` | Documentation |
| `skip-changelog` | Left out of the notes |
| anything else | Other changes |

Write the title as you want it to read in the notes. Use `skip-changelog` on release and back-merge pull requests.

## Releasing

Pushing a `vX.Y.Z` tag on `main` starts [release.yml](.github/workflows/release.yml). The steps below use the git-flow commands.

1. Start the release branch from `develop`: `git flow release start X.Y.Z`.
2. Set `version` in `pyproject.toml` to `X.Y.Z`. Nothing else needs editing, because the image labels and the `--version` output come from that one value. Run `make audit.release-version` and `make test`, then commit.
3. Finish the release: `git flow release finish -m "Release X.Y.Z" X.Y.Z`. This merges into `main`, tags `vX.Y.Z` and merges back into `develop`. The tag must read `v` plus the `pyproject.toml` version, or the workflow stops.
4. Push both branches and the tag: `git push origin main develop --follow-tags`.

If `main` and `develop` require pull requests, push the release branch and merge it through pull requests instead, then push the tag once `main` has the release commit.

The workflow checks that the tagged commit is on `main`, that the tag matches the project version, and that [ci.yml](.github/workflows/ci.yml) has a successful run for that commit (it waits for one that is still in progress; if CI failed, fix it and re-run the workflow or tag again). It builds the image for amd64 and arm64, scans each pushed image with the same Trivy and size checks as CI (a failed scan stops the release before any tag is created, leaving only an untagged image in the registry), publishes it to `ghcr.io/rodw/graphviz-mcp` as `X.Y.Z`, `X.Y` and `latest`, and creates a GitHub Release with generated notes. A tag with a suffix, such as `v1.0.0-rc1`, becomes a pre-release and leaves `latest` alone. It still has to be on `main`.
