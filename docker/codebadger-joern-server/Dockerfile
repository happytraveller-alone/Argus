# CodeBadger Joern server container.
#
# This image bundles:
# - Joern CLI + server (downloaded release tarball)
# - Python3 (used by /playground/build_cpg.py invoked via docker exec)
#
# It stays idle by default; CodeBadger MCP will docker-exec into it to:
# - Generate CPGs into /playground/cpgs/<hash>/
# - Start/stop Joern server instances on ports 2000-2999

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim

WORKDIR /

ARG CODEBADGER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG CODEBADGER_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG CODEBADGER_APT_MIRROR_FALLBACK=deb.debian.org
ARG CODEBADGER_APT_SECURITY_FALLBACK=security.debian.org
ARG GIT_MIRROR_PREFIX=https://gh-proxy.org

RUN set -eux; \
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
    install_packages() { \
        apt-get update && apt-get install -y --no-install-recommends wget curl unzip openjdk-21-jre-headless ca-certificates; \
    }; \
    write_sources "${CODEBADGER_APT_MIRROR_PRIMARY}" "${CODEBADGER_APT_SECURITY_PRIMARY}"; \
    if ! install_packages; then \
        rm -rf /var/lib/apt/lists/*; \
        write_sources "${CODEBADGER_APT_MIRROR_FALLBACK}" "${CODEBADGER_APT_SECURITY_FALLBACK}"; \
        install_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# Pin Joern version for reproducibility (matches CodeBadger default).
ENV JOERN_VERSION=4.0.478

RUN set -eux; \
    ORIGIN_URL="https://github.com/joernio/joern/releases/download/v${JOERN_VERSION}/joern-cli.zip"; \
    MIRROR_URL="${GIT_MIRROR_PREFIX}/${ORIGIN_URL}"; \
    if ! curl -fsSL "${MIRROR_URL}" -o /tmp/joern-cli.zip; then \
        curl -fsSL "${ORIGIN_URL}" -o /tmp/joern-cli.zip; \
    fi; \
    mkdir -p /opt/joern; \
    unzip -q /tmp/joern-cli.zip -d /opt/joern; \
    rm /tmp/joern-cli.zip

ENV PATH="/opt/joern/joern-cli:${PATH}"

WORKDIR /playground

CMD ["sh", "-c", "tail -f /dev/null"]
