ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG BACKEND_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple
ARG BACKEND_INSTALL_CJK_FONTS=1

FROM ${UV_IMAGE} AS uvbin
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS builder

WORKDIR /app

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BACKEND_VENV_PATH=/opt/backend-venv

RUN set -eux; \
  rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
  printf 'deb https://%s/debian bookworm main\n' "${BACKEND_APT_MIRROR_PRIMARY}" > /etc/apt/sources.list || true; \
  printf 'deb https://%s/debian bookworm-updates main\n' "${BACKEND_APT_MIRROR_PRIMARY}" >> /etc/apt/sources.list || true; \
  printf 'deb https://%s/debian-security bookworm-security main\n' "${BACKEND_APT_SECURITY_PRIMARY}" >> /etc/apt/sources.list || true; \
  apt-get update || true; \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  build-essential \
  gcc \
  libffi-dev \
  libpq-dev || \
  (rm -f /etc/apt/sources.list && \
  printf 'deb https://%s/debian bookworm main\n' "${BACKEND_APT_MIRROR_FALLBACK}" > /etc/apt/sources.list && \
  printf 'deb https://%s/debian-security bookworm-security main\n' "${BACKEND_APT_SECURITY_FALLBACK}" >> /etc/apt/sources.list && \
  apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends build-essential gcc libffi-dev libpq-dev); \
  rm -rf /var/lib/apt/lists/*

COPY --from=uvbin /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock ./

RUN set -eux; \
  uv venv "${BACKEND_VENV_PATH}"; \
  env \
  VIRTUAL_ENV="${BACKEND_VENV_PATH}" \
  PATH="${BACKEND_VENV_PATH}/bin:${PATH}" \
  UV_INDEX_URL="${BACKEND_PYPI_INDEX_PRIMARY}" \
  PIP_INDEX_URL="${BACKEND_PYPI_INDEX_PRIMARY}" \
  uv sync --active --frozen --no-dev || \
  env \
  VIRTUAL_ENV="${BACKEND_VENV_PATH}" \
  PATH="${BACKEND_VENV_PATH}/bin:${PATH}" \
  UV_INDEX_URL="${BACKEND_PYPI_INDEX_FALLBACK}" \
  PIP_INDEX_URL="${BACKEND_PYPI_INDEX_FALLBACK}" \
  uv sync --active --frozen --no-dev

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS runtime-release

WORKDIR /app

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_INSTALL_CJK_FONTS

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BACKEND_VENV_PATH=/opt/backend-venv
ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config

RUN set -eux; \
  rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
  printf 'deb https://%s/debian bookworm main\n' "${BACKEND_APT_MIRROR_PRIMARY}" > /etc/apt/sources.list || true; \
  printf 'deb https://%s/debian-security bookworm-security main\n' "${BACKEND_APT_SECURITY_PRIMARY}" >> /etc/apt/sources.list || true; \
  apt-get update || true; \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  libpq5 \
  libffi8 \
  libcairo2 \
  libpango-1.0-0 \
  libgdk-pixbuf-2.0-0 \
  shared-mime-info \
  fonts-dejavu-core || \
  (rm -f /etc/apt/sources.list && \
  printf 'deb https://%s/debian bookworm main\n' "${BACKEND_APT_MIRROR_FALLBACK}" > /etc/apt/sources.list && \
  printf 'deb https://%s/debian-security bookworm-security main\n' "${BACKEND_APT_SECURITY_FALLBACK}" >> /etc/apt/sources.list && \
  apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libpq5 libffi8 libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu-core); \
  rm -rf /var/lib/apt/lists/*; \
  mkdir -p /app/uploads/zip_files /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config

COPY --from=builder /opt/backend-venv /opt/backend-venv
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py

RUN groupadd --gid 1001 appgroup && \
  useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser && \
  chown -R appuser:appgroup /app /opt/backend-venv

USER appuser

EXPOSE 8000

CMD ["python3", "-m", "app.runtime.container_startup", "prod"]
