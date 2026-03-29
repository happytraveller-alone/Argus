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

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS yasa-builder

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES
ARG YASA_VERSION
ARG YASA_UAST_VERSION

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV YASA_HOME=/opt/yasa
ENV YASA_BIN_DIR=/opt/yasa/bin
ENV YASA_ENGINE_DIR=/opt/yasa/engine
ENV YASA_REAL_BIN=/opt/yasa/bin/yasa-engine.real
ENV YASA_ENGINE_WRAPPER_BIN=/opt/yasa/bin/yasa-engine
ENV YASA_WRAPPER_BIN=/opt/yasa/bin/yasa

COPY --chmod=755 backend/app/runtime/launchers/yasa_engine_launcher.py /tmp/yasa-launchers/yasa-engine
COPY --chmod=755 backend/app/runtime/launchers/yasa_launcher.py /tmp/yasa-launchers/yasa
COPY --chmod=755 backend/app/runtime/launchers/yasa_uast4py_launcher.py /tmp/yasa-launchers/uast4py
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}

COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py
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
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_builder_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_builder_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    cmd_timeout=420; \
    download_step_timeout=90; \
    if [ "${cmd_timeout}" -lt "${download_step_timeout}" ]; then download_step_timeout="${cmd_timeout}"; fi; \
    mkdir -p /var/cache/vulhunter-tools "${YASA_BIN_DIR}" "${YASA_ENGINE_DIR}" /opt/yasa-runtime; \
    ARCH="$(uname -m)"; \
    case "${ARCH}" in \
      x86_64|amd64) \
        YASA_PKG_TARGET="node18-linux-x64"; \
        YASA_GO_ARCH="amd64" ;; \
      aarch64|arm64) \
        YASA_PKG_TARGET="node18-linux-arm64"; \
        YASA_GO_ARCH="arm64" ;; \
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
    mkdir -p "${YASA_ENGINE_DIR}/deps/uast4go" "${YASA_ENGINE_DIR}/deps/uast4py"; \
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
    cp /tmp/yasa-launchers/uast4py "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
    chmod +x "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \
    ln -sfn "${YASA_ENGINE_DIR}/resource" "${YASA_HOME}/resource"; \
    cp /tmp/yasa-launchers/yasa-engine "${YASA_ENGINE_WRAPPER_BIN}"; \
    chmod +x "${YASA_ENGINE_WRAPPER_BIN}"; \
    cp /tmp/yasa-launchers/yasa "${YASA_WRAPPER_BIN}"; \
    chmod +x "${YASA_WRAPPER_BIN}"; \
    mkdir -p /opt/yasa-runtime/bin /opt/yasa-runtime/engine/deps/uast4go /opt/yasa-runtime/engine/deps/uast4py; \
    cp "${YASA_REAL_BIN}" /opt/yasa-runtime/bin/yasa-engine.real; \
    cp "${YASA_ENGINE_WRAPPER_BIN}" /opt/yasa-runtime/bin/yasa-engine; \
    cp "${YASA_WRAPPER_BIN}" /opt/yasa-runtime/bin/yasa; \
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
    test -x /opt/yasa-runtime/bin/yasa

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

COPY --chmod=755 backend/app/runtime/launchers/yasa_engine_launcher.py /tmp/yasa-launchers/yasa-engine
COPY --chmod=755 backend/app/runtime/launchers/yasa_launcher.py /tmp/yasa-launchers/yasa
COPY --chmod=755 backend/app/runtime/launchers/yasa_uast4py_launcher.py /tmp/yasa-launchers/uast4py

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
