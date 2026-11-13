#!/bin/sh
# Check that the host tools needed to build, test and run this project are installed and usable.
#
# Written in POSIX sh (not Python) because Python is one of the things being checked.
#
# Required: python (>= requires-python in pyproject.toml, with the venv and ensurepip modules), docker (CLI, reachable
# daemon, engine >= MIN_DOCKER_VERSION). Optional (a warning only): buildx, curl, git.
#
# Usage: scripts/check_prereqs.sh
# Environment (the Makefile passes these): HOST_PYTHON_EXE, HOST_DOCKER_EXE, HOST_CURL_EXE, MIN_DOCKER_VERSION
# Exit status: 0 if every required check passed, 1 otherwise.

PYTHON="${HOST_PYTHON_EXE:-python3}"
DOCKER="${HOST_DOCKER_EXE:-docker}"
CURL="${HOST_CURL_EXE-curl}"
MIN_DOCKER="${MIN_DOCKER_VERSION:-23.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -t 1 ]; then
	OK='\033[32m'; WARN='\033[33m'; FAIL='\033[31m'; RESET='\033[0m'
else
	OK=''; WARN=''; FAIL=''; RESET=''
fi
failures=0

ok() { printf "  ${OK}[ OK ]${RESET} %s\n" "$*"; }
warn() { printf "  ${WARN}[WARN]${RESET} %s\n" "$*"; }
fail() { printf "  ${FAIL}[FAIL]${RESET} %s\n" "$*"; failures=$((failures + 1)); }

# have <cmd>: is <cmd> (a name on the PATH or a path) executable?
have() { [ -n "$1" ] && command -v "$1" >/dev/null 2>&1; }

# version_ge <have> <want>: compare the leading "major.minor" of two dotted versions.
version_ge() {
	have_major="${1%%.*}"; have_rest="${1#*.}"; have_minor="${have_rest%%.*}"
	want_major="${2%%.*}"; want_rest="${2#*.}"; want_minor="${want_rest%%.*}"
	case "$have_rest" in "$1") have_minor=0 ;; esac
	case "$want_rest" in "$2") want_minor=0 ;; esac
	have_minor="${have_minor%%[!0-9]*}"; want_minor="${want_minor%%[!0-9]*}"
	[ "$have_major" -gt "$want_major" ] && return 0
	[ "$have_major" -eq "$want_major" ] && [ "${have_minor:-0}" -ge "${want_minor:-0}" ]
}

printf 'Checking host prerequisites\n'

# ---------------------------------------------------------------- python --
printf '\npython (%s)\n' "$PYTHON"
min_python="$(sed -n 's/^requires-python *= *"[>=~ ]*\([0-9][0-9.]*\)".*/\1/p' "$ROOT/pyproject.toml" 2>/dev/null | head -n 1)"
if ! have "$PYTHON"; then
	fail "not found (set HOST_PYTHON_EXE; need Python >= ${min_python:-3.12})"
else
	py_version="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
	if [ -z "$py_version" ]; then
		fail "could not run $PYTHON"
	elif [ -n "$min_python" ] && ! version_ge "$py_version" "$min_python"; then
		fail "version $py_version is older than the required >= $min_python"
	else
		ok "version $py_version (required >= ${min_python:-unknown})"
	fi
	if [ -n "$py_version" ]; then
		if "$PYTHON" -c 'import venv, ensurepip' >/dev/null 2>&1; then
			ok "venv and ensurepip modules available"
		else
			fail "the venv/ensurepip modules are missing (on Debian/Ubuntu: apt install python3-venv)"
		fi
	fi
fi

# ---------------------------------------------------------------- docker --
printf '\ndocker (%s)\n' "$DOCKER"
if ! have "$DOCKER"; then
	fail "not found (set HOST_DOCKER_EXE; need Docker Engine >= $MIN_DOCKER)"
else
	client_version="$("$DOCKER" version --format '{{.Client.Version}}' 2>/dev/null)"
	ok "client ${client_version:-found}"
	if ! "$DOCKER" info >/dev/null 2>&1; then
		fail "the docker daemon is not reachable (is Docker running? do you have permission to use it?)"
	else
		server_version="$("$DOCKER" info --format '{{.ServerVersion}}' 2>/dev/null)"
		if [ -z "$server_version" ]; then
			warn "daemon reachable, but its version could not be read"
		elif version_ge "$server_version" "$MIN_DOCKER"; then
			ok "daemon reachable, engine $server_version (required >= $MIN_DOCKER)"
		else
			fail "engine $server_version is older than the required >= $MIN_DOCKER (BuildKit by default)"
		fi
	fi
	if "$DOCKER" buildx version >/dev/null 2>&1; then
		ok "buildx available"
	else
		warn "buildx not found: images will build with the legacy builder, and the Dockerfile's BuildKit syntax line is ignored"
	fi
fi

# -------------------------------------------------------------- optional --
printf '\noptional\n'
if [ -z "$CURL" ]; then
	warn "curl disabled (HOST_CURL_EXE is blank): 'make start' will skip its health check"
elif have "$CURL"; then
	ok "$CURL found"
else
	warn "$CURL not found: 'make start' will skip its health check"
fi
if have git; then
	ok "git found"
else
	warn "git not found: the release tag check in 'make audit.release-version' will be skipped"
fi

printf '\n'
if [ "$failures" -gt 0 ]; then
	printf "${FAIL}%d required prerequisite check(s) failed${RESET}\n" "$failures" >&2
	exit 1
fi
printf 'All required prerequisites are available\n'
