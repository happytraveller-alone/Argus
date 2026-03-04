# ============================================
# 多阶段构建 - 构建阶段
# ============================================
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG UV_IMAGE=ghcr.nju.edu.cn/astral-sh/uv:latest
ARG BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com
ARG BACKEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG BACKEND_PNPM_VERSION=9.15.4
ARG BACKEND_PNPM_INSTALL_OPTIONAL=0
ARG BACKEND_INSTALL_CJK_FONTS=1
FROM ${UV_IMAGE} AS uvbin
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim AS nodebase
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
RUN --mount=type=cache,id=deepaudit-backend-builder-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=deepaudit-backend-builder-apt-cache,target=/var/cache/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libffi-dev \
        wget \
        gitleaks

# 下载并安装 Gitleaks 预编译二进制文件
# ENV GITLEAKS_VERSION=8.30.0
# RUN wget -q https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     tar -xzf gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     mv gitleaks /usr/local/bin/gitleaks && \
#     chmod +x /usr/local/bin/gitleaks && \
#     rm gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz

# 安装 uv
COPY --from=uvbin /uv /usr/local/bin/uv

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

# 只安装运行时依赖（不需要 gcc）；CJK 字体可通过 BACKEND_INSTALL_CJK_FONTS 控制
ARG BACKEND_INSTALL_CJK_FONTS
RUN --mount=type=cache,id=deepaudit-backend-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=deepaudit-backend-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    RUNTIME_PACKAGES=" \
        libpq5 \
        curl \
        git \
        unzip \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        shared-mime-info"; \
    if [ "${BACKEND_INSTALL_CJK_FONTS}" = "1" ]; then \
      RUNTIME_PACKAGES="${RUNTIME_PACKAGES} fonts-noto-cjk"; \
    fi; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${RUNTIME_PACKAGES}; \
    if [ "${BACKEND_INSTALL_CJK_FONTS}" = "1" ]; then \
      fc-cache -fv; \
    fi

