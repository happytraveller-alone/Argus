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
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.mirrors.ustc.edu.cn/simple/,https://pypi.org/simple
ARG BACKEND_INSTALL_CJK_FONTS=0
ARG BACKEND_INSTALL_YASA=1
ARG YASA_VERSION=v0.2.33
ARG YASA_UAST_VERSION=v0.2.8
ARG YASA_BUILD_FROM_SOURCE=1
ARG DOCKER_CLI_IMAGE=docker:cli
FROM ${UV_IMAGE} AS uvbin
FROM ${DOCKER_CLI_IMAGE} AS docker-cli-src
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS python-base
FROM python-base AS builder

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
        libffi-dev; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_builder_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_builder_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=uvbin /uv /usr/local/bin/uv

# 配置 uv/pip 镜像（主源 + 回退）
ENV UV_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}

# 复制依赖文件与镜像源测速脚本
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

# 安装 Python 依赖到虚拟环境
RUN --mount=type=cache,id=vulhunter-backend-uv-cache,target=/root/.cache/uv \
    set -eux; \
    cmd_timeout=420; \
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
        if timeout "${uv_step_timeout}" env VIRTUAL_ENV="${BACKEND_VENV_PATH}" PATH="${BACKEND_VENV_PATH}/bin:${PATH}" UV_HTTP_TIMEOUT="${uv_http_timeout}" UV_INDEX_URL="${index_url}" PIP_INDEX_URL="${index_url}" uv sync --active --frozen --no-dev; then \
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
    uv venv "${BACKEND_VENV_PATH}"; \
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
FROM python-base AS runtime-base

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
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}

ENV YASA_HOME=/opt/yasa
ENV YASA_BIN_DIR=/opt/yasa/bin
ENV YASA_ENGINE_DIR=/opt/yasa/engine
ENV YASA_REAL_BIN=/opt/yasa/bin/yasa-engine.real
ENV YASA_ENGINE_WRAPPER_BIN=/opt/yasa/bin/yasa-engine
ENV YASA_WRAPPER_BIN=/opt/yasa/bin/yasa

COPY --chmod=755 backend/app/runtime/launchers/yasa_engine_launcher.py /tmp/yasa-launchers/yasa-engine
COPY --chmod=755 backend/app/runtime/launchers/yasa_launcher.py /tmp/yasa-launchers/yasa
COPY --chmod=755 backend/app/runtime/launchers/yasa_uast4py_launcher.py /tmp/yasa-launchers/uast4py

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

COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

# 复制 docker CLI 及 buildx 插件，供 runner_preflight 以 subprocess 方式执行 docker build
# buildx 是 Docker 23+ 执行 BuildKit 构建的必要插件（--mount=type=cache 等特性依赖它）
COPY --from=docker-cli-src /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli-src /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx

# ============================================
# 多阶段构建 - 扫描工具基础阶段
# ============================================
FROM runtime-base AS scanner-tools-base

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_INSTALL_YASA
ARG YASA_VERSION
ARG YASA_UAST_VERSION
ARG YASA_BUILD_FROM_SOURCE

COPY frontend/yasa-engine-overrides /tmp/yasa-engine-overrides

