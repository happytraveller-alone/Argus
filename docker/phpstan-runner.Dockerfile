ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS phpstan-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PHPSTAN_HOME=/opt/phpstan

COPY --chmod=755 backend/app/runtime/launchers/phpstan_launcher.py /usr/local/bin/phpstan

RUN --mount=type=cache,id=vulhunter-phpstan-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-phpstan-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=vulhunter-phpstan-runner-tool-archive,target=/var/cache/vulhunter-tools \
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
        php-cli; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /var/cache/vulhunter-tools "${PHPSTAN_HOME}" /scan; \
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
    PHPSTAN_CACHE="/var/cache/vulhunter-tools/phpstan.phar"; \
    if [ ! -s "${PHPSTAN_CACHE}" ]; then \
      download_with_fallback \
        "${PHPSTAN_CACHE}" \
        "https://gh-proxy.com/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar" \
        "https://v6.gh-proxy.org/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar" \
        "https://gh-proxy.org/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar" \
        "https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar"; \
    fi; \
    cp "${PHPSTAN_CACHE}" "${PHPSTAN_HOME}/phpstan"; \
    chmod +x "${PHPSTAN_HOME}/phpstan"; \
    phpstan --version >/dev/null

WORKDIR /scan

CMD ["phpstan", "--version"]
