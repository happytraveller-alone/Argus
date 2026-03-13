# ============================================
# 多阶段构建 - 构建阶段
# ============================================
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG UV_IMAGE=ghcr.nju.edu.cn/astral-sh/uv:latest
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG BACKEND_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple
ARG BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com
ARG BACKEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG BACKEND_NPM_REGISTRY_CANDIDATES=https://registry.npmmirror.com,https://mirrors.cloud.tencent.com/npm,https://registry.npmjs.org
ARG BACKEND_PNPM_VERSION=9.15.4
ARG BACKEND_PNPM_CMD_TIMEOUT_SECONDS=420
ARG BACKEND_PNPM_INSTALL_OPTIONAL=0
ARG BACKEND_INSTALL_CJK_FONTS=0
FROM ${UV_IMAGE} AS uvbin
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim AS nodebase
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS builder

WORKDIR /app
ARG BACKEND_PNPM_CMD_TIMEOUT_SECONDS
ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES

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

RUN --mount=type=cache,id=vulhunter-backend-builder-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-backend-builder-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "60";'; \
    } > /etc/apt/apt.conf.d/99-no-proxy; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_builder_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libffi-dev \
        gitleaks; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_builder_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_builder_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# 下载并安装 Gitleaks 预编译二进制文件
# ENV GITLEAKS_VERSION=8.30.0
# RUN wget -q https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     tar -xzf gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz && \
#     mv gitleaks /usr/local/bin/gitleaks && \
#     chmod +x /usr/local/bin/gitleaks && \
#     rm gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz

# 安装 uv
COPY --from=uvbin /uv /usr/local/bin/uv

# 配置 uv/pip 镜像（主源 + 回退）
ENV UV_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}

# 复制依赖文件与镜像源测速脚本
COPY pyproject.toml uv.lock README.md ./
COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

