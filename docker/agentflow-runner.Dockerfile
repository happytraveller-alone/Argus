# syntax=docker/dockerfile:1.7

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG AGENTFLOW_REPOSITORY=https://github.com/berabuddies/agentflow.git
ARG AGENTFLOW_COMMIT=1667fa35ed99e3c1583a7d60cac8e3406cafd3ee
ARG AGENTFLOW_VERSION=0.1.0

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS agentflow-build
ARG AGENTFLOW_REPOSITORY
ARG AGENTFLOW_COMMIT
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=
ARG BACKEND_PYPI_INDEX_FALLBACK=

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN --mount=type=cache,id=argus-agentflow-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=argus-agentflow-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    sed -i "s|deb.debian.org|${BACKEND_APT_MIRROR_PRIMARY}|g; s|security.debian.org|${BACKEND_APT_SECURITY_PRIMARY}|g" /etc/apt/sources.list.d/debian.sources; \
    apt-get update || { \
      sed -i "s|${BACKEND_APT_MIRROR_PRIMARY}|${BACKEND_APT_MIRROR_FALLBACK}|g; s|${BACKEND_APT_SECURITY_PRIMARY}|${BACKEND_APT_SECURITY_FALLBACK}|g" /etc/apt/sources.list.d/debian.sources; \
      apt-get update; \
    }; \
    apt-get install -y --no-install-recommends ca-certificates git; \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,id=argus-agentflow-git,target=/var/cache/argus-agentflow/git,sharing=locked \
    set -eux; \
    git clone --filter=blob:none "${AGENTFLOW_REPOSITORY}" /opt/agentflow-src; \
    git -C /opt/agentflow-src checkout "${AGENTFLOW_COMMIT}"; \
    git -C /opt/agentflow-src rev-parse HEAD > /opt/agentflow-src/ARGUS_AGENTFLOW_COMMIT

RUN --mount=type=cache,id=argus-agentflow-pip,target=/root/.cache/pip,sharing=locked \
    set -eux; \
    if [ -n "${BACKEND_PYPI_INDEX_PRIMARY}" ]; then \
      python -m pip config set global.index-url "${BACKEND_PYPI_INDEX_PRIMARY}"; \
    fi; \
    if [ -n "${BACKEND_PYPI_INDEX_FALLBACK}" ]; then \
      python -m pip config set global.extra-index-url "${BACKEND_PYPI_INDEX_FALLBACK}"; \
    fi; \
    python -m pip install --upgrade pip; \
    python -m pip wheel --wheel-dir /opt/agentflow-wheels /opt/agentflow-src

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS agentflow-runner
ARG AGENTFLOW_REPOSITORY
ARG AGENTFLOW_COMMIT
ARG AGENTFLOW_VERSION
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org

LABEL org.opencontainers.image.title="Argus AgentFlow runner" \
      org.opencontainers.image.description="Controlled AgentFlow execution image for Argus intelligent audit P1" \
      org.opencontainers.image.source="${AGENTFLOW_REPOSITORY}" \
      org.opencontainers.image.revision="${AGENTFLOW_COMMIT}" \
      org.opencontainers.image.version="${AGENTFLOW_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    AGENTFLOW_RUNS_DIR=/work/agentflow-runs \
    AGENTFLOW_MAX_CONCURRENT_RUNS=2 \
    ARGUS_AGENTFLOW_SOURCE_REPOSITORY=${AGENTFLOW_REPOSITORY} \
    ARGUS_AGENTFLOW_SOURCE_COMMIT=${AGENTFLOW_COMMIT} \
    ARGUS_AGENTFLOW_SOURCE_VERSION=${AGENTFLOW_VERSION} \
    ARGUS_AGENTFLOW_OUTPUT_DIR=/work/outputs \
    ARGUS_AGENTFLOW_INPUT_PATH=/work/input/runner_input.json \
    HOME=/tmp/argus-agentflow-home

RUN --mount=type=cache,id=argus-agentflow-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=argus-agentflow-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    sed -i "s|deb.debian.org|${BACKEND_APT_MIRROR_PRIMARY}|g; s|security.debian.org|${BACKEND_APT_SECURITY_PRIMARY}|g" /etc/apt/sources.list.d/debian.sources; \
    apt-get update || { \
      sed -i "s|${BACKEND_APT_MIRROR_PRIMARY}|${BACKEND_APT_MIRROR_FALLBACK}|g; s|${BACKEND_APT_SECURITY_PRIMARY}|${BACKEND_APPT_SECURITY_FALLBACK:-${BACKEND_APT_SECURITY_FALLBACK}}|g" /etc/apt/sources.list.d/debian.sources; \
      apt-get update; \
    }; \
    apt-get install -y --no-install-recommends ca-certificates tini; \
    rm -rf /var/lib/apt/lists/*; \
    useradd --create-home --home-dir /home/agentflow --shell /usr/sbin/nologin --uid 10001 agentflow; \
    mkdir -p /app/backend/agentflow /work/input /work/outputs /work/agentflow-runs /tmp/argus-agentflow-home /licenses/agentflow; \
    chown -R agentflow:agentflow /work /tmp/argus-agentflow-home

COPY --from=agentflow-build /opt/agentflow-wheels /opt/agentflow-wheels
COPY --from=agentflow-build /opt/agentflow-src/LICENSE /licenses/agentflow/LICENSE
COPY --from=agentflow-build /opt/agentflow-src/ARGUS_AGENTFLOW_COMMIT /licenses/agentflow/ARGUS_AGENTFLOW_COMMIT
COPY docker/agentflow-entrypoint.sh /usr/local/bin/agentflow-entrypoint
COPY docker/agentflow-runner.sh /usr/local/bin/argus-agentflow-runner
COPY backend/agentflow /app/backend/agentflow
RUN set -eux; \
    python -m pip install --no-index --find-links=/opt/agentflow-wheels "agentflow==${AGENTFLOW_VERSION}"; \
    chmod +x /usr/local/bin/agentflow-entrypoint /usr/local/bin/argus-agentflow-runner; \
    chown -R agentflow:agentflow /app/backend/agentflow /work /tmp/argus-agentflow-home; \
    agentflow --help >/dev/null

WORKDIR /app
USER agentflow
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/agentflow-entrypoint"]
CMD ["agentflow", "--help"]
