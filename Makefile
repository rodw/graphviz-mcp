# graphviz-mcp: build, test, and service management targets (run `make help`)
# requires: GNU Make, bash, docker, and python 3 (see `make audit.prereqs`)
#------------------------------------------------------------------------------

#==================================================================== SET UP ==

#---------------------------------------------------------- make scaffolding --
.DEFAULT_GOAL := help
SHELL := bash
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules
.DELETE_ON_ERROR:
.PHONY: help help-all version version-porcelain audit.prereqs
.PHONY: install install.python install.python.venv install.python.venv-help
.PHONY: install.python.deps install.python.reinstall-deps
.PHONY: audit audit-build audit-all
.PHONY: audit.python audit.python.codestyle audit.python.lint audit.python.typecheck
.PHONY: audit.licenses audit.release-version audit.attribute-list
.PHONY: audit.docker audit.docker.dockerfile audit.docker.dockerfile.lint
.PHONY: audit.docker.dockerfile-test-coverage.lint
.PHONY: audit.docker.image audit.docker.image.scan audit.docker.image.size
.PHONY: audit.docker.image-run audit.docker.image.scan-run audit.docker.image.size-run
.PHONY: audit.docs audit.docs.tools-md audit.docs.notices-md
.PHONY: update update.python.codestyle fix.python.codestyle
.PHONY: update.docs update.docs.tools-md update.docs.notices-md
.PHONY: update.test-fixtures update.test-fixtures.golden update.attribute-list
.PHONY: build build.docker-image build.docker-image-coverage rebuild.docker-image
.PHONY: test test.unit test.docker-image
.PHONY: test-coverage test-coverage.unit test-coverage.docker-image test-coverage.docker-image-run
.PHONY: run run-http run-stdio start stop restart status logs
.PHONY: clean clean-all uninstall
.PHONY: clean.python clean.python.bytecode clean.python.caches clean.python.venv clean.stamps clean.macos
.PHONY: clean.test clean.test-coverage clean.test.cache
.PHONY: clean.docker clean.docker.containers clean.docker.images clean.docker.volumes
.PHONY: docker.build docker.image.build docker.dockerfile.lint
.PHONY: docker.dockerfile-test-coverage.lint docker.image.scan docker.image.size
.PHONY: docker.check-daemon docker.clean
#------------------------------------------------------------------------------

#----------------------------------------- overridable and derived variables --
HOST_DOCKER_EXE ?= docker
MIN_DOCKER_VERSION ?= 23.0
HOST_PYTHON_EXE ?= $(shell command -v python3.12 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python)
HOST_CURL_EXE ?= curl
VENV_DIR ?= .venv
VENV_BIN_DIR ?= ${VENV_DIR}/bin
VENV_PYTHON_EXE ?= ${VENV_BIN_DIR}/python
VENV_RUFF_EXE ?= ${VENV_BIN_DIR}/ruff
VENV_PYTEST_EXE ?= ${VENV_BIN_DIR}/pytest
VENV_MYPY_EXE ?= ${VENV_BIN_DIR}/mypy
#------------------------------------------------------------------------------
PYTEST_ARGS ?=
#------------------------------------------------------------------------------
toml_project = $(shell ${HOST_PYTHON_EXE} -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["$(1)"])')
APP_NAME = $(eval APP_NAME := $$(call toml_project,name))$(APP_NAME)
APP_VERSION = $(eval APP_VERSION := $$(call toml_project,version))$(APP_VERSION)
#------------------------------------------------------------------------------
DOCKER_IMAGE_NAME = ${APP_NAME}
COVERAGE_IMAGE ?= $(DOCKER_IMAGE_NAME):coverage
COVERAGE_DOCKER_DIR ?= .coverage-docker
COVERAGE_ALL_DIR ?= .coverage-all
#------------------------------------------------------------------------------
SERVICE_IMAGE_TAG ?= dev
SERVICE_IMAGE = $(DOCKER_IMAGE_NAME):$(SERVICE_IMAGE_TAG)
SERVICE_CONTAINER_NAME ?= $(DOCKER_IMAGE_NAME)-http
SERVICE_HTTP_BIND_ADDR ?= 127.0.0.1
SERVICE_HTTP_PORT ?= 8000
SERVICE_HARDENING_ARGS ?= --read-only --tmpfs /tmp:rw,noexec,nosuid,size=256m --cap-drop=ALL --security-opt no-new-privileges
SERVICE_DOCKER_ARGS ?=
SERVICE_START_TIMEOUT_SECONDS ?= 30
#------------------------------------------------------------------------------
AUDIT_IMAGE ?= $(DOCKER_IMAGE_NAME):dev
# 0 = report the image size only; set a ceiling (in MB) to fail above it.
# The size is the uncompressed size of the image's filesystem (`du` run inside the image). Unlike `docker image inspect`
# (compressed or uncompressed depending on the Docker storage backend), it is the same on every backend. It is larger
# for arm64 than for amd64, so the cap is sized for arm64 (about 278 MB at the time of writing) plus a little headroom.
MAX_DOCKER_IMAGE_SIZE_MB ?= 300
#------------------------------------------------------------------------------
HADOLINT_IMAGE_TAG ?= v2.15.1
HADOLINT_IMAGE_NAME ?= hadolint/hadolint
HADOLINT_IMAGE = $(HADOLINT_IMAGE_NAME):$(HADOLINT_IMAGE_TAG)
HADOLINT_FAILURE_THRESHOLD ?= warning
#------------------------------------------------------------------------------
TRIVY_IMAGE_TAG ?= 0.76.2
TRIVY_IMAGE_NAME ?= aquasec/trivy
TRIVY_IMAGE = $(TRIVY_IMAGE_NAME):$(TRIVY_IMAGE_TAG)
TRIVY_SEVERITY ?= HIGH,CRITICAL
# 1 = findings fail the scan; 0 = advisory only
TRIVY_EXIT_CODE ?= 1
TRIVY_CACHE_VOLUME ?= $(DOCKER_IMAGE_NAME)-trivy-cache
#------------------------------------------------------------------------------