# 引入 Node.js 22 运行时并安装 pnpm（镜像优先，失败回退官方源）
ARG BACKEND_NPM_REGISTRY_PRIMARY
ARG BACKEND_NPM_REGISTRY_FALLBACK
ARG BACKEND_PNPM_VERSION
ARG BACKEND_PNPM_INSTALL_OPTIONAL
COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=cache,id=deepaudit-backend-npm,target=/root/.npm \
    set -eux; \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
    ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack; \
    npm config set fetch-retries 2; \
    npm config set fetch-retry-factor 2; \
    npm config set fetch-retry-mintimeout 5000; \
    npm config set fetch-retry-maxtimeout 20000; \
    install_pnpm() { \
      reg="$1"; \
      attempt=1; \
      if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
        echo "npm registry ${reg} is unreachable, skip directly." >&2; \
        return 1; \
      fi; \
      npm config set registry "${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        if npm install -g "pnpm@${BACKEND_PNPM_VERSION}" --loglevel=warn; then \
          return 0; \
        fi; \
        echo "npm install pnpm failed via ${reg} (attempt ${attempt}/2), retrying..." >&2; \
        sleep $((attempt * 2)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    install_pnpm "${BACKEND_NPM_REGISTRY_PRIMARY}" || install_pnpm "${BACKEND_NPM_REGISTRY_FALLBACK}"; \
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
    
# 安装 PMD
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip -o /tmp/pmd.zip && \
    unzip -q /tmp/pmd.zip -d /opt && \
    ln -s /opt/pmd-bin-7.0.0/bin/pmd /usr/local/bin/pmd && \
    rm /tmp/pmd.zip

# 安装 MCP 相关运行时（pnpm + qmd CLI），镜像优先并支持官方回退
# 使用 --ignore-scripts 避免 node-llama-cpp 等可选构建脚本拖慢构建
RUN --mount=type=cache,id=deepaudit-backend-pnpm-store,target=/pnpm/store \
    set -eux; \
    mkdir -p /pnpm /pnpm/global /pnpm/store; \
    pnpm config set store-dir /pnpm/store; \
    pnpm config set global-bin-dir /pnpm; \
    pnpm config set global-dir /pnpm/global; \
    pnpm config set fetch-retries 1; \
    pnpm config set fetch-retry-factor 2; \
    pnpm config set fetch-retry-mintimeout 2000; \
    pnpm config set fetch-retry-maxtimeout 8000; \
    pnpm config set network-concurrency 8; \
    pnpm config set prefer-offline true; \
    pnpm config set @node-llama-cpp:registry "${BACKEND_NPM_REGISTRY_FALLBACK}"; \
    pnpm config set @huggingface:registry "${BACKEND_NPM_REGISTRY_FALLBACK}"; \
    install_mcp_packages() { \
      reg="$1"; \
      attempt=1; \
      install_flags="--ignore-scripts --prefer-offline"; \
      if [ "${BACKEND_PNPM_INSTALL_OPTIONAL}" != "1" ]; then \
        install_flags="${install_flags} --no-optional"; \
      fi; \
      if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
        echo "pnpm registry ${reg} is unreachable, skip directly." >&2; \
        return 1; \
      fi; \
      pnpm config set registry "${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        if pnpm add -g ${install_flags} \
          @modelcontextprotocol/server-filesystem \
          @modelcontextprotocol/server-memory \
          @modelcontextprotocol/server-sequential-thinking \
          @tobilu/qmd; then \
          return 0; \
        fi; \
        echo "pnpm add global MCP packages failed via ${reg} (attempt ${attempt}/2), retrying..." >&2; \
        sleep $((attempt * 2)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    install_mcp_packages "${BACKEND_NPM_REGISTRY_PRIMARY}" || install_mcp_packages "${BACKEND_NPM_REGISTRY_FALLBACK}"; \
    pnpm bin -g; \
    command -v qmd; \
    PNPM_GLOBAL_ROOT="$(pnpm root -g)"; \
    PNPM_GLOBAL_DIR="$(dirname "${PNPM_GLOBAL_ROOT}")"; \
    export PNPM_GLOBAL_ROOT; \
    # 定向补齐 better-sqlite3 原生模块，避免 --ignore-scripts 导致运行期缺失 binding。
    pnpm --dir "${PNPM_GLOBAL_DIR}" --config.virtual-store-dir=.pnpm rebuild better-sqlite3; \
    # 构建期硬性校验：确保 better-sqlite3 可实际创建连接。
    PNPM_BETTER_SQLITE_DIR="$(find "${PNPM_GLOBAL_DIR}/.pnpm" -maxdepth 1 -type d -name 'better-sqlite3@*' | head -n 1)"; \
    [ -n "${PNPM_BETTER_SQLITE_DIR}" ]; \
    export PNPM_BETTER_SQLITE_DIR; \
    node -e 'const path=require("node:path");const pkg=process.env.PNPM_BETTER_SQLITE_DIR;if(!pkg){throw new Error("PNPM_BETTER_SQLITE_DIR is not set");}const Database=require(path.join(pkg,"node_modules","better-sqlite3"));const db=new Database(":memory:");db.prepare("SELECT 1 AS ok").get();db.close();console.log("better-sqlite3 smoke check passed");'; \
    mkdir -p /app/mcp-src; \
    cp -R -L "${PNPM_GLOBAL_ROOT}/@modelcontextprotocol/server-filesystem" /app/mcp-src/filesystem; \
    cp -R -L "${PNPM_GLOBAL_ROOT}/@modelcontextprotocol/server-sequential-thinking" /app/mcp-src/sequential-thinking; \
    cp -R -L "${PNPM_GLOBAL_ROOT}/@tobilu/qmd" /app/mcp-src/qmd

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

# code-index-mcp 是 Python 包（非 npm 包），安装到系统 PATH（镜像失败时回退官方源）
RUN --mount=type=cache,id=deepaudit-backend-pip-cache,target=/root/.cache/pip \
    set -eux; \
    if ! pip install --retries 5 --timeout 60 --disable-pip-version-check code-index-mcp; then \
      PIP_INDEX_URL="https://pypi.org/simple" pip install --retries 5 --timeout 60 --disable-pip-version-check code-index-mcp; \
    fi
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
    chmod +x /app/docker-entrypoint.sh /app/scripts/sync_mcp_sources.sh /app/scripts/install_codex_skills.sh

# 暴露端口
EXPOSE 8000

# 启动命令 - 使用启动脚本自动执行数据库迁移
CMD ["/app/docker-entrypoint.sh"]
