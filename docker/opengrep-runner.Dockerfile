ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG OPENGREP_VERSION=v1.20.0

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS opengrep-builder

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG OPENGREP_VERSION
ARG TARGETARCH

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1

RUN --mount=type=cache,id=vulhunter-opengrep-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-opengrep-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=vulhunter-opengrep-runner-tool-archive,target=/var/cache/vulhunter-tools \
    set -eux; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-trixie}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb http://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb http://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb http://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        bash \
        python3-minimal; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /var/cache/vulhunter-tools /opt/opengrep /scan; \
    ARCH="${TARGETARCH:-}"; \
    if [ -z "${ARCH}" ]; then \
      ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"; \
    fi; \
    case "${ARCH}" in \
      amd64|x86_64) OG_DIST="opengrep_manylinux_x86" ;; \
      arm64|aarch64) OG_DIST="opengrep_manylinux_aarch64" ;; \
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
    cp "${OG_CACHE}" /opt/opengrep/opengrep.real; \
    chmod +x /opt/opengrep/opengrep.real; \
    printf '%s\n' '#!/bin/sh' \
      'unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy' \
      'export NO_PROXY=*' \
      'export no_proxy=*' \
      'exec /opt/opengrep/opengrep.real "$@"' \
      > /usr/local/bin/opengrep; \
    chmod +x /usr/local/bin/opengrep

COPY backend/assets/scan_rule_assets/rules_opengrep /opt/opengrep/rules/rules_opengrep
COPY backend/assets/scan_rule_assets/rules_from_patches /opt/opengrep/rules/rules_from_patches
COPY docker/opengrep-scan.sh /usr/local/bin/opengrep-scan
RUN chmod +x /usr/local/bin/opengrep-scan && /usr/local/bin/opengrep-scan --self-test

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS opengrep-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1

RUN --mount=type=cache,id=vulhunter-opengrep-runner-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-opengrep-runner-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-trixie}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb http://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb http://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb http://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        bash \
        python3-minimal; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

COPY --from=opengrep-builder /opt/opengrep/opengrep.real /opt/opengrep/opengrep.real
COPY --from=opengrep-builder /opt/opengrep/rules /opt/opengrep/rules
COPY --from=opengrep-builder /usr/local/bin/opengrep /usr/local/bin/opengrep
COPY --from=opengrep-builder /usr/local/bin/opengrep-scan /usr/local/bin/opengrep-scan

RUN chmod +x /opt/opengrep/opengrep.real /usr/local/bin/opengrep /usr/local/bin/opengrep-scan && \
    mkdir -p /scan

WORKDIR /scan

CMD ["opengrep-scan", "--self-test"]
