ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG HERMES_UV_IMAGE=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:b3c543b6c4f23a5f2df22866bd7857e5d304b67a564f4feab6ac22044dde719b
ARG HERMES_GOSU_IMAGE=tianon/gosu:1.19-trixie@sha256:3b176695959c71e123eb390d427efc665eeb561b1540e82679c15e992006b8b9
ARG HERMES_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG HERMES_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG HERMES_APT_MIRROR_FALLBACK=deb.debian.org
ARG HERMES_APT_SECURITY_FALLBACK=security.debian.org

FROM ${HERMES_UV_IMAGE} AS uv_source
FROM ${HERMES_GOSU_IMAGE} AS gosu_source
FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:13.4

ARG VCS_REF=unknown
ARG HERMES_UPSTREAM_SHA=bf196a3fc0fd1f79353369e8732051db275c6276
ARG HERMES_SUBMODULE_STATUS=third_party/hermes-agent=bf196a3fc0fd1f79353369e8732051db275c6276;third_party/hermes-agent/tinker-atropos=65f084ee8054a5d02aeac76e24ed60388511c82b
ARG HERMES_SOURCE_DIGEST=sha256:e0c66b8305e844fcf469412d99f0016f35382d3bc1f04159a61319c67a5f63fc

LABEL org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/NousResearch/hermes-agent" \
      org.vulhunter.hermes.upstream_sha="${HERMES_UPSTREAM_SHA}" \
      org.vulhunter.hermes.submodules="${HERMES_SUBMODULE_STATUS}" \
      org.opencontainers.image.digest="${HERMES_SOURCE_DIGEST}"

ENV PYTHONUNBUFFERED=1

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
    write_secure_sources() { \
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
        build-essential \
        ca-certificates \
        docker-cli \
        git \
        libffi-dev \
        openssh-client \
        procps \
        python3 \
        python3-dev \
        ripgrep; \
    }; \
    main_host="${HERMES_APT_MIRROR_PRIMARY}"; \
    security_host="${HERMES_APT_SECURITY_PRIMARY}"; \
    write_sources "${main_host}" "${security_host}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      main_host="${HERMES_APT_MIRROR_FALLBACK}"; \
      security_host="${HERMES_APT_SECURITY_FALLBACK}"; \
      write_sources "${main_host}" "${security_host}"; \
      install_runtime_packages; \
    fi; \
    write_secure_sources "${main_host}" "${security_host}"; \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10000 -m -d /opt/data hermes

COPY --chmod=0755 --from=gosu_source /gosu /usr/local/bin/
COPY --chmod=0755 --from=uv_source /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /opt/hermes

COPY --chown=hermes:hermes third_party/hermes-agent/. .
RUN rm -rf web package.json package-lock.json \
  && chown hermes:hermes /opt/hermes

USER hermes
RUN uv venv && \
    uv pip install --no-cache-dir -e "."

USER root
RUN mkdir -p /opt/bin
COPY --chmod=0755 backend/agents/shared/bin/healthcheck.sh /opt/bin/healthcheck.sh
COPY --chmod=0755 backend/agents/shared/bin/role-init.sh /opt/bin/role-init.sh

ENV HERMES_HOME=/opt/data
ENV PATH="/opt/hermes/.venv/bin:/opt/data/.local/bin:${PATH}"

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD ["sh", "/opt/bin/healthcheck.sh"]

VOLUME ["/opt/data"]
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["sh", "-c", "/opt/bin/role-init.sh && exec sleep infinity"]
