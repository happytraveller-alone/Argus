ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG OPENGREP_VERSION=v1.15.1

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS opengrep-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG OPENGREP_VERSION

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV OPENGREP_HOME=/opt/opengrep
ENV OPENGREP_REAL_BIN=/opt/opengrep/opengrep.real
ENV XDG_CONFIG_HOME=/opt/opengrep/xdg-config
ENV XDG_DATA_HOME=/opt/opengrep/xdg-data
ENV XDG_CACHE_HOME=/opt/opengrep/xdg-cache

RUN --mount=type=cache,id=vulhunter-opengrep-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-opengrep-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=vulhunter-opengrep-runner-tool-archive,target=/var/cache/vulhunter-tools \
    set -eux; \
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
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        bash; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /var/cache/vulhunter-tools "${OPENGREP_HOME}" "${XDG_CONFIG_HOME}" "${XDG_DATA_HOME}" "${XDG_CACHE_HOME}" /scan; \
    ARCH="$(uname -m)"; \
    case "${ARCH}" in \
      x86_64|amd64) OG_DIST="opengrep_manylinux_x86" ;; \
      aarch64|arm64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    download_with_fallback() { \
      output="$1"; \
      shift; \
      for url in "$@"; do \
        if curl -fL --connect-timeout 8 --max-time 60 "${url}" -o "${output}.tmp"; then \
          mv "${output}.tmp" "${output}"; \
          return 0; \
        fi; \
        rm -f "${output}.tmp"; \
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
    printf '%s\n' '#!/bin/sh' \
      'unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy' \
      'export NO_PROXY=*' \
      'export no_proxy=*' \
      'exec /opt/opengrep/opengrep.real "$@"' \
      > /usr/local/bin/opengrep; \
    chmod +x /usr/local/bin/opengrep; \
    opengrep --version >/dev/null

COPY backend/assets/scan_rule_assets/rules_opengrep /opt/opengrep/rules/rules_opengrep
COPY backend/assets/scan_rule_assets/rules_from_patches /opt/opengrep/rules/rules_from_patches
COPY docker/opengrep-scan.sh /usr/local/bin/opengrep-scan
RUN chmod +x /usr/local/bin/opengrep-scan && /usr/local/bin/opengrep-scan --self-test

WORKDIR /scan

CMD ["opengrep-scan", "--self-test"]