#-------------------------------------------------- util: freshness tracking --
# (to force a step, delete its stamp, or run `make -B <target>`)
STAMP_DIR ?= .make
PYTHON_DEPS_STAMP := $(STAMP_DIR)/python-deps.stamp
DOCKER_IMAGE_STAMP := $(STAMP_DIR)/docker-image.stamp
DOCKER_COVERAGE_IMAGE_STAMP := $(STAMP_DIR)/docker-coverage-image.stamp
NOTICES_STAMP := $(STAMP_DIR)/notices.stamp
GOLDEN_STAMP := $(STAMP_DIR)/golden.stamp
HADOLINT_STAMP_PREFIX = $(STAMP_DIR)/hadolint-$(HADOLINT_IMAGE_TAG)-$(HADOLINT_FAILURE_THRESHOLD)
DOCKER_BUILD_ARGS ?=
SRC_FILES = $(eval SRC_FILES := $$(shell find src -type f ! -path '*/__pycache__/*' ! -name '*.pyc'))$(SRC_FILES)
#------------------------------------------------------------------------------

#------------------------------------------------------- util: guard_rm_path --
# refuse to rm -rf an empty path, the current or parent directory, or filesystem root
# deferred: macro, $(1) = path value, $(2) = name of the variable (for the message)
guard_rm_path = case "$(1)" in ""|.|./|..|../|/|//) printf 'refusing to remove %s="%s"\n' "$(2)" "$(1)" >&2; exit 1;; esac
#------------------------------------------------------------------------------

#-------------------------------------------------- util: console formatting --
# set NO_COLOR to a non-empty value to disable fancy ANSI formatting
NO_COLOR ?=
ifneq ($(NO_COLOR),)
	STY_H1 :=
	STY_B :=
	STY_U :=
	STY_REVERSE :=
	STY_FAILURE :=
	STY_SUCCESS :=
	STY_WARN :=
	STY_CODE :=
	STY_RESET :=
