ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS flow-parser-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/flow-parser-venv
ENV PATH=/opt/flow-parser-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1
ENV PYTHONPATH=/opt/flow-parser

RUN --mount=type=cache,id=vulhunter-flow-parser-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=vulhunter-flow-parser-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_runtime_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        graphviz; \
    }; \
    write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*; \
    python3 -m venv /opt/flow-parser-venv

COPY docker/flow-parser-runner.requirements.txt /tmp/flow-parser-runner.requirements.txt

# Runtime deps pinned in requirements: tree-sitter, tree-sitter-language-pack, code2flow
RUN set -eux; \
    if [ -n "${BACKEND_PYPI_INDEX_PRIMARY}" ]; then \
      /opt/flow-parser-venv/bin/pip install --disable-pip-version-check --no-cache-dir -i "${BACKEND_PYPI_INDEX_PRIMARY}" -r /tmp/flow-parser-runner.requirements.txt; \
    else \
      /opt/flow-parser-venv/bin/pip install --disable-pip-version-check --no-cache-dir -r /tmp/flow-parser-runner.requirements.txt; \
    fi

WORKDIR /opt/flow-parser

COPY app /opt/flow-parser/app
COPY scripts/flow_parser_runner.py /opt/flow-parser/flow_parser_runner.py

RUN mkdir -p /scan && python3 /opt/flow-parser/flow_parser_runner.py definitions-batch --request /tmp/nonexistent.json --response /tmp/nonexistent.out >/dev/null 2>&1 || true

WORKDIR /scan

CMD ["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"]
