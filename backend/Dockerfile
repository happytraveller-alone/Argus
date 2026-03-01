# ============================================
# 多阶段构建 - 构建阶段
# ============================================
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 彻底清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"

# 清除 apt 代理配置并配置重试，使用阿里云镜像（包含 security 源）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -ri 's|https?://deb.debian.org|https://mirrors.aliyun.com|g; s|https?://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -ri 's|https?://deb.debian.org|https://mirrors.aliyun.com|g; s|https?://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "60";'; \
    } > /etc/apt/apt.conf.d/99-no-proxy

# 安装构建依赖（gcc 只在构建阶段需要）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libffi-dev \
        wget \
        gitleaks \
    && rm -rf /var/lib/apt/lists/*

# 下载并安装 Gitleaks 预编译二进制文件
# ENV GITLEAKS_VERSION=8.30.0
# RUN wget -q https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     tar -xzf gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     mv gitleaks /usr/local/bin/gitleaks && \
#     chmod +x /usr/local/bin/gitleaks && \
#     rm gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz

# 安装 uv
COPY --from=ghcr.nju.edu.cn/astral-sh/uv:latest /uv /usr/local/bin/uv

# 配置 uv/pip 使用阿里云 PyPI 镜像
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# 复制依赖文件
COPY pyproject.toml uv.lock README.md ./

# 安装 Python 依赖到虚拟环境
RUN uv sync --frozen --no-dev

# ============================================
# 多阶段构建 - 运行阶段
# ============================================
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 彻底清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 配置使用阿里云 Debian 镜像源并清除 apt 代理（包含 security 源）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -ri 's|https?://deb.debian.org|https://mirrors.aliyun.com|g; s|https?://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -ri 's|https?://deb.debian.org|https://mirrors.aliyun.com|g; s|https?://security.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "60";'; \
    } > /etc/apt/apt.conf.d/99-no-proxy

# 只安装运行时依赖（不需要 gcc）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        git \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        shared-mime-info \
        fonts-noto-cjk \
        xz-utils \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 安装 Node.js 22+（qmd 要求 >=22），使用国内镜像下载二进制包，避免新增非阿里 apt 源
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "$ARCH" in \
      amd64) NODE_ARCH="x64" ;; \
      arm64) NODE_ARCH="arm64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    NODE_BASE_URL_PRIMARY="https://npmmirror.com/mirrors/node/latest-v22.x"; \
    NODE_BASE_URL_FALLBACK="https://nodejs.org/dist/latest-v22.x"; \
    NODE_BASE_URL="${NODE_BASE_URL_PRIMARY}"; \
    NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" 2>/dev/null | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
    if [ -z "${NODE_TARBALL}" ]; then \
      NODE_BASE_URL="${NODE_BASE_URL_FALLBACK}"; \
      NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
    fi; \
    test -n "${NODE_TARBALL}"; \
    if ! curl -fL --retry 5 --retry-delay 2 --retry-all-errors --connect-timeout 20 --max-time 600 "${NODE_BASE_URL}/${NODE_TARBALL}" -o /tmp/node.tar.xz; then \
      NODE_BASE_URL="${NODE_BASE_URL_FALLBACK}"; \
      NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
      test -n "${NODE_TARBALL}"; \
      curl -fL --retry 5 --retry-delay 2 --retry-all-errors --connect-timeout 20 --max-time 600 "${NODE_BASE_URL}/${NODE_TARBALL}" -o /tmp/node.tar.xz; \
    fi; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner; \
    rm -f /tmp/node.tar.xz; \
    export COREPACK_NPM_REGISTRY="https://registry.npmmirror.com"; \
    corepack enable; \
    corepack prepare pnpm@9.15.4 --activate; \
    pnpm --version; \
    node --version; \
    npm --version

# 安装 Opengrep CLI（仅使用官方安装脚本）
ARG OPENGREP_VERSION=v1.15.1

RUN set -eux; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64|amd64) OG_DIST="opengrep_manylinux_x86" ;; \
      aarch64|arm64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    curl -fL "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
      -o /usr/local/bin/opengrep.real; \
    chmod +x /usr/local/bin/opengrep.real; \
    printf '#!/bin/sh\nunset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\nexport NO_PROXY="*"\nexport no_proxy="*"\nexec /usr/local/bin/opengrep.real "$@"\n' \
      > /usr/local/bin/opengrep; \
    chmod +x /usr/local/bin/opengrep; \
    opengrep --version

# 安装 MCP 相关运行时（pnpm + qmd CLI）
RUN mkdir -p /pnpm /pnpm/global && \
    pnpm config set registry https://registry.npmmirror.com && \
    pnpm config set global-bin-dir /pnpm && \
    pnpm config set global-dir /pnpm/global && \
    pnpm add -g \
      @modelcontextprotocol/server-filesystem \
      @modelcontextprotocol/server-memory \
      @modelcontextprotocol/server-sequential-thinking \
      @tobilu/qmd && \
    pnpm bin -g && \
    command -v qmd && \
    PNPM_GLOBAL_ROOT="$(pnpm root -g)" && \
    mkdir -p /app/mcp-src && \
    cp -R "${PNPM_GLOBAL_ROOT}/@modelcontextprotocol/server-filesystem" /app/mcp-src/filesystem && \
    cp -R "${PNPM_GLOBAL_ROOT}/@modelcontextprotocol/server-sequential-thinking" /app/mcp-src/sequential-thinking && \
    cp -R "${PNPM_GLOBAL_ROOT}/@tobilu/qmd" /app/mcp-src/qmd

# MCP / QMD 持久化目录
ENV XDG_DATA_HOME=/app/data/mcp/xdg-data
ENV XDG_CACHE_HOME=/app/data/mcp/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/mcp/xdg-config
ENV QMD_DATA_DIR=/app/data/qmd
ENV CODE_INDEX_INDEXER_PATH=/app/data/mcp/code-index



# 从构建阶段复制虚拟环境、uv 和 gitleaks
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
# COPY --from=builder /usr/local/bin/gitleaks /usr/local/bin/gitleaks
COPY --from=builder /usr/bin/gitleaks /usr/local/bin/gitleaks

# code-index-mcp 是 Python 包（非 npm 包），安装到系统 PATH
RUN pip install --no-cache-dir code-index-mcp
RUN python - <<'PY'
from pathlib import Path
import importlib.util
import shutil

target = Path("/app/mcp-src/code-index-mcp")
target.mkdir(parents=True, exist_ok=True)
spec = importlib.util.find_spec("code_index_mcp")
if spec and spec.submodule_search_locations:
    source_root = Path(list(spec.submodule_search_locations)[0]).resolve()
    package_root = source_root.parent
    dst = target / "code_index_mcp"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(source_root, dst)
    marker = target / ".source_snapshot"
    marker.write_text(f"{package_root}\n", encoding="utf-8")
PY

# 复制应用代码
COPY . .

# 创建上传目录并设置启动脚本权限
RUN mkdir -p /app/uploads/zip_files /app/data/mcp /app/data/mcp/code-index /app/data/mcp/xdg-config /app/data/qmd /app/mcp-src /app/mcp-src/code-index-mcp && \
    chmod +x /app/docker-entrypoint.sh /app/scripts/sync_mcp_sources.sh

# 暴露端口
EXPOSE 8000

# 启动命令 - 使用启动脚本自动执行数据库迁移
CMD ["/app/docker-entrypoint.sh"]
