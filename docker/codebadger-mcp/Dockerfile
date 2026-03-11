# CodeBadger MCP service container (Streamable HTTP at /mcp).
#
# We vendor CodeBadger at build time by downloading a tagged source tarball.
# This avoids needing git in the build environment and makes the version explicit.

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim

WORKDIR /app

ARG CODEBADGER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG CODEBADGER_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG CODEBADGER_APT_MIRROR_FALLBACK=deb.debian.org
ARG CODEBADGER_APT_SECURITY_FALLBACK=security.debian.org
ARG CODEBADGER_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG CODEBADGER_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG CODEBADGER_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_INDEX_URL=${CODEBADGER_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${CODEBADGER_PYPI_INDEX_PRIMARY}

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
        apt-get update && apt-get install -y --no-install-recommends curl ca-certificates; \
    }; \
    write_sources "${CODEBADGER_APT_MIRROR_PRIMARY}" "${CODEBADGER_APT_SECURITY_PRIMARY}"; \
    if ! install_packages; then \
        rm -rf /var/lib/apt/lists/*; \
        write_sources "${CODEBADGER_APT_MIRROR_FALLBACK}" "${CODEBADGER_APT_SECURITY_FALLBACK}"; \
        install_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# Pinned CodeBadger version (update consciously).
ARG CODEBADGER_VERSION=v0.3.5-beta
ARG GIT_MIRROR_PREFIX=https://ghfast.top

RUN set -eux; \
    ORIGIN_URL="https://github.com/Lekssays/codebadger/archive/refs/tags/${CODEBADGER_VERSION}.tar.gz"; \
    MIRROR_URL="${GIT_MIRROR_PREFIX}/${ORIGIN_URL}"; \
    if ! curl -fsSL "${MIRROR_URL}" | tar -xz --strip-components=1; then \
        curl -fsSL "${ORIGIN_URL}" | tar -xz --strip-components=1; \
    fi

RUN set -eux; \
    install_with_index() { \
        index_url="$1"; \
        PIP_INDEX_URL="${index_url}" pip install --no-cache-dir --retries 3 --timeout 120 -r requirements.txt; \
    }; \
    if ! install_with_index "${CODEBADGER_PYPI_INDEX_PRIMARY}"; then \
        old_ifs="$IFS"; \
        IFS=','; \
        for index_url in ${CODEBADGER_PYPI_INDEX_CANDIDATES}; do \
            [ -n "${index_url}" ] || continue; \
            if install_with_index "${index_url}"; then \
                IFS="$old_ifs"; \
                exit 0; \
            fi; \
        done; \
        IFS="$old_ifs"; \
        install_with_index "${CODEBADGER_PYPI_INDEX_FALLBACK}"; \
    fi

EXPOSE 4242

CMD ["python", "main.py"]
