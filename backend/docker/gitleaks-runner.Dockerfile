ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG GITLEAKS_VERSION=8.24.2

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS gitleaks-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG GITLEAKS_VERSION

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN --mount=type=cache,id=vulhunter-gitleaks-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-gitleaks-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=vulhunter-gitleaks-runner-tool-archive,target=/var/cache/vulhunter-tools \
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
        tar; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /var/cache/vulhunter-tools /scan; \
    ARCH="$(uname -m)"; \
    case "${ARCH}" in \
      x86_64|amd64) GITLEAKS_ARCH="x64" ;; \
      aarch64|arm64) GITLEAKS_ARCH="arm64" ;; \
      *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    GITLEAKS_CACHE="/var/cache/vulhunter-tools/gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz"; \
    if [ ! -s "${GITLEAKS_CACHE}" ]; then \
      curl -fL --connect-timeout 8 --max-time 60 \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz" \
        -o "${GITLEAKS_CACHE}"; \
    fi; \
    tar -xzf "${GITLEAKS_CACHE}" -C /usr/local/bin gitleaks; \
    chmod +x /usr/local/bin/gitleaks; \
    gitleaks version >/dev/null

WORKDIR /scan

CMD ["gitleaks", "version"]