RUN --mount=type=cache,id=vulhunter-backend-scanner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-backend-scanner-apt-cache,target=/var/cache/apt,sharing=locked \
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
    install_unzip() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends unzip; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_unzip; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_unzip; \
    fi; \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,id=vulhunter-backend-tool-archive,target=/var/cache/vulhunter-tools \
    set -eux; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    cmd_timeout=420; \
    download_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${download_step_timeout}" ]; then download_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /var/cache/vulhunter-tools "${YASA_BIN_DIR}" "${YASA_ENGINE_DIR}"; \
    ARCH="$(uname -m)"; \
    case "${ARCH}" in \
      x86_64|amd64) \
        YASA_RELEASE_ASSET="yasa-linux-x64.zip"; \
        YASA_RELEASE_BIN="yasa-engine-linux-x64"; \
        UAST_PLATFORM="linux-amd64"; \
        YASA_PKG_TARGET="node18-linux-x64"; \
        YASA_GO_ARCH="amd64"; \
        YASA_UAST_BUILD_MODE="prebuilt"; \
        YASA_SOURCE_BUILD_REQUIRED="0" ;; \
      aarch64|arm64) \
        YASA_RELEASE_ASSET=""; \
        YASA_RELEASE_BIN=""; \
        UAST_PLATFORM="linux-arm64"; \
        YASA_PKG_TARGET="node18-linux-arm64"; \
        YASA_GO_ARCH="arm64"; \
        YASA_UAST_BUILD_MODE="source"; \
        YASA_SOURCE_BUILD_REQUIRED="1" ;; \
      *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;; \
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
    if [ "${BACKEND_INSTALL_YASA}" != "1" ]; then \
      echo "BACKEND_INSTALL_YASA=${BACKEND_INSTALL_YASA}, skip built-in YASA install."; \
      exit 0; \
    fi; \
    if [ "${YASA_BUILD_FROM_SOURCE}" != "1" ] && [ "${YASA_SOURCE_BUILD_REQUIRED}" = "1" ]; then \
      echo "YASA source build is required for ${ARCH}; set YASA_BUILD_FROM_SOURCE=1, BACKEND_INSTALL_YASA=0, or provide host override." >&2; \
      exit 1; \
    fi; \
    if [ "${YASA_BUILD_FROM_SOURCE}" != "1" ] && { [ -z "${YASA_RELEASE_ASSET}" ] || [ -z "${YASA_RELEASE_BIN}" ]; }; then \
      echo "YASA prebuilt release is unavailable for ${ARCH}; set YASA_BUILD_FROM_SOURCE=1, BACKEND_INSTALL_YASA=0, or provide host override." >&2; \
      exit 1; \
    fi; \
    YASA_TARBALL="/var/cache/vulhunter-tools/yasa-engine-${YASA_VERSION}.tar.gz"; \
    if [ ! -s "${YASA_TARBALL}" ]; then \
      download_with_fallback \
        "${YASA_TARBALL}" \
        "https://gh-proxy.com/https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" \
        "https://v6.gh-proxy.org/https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" \
        "https://gh-proxy.org/https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" \
        "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz"; \
    fi; \
    tar -xzf "${YASA_TARBALL}" -C /tmp; \
    rm -rf "${YASA_ENGINE_DIR}"; \
    mv "/tmp/YASA-Engine-${YASA_VERSION#v}" "${YASA_ENGINE_DIR}"; \
    if [ "${YASA_BUILD_FROM_SOURCE}" = "1" ]; then \
      build_deps="nodejs npm"; \
      if [ "${YASA_UAST_BUILD_MODE}" = "source" ]; then \
        build_deps="${build_deps} golang-go"; \
      fi; \
      apt-get update; \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${build_deps}; \
      rm -rf /var/lib/apt/lists/*; \
      if [ -f /tmp/yasa-engine-overrides/src/config.ts ]; then \
        cp /tmp/yasa-engine-overrides/src/config.ts "${YASA_ENGINE_DIR}/src/config.ts"; \
      fi; \
      if [ -f /tmp/yasa-engine-overrides/src/interface/starter.ts ]; then \
        cp /tmp/yasa-engine-overrides/src/interface/starter.ts "${YASA_ENGINE_DIR}/src/interface/starter.ts"; \
      fi; \
      if [ -f /tmp/yasa-engine-overrides/src/engine/analyzer/common/analyzer.ts ]; then \
        cp /tmp/yasa-engine-overrides/src/engine/analyzer/common/analyzer.ts "${YASA_ENGINE_DIR}/src/engine/analyzer/common/analyzer.ts"; \
      fi; \
      if [ -f /tmp/yasa-engine-overrides/src/engine/analyzer/java/common/java-analyzer.ts ]; then \
        cp /tmp/yasa-engine-overrides/src/engine/analyzer/java/common/java-analyzer.ts "${YASA_ENGINE_DIR}/src/engine/analyzer/java/common/java-analyzer.ts"; \
      fi; \
      cd "${YASA_ENGINE_DIR}"; \
      npm ci --no-audit --fund=false || npm install --no-audit --fund=false; \
      npx tsc; \
      npx pkg . --targets "${YASA_PKG_TARGET}" --output "${YASA_REAL_BIN}" --options max-old-space-size=13312; \
    else \
      if [ -z "${YASA_RELEASE_ASSET}" ] || [ -z "${YASA_RELEASE_BIN}" ]; then \
        echo "YASA prebuilt release is unavailable for ${ARCH}; set YASA_BUILD_FROM_SOURCE=1 or BACKEND_INSTALL_YASA=0." >&2; \
        exit 1; \
      fi; \
      YASA_RELEASE_ZIP="/var/cache/vulhunter-tools/${YASA_RELEASE_ASSET}"; \
      if [ ! -s "${YASA_RELEASE_ZIP}" ]; then \
        download_with_fallback \
          "${YASA_RELEASE_ZIP}" \
          "https://gh-proxy.com/https://github.com/antgroup/YASA-Engine/releases/download/${YASA_VERSION}/${YASA_RELEASE_ASSET}" \
          "https://v6.gh-proxy.org/https://github.com/antgroup/YASA-Engine/releases/download/${YASA_VERSION}/${YASA_RELEASE_ASSET}" \
          "https://gh-proxy.org/https://github.com/antgroup/YASA-Engine/releases/download/${YASA_VERSION}/${YASA_RELEASE_ASSET}" \
          "https://github.com/antgroup/YASA-Engine/releases/download/${YASA_VERSION}/${YASA_RELEASE_ASSET}"; \
      fi; \
      rm -rf /tmp/yasa-release; \
      unzip -oq "${YASA_RELEASE_ZIP}" "${YASA_RELEASE_BIN}" -d /tmp/yasa-release; \
      cp "/tmp/yasa-release/${YASA_RELEASE_BIN}" "${YASA_REAL_BIN}"; \
    fi; \
    chmod +x "${YASA_REAL_BIN}"; \
    mkdir -p "${YASA_ENGINE_DIR}/deps/uast4go" "${YASA_ENGINE_DIR}/deps/uast4py"; \
    build_uast4go_with_proxy() { \
      proxy="$1"; \
      sumdb="$2"; \
      GOPROXY="${proxy}" GOSUMDB="${sumdb}" CGO_ENABLED=0 GOOS=linux GOARCH="${YASA_GO_ARCH}" \
        go build -o "${YASA_ENGINE_DIR}/deps/uast4go/uast4go" .; \
    }; \
    download_uast_bin() { \
      bin_name="$1"; \
      target="$2"; \
      cache_file="/var/cache/vulhunter-tools/${bin_name}"; \
      if [ ! -s "${cache_file}" ]; then \
        download_with_fallback \
          "${cache_file}" \
          "https://gh-proxy.com/https://github.com/antgroup/YASA-UAST/releases/latest/download/${bin_name}" \
          "https://v6.gh-proxy.org/https://github.com/antgroup/YASA-UAST/releases/latest/download/${bin_name}" \
          "https://gh-proxy.org/https://github.com/antgroup/YASA-UAST/releases/latest/download/${bin_name}" \
          "https://github.com/antgroup/YASA-UAST/releases/latest/download/${bin_name}"; \
      fi; \
      cp "${cache_file}" "${target}"; \
      chmod +x "${target}"; \
    }; \
    if [ "${YASA_UAST_BUILD_MODE}" = "source" ]; then \
      YASA_UAST_TARBALL="/var/cache/vulhunter-tools/yasa-uast-${YASA_UAST_VERSION}.tar.gz"; \
      if [ ! -s "${YASA_UAST_TARBALL}" ]; then \
        download_with_fallback \
          "${YASA_UAST_TARBALL}" \
          "https://gh-proxy.com/https://github.com/antgroup/YASA-UAST/archive/refs/tags/${YASA_UAST_VERSION}.tar.gz" \
          "https://v6.gh-proxy.org/https://github.com/antgroup/YASA-UAST/archive/refs/tags/${YASA_UAST_VERSION}.tar.gz" \
          "https://gh-proxy.org/https://github.com/antgroup/YASA-UAST/archive/refs/tags/${YASA_UAST_VERSION}.tar.gz" \
          "https://github.com/antgroup/YASA-UAST/archive/refs/tags/${YASA_UAST_VERSION}.tar.gz"; \
      fi; \
      rm -rf /tmp/yasa-uast-src; \
      mkdir -p /tmp/yasa-uast-src; \
      tar -xzf "${YASA_UAST_TARBALL}" -C /tmp/yasa-uast-src; \
      YASA_UAST_SRC_DIR="$(find /tmp/yasa-uast-src -maxdepth 1 -type d -name 'YASA-UAST-*' | head -n1)"; \
      if [ -z "${YASA_UAST_SRC_DIR}" ]; then \
        echo "failed to locate extracted YASA-UAST source tree" >&2; \
        exit 1; \
      fi; \
      export GOCACHE="/var/cache/vulhunter-tools/go-build-cache"; \
      export GOMODCACHE="/var/cache/vulhunter-tools/go-mod-cache"; \
      mkdir -p "${GOCACHE}" "${GOMODCACHE}"; \
      (cd "${YASA_UAST_SRC_DIR}/parser-Go" && mkdir -p dist && \
        build_uast4go_with_proxy "https://goproxy.cn,direct" "sum.golang.google.cn" || \
        build_uast4go_with_proxy "https://proxy.golang.org,direct" "sum.golang.org"); \
      chmod +x "${YASA_ENGINE_DIR}/deps/uast4go/uast4go"; \
      rm -rf "${YASA_ENGINE_DIR}/deps/uast4py-src" "${YASA_HOME}/uast4py-venv"; \
      cp -R "${YASA_UAST_SRC_DIR}/parser-Python" "${YASA_ENGINE_DIR}/deps/uast4py-src"; \
      python3 -m venv "${YASA_HOME}/uast4py-venv"; \
      order_pypi_indexes() { \
        raw_candidates="${PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"; \
        python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind pypi --timeout-seconds 2 || printf '%s\n' "${raw_candidates}" | tr ',' '\n'; \
      }; \
      install_uast4py_deps() { \
        idx="$1"; \
        PIP_CACHE_DIR="/var/cache/vulhunter-tools/pip-cache" \
        "${YASA_HOME}/uast4py-venv/bin/pip" install --disable-pip-version-check -i "${idx}" \
          -r "${YASA_ENGINE_DIR}/deps/uast4py-src/requirements.txt"; \
      }; \
      ordered_pypi_indexes="$(order_pypi_indexes)"; \
      installed_uast4py=0; \
      for idx in $(printf '%s\n' "${ordered_pypi_indexes}"); do \
        [ -n "${idx}" ] || continue; \
        if install_uast4py_deps "${idx}"; then \
          installed_uast4py=1; \
          break; \
        fi; \
      done; \
      if [ "${installed_uast4py}" != "1" ]; then \
        echo "failed to install YASA Python parser dependencies" >&2; \
        exit 1; \
      fi; \
      cp /tmp/yasa-launchers/uast4py "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
      chmod +x "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
    else \
      download_uast_bin "uast4go-${UAST_PLATFORM}" "${YASA_ENGINE_DIR}/deps/uast4go/uast4go"; \
      download_uast_bin "uast4py-${UAST_PLATFORM}" "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
    fi; \
    ln -sfn "${YASA_ENGINE_DIR}/resource" "${YASA_HOME}/resource"; \
    cp /tmp/yasa-launchers/yasa-engine "${YASA_ENGINE_WRAPPER_BIN}"; \
    chmod +x "${YASA_ENGINE_WRAPPER_BIN}"; \
    cp /tmp/yasa-launchers/yasa "${YASA_WRAPPER_BIN}"; \
    chmod +x "${YASA_WRAPPER_BIN}"; \
    ln -sf "${YASA_WRAPPER_BIN}" /usr/local/bin/yasa; \
    ln -sf "${YASA_ENGINE_WRAPPER_BIN}" /usr/local/bin/yasa-engine; \
    /usr/local/bin/yasa --version; \
    test -d /opt/yasa/resource

# ============================================
# 多阶段构建 - 运行阶段
# ============================================
FROM runtime-base AS dev-runtime

COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

RUN set -eux; \
    for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
      find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
    done; \
    rm -rf /root/.cache/pip; \
    rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1
ENV RUNNER_PREFLIGHT_BUILD_CONTEXT=/app

RUN mkdir -p /app /opt/backend-venv /root/.cache/uv /app/uploads/zip_files /app/data/runtime

EXPOSE 8000

CMD ["python3", "-m", "app.runtime.container_startup", "dev"]

FROM runtime-base AS runtime

# 提前复制 builder 产物，避免 runtime 与 builder 并行下载导致网络争抢
COPY --from=builder /opt/backend-venv /opt/backend-venv

RUN set -eux; \
    for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
      find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
    done; \
    rm -rf /root/.cache/pip; \
    rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1
ENV RUNNER_PREFLIGHT_BUILD_CONTEXT=/opt/backend-build-context

# Runtime 持久化目录
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
RUN mkdir -p /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config



# 仅复制运行时所需代码与脚本，避免把测试/文档打进运行镜像
COPY backend/app /app/app
COPY backend/static /app/static
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py
COPY docker /opt/backend-build-context/docker
COPY backend/app /opt/backend-build-context/backend/app
COPY backend/scripts/package_source_selector.py /opt/backend-build-context/backend/scripts/package_source_selector.py
COPY backend/scripts/flow_parser_runner.py /opt/backend-build-context/backend/scripts/flow_parser_runner.py
COPY frontend/yasa-engine-overrides /opt/backend-build-context/frontend/yasa-engine-overrides

# 创建运行时持久化目录
RUN mkdir -p /app/uploads/zip_files /app/data/runtime /app/data/runtime/xdg-config /opt/backend-build-context/backend/scripts /opt/backend-build-context/frontend

# 暴露端口
EXPOSE 8000

CMD ["python3", "-m", "app.runtime.container_startup", "prod"]
