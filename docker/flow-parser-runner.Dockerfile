ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS flow-parser-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_CANDIDATES

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/flow-parser-venv
ENV PATH=/opt/flow-parser-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}

RUN --mount=type=cache,id=argus-flow-parser-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=argus-flow-parser-runner-apt-cache,target=/var/cache/apt,sharing=locked \
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
RUN --mount=type=cache,id=argus-flow-parser-runner-pip,target=/root/.cache/pip \
  set -eux; \
  order_pypi_indexes() { \
  raw_candidates="${PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"; \
  if [ -n "${BACKEND_PYPI_INDEX_PRIMARY}" ]; then \
  raw_candidates="${BACKEND_PYPI_INDEX_PRIMARY},${raw_candidates}"; \
  fi; \
  printf '%s\n' "${raw_candidates}" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | awk 'NF && !seen[$0]++'; \
  }; \
  install_runtime_deps() { \
  idx="$1"; \
  PIP_DEFAULT_TIMEOUT=60 /opt/flow-parser-venv/bin/pip install --disable-pip-version-check -i "${idx}" -r /tmp/flow-parser-runner.requirements.txt; \
  }; \
  ordered_pypi_indexes="$(order_pypi_indexes)"; \
  installed_runtime_deps=0; \
  for idx in $(printf '%s\n' "${ordered_pypi_indexes}"); do \
  [ -n "${idx}" ] || continue; \
  if install_runtime_deps "${idx}"; then \
  installed_runtime_deps=1; \
  break; \
  fi; \
  done; \
  if [ "${installed_runtime_deps}" != "1" ]; then \
  echo "failed to install flow-parser runner runtime dependencies" >&2; \
  exit 1; \
  fi

WORKDIR /opt/flow-parser

COPY backend/scripts/flow_parser_runner.py /opt/flow-parser/flow_parser_runner.py
COPY backend/scripts/flow_parser_host.py /opt/flow-parser/flow_parser_host.py

RUN set -eux; \
  mkdir -p /scan; \
  command -v code2flow >/dev/null 2>&1; \
  code2flow --help >/dev/null 2>&1; \
  python3 /opt/flow-parser/flow_parser_runner.py --help >/dev/null 2>&1; \
  python3 /opt/flow-parser/flow_parser_runner.py definitions-batch --request /tmp/nonexistent.json --response /tmp/nonexistent.out >/dev/null 2>&1 || true

WORKDIR /scan

CMD ["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"]
