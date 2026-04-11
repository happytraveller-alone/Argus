ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG BACKEND_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple
ARG YASA_VERSION=v0.2.33
ARG YASA_UAST_VERSION=v0.2.8
# 0 = 自动选择（x86_64 使用预构建二进制，arm64 从源码编译）
# 1 = 强制从源码编译
ARG YASA_BUILD_FROM_SOURCE=0

# ─── Stage 1: yasa-fetcher ────────────────────────────────────────────────────
# 纯下载/编译阶段。launcher 文件不在此阶段 COPY，因此 launcher 变动不会破坏此层缓存。
# cache key = 版本 ARG + 基础镜像 + overrides（arm64 编译需要）
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS yasa-fetcher

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES
ARG YASA_VERSION
ARG YASA_UAST_VERSION
ARG YASA_BUILD_FROM_SOURCE

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV YASA_HOME=/opt/yasa
ENV YASA_BIN_DIR=/opt/yasa/bin
ENV YASA_ENGINE_DIR=/opt/yasa/engine
ENV YASA_REAL_BIN=/opt/yasa/bin/yasa-engine.real
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}

# 注意：launcher 文件不在此处 COPY，移至 yasa-builder 阶段
COPY backend_old/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py
COPY frontend/yasa-engine-overrides /tmp/yasa-engine-overrides

RUN --mount=type=cache,id=vulhunter-yasa-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-yasa-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=vulhunter-yasa-runner-tool-archive,target=/var/cache/vulhunter-tools \
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
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    cmd_timeout=420; \
    download_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${download_step_timeout}" ]; then download_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /var/cache/vulhunter-tools "${YASA_BIN_DIR}" "${YASA_ENGINE_DIR}" /opt/yasa-runtime; \
    ARCH="$(uname -m)"; \
    case "${ARCH}" in \
      x86_64|amd64) \
        YASA_RELEASE_ASSET="yasa-linux-x64.zip"; \
        YASA_RELEASE_BIN="yasa-engine-linux-x64"; \
        UAST_PLATFORM="linux-amd64"; \
        YASA_PKG_TARGET="node18-linux-x64"; \
        YASA_GO_ARCH="amd64"; \
        YASA_SOURCE_BUILD_REQUIRED="0" ;; \
      aarch64|arm64) \
        YASA_RELEASE_ASSET=""; \
        YASA_RELEASE_BIN=""; \
        UAST_PLATFORM="linux-arm64"; \
        YASA_PKG_TARGET="node18-linux-arm64"; \
        YASA_GO_ARCH="arm64"; \
        YASA_SOURCE_BUILD_REQUIRED="1" ;; \
      *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    if [ "${YASA_BUILD_FROM_SOURCE}" = "1" ] || [ "${YASA_SOURCE_BUILD_REQUIRED}" = "1" ]; then \
      DOING_SOURCE_BUILD="1"; \
    else \
      DOING_SOURCE_BUILD="0"; \
    fi; \
    if [ "${DOING_SOURCE_BUILD}" = "1" ]; then \
      install_builder_packages() { \
        apt-get update && \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
          bash \
          ca-certificates \
          curl \
          unzip \
          git \
          nodejs \
          npm \
          golang-go; \
      }; \
    else \
      install_builder_packages() { \
        apt-get update && \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
          ca-certificates \
          curl \
          unzip; \
      }; \
    fi; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_builder_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_builder_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
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
    mkdir -p "${YASA_ENGINE_DIR}/deps/uast4go" "${YASA_ENGINE_DIR}/deps/uast4py"; \
    if [ "${DOING_SOURCE_BUILD}" = "1" ]; then \
      cd "${YASA_ENGINE_DIR}"; \
      npm ci --no-audit --fund=false || npm install --no-audit --fund=false; \
      npx tsc; \
      npx pkg . --targets "${YASA_PKG_TARGET}" --output "${YASA_REAL_BIN}" --options max-old-space-size=13312; \
      chmod +x "${YASA_REAL_BIN}"; \
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
      build_uast4go_with_proxy() { \
        proxy="$1"; \
        sumdb="$2"; \
        GOPROXY="${proxy}" GOSUMDB="${sumdb}" CGO_ENABLED=0 GOOS=linux GOARCH="${YASA_GO_ARCH}" \
          go build -o "${YASA_ENGINE_DIR}/deps/uast4go/uast4go" .; \
      }; \
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
    else \
      if [ -z "${YASA_RELEASE_ASSET}" ] || [ -z "${YASA_RELEASE_BIN}" ]; then \
        echo "prebuilt release unavailable for ${ARCH}; set YASA_BUILD_FROM_SOURCE=1 to compile from source" >&2; \
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
      chmod +x "${YASA_REAL_BIN}"; \
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
      download_uast_bin "uast4go-${UAST_PLATFORM}" "${YASA_ENGINE_DIR}/deps/uast4go/uast4go"; \
      download_uast_bin "uast4py-${UAST_PLATFORM}" "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
    fi; \
    ln -sfn "${YASA_ENGINE_DIR}/resource" "${YASA_HOME}/resource"; \
    mkdir -p /opt/yasa-runtime/bin /opt/yasa-runtime/engine/deps/uast4go /opt/yasa-runtime/engine/deps/uast4py; \
    cp "${YASA_REAL_BIN}" /opt/yasa-runtime/bin/yasa-engine.real; \
    cp -R "${YASA_ENGINE_DIR}/resource" /opt/yasa-runtime/resource; \
    cp -R "${YASA_ENGINE_DIR}/deps/uast4go/." /opt/yasa-runtime/engine/deps/uast4go/; \
    cp -R "${YASA_ENGINE_DIR}/deps/uast4py/." /opt/yasa-runtime/engine/deps/uast4py/; \
    if [ -d "${YASA_ENGINE_DIR}/deps/uast4py-src" ]; then \
      mkdir -p /opt/yasa-runtime/engine/deps/uast4py-src; \
      cp -R "${YASA_ENGINE_DIR}/deps/uast4py-src/." /opt/yasa-runtime/engine/deps/uast4py-src/; \
    fi; \
    if [ -d "${YASA_HOME}/uast4py-venv" ]; then \
      cp -R "${YASA_HOME}/uast4py-venv" /opt/yasa-runtime/uast4py-venv; \
    fi; \
    test -x /opt/yasa-runtime/bin/yasa-engine.real

