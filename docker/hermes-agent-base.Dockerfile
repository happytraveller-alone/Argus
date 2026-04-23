# TODO: Replace with official Hermes image when available (ghcr.io/nousresearch/hermes-agent:latest)
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG HERMES_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG HERMES_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG HERMES_APT_MIRROR_FALLBACK=deb.debian.org
ARG HERMES_APT_SECURITY_FALLBACK=security.debian.org

FROM ${DOCKERHUB_LIBRARY_MIRROR}/ubuntu:22.04 AS base

ARG HERMES_APT_MIRROR_PRIMARY
ARG HERMES_APT_SECURITY_PRIMARY
ARG HERMES_APT_MIRROR_FALLBACK
ARG HERMES_APT_SECURITY_FALLBACK

RUN --mount=type=cache,id=vulhunter-hermes-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-hermes-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "30";'; \
      echo 'Acquire::https::Timeout "30";'; \
      echo 'Acquire::ForceIPv4 "true";'; \
    } > /etc/apt/apt.conf.d/99-hermes-network; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      printf 'deb http://%s/ubuntu jammy main restricted universe multiverse\n' "${main_host}" > /etc/apt/sources.list; \
      printf 'deb http://%s/ubuntu jammy-updates main restricted universe multiverse\n' "${main_host}" >> /etc/apt/sources.list; \
      printf 'deb http://%s/ubuntu jammy-security main restricted universe multiverse\n' "${security_host}" >> /etc/apt/sources.list; \
    }; \
    install_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        jq \
        git; \
    }; \
    main_host="${HERMES_APT_MIRROR_PRIMARY}"; \
    security_host="${HERMES_APT_SECURITY_PRIMARY}"; \
    write_sources "${main_host}" "${security_host}"; \
    if ! install_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      main_host="${HERMES_APT_MIRROR_FALLBACK}"; \
      security_host="${HERMES_APT_SECURITY_FALLBACK}"; \
      write_sources "${main_host}" "${security_host}"; \
      install_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/data /opt/bin /opt/seed

COPY backend/agents/shared/bin/healthcheck.sh /opt/bin/healthcheck.sh
COPY backend/agents/shared/bin/run-agent.sh /opt/bin/run-agent.sh
RUN chmod +x /opt/bin/healthcheck.sh /opt/bin/run-agent.sh

VOLUME ["/opt/data"]

WORKDIR /opt/data

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD ["sh", "/opt/bin/healthcheck.sh"]

ENTRYPOINT ["/opt/bin/run-agent.sh"]