# 安装 Python 依赖到虚拟环境
RUN --mount=type=cache,id=vulhunter-backend-uv-cache,target=/root/.cache/uv \
    set -eux; \
    cmd_timeout="${BACKEND_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
    case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
    uv_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${uv_step_timeout}" ]; then uv_step_timeout="${cmd_timeout}"; fi; \
    uv_http_timeout=45; \
    pypi_index_candidates="${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"; \
    append_unique_index() { \
      index_url="$(printf '%s' "$1" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"; \
      target_file="$2"; \
      [ -n "${index_url}" ] || return 0; \
      touch "${target_file}"; \
      if ! grep -Fxq "${index_url}" "${target_file}"; then \
        printf '%s\n' "${index_url}" >> "${target_file}"; \
      fi; \
    }; \
    append_csv_indexes() { \
      csv="$1"; \
      target_file="$2"; \
      old_ifs="$IFS"; \
      IFS=','; \
      set -- ${csv}; \
      IFS="$old_ifs"; \
      for item do \
        append_unique_index "${item}" "${target_file}"; \
      done; \
    }; \
    order_indexes() { \
      raw_candidates="$1"; \
      python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind pypi --timeout-seconds 2 || printf '%s\n' "${raw_candidates}" | tr ',' '\n'; \
    }; \
    sync_with_index() { \
      index_url="$1"; \
      attempt=1; \
      while [ "${attempt}" -le 2 ]; do \
        echo "uv sync via ${index_url} (attempt ${attempt}/2, timeout ${uv_step_timeout}s)"; \
        if timeout "${uv_step_timeout}" env UV_HTTP_TIMEOUT="${uv_http_timeout}" UV_INDEX_URL="${index_url}" PIP_INDEX_URL="${index_url}" uv sync --frozen --no-dev; then \
          return 0; \
        else \
          status="$?"; \
        fi; \
        if [ "${status}" -eq 124 ]; then \
          echo "uv sync timed out via ${index_url} after ${uv_step_timeout}s (attempt ${attempt}/2)." >&2; \
        else \
          echo "uv sync failed via ${index_url} (attempt ${attempt}/2, exit ${status})." >&2; \
        fi; \
        sleep $((attempt + 1)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    ranked_candidates_file="$(mktemp)"; \
    ordered_indexes_file="$(mktemp)"; \
    attempt_indexes_file="$(mktemp)"; \
    if [ -n "${BACKEND_PYPI_INDEX_PRIMARY:-}" ]; then \
      append_unique_index "${BACKEND_PYPI_INDEX_PRIMARY}" "${attempt_indexes_file}"; \
    fi; \
    if [ -n "${BACKEND_PYPI_INDEX_FALLBACK:-}" ]; then \
      append_unique_index "${BACKEND_PYPI_INDEX_FALLBACK}" "${attempt_indexes_file}"; \
    fi; \
    append_csv_indexes "${pypi_index_candidates}" "${ranked_candidates_file}"; \
    ordered_indexes=""; \
    if [ -s "${ranked_candidates_file}" ]; then \
      pypi_index_candidates="$(paste -sd, "${ranked_candidates_file}")"; \
      ordered_indexes="$(order_indexes "${pypi_index_candidates}")"; \
    fi; \
    if [ -n "${ordered_indexes}" ]; then \
      printf '%s\n' "${ordered_indexes}" > "${ordered_indexes_file}"; \
    elif [ -s "${ranked_candidates_file}" ]; then \
      cp "${ranked_candidates_file}" "${ordered_indexes_file}"; \
    fi; \
    if [ -s "${ordered_indexes_file}" ]; then \
      while IFS= read -r index_url; do \
        append_unique_index "${index_url}" "${attempt_indexes_file}"; \
      done < "${ordered_indexes_file}"; \
    fi; \
    echo "uv sync candidate order:"; \
    cat "${attempt_indexes_file}"; \
    install_result=1; \
    while IFS= read -r index_url; do \
      [ -n "${index_url}" ] || continue; \
      if sync_with_index "${index_url}"; then \
        install_result=0; \
        break; \
      fi; \
    done < "${attempt_indexes_file}"; \
    rm -f "${ranked_candidates_file}" "${ordered_indexes_file}" "${attempt_indexes_file}"; \
    [ "${install_result}" -eq 0 ]; \
    printf 'ready\n' > /tmp/builder-network-ready

# ============================================
# 多阶段构建 - 运行时基础阶段
# ============================================
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim AS runtime-base

WORKDIR /app
ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES
ARG BACKEND_NPM_REGISTRY_CANDIDATES

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
ENV UV_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}
ENV NPM_REGISTRY_CANDIDATES=${BACKEND_NPM_REGISTRY_CANDIDATES}

ENV OPENGREP_HOME=/opt/opengrep
ENV OPENGREP_REAL_BIN=/opt/opengrep/opengrep.real
ENV OPENGREP_WRAPPER_BIN=/opt/opengrep/opengrep

# 只安装运行时依赖（不需要 gcc）；CJK 字体可通过 BACKEND_INSTALL_CJK_FONTS 控制
ARG BACKEND_INSTALL_CJK_FONTS
RUN --mount=type=cache,id=vulhunter-backend-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-backend-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "60";'; \
    } > /etc/apt/apt.conf.d/99-no-proxy; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    RUNTIME_PACKAGES=" \
        libpq5 \
        curl \
        git \
        unzip \
        openjdk-21-jre-headless \
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
    install_runtime_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${RUNTIME_PACKAGES}; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    if [ "${BACKEND_INSTALL_CJK_FONTS}" = "1" ]; then \
      fc-cache -fv; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

# 引入 Node.js 22 运行时并安装 pnpm（镜像优先，失败回退官方源）
ARG BACKEND_NPM_REGISTRY_PRIMARY
ARG BACKEND_NPM_REGISTRY_FALLBACK
ARG BACKEND_PNPM_VERSION
COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=cache,id=vulhunter-backend-npm,target=/root/.npm \
    set -eux; \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
    ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack; \
    npm config set fetch-retries 2; \
    npm config set fetch-retry-factor 2; \
    npm config set fetch-retry-mintimeout 5000; \
    npm config set fetch-retry-maxtimeout 20000; \
    corepack enable; \
    install_pnpm() { \
      reg="$1"; \
      attempt=1; \
      if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
        echo "npm registry probe failed for ${reg}, continue with direct install attempt." >&2; \
      fi; \
      npm config set registry "${reg}"; \
      export COREPACK_NPM_REGISTRY="${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        if corepack prepare "pnpm@${BACKEND_PNPM_VERSION}" --activate; then \
          return 0; \
        fi; \
        echo "corepack prepare pnpm failed via ${reg} (attempt ${attempt}/2), retrying..." >&2; \
        sleep $((attempt * 2)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    install_pnpm "${BACKEND_NPM_REGISTRY_PRIMARY}" || install_pnpm "${BACKEND_NPM_REGISTRY_FALLBACK}"; \
    pnpm --version; \
    node --version; \
    npm --version

# ============================================
# 多阶段构建 - MCP 运行时构建阶段
# ============================================
FROM runtime-base AS mcp-builder

ARG BACKEND_NPM_REGISTRY_PRIMARY
ARG BACKEND_NPM_REGISTRY_FALLBACK
ARG BACKEND_NPM_REGISTRY_CANDIDATES
ARG BACKEND_PNPM_INSTALL_OPTIONAL
ARG BACKEND_PNPM_CMD_TIMEOUT_SECONDS
COPY --from=builder /tmp/builder-network-ready /tmp/builder-network-ready

# 安装 MCP 相关运行时（pnpm + qmd CLI），镜像优先并支持官方回退
# 使用 --ignore-scripts 避免 node-llama-cpp 等可选构建脚本拖慢构建
RUN --mount=type=cache,id=vulhunter-backend-pnpm-store,target=/pnpm/store \
    set -eux; \
    cmd_timeout="${BACKEND_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
    case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
    npm_registry_candidates="${BACKEND_NPM_REGISTRY_CANDIDATES:-${BACKEND_NPM_REGISTRY_PRIMARY},https://mirrors.cloud.tencent.com/npm,${BACKEND_NPM_REGISTRY_FALLBACK}}"; \
    pnpm_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${pnpm_step_timeout}" ]; then pnpm_step_timeout="${cmd_timeout}"; fi; \
    qmd_step_timeout=120; \
    if [ "${cmd_timeout}" -lt "${qmd_step_timeout}" ]; then qmd_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /pnpm /pnpm/global /pnpm/store; \
    pnpm config set store-dir /pnpm/store; \
    pnpm config set global-bin-dir /pnpm; \
    pnpm config set global-dir /pnpm/global; \
    pnpm config set fetch-retries 1; \
    pnpm config set fetch-retry-factor 2; \
    pnpm config set fetch-retry-mintimeout 2000; \
    pnpm config set fetch-retry-maxtimeout 8000; \
    pnpm config set network-concurrency 4; \
    pnpm config set prefer-offline true; \
    install_flags="--ignore-scripts --prefer-offline"; \
    if [ "${BACKEND_PNPM_INSTALL_OPTIONAL}" != "1" ]; then \
      install_flags="${install_flags} --no-optional"; \
    fi; \
    order_registries() { \
      raw_candidates="$1"; \
      python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind npm --timeout-seconds 2 || printf '%s\n' "${raw_candidates}" | tr ',' '\n'; \
    }; \
    install_mcp_package_once() { \
      reg="$1"; \
      label="$2"; \
      step_timeout="$3"; \
      package_name="$4"; \
      attempt=1; \
      if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
        echo "pnpm registry probe failed for ${reg}, continue with direct add attempt." >&2; \
      fi; \
      pnpm config set registry "${reg}"; \
      pnpm config set @node-llama-cpp:registry "${reg}"; \
      pnpm config set @huggingface:registry "${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        echo "pnpm add ${label} via ${reg} (attempt ${attempt}/2, timeout ${step_timeout}s)"; \
        if timeout "${step_timeout}" pnpm add -g ${install_flags} "${package_name}"; then \
          return 0; \
        else \
          status="$?"; \
        fi; \
        if [ "${status}" -eq 124 ]; then \
          echo "pnpm add ${label} timed out via ${reg} after ${step_timeout}s (attempt ${attempt}/2)." >&2; \
        else \
          echo "pnpm add ${label} failed via ${reg} (attempt ${attempt}/2, exit ${status})." >&2; \
        fi; \
        sleep $((attempt + 1)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    install_mcp_package() { \
      label="$1"; \
      step_timeout="$2"; \
      package_name="$3"; \
      ordered_registries="$(order_registries "${npm_registry_candidates}")"; \
      order_file="$(mktemp)"; \
      printf '%s\n' "${ordered_registries}" > "${order_file}"; \
      while IFS= read -r reg; do \
        [ -n "${reg}" ] || continue; \
        if install_mcp_package_once "${reg}" "${label}" "${step_timeout}" "${package_name}"; then \
          rm -f "${order_file}"; \
          return 0; \
        fi; \
      done < "${order_file}"; \
      rm -f "${order_file}"; \
      return 1; \
    }; \
    install_or_mark_npx_fallback() { \
      label="$1"; \
      step_timeout="$2"; \
      package_name="$3"; \
      binary_name="$4"; \
      if install_mcp_package "${label}" "${step_timeout}" "${package_name}"; then \
        return 0; \
      fi; \
      echo "pnpm add ${label} failed on all candidates; runtime will fallback to npx for ${package_name} (${binary_name})." >&2; \
      return 0; \
    }; \
    install_or_mark_npx_fallback "filesystem" "${pnpm_step_timeout}" "@modelcontextprotocol/server-filesystem" "mcp-server-filesystem"; \
    install_or_mark_npx_fallback "sequential-thinking" "${pnpm_step_timeout}" "@modelcontextprotocol/server-sequential-thinking" "mcp-server-sequential-thinking"; \
    install_or_mark_npx_fallback "qmd-cli" "${qmd_step_timeout}" "@tobilu/qmd" "qmd"; \
    pnpm bin -g || true

# 定向补齐 better-sqlite3 原生模块，避免 --ignore-scripts 导致运行期缺失 binding。
# 构建期硬性校验：确保 better-sqlite3 可实际创建连接。
RUN --mount=type=cache,id=vulhunter-backend-pnpm-store,target=/pnpm/store \
    set -eux; \
    cmd_timeout="${BACKEND_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
    case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
    rebuild_timeout=120; \
    if [ "${cmd_timeout}" -lt "${rebuild_timeout}" ]; then rebuild_timeout="${cmd_timeout}"; fi; \
    PNPM_GLOBAL_ROOT="$(pnpm root -g)"; \
    PNPM_GLOBAL_DIR="$(dirname "${PNPM_GLOBAL_ROOT}")"; \
    PNPM_BETTER_SQLITE_DIR="$(find "${PNPM_GLOBAL_DIR}/.pnpm" -maxdepth 1 -type d -name 'better-sqlite3@*' | head -n 1)"; \
    if [ -z "${PNPM_BETTER_SQLITE_DIR}" ]; then \
      echo "better-sqlite3 not present in pnpm global store; skip rebuild and smoke check."; \
      exit 0; \
    fi; \
    export PNPM_GLOBAL_ROOT; \
    attempt=1; \
    while [ "${attempt}" -le 2 ]; do \
      echo "pnpm rebuild better-sqlite3 (attempt ${attempt}/2, timeout ${rebuild_timeout}s)"; \
      if timeout "${rebuild_timeout}" pnpm --dir "${PNPM_GLOBAL_DIR}" --config.virtual-store-dir=.pnpm rebuild better-sqlite3; then \
        break; \
      fi; \
      rebuild_status="$?"; \
      if [ "${rebuild_status}" -eq 124 ]; then \
        echo "pnpm rebuild better-sqlite3 timed out after ${rebuild_timeout}s (attempt ${attempt}/2)." >&2; \
      else \
        echo "pnpm rebuild better-sqlite3 failed with exit ${rebuild_status} (attempt ${attempt}/2)." >&2; \
      fi; \
      if [ "${attempt}" -eq 2 ]; then \
        exit "${rebuild_status}"; \
      fi; \
      sleep $((attempt + 1)); \
      attempt=$((attempt + 1)); \
    done; \
    export PNPM_BETTER_SQLITE_DIR; \
    node -e 'const path=require("node:path");const pkg=process.env.PNPM_BETTER_SQLITE_DIR;if(!pkg){throw new Error("PNPM_BETTER_SQLITE_DIR is not set");}const Database=require(path.join(pkg,"node_modules","better-sqlite3"));const db=new Database(":memory:");db.prepare("SELECT 1 AS ok").get();db.close();console.log("better-sqlite3 smoke check passed");'

# ============================================
# 多阶段构建 - 运行阶段
# ============================================
FROM runtime-base AS dev-runtime

COPY --from=builder /app/.venv /opt/backend-venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/bin/gitleaks /usr/local/bin/gitleaks
COPY --chmod=755 scripts/dev-entrypoint.sh /usr/local/bin/backend-dev-entrypoint.sh

ARG OPENGREP_VERSION=v1.15.1
ARG BACKEND_PNPM_CMD_TIMEOUT_SECONDS
RUN --mount=type=cache,id=vulhunter-backend-tool-archive,target=/var/cache/vulhunter-tools \
    set -eux; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    cmd_timeout="${BACKEND_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
    case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
    download_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${download_step_timeout}" ]; then download_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /var/cache/vulhunter-tools "${OPENGREP_HOME}"; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64|amd64) OG_DIST="opengrep_manylinux_x86" ;; \
      aarch64|arm64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    download_with_fallback() { \
      output="$1"; \
      shift; \
      for url in "$@"; do \
        if ! curl -fsSI --connect-timeout 5 --max-time 12 "${url}" >/dev/null 2>&1 && \
           ! curl -fsS --connect-timeout 5 --max-time 12 --range 0-0 "${url}" -o /dev/null >/dev/null 2>&1; then \
          echo "download source probe failed for ${url}, continue with direct download attempts." >&2; \
        fi; \
        attempt=1; \
        while [ "${attempt}" -le 2 ]; do \
          echo "download ${output} via ${url} (attempt ${attempt}/2, timeout ${download_step_timeout}s)"; \
          if timeout "${download_step_timeout}" curl -fL \
            --connect-timeout 8 \
            --max-time 60 \
            --speed-time 15 \
            --speed-limit 2048 \
            "${url}" \
            -o "${output}.tmp"; then \
            mv "${output}.tmp" "${output}"; \
            return 0; \
          else \
            status="$?"; \
          fi; \
          if [ "${status}" -eq 124 ]; then \
            echo "download timed out: ${url} (attempt ${attempt}/2)." >&2; \
          else \
            echo "download failed: ${url} (attempt ${attempt}/2, exit ${status})." >&2; \
          fi; \
          rm -f "${output}.tmp"; \
          sleep $((attempt + 1)); \
          attempt=$((attempt + 1)); \
        done; \
      done; \
      return 1; \
    }; \
    OG_CACHE="/var/cache/vulhunter-tools/opengrep-${OPENGREP_VERSION}-${OG_DIST}"; \
    if [ ! -s "${OG_CACHE}" ]; then \
      download_with_fallback \
        "${OG_CACHE}" \
        "https://gh-proxy.com/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://v6.gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}"; \
    fi; \
    cp "${OG_CACHE}" "${OPENGREP_REAL_BIN}"; \
    chmod +x "${OPENGREP_REAL_BIN}"; \
    printf '#!/bin/sh\nunset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\nexport NO_PROXY="*"\nexport no_proxy="*"\nexec /usr/local/bin/opengrep.real "$@"\n' \
      > "${OPENGREP_WRAPPER_BIN}"; \
    chmod +x "${OPENGREP_WRAPPER_BIN}"; \
    ln -sf "${OPENGREP_REAL_BIN}" /usr/local/bin/opengrep.real; \
    ln -sf "${OPENGREP_WRAPPER_BIN}" /usr/local/bin/opengrep; \
    opengrep --version


ENV PATH=/app/.venv/bin:/pnpm:${PATH}

RUN mkdir -p /app /app/.venv /root/.cache/uv /app/uploads/zip_files /app/data/mcp

EXPOSE 8000

CMD ["/usr/local/bin/backend-dev-entrypoint.sh"]

FROM runtime-base AS runtime

# 提前复制 builder 产物，避免 runtime 与 builder 并行下载导致网络争抢
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /usr/bin/gitleaks /usr/local/bin/gitleaks

# 从 mcp-builder 复制 MCP 运行时（前置以减少网络并发抢占）
COPY --from=mcp-builder /pnpm /pnpm

# 安装 Opengrep CLI 和 PMD
ARG OPENGREP_VERSION=v1.15.1
ARG BACKEND_PNPM_CMD_TIMEOUT_SECONDS
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK

RUN --mount=type=cache,id=vulhunter-backend-tool-archive,target=/var/cache/vulhunter-tools \
    set -eux; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    cmd_timeout="${BACKEND_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
    case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
    download_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${download_step_timeout}" ]; then download_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /var/cache/vulhunter-tools "${OPENGREP_HOME}"; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64|amd64) OG_DIST="opengrep_manylinux_x86" ;; \
      aarch64|arm64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    download_with_fallback() { \
      output="$1"; \
      shift; \
      for url in "$@"; do \
        if ! curl -fsSI --connect-timeout 5 --max-time 12 "${url}" >/dev/null 2>&1 && \
           ! curl -fsS --connect-timeout 5 --max-time 12 --range 0-0 "${url}" -o /dev/null >/dev/null 2>&1; then \
          echo "download source probe failed for ${url}, continue with direct download attempts." >&2; \
        fi; \
        attempt=1; \
        while [ "${attempt}" -le 2 ]; do \
          echo "download ${output} via ${url} (attempt ${attempt}/2, timeout ${download_step_timeout}s)"; \
          if timeout "${download_step_timeout}" curl -fL \
            --connect-timeout 8 \
            --max-time 60 \
            --speed-time 15 \
            --speed-limit 2048 \
            "${url}" \
            -o "${output}.tmp"; then \
            mv "${output}.tmp" "${output}"; \
            return 0; \
          else \
            status="$?"; \
          fi; \
          if [ "${status}" -eq 124 ]; then \
            echo "download timed out: ${url} (attempt ${attempt}/2)." >&2; \
          else \
            echo "download failed: ${url} (attempt ${attempt}/2, exit ${status})." >&2; \
          fi; \
          rm -f "${output}.tmp"; \
          sleep $((attempt + 1)); \
          attempt=$((attempt + 1)); \
        done; \
      done; \
      return 1; \
    }; \
    OG_CACHE="/var/cache/vulhunter-tools/opengrep-${OPENGREP_VERSION}-${OG_DIST}"; \
    if [ ! -s "${OG_CACHE}" ]; then \
      download_with_fallback \
        "${OG_CACHE}" \
        "https://gh-proxy.com/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://v6.gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
        "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}"; \
    fi; \
    cp "${OG_CACHE}" "${OPENGREP_REAL_BIN}"; \
    chmod +x "${OPENGREP_REAL_BIN}"; \
    printf '#!/bin/sh\nunset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\nexport NO_PROXY="*"\nexport no_proxy="*"\nexec /usr/local/bin/opengrep.real "$@"\n' \
      > "${OPENGREP_WRAPPER_BIN}"; \
    chmod +x "${OPENGREP_WRAPPER_BIN}"; \
    ln -sf "${OPENGREP_REAL_BIN}" /usr/local/bin/opengrep.real; \
    ln -sf "${OPENGREP_WRAPPER_BIN}" /usr/local/bin/opengrep; \
    opengrep --version; \
    PMD_CACHE="/var/cache/vulhunter-tools/pmd-dist-7.0.0-bin.zip"; \
    if [ ! -s "${PMD_CACHE}" ]; then \
      download_with_fallback \
        "${PMD_CACHE}" \
        "https://gh-proxy.com/https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip" \
        "https://v6.gh-proxy.org/https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip" \
        "https://gh-proxy.org/https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip" \
        "https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip"; \
    fi; \
    cp "${PMD_CACHE}" /tmp/pmd.zip; \
    unzip -q /tmp/pmd.zip -d /opt; \
    ln -s /opt/pmd-bin-7.0.0/bin/pmd /usr/local/bin/pmd; \
    rm /tmp/pmd.zip

# MCP / QMD 持久化目录
ENV XDG_DATA_HOME=/app/data/mcp/xdg-data
ENV XDG_CACHE_HOME=/app/data/mcp/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/mcp/xdg-config
RUN mkdir -p /app/data/mcp/xdg-data /app/data/mcp/xdg-cache /app/data/mcp/xdg-config



# code2flow 是 Python 包（非 npm 包），安装到系统 PATH（镜像失败时回退官方源）
RUN --mount=type=cache,id=vulhunter-backend-pip-cache,target=/root/.cache/pip \
    set -eux; \
    pypi_index_candidates="${PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"; \
    order_indexes() { \
      raw_candidates="$1"; \
      python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind pypi --timeout-seconds 2 || printf '%s\n' "${raw_candidates}" | tr ',' '\n'; \
    }; \
    install_python_helpers() { \
      idx="$1"; \
      PIP_INDEX_URL="${idx}" pip install --retries 5 --timeout 60 --disable-pip-version-check code2flow bandit; \
    }; \
    installed=0; \
    ordered_indexes="$(order_indexes "${pypi_index_candidates}")"; \
    order_file="$(mktemp)"; \
    printf '%s\n' "${ordered_indexes}" > "${order_file}"; \
    while IFS= read -r idx; do \
      [ -n "${idx}" ] || continue; \
      if install_python_helpers "${idx}"; then \
        installed=1; \
        break; \
      fi; \
    done < "${order_file}"; \
    rm -f "${order_file}"; \
    [ "${installed}" -eq 1 ]

# 仅复制运行时所需代码与脚本，避免把测试/文档打进运行镜像
COPY app /app/app
COPY static /app/static
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh
COPY --chmod=755 scripts/install_codex_skills.sh /app/scripts/install_codex_skills.sh
COPY scripts/build_skill_registry.py /app/scripts/build_skill_registry.py
COPY scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py
COPY --chmod=755 scripts/run_npx_from_candidates.sh /usr/local/bin/run_npx_from_candidates.sh

RUN set -eux; \
    ensure_npx_wrapper() { \
      binary_name="$1"; \
      package_name="$2"; \
      if command -v "${binary_name}" >/dev/null 2>&1; then \
        return 0; \
      fi; \
      printf '%s\n' '#!/bin/sh' "exec /usr/local/bin/run_npx_from_candidates.sh '${package_name}' \"\\$@\"" > "/usr/local/bin/${binary_name}"; \
      chmod +x "/usr/local/bin/${binary_name}"; \
    }; \
    ensure_npx_wrapper "mcp-server-filesystem" "@modelcontextprotocol/server-filesystem"; \
    ensure_npx_wrapper "mcp-server-sequential-thinking" "@modelcontextprotocol/server-sequential-thinking"; \
    ensure_npx_wrapper "qmd" "@tobilu/qmd"

# 创建运行时持久化目录
RUN mkdir -p /app/uploads/zip_files /app/data/mcp /app/data/mcp/code-index /app/data/mcp/xdg-config

# 暴露端口
EXPOSE 8000

# 启动命令 - 使用启动脚本自动执行数据库迁移
CMD ["/app/docker-entrypoint.sh"]