# ─── Stage 2: yasa-builder ───────────────────────────────────────────────────
# 应用 launcher wrapper 脚本。cache key = fetcher 产物 + launcher 文件内容。
# 当仅 launcher 变动时，fetcher 层命中 GHA 缓存，本阶段仅执行文件复制操作（极快）。
FROM yasa-fetcher AS yasa-builder

COPY --chmod=755 backend_old/app/runtime/launchers/yasa_engine_launcher.py /tmp/yasa-launchers/yasa-engine
COPY --chmod=755 backend_old/app/runtime/launchers/yasa_launcher.py /tmp/yasa-launchers/yasa
COPY --chmod=755 backend_old/app/runtime/launchers/yasa_uast4py_launcher.py /tmp/yasa-launchers/uast4py

RUN set -eux; \
    cp /tmp/yasa-launchers/yasa-engine /opt/yasa-runtime/bin/yasa-engine; \
    chmod +x /opt/yasa-runtime/bin/yasa-engine; \
    cp /tmp/yasa-launchers/yasa /opt/yasa-runtime/bin/yasa; \
    chmod +x /opt/yasa-runtime/bin/yasa; \
    # arm64 源码构建路径：uast4py-venv 存在时使用 launcher 替换预构建 uast4py 二进制
    if [ -d /opt/yasa-runtime/uast4py-venv ]; then \
      cp /tmp/yasa-launchers/uast4py /opt/yasa-runtime/engine/deps/uast4py/uast4py; \
      chmod +x /opt/yasa-runtime/engine/deps/uast4py/uast4py; \
    fi; \
    test -x /opt/yasa-runtime/bin/yasa

# ─── Stage 3: yasa-runner (最终运行镜像) ──────────────────────────────────────
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS yasa-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV YASA_HOME=/opt/yasa
ENV YASA_BIN_DIR=/opt/yasa/bin
ENV YASA_RESOURCE_DIR=/opt/yasa/resource
ENV PATH=/opt/yasa/bin:${PATH}

RUN --mount=type=cache,id=vulhunter-yasa-runner-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-yasa-runner-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
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
    install_runtime_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY --from=yasa-builder /opt/yasa-runtime /opt/yasa

RUN set -eux; \
    ln -sf /opt/yasa/bin/yasa /usr/local/bin/yasa; \
    ln -sf /opt/yasa/bin/yasa-engine /usr/local/bin/yasa-engine; \
    /opt/yasa/bin/yasa --version; \
    test -d /opt/yasa/resource; \
    test -x /opt/yasa/engine/deps/uast4go/uast4go; \
    test -x /opt/yasa/engine/deps/uast4py/uast4py

WORKDIR /scan

CMD ["/opt/yasa/bin/yasa", "--version"]
