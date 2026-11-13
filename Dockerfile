# syntax=docker/dockerfile:1.7
# graphviz-mcp: python MCP service exposing self-contained, version-pinned Graphviz tool suite

# =========================================================== VERSION CONFIG ==
ARG APP_VERSION
ARG DEBIAN_IMAGE_BASENAME=debian:trixie-slim
ARG DEBIAN_IMAGE="${DEBIAN_IMAGE_BASENAME}@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad"
ARG GV_VERSION=16.1.0
ARG GV_SHA256=beea483ab130f456c1c3905f4f2e40778a9c493c3d73ae8012367d552d71ca84
ARG GV_SOURCE_URL="https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/${GV_VERSION}/graphviz-${GV_VERSION}.tar.gz"
# =============================================================================

# ==================================== STAGE 1: COMPILE GRAPHVIZ FROM SOURCE ==
FROM ${DEBIAN_IMAGE} AS graphviz-builder
ARG GV_SHA256
ARG GV_SOURCE_URL
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# INSTALL BUILD TOOLS AND DEPENDENCIES
# (unpinned; see the note at the end of this file)
# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential pkg-config ca-certificates curl \
      zlib1g-dev libexpat1-dev libltdl-dev libfreetype-dev libfontconfig-dev \
      libpango1.0-dev libcairo2-dev libgd-dev librsvg2-dev libwebp-dev libann-dev libgts-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
# FETCH AND VERIFY GRAPHVIZ SOURCE
RUN curl -fsSL -o graphviz.tar.gz "${GV_SOURCE_URL}" \
    && echo "${GV_SHA256}  graphviz.tar.gz" | sha256sum -c - \
    && tar -xzf graphviz.tar.gz --strip-components=1 \
    && rm graphviz.tar.gz
# BUILD IT
RUN ./configure --prefix=/opt/graphviz --disable-static \
      --disable-swig --disable-sharp --disable-d --disable-go --disable-guile --disable-java \
      --disable-javascript --disable-lua --disable-ocaml --disable-perl --disable-php \
      --disable-python --disable-r --disable-ruby --disable-tcl \
      --with-pangocairo=yes --with-libgd=yes --with-rsvg=yes --with-webp=yes --with-ann=yes \
      --with-expat=yes --with-freetype2=yes --with-gts=yes \
      --without-qt --without-glut --without-smyrna --without-gdk --without-gdk-pixbuf \
      --without-gtk --without-gtkgl --without-gtkglext --without-devil --without-poppler \
      --without-ghostscript --without-lasi --without-x \
    && make -j"$(nproc)" && make install-strip \
    && mkdir -p /opt/graphviz/share/licenses \
    && cp COPYING cpl1.0.txt /opt/graphviz/share/licenses/
# =============================================================================

# ======================================== STAGE 2: BUILD PYTHON MCP SERVICE ==
FROM ${DEBIAN_IMAGE} AS python-builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# INSTALL PYTHON
# (unpinned; see the note at the end of this file)
# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
# BUILD SERVICE
WORKDIR /src
COPY requirements.lock ./
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN /opt/venv/bin/pip install --no-deps . \
    && /opt/venv/bin/pip check \
    && /opt/venv/bin/pip uninstall -y pip
# =============================================================================

# ========================================== STAGE 3: ASSEMBLE RUNTIME IMAGE ==
FROM ${DEBIAN_IMAGE} AS runtime
ARG DEBIAN_IMAGE_BASENAME
ARG GV_VERSION
ARG APP_VERSION
RUN test -n "${APP_VERSION}" || \
    { echo "APP_VERSION build argument is required" >&2; exit 1; }
LABEL org.opencontainers.image.title="graphviz-mcp" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="MCP server exposing the Graphviz suite (Graphviz ${GV_VERSION})" \
      org.opencontainers.image.source="https://github.com/rodw/graphviz-mcp" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="${DEBIAN_IMAGE_BASENAME}" \
      io.github.rodw.graphviz-mcp.graphviz.version="${GV_VERSION}"
# INSTALL RUNTIME DEPENDENCIES
# (unpinned; see the note at the end of this file)
# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 fontconfig fonts-dejavu-core fonts-liberation \
      libexpat1 libltdl7 zlib1g libfreetype6 libfontconfig1 \
      libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libcairo2 libgd3 librsvg2-2 libwebp7 libann0 libgts-0.7-5t64 \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && echo /opt/graphviz/lib > /etc/ld.so.conf.d/graphviz.conf
# INSTALL ARTIFACTS FROM GRAPHVIZ-BUILDER
COPY --from=graphviz-builder /opt/graphviz /opt/graphviz
RUN ldconfig && /opt/graphviz/bin/dot -c && fc-cache -f && /opt/graphviz/bin/dot -V
# BUILD-TIME SMOKE TEST OF GRAPHVIZ INSTALL (ABORTING ON FAILURE)
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# 1. Verify required programs exist and are executable.
RUN set -e; \
    for p in dot neato fdp sfdp twopi circo osage patchwork nop ccomps gvgen; do \
      test -x "/opt/graphviz/bin/$p" || { echo "required Graphviz program missing: $p" >&2; exit 1; }; \
    done
# 2. Verify each layout engine can render a graph.
RUN set -e; \
    for p in dot neato fdp sfdp twopi circo osage patchwork; do \
      echo 'graph { a -- b; b -- c; c -- a }' \
        | "/opt/graphviz/bin/$p" -Tsvg > /dev/null \
        || { echo "Graphviz layout engine failed: $p" >&2; exit 1; }; \
    done
# 3. Verify required output formats work.
RUN set -e; \
    for f in svg png dot plain; do \
      echo 'digraph { a -> b }' \
        | /opt/graphviz/bin/dot -T"$f" > /dev/null \
        || { echo "required output format failed: $f" >&2; exit 1; }; \
    done
# INSTALL ARTIFACTS FROM PYTHON-BUILDER
COPY --from=python-builder /opt/venv /opt/venv
RUN /opt/venv/bin/graphviz-mcp --version
COPY LICENSE THIRD_PARTY_NOTICES.md docs/attribute-security-policy.md /usr/share/doc/graphviz-mcp/
# CONFIGURE RUNTIME ENVIRONMENT
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin gvmcp
ENV PATH=/opt/venv/bin:/opt/graphviz/bin:/usr/local/bin:/usr/bin:/bin \
    GVMCP_GRAPHVIZ_BIN=/opt/graphviz/bin \
    GVMCP_HOST=0.0.0.0 GVMCP_PORT=8000 \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/tmp
USER 10001:10001
WORKDIR /tmp
EXPOSE 8000
# LAUNCH IT
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python3", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('GVMCP_PORT','8000'), timeout=3).status == 200 else 1)"]
ENTRYPOINT ["graphviz-mcp"]
CMD ["--http"]
# =============================================================================


# ==================================================================== NOTES ==
# APT PACKAGES ARE NOT VERSION-PINNED (hadolint DL3008 is ignored above)
#   Debian stable keeps ABI compatibility within a release and ships security
#   fixes, so packages resolve to current versions at build time. The base
#   image is pinned by digest; exact per-package pins would add maintenance
#   work and break rebuilds once old revisions leave the archive.
# =============================================================================