else
	STY_H1 := \033[1;4m
	STY_B := \033[1m
	STY_U := \033[4m
	STY_REVERSE := \033[7m
	STY_FAILURE := \033[1;31m
	STY_SUCCESS := \033[1;32m
	STY_WARN := \033[1;33m
	STY_CODE := \033[36m
	STY_RESET := \033[0m
endif
#------------------------------------------------------------------------------

#============================================================= BUILD TARGETS ==

#------------------------------------------------------------ help & version --
help: ## show this help message
	@printf "\n"
	@printf "$(STY_H1)Common Build Targets$(STY_RESET)\n"
	@printf "\n"
	@grep -E -- '^[a-zA-Z_.-]+:.*?## .*$$' $(firstword $(MAKEFILE_LIST)) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(STY_CODE)%-16s$(STY_RESET) %s\n", $$1, $$2}'
	@printf "\n"
	@printf "$(STY_WARN)NOTE:$(STY_RESET) Python and Docker are needed to successfully bootstrap this project.\n"
	@printf "      Run $(STY_CODE)make audit.prereqs$(STY_RESET) to confirm prerequisites are available.\n"
	@printf "\n"

help-all: ## list all build targets in this Makefile
	@printf "\n"
	@printf "$(STY_H1)All Build Targets in this Makefile$(STY_RESET)\n"
	@printf "\n"
	@grep -E -- '^(%/)?[a-zA-Z_.-]+:.*$$' $(firstword $(MAKEFILE_LIST)) | grep -Ev -- "^.[A-Z_]+:" | awk 'BEGIN {FS = ":.*?# "}; {printf "  $(STY_CODE)%-43s$(STY_RESET) %s\n", $$1, $$2}'
	@printf "\n"

version: # show app version (long form)
	@printf "${APP_NAME} v${APP_VERSION}\n"

version-porcelain: # show app version (number only)
	@printf "${APP_VERSION}\n"

audit.prereqs: ## check that the required build tools are available
	@HOST_PYTHON_EXE="${HOST_PYTHON_EXE}" HOST_DOCKER_EXE="${HOST_DOCKER_EXE}" HOST_CURL_EXE="${HOST_CURL_EXE}" \
		MIN_DOCKER_VERSION="${MIN_DOCKER_VERSION}" sh scripts/check_prereqs.sh
#------------------------------------------------------------------------------


#------------------------------------------------------------------- install --
install: install.python ## set up

install.python: install.python.deps # set up python

install.python.venv: ${VENV_DIR}/pyvenv.cfg # set up python venv

${VENV_DIR}/pyvenv.cfg:
	"${HOST_PYTHON_EXE}" -m venv "${VENV_DIR}"

install.python.venv-help: # how to activate python venv in local shell
	@printf "RUN:\n"
	@printf "  source ${VENV_BIN_DIR}/activate\n"
	@printf "TO ACTIVATE THE VIRTUAL ENV IN THE LOCAL SHELL\n"

install.python.deps: $(PYTHON_DEPS_STAMP) # install 3rd-party python dependencies (when pyproject.toml or the venv changed)

$(PYTHON_DEPS_STAMP): pyproject.toml ${VENV_DIR}/pyvenv.cfg
	"${VENV_PYTHON_EXE}" -m pip install -e '.[dev]'
	@mkdir -p "$(STAMP_DIR)" && touch "$@"

install.python.reinstall-deps: install.python.venv # install 3rd-party python dependencies (regenerating lock file)
	# resolve the runtime dependencies (only) afresh in a throwaway venv, then freeze them
	set -e; tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	"${HOST_PYTHON_EXE}" -m venv "$$tmp/venv"; \
	"$$tmp/venv/bin/python" -m pip install --upgrade pip .; \
	"$$tmp/venv/bin/python" -m pip freeze --exclude "$(call toml_project,name)" > "$$tmp/requirements.lock"; \
	mv "$$tmp/requirements.lock" requirements.lock
	"${VENV_PYTHON_EXE}" -m pip install --upgrade -e '.[dev]'
	@mkdir -p "$(STAMP_DIR)" && touch "$(PYTHON_DEPS_STAMP)"
#------------------------------------------------------------------------------


#--------------------------------------------------------------------- audit --
audit: audit.licenses audit.release-version audit.attribute-list audit.docs audit.python audit.docker.dockerfile ## check source artifacts

audit-build: audit.docker.image # check build artifacts

audit-all: audit audit-build # check source and build artifacts 

audit.python: audit.python.codestyle audit.python.lint audit.python.typecheck # check python formatting, linting, types

audit.python.codestyle: $(PYTHON_DEPS_STAMP) # check python source formatting
	@"${VENV_RUFF_EXE}" format --diff \
	|| { printf "\n$(STY_WARN)$(STY_REVERSE) TIP $(STY_RESET)$(STY_WARN) You may be able to fix these issues automatically by running:\n        make fix.python.codestyle$(STY_RESET)\n\n" >&2; exit 1; }

audit.python.lint: $(PYTHON_DEPS_STAMP) # lint python source
	@"${VENV_RUFF_EXE}" check

audit.python.typecheck: $(PYTHON_DEPS_STAMP) # check python types
	@"${VENV_MYPY_EXE}"

audit.licenses: $(PYTHON_DEPS_STAMP) # check for viral/copyleft runtime dependencies
	@"${VENV_PYTHON_EXE}" scripts/check_licenses.py

audit.docker: audit.docker.dockerfile audit.docker.image # lint the Dockerfiles and audit the built image

audit.docker.dockerfile: audit.docker.dockerfile.lint audit.docker.dockerfile-test-coverage.lint # lint all Dockerfiles

audit.docker.dockerfile.lint: $(HADOLINT_STAMP_PREFIX)-Dockerfile.stamp # hadolint Dockerfile (when it or the hadolint settings changed)

audit.docker.dockerfile-test-coverage.lint: $(HADOLINT_STAMP_PREFIX)-Dockerfile.test-coverage.stamp # hadolint Dockerfile.test-coverage (when it or the hadolint settings changed)

# one stamp per (hadolint version, threshold, Dockerfile), so changing either setting re-lints
$(HADOLINT_STAMP_PREFIX)-%.stamp: % | docker.check-daemon
	@"${HOST_DOCKER_EXE}" run --rm -i $(HADOLINT_IMAGE) hadolint --failure-threshold $(HADOLINT_FAILURE_THRESHOLD) - < "$<"
	@mkdir -p "$(STAMP_DIR)" && touch "$@"

audit.docker.image: audit.docker.image.scan audit.docker.image.size # build the image, then scan it and report its size

audit.docker.image.scan: $(DOCKER_IMAGE_STAMP) # build (if stale), then trivy scan (see -run)
	@$(MAKE) --no-print-directory audit.docker.image.scan-run

audit.docker.image.size: $(DOCKER_IMAGE_STAMP) # build (if stale), then report the size (see -run)
	@$(MAKE) --no-print-directory audit.docker.image.size-run

audit.docker.image-run: audit.docker.image.scan-run audit.docker.image.size-run # scan and size audits of an existing $(AUDIT_IMAGE)

audit.docker.image.scan-run: docker.check-daemon # trivy scan of $(AUDIT_IMAGE) for fixable vulnerabilities
	@tar="$$(mktemp -t gvmcp-image.XXXXXX)"; trap 'rm -f "$$tar"' EXIT; \
	"${HOST_DOCKER_EXE}" save -o "$$tar" $(AUDIT_IMAGE); \
	"${HOST_DOCKER_EXE}" run --rm -v "$$tar:/image.tar:ro" -v $(TRIVY_CACHE_VOLUME):/root/.cache/trivy $(TRIVY_IMAGE) \
		image --input /image.tar --severity $(TRIVY_SEVERITY) --ignore-unfixed --exit-code $(TRIVY_EXIT_CODE)

audit.docker.image.size-run: docker.check-daemon # report the layer sizes and the uncompressed size of $(AUDIT_IMAGE) (fails above MAX_DOCKER_IMAGE_SIZE_MB when set)
	@"${HOST_DOCKER_EXE}" history --format 'table {{.Size}}\t{{.CreatedBy}}' $(AUDIT_IMAGE)
	@kb=$$("${HOST_DOCKER_EXE}" run --rm --network=none --entrypoint sh $(AUDIT_IMAGE) -c 'du -sxk / 2>/dev/null | cut -f1'); \
	mb=$$((kb * 1024 / 1000000)); \
	printf '\n%s  %s MB (uncompressed)\n' "$(AUDIT_IMAGE)" "$$mb"; \
	if [ "$(MAX_DOCKER_IMAGE_SIZE_MB)" -gt 0 ] && [ "$$mb" -gt "$(MAX_DOCKER_IMAGE_SIZE_MB)" ]; then \
		printf 'FAIL: exceeds MAX_DOCKER_IMAGE_SIZE_MB=%s\n' "$(MAX_DOCKER_IMAGE_SIZE_MB)" >&2; exit 1; fi

audit.release-version: # check the app version numbers are consistent
	@"${HOST_PYTHON_EXE}" scripts/check_release_version.py

audit.attribute-list: # check the master attribute list matches the pinned Graphviz release (offline)
	@"${HOST_PYTHON_EXE}" scripts/gen_attribute_list.py --check

audit.docs: audit.docs.tools-md audit.docs.notices-md # check if generated docs are up-to-date

audit.docs.tools-md: $(PYTHON_DEPS_STAMP) # check if docs/graphviz-tools.md is up-to-date
	@"${VENV_PYTHON_EXE}" scripts/gen_tool_docs.py --check

audit.docs.notices-md: $(PYTHON_DEPS_STAMP) # check if THIRD_PARTY_NOTICES.md is up-to-date
	@"${VENV_PYTHON_EXE}" scripts/gen_notices.py --check
#------------------------------------------------------------------------------


#-------------------------------------------------------------------- update --
update: update.python.codestyle update.docs update.test-fixtures ## update generated/derived files

update.python.codestyle: $(PYTHON_DEPS_STAMP) # apply python source formatting
	@"${VENV_RUFF_EXE}" format

fix.python.codestyle: update.python.codestyle # alias for update.python.codestyle

update.docs: update.docs.tools-md update.docs.notices-md # update generated docs

update.docs.tools-md: docs/graphviz-tools.md # update docs/graphviz-tools.md (when the generator or the sources changed)

# (the venv is needed to run the generator but a dependency bump rarely changes the output, hence order-only)
docs/graphviz-tools.md: scripts/gen_tool_docs.py $(SRC_FILES) | $(PYTHON_DEPS_STAMP)
	@"${VENV_PYTHON_EXE}" scripts/gen_tool_docs.py

update.docs.notices-md: $(NOTICES_STAMP) # update THIRD_PARTY_NOTICES.md (when the dependencies changed)

# (a stamp, not THIRD_PARTY_NOTICES.md itself: that file is partly hand-written and is also an input to the docker image)
$(NOTICES_STAMP): pyproject.toml requirements.lock scripts/gen_notices.py scripts/check_licenses.py $(PYTHON_DEPS_STAMP)
	@"${VENV_PYTHON_EXE}" scripts/gen_notices.py
	@mkdir -p "$(STAMP_DIR)" && touch "$@"

update.attribute-list: # regenerate the master attribute list from the pinned graphviz.org docs commit (needs network; not part of `update`)
	@"${HOST_PYTHON_EXE}" scripts/gen_attribute_list.py

update.test-fixtures: update.test-fixtures.golden # regenerate test fixtures

update.test-fixtures.golden: $(GOLDEN_STAMP) # regenerate tests/fixtures/golden SVGs (when the image or the inputs changed; -B to force)

$(GOLDEN_STAMP): $(DOCKER_IMAGE_STAMP) $(PYTHON_DEPS_STAMP) tests/integration/test_docker_image_tools.py tests/conftest.py $(wildcard tests/support/*.py tests/fixtures/dot/*)
	GVMCP_UPDATE_GOLDEN=1 \
	GVMCP_TEST_DOCKER_IMAGE=$(DOCKER_IMAGE_NAME):dev \
	"${VENV_PYTEST_EXE}" -m docker_image tests/integration/test_docker_image_tools.py -k test_golden_svg
	@mkdir -p "$(STAMP_DIR)" && touch "$@"
#------------------------------------------------------------------------------


#---------------------------------------------------------------------- test --
test: test.unit test.docker-image ## run all tests

test.unit: $(PYTHON_DEPS_STAMP) # fast tests, no docker (the `docker_image`-marked tests are excluded by pytest's default addopts)
	"${VENV_PYTEST_EXE}" $(PYTEST_ARGS)

test.docker-image: docker.check-daemon $(DOCKER_IMAGE_STAMP) $(PYTHON_DEPS_STAMP) # run tests against the built docker image
	GVMCP_REQUIRE_DOCKER=1 GVMCP_TEST_DOCKER_IMAGE=$(DOCKER_IMAGE_NAME):dev "${VENV_PYTEST_EXE}" -m docker_image $(PYTEST_ARGS)

test-coverage: test-coverage.unit test-coverage.docker-image # unit and docker image tests, with one combined coverage report
	@$(call guard_rm_path,${COVERAGE_ALL_DIR},COVERAGE_ALL_DIR)
	rm -rf -- "${COVERAGE_ALL_DIR}"
	mkdir -p "${COVERAGE_ALL_DIR}"
	export COVERAGE_FILE="${COVERAGE_ALL_DIR}/.coverage"; \
	"${VENV_PYTHON_EXE}" -m coverage combine --keep .coverage "${COVERAGE_DOCKER_DIR}/.coverage" \
		&& "${VENV_PYTHON_EXE}" -m coverage report --skip-empty --show-missing \
		&& "${VENV_PYTHON_EXE}" -m coverage html -d "${COVERAGE_ALL_DIR}/html"

test-coverage.unit: $(PYTHON_DEPS_STAMP) # unit tests with a coverage report
	"${VENV_PYTEST_EXE}" --cov=graphviz_mcp --cov-report=term-missing --cov-report=html:htmlcov $(PYTEST_ARGS)

test-coverage.docker-image: $(DOCKER_COVERAGE_IMAGE_STAMP) # docker image tests with line coverage of the code in the containers and on the host
	@$(MAKE) --no-print-directory test-coverage.docker-image-run

test-coverage.docker-image-run: docker.check-daemon $(PYTHON_DEPS_STAMP) # the coverage run itself, against an existing $(COVERAGE_IMAGE)
	@$(call guard_rm_path,${COVERAGE_DOCKER_DIR},COVERAGE_DOCKER_DIR)
	rm -rf -- "${COVERAGE_DOCKER_DIR}"
	mkdir -p "${COVERAGE_DOCKER_DIR}/data"
	chmod 777 "${COVERAGE_DOCKER_DIR}/data"
	COVERAGE_FILE="${COVERAGE_DOCKER_DIR}/data/.coverage.host" GVMCP_REQUIRE_DOCKER=1 \
	GVMCP_TEST_DOCKER_IMAGE=$(COVERAGE_IMAGE) GVMCP_DOCKER_COVERAGE_DIR="$(abspath ${COVERAGE_DOCKER_DIR}/data)" \
		"${VENV_PYTEST_EXE}" -m docker_image --cov=graphviz_mcp --cov-report= $(PYTEST_ARGS); status=$$?; \
	export COVERAGE_FILE="${COVERAGE_DOCKER_DIR}/.coverage"; \
	"${VENV_PYTHON_EXE}" -m coverage combine --keep "${COVERAGE_DOCKER_DIR}/data" \
		&& "${VENV_PYTHON_EXE}" -m coverage report --skip-empty \
		&& "${VENV_PYTHON_EXE}" -m coverage html -d "${COVERAGE_DOCKER_DIR}/html"; \
	exit $$status
#------------------------------------------------------------------------------


#--------------------------------------------------------------------- build --
build: docker.build ## build docker image

build.docker-image: $(DOCKER_IMAGE_STAMP) # build docker image (when its inputs changed)

# the prerequisites are the files the Dockerfile COPYs (keep in sync with its COPY lines), plus the Dockerfile itself
# (the stamp can outlive the image, eg. after `docker rmi`: use rebuild.docker-image or delete the stamp)
$(DOCKER_IMAGE_STAMP): Dockerfile .dockerignore requirements.lock pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md docs/attribute-security-policy.md $(SRC_FILES) | docker.check-daemon
	@"${HOST_DOCKER_EXE}" build $(DOCKER_BUILD_ARGS) \
		--build-arg APP_VERSION=$(APP_VERSION) \
		-t $(DOCKER_IMAGE_NAME):dev \
		-t $(DOCKER_IMAGE_NAME):$(APP_VERSION) \
		-t $(DOCKER_IMAGE_NAME):latest \
		.
	@mkdir -p "$(STAMP_DIR)" && touch "$@"

rebuild.docker-image: # rebuild the docker image from scratch, bypassing the layer cache (eg. to pick up new apt security updates)
	@rm -f "$(DOCKER_IMAGE_STAMP)"
	@$(MAKE) --no-print-directory DOCKER_BUILD_ARGS=--no-cache $(DOCKER_IMAGE_STAMP)

build.docker-image-coverage: $(DOCKER_COVERAGE_IMAGE_STAMP) # coverage-instrumented variant of the docker image (for test-coverage.docker-image only; never shipped)

$(DOCKER_COVERAGE_IMAGE_STAMP): $(DOCKER_IMAGE_STAMP) Dockerfile.test-coverage $(PYTHON_DEPS_STAMP) | docker.check-daemon
	@cov_version="$$("${VENV_PYTHON_EXE}" -c 'import coverage; print(coverage.__version__)')" \
		|| { printf 'cannot import coverage via %s; run "make install" first\n' "${VENV_PYTHON_EXE}" >&2; exit 1; }; \
	"${HOST_DOCKER_EXE}" build \
		--build-arg BASE=$(DOCKER_IMAGE_NAME):dev \
		--build-arg COVERAGE_VERSION="$$cov_version" \
		-t $(COVERAGE_IMAGE) \
		- < Dockerfile.test-coverage
	@mkdir -p "$(STAMP_DIR)" && touch "$@"
#------------------------------------------------------------------------------


#--------------------------------------------- daemon-ish service management --
run: run-http # alias for run-http

run-http: docker.check-daemon $(DOCKER_IMAGE_STAMP) ## run the HTTP server in the foreground
	@"${HOST_DOCKER_EXE}" run --rm --name "$(SERVICE_CONTAINER_NAME)" -p "$(SERVICE_HTTP_BIND_ADDR):$(SERVICE_HTTP_PORT):8000" \
		$(SERVICE_HARDENING_ARGS) $(SERVICE_DOCKER_ARGS) "$(SERVICE_IMAGE)" --http

run-stdio: docker.check-daemon $(DOCKER_IMAGE_STAMP) # run the stdio server in the foreground
	@"${HOST_DOCKER_EXE}" run -i --rm --network=none $(SERVICE_HARDENING_ARGS) $(SERVICE_DOCKER_ARGS) "$(SERVICE_IMAGE)" --stdio

start: docker.check-daemon $(DOCKER_IMAGE_STAMP) ## start the HTTP server in the background
	@name="$(SERVICE_CONTAINER_NAME)"; \
	if [ "$$("${HOST_DOCKER_EXE}" inspect -f '{{.State.Running}}' "$$name" 2>/dev/null)" = true ]; then \
		printf "$(STY_WARN)WARNING:$(STY_RESET) %s is already running (see: make status)\n" "$$name" >&2; exit 0; fi; \
	"${HOST_DOCKER_EXE}" rm -f "$$name" >/dev/null 2>&1; \
	"${HOST_DOCKER_EXE}" run -d --name "$$name" -p "$(SERVICE_HTTP_BIND_ADDR):$(SERVICE_HTTP_PORT):8000" \
		$(SERVICE_HARDENING_ARGS) $(SERVICE_DOCKER_ARGS) "$(SERVICE_IMAGE)" --http >/dev/null \
		|| { "${HOST_DOCKER_EXE}" rm -f "$$name" >/dev/null 2>&1; exit 1; }; \
	if [ -n "$(HOST_CURL_EXE)" ] && command -v "$(HOST_CURL_EXE)" >/dev/null 2>&1; then \
		i=0; \
		until "$(HOST_CURL_EXE)" -fsS -o /dev/null "http://${SERVICE_HTTP_BIND_ADDR}:$(SERVICE_HTTP_PORT)/health" 2>/dev/null; do \
			if [ "$$("${HOST_DOCKER_EXE}" inspect -f '{{.State.Running}}' "$$name")" != true ] || [ "$$i" -ge "$(SERVICE_START_TIMEOUT_SECONDS)" ]; then \
				printf "$(STY_FAILURE)%s did not become healthy; last logs:$(STY_RESET)\n" "$$name" >&2; \
				"${HOST_DOCKER_EXE}" logs --tail=20 "$$name" >&2; exit 1; fi; \
			i=$$((i + 1)); sleep 1; \
		done; \
	else \
		printf "$(STY_WARN)WARNING:$(STY_RESET) HOST_CURL_EXE ('%s') is blank or not on the PATH; health check skipped\n" "$(HOST_CURL_EXE)" >&2; \
	fi; \
	printf "started %s ($(SERVICE_IMAGE))\n  Web UI: http://$(SERVICE_HTTP_BIND_ADDR):$(SERVICE_HTTP_PORT)/ui\n  MCP:    http://$(SERVICE_HTTP_BIND_ADDR):$(SERVICE_HTTP_PORT)/mcp\n" "$$name"

stop: docker.check-daemon ## stop the HTTP server
	@name="$(SERVICE_CONTAINER_NAME)"; \
	if "${HOST_DOCKER_EXE}" inspect "$$name" >/dev/null 2>&1; then \
		"${HOST_DOCKER_EXE}" stop "$$name" >/dev/null; \
		"${HOST_DOCKER_EXE}" rm "$$name" >/dev/null 2>&1; \
		printf "stopped %s\n" "$$name"; \
	else \
		printf "$(STY_WARN)WARNING:$(STY_RESET) %s was not running\n" "$$name" >&2; fi

restart: ## stop then start the HTTP server
	@$(MAKE) --no-print-directory stop
	@$(MAKE) --no-print-directory start

status: docker.check-daemon ## check if the HTTP server is running
	@name="$(SERVICE_CONTAINER_NAME)"; \
	state="$$("${HOST_DOCKER_EXE}" inspect -f '{{.State.Status}}' "$$name" 2>/dev/null)"; \
	if [ "$$state" != running ]; then printf "%s is not running%s\n" "$$name" "$${state:+ ($$state)}"; exit 1; fi; \
	health="$$("${HOST_DOCKER_EXE}" inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$$name")"; \
	image="$$("${HOST_DOCKER_EXE}" inspect -f '{{.Config.Image}}' "$$name")"; \
	addr="$$("${HOST_DOCKER_EXE}" port "$$name" 8000/tcp | head -n 1)"; \
	printf "%s is running\n  image:  %s\n  health: %s\n  Web UI: http://%s/ui\n  MCP:    http://%s/mcp\n" "$$name" "$$image" "$$health" "$$addr" "$$addr"

logs: docker.check-daemon ## tail the HTTP server logs
	@name="$(SERVICE_CONTAINER_NAME)"; \
	if "${HOST_DOCKER_EXE}" inspect "$$name" >/dev/null 2>&1; then "${HOST_DOCKER_EXE}" logs -f --tail=100 "$$name"; \
	else printf "$(STY_WARN)WARNING:$(STY_RESET) %s has no logs (no such container)\n" "$$name" >&2; fi
#------------------------------------------------------------------------------


#--------------------------------------------------------------------- clean --
clean: clean.python clean.test clean.stamps clean.macos ## remove generated artifacts (keeps venv and docker images)

clean-all: clean clean.python.venv clean.docker ## remove all generated artifacts (including venv and docker images)

clean.python: clean.python.bytecode clean.python.caches # remove generated python artifacts

clean.python.bytecode: # remove compiled python __pycaches__
	find . -path "./${VENV_DIR}" -prune -o -path ./.git -prune -o -type d -name __pycache__ -prune -exec rm -rf {} +

clean.python.caches: # remove ruff and mypy caches
	rm -rf .ruff_cache .mypy_cache

clean.python.venv: # remove the python venv (and everything installed in it)
	@$(call guard_rm_path,${VENV_DIR},VENV_DIR)
	rm -rf -- "${VENV_DIR}" "$(PYTHON_DEPS_STAMP)"

clean.macos: # remove macOS .DS_Store files
	find . -path "./${VENV_DIR}" -prune -o -path ./.git -prune -o -type f -name .DS_Store -exec rm -f {} +

clean.stamps: # remove the freshness-tracking stamp files (the next build redoes every stamped step)
	@$(call guard_rm_path,${STAMP_DIR},STAMP_DIR)
	rm -rf -- "${STAMP_DIR}"

clean.test: clean.test-coverage clean.test.cache # remove all test artifacts

clean.test-coverage: # remove coverage data and reports
	@$(call guard_rm_path,${COVERAGE_DOCKER_DIR},COVERAGE_DOCKER_DIR)
	@$(call guard_rm_path,${COVERAGE_ALL_DIR},COVERAGE_ALL_DIR)
	rm -rf -- .coverage .coverage.* htmlcov coverage.xml "${COVERAGE_DOCKER_DIR}" "${COVERAGE_ALL_DIR}"

clean.test.cache: # remove the pytest cache
	rm -rf .pytest_cache

clean.docker: clean.docker.containers clean.docker.images clean.docker.volumes # remove this project's docker artifacts

clean.docker.containers: docker.check-daemon # remove leftover test containers
	@ids=$$("${HOST_DOCKER_EXE}" ps -aq --filter "name=$(DOCKER_IMAGE_NAME)-test-"); \
	[ -z "$$ids" ] || "${HOST_DOCKER_EXE}" rm -f $$ids
	@"${HOST_DOCKER_EXE}" rm -f "$(SERVICE_CONTAINER_NAME)" >/dev/null 2>&1 || true

clean.docker.images: docker.check-daemon # remove this project's docker images
	@for tag in dev $(APP_VERSION) latest coverage; do \
		ref="$(DOCKER_IMAGE_NAME):$$tag"; \
		if "${HOST_DOCKER_EXE}" image inspect "$$ref" >/dev/null 2>&1; then "${HOST_DOCKER_EXE}" image rm "$$ref"; fi; \
	done
	"${HOST_DOCKER_EXE}" image prune -f --filter "label=org.opencontainers.image.title=$(DOCKER_IMAGE_NAME)"
	rm -f -- "$(DOCKER_IMAGE_STAMP)" "$(DOCKER_COVERAGE_IMAGE_STAMP)" "$(GOLDEN_STAMP)"

clean.docker.volumes: docker.check-daemon # remove the trivy vulnerability-db cache volume
	@if "${HOST_DOCKER_EXE}" volume inspect $(TRIVY_CACHE_VOLUME) >/dev/null 2>&1; then "${HOST_DOCKER_EXE}" volume rm $(TRIVY_CACHE_VOLUME); fi
#------------------------------------------------------------------------------


#-------------------------------------------------------------------- docker --
docker.build: audit.docker.dockerfile audit.docker.image docker.image.build # lint both Dockerfiles, build the image, then scan it and report its size
docker.image.build: build.docker-image # alias for build.docker-image
docker.dockerfile.lint: audit.docker.dockerfile.lint # alias for audit.docker.dockerfile.lint
docker.dockerfile-test-coverage.lint: audit.docker.dockerfile-test-coverage.lint # alias for audit.docker.dockerfile-test-coverage.lint
docker.image.scan: audit.docker.image.scan # alias for audit.docker.image.scan
docker.image.size: audit.docker.image.size # alias for audit.docker.image.size
docker.check-daemon: # fail early with a clear message if docker isn't reachable
	@"${HOST_DOCKER_EXE}" info >/dev/null 2>&1 || { printf 'docker daemon is not reachable (HOST_DOCKER_EXE=%s)\n' "${HOST_DOCKER_EXE}" >&2; exit 1; }
docker.clean: clean.docker # alias for clean.docker
#------------------------------------------------------------------------------
