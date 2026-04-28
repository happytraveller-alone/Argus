#!/bin/sh
set -eu

usage() {
  cat <<'USAGE'
Usage: scripts/prepare-agentflow-wheelhouse.sh [--clean] [--dry-run]

Populate the local AgentFlow runner wheelhouse used by docker/agentflow-runner.Dockerfile.
Generated *.whl files are local build artifacts: keep them out of git, but keep them
inside the Docker build context.

Environment overrides:
  AGENTFLOW_WHEELHOUSE_DIR       default: docker/agentflow-wheelhouse
  AGENTFLOW_WHEELHOUSE_USE_DOCKER default: auto (auto|1|0)
  DOCKERHUB_LIBRARY_MIRROR       default: docker.m.daocloud.io/library
  BACKEND_PYPI_INDEX_PRIMARY     default: https://pypi.tuna.tsinghua.edu.cn/simple
  BACKEND_PYPI_EXTRA_INDEX_URLS  default: https://mirrors.aliyun.com/pypi/simple/ (sequential fallback, not pip fanout)
  BACKEND_PYPI_INDEX_FALLBACK    default: https://pypi.org/simple
  BACKEND_PIP_TIMEOUT_SECONDS    default: 45
  BACKEND_PIP_RETRIES            default: 2
  AGENTFLOW_P1_PYTHON_DEPS       default: jinja2>=3.1.6 pydantic>=2.11.0 PyYAML>=6.0.2 typer>=0.16.0
USAGE
}

clean=0
dry_run=0
for arg in "$@"; do
  case "${arg}" in
    --clean) clean=1 ;;
    --dry-run) dry_run=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: ${arg}" >&2; usage >&2; exit 2 ;;
  esac
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd)
cd "${repo_root}"

: "${AGENTFLOW_WHEELHOUSE_DIR:=docker/agentflow-wheelhouse}"
: "${AGENTFLOW_WHEELHOUSE_USE_DOCKER:=auto}"
: "${DOCKERHUB_LIBRARY_MIRROR:=docker.m.daocloud.io/library}"
: "${BACKEND_PYPI_INDEX_PRIMARY:=https://pypi.tuna.tsinghua.edu.cn/simple}"
: "${BACKEND_PYPI_EXTRA_INDEX_URLS:=https://mirrors.aliyun.com/pypi/simple/}"
: "${BACKEND_PYPI_INDEX_FALLBACK:=https://pypi.org/simple}"
: "${BACKEND_PIP_TIMEOUT_SECONDS:=45}"
: "${BACKEND_PIP_RETRIES:=2}"
: "${AGENTFLOW_P1_PYTHON_DEPS:=jinja2>=3.1.6 pydantic>=2.11.0 PyYAML>=6.0.2 typer>=0.16.0}"

mkdir -p "${AGENTFLOW_WHEELHOUSE_DIR}"
if [ ! -e "${AGENTFLOW_WHEELHOUSE_DIR}/.gitkeep" ]; then
  : > "${AGENTFLOW_WHEELHOUSE_DIR}/.gitkeep"
fi

if [ "${clean}" -eq 1 ]; then
  find "${AGENTFLOW_WHEELHOUSE_DIR}" -maxdepth 1 -type f -name '*.whl' -delete
fi

should_use_docker=0
case "${AGENTFLOW_WHEELHOUSE_USE_DOCKER}" in
  1|true|yes|on) should_use_docker=1 ;;
  0|false|no|off) should_use_docker=0 ;;
  auto)
    if command -v docker >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
      should_use_docker=1
    fi
    ;;
  *) echo "Invalid AGENTFLOW_WHEELHOUSE_USE_DOCKER=${AGENTFLOW_WHEELHOUSE_USE_DOCKER}; expected auto|1|0" >&2; exit 2 ;;
esac

if [ "${should_use_docker}" -eq 1 ]; then
  image="${DOCKERHUB_LIBRARY_MIRROR}/python:3.12-slim"
  echo "[agentflow-wheelhouse-script] target-python=docker image=${image}"
  if [ "${dry_run}" -eq 1 ]; then
    echo "[agentflow-wheelhouse-script] dry-run docker run --rm -v ${repo_root}:/workspace -w /workspace ${image} sh scripts/prepare-agentflow-wheelhouse.sh"
    exit 0
  fi
  exec docker run --rm \
    -e AGENTFLOW_WHEELHOUSE_USE_DOCKER=0 \
    -e AGENTFLOW_WHEELHOUSE_DIR="${AGENTFLOW_WHEELHOUSE_DIR}" \
    -e BACKEND_PYPI_INDEX_PRIMARY="${BACKEND_PYPI_INDEX_PRIMARY}" \
    -e BACKEND_PYPI_EXTRA_INDEX_URLS="${BACKEND_PYPI_EXTRA_INDEX_URLS}" \
    -e BACKEND_PYPI_INDEX_FALLBACK="${BACKEND_PYPI_INDEX_FALLBACK}" \
    -e BACKEND_PIP_TIMEOUT_SECONDS="${BACKEND_PIP_TIMEOUT_SECONDS}" \
    -e BACKEND_PIP_RETRIES="${BACKEND_PIP_RETRIES}" \
    -e AGENTFLOW_P1_PYTHON_DEPS="${AGENTFLOW_P1_PYTHON_DEPS}" \
    -v "${repo_root}:/workspace" \
    -w /workspace \
    "${image}" \
    sh scripts/prepare-agentflow-wheelhouse.sh "$@"
fi

run_pip_wheel_group() {
  group=$1
  shift
  index_url=$1
  shift
  index_label=$1
  shift

  echo "[agentflow-wheelhouse-script][${group}] network-download index=${index_label} url=${index_url:-pip-default}"
  if [ -n "${index_url}" ]; then
    # Intentional word splitting for extra indexes and dependency list build args.
    python -m pip wheel \
      --find-links "${AGENTFLOW_WHEELHOUSE_DIR}" \
      --index-url "${index_url}" \
      --prefer-binary \
      --timeout "${BACKEND_PIP_TIMEOUT_SECONDS}" \
      --retries "${BACKEND_PIP_RETRIES}" \
      --wheel-dir "${AGENTFLOW_WHEELHOUSE_DIR}" \
      "$@"
  else
    python -m pip wheel \
      --find-links "${AGENTFLOW_WHEELHOUSE_DIR}" \
      --prefer-binary \
      --timeout "${BACKEND_PIP_TIMEOUT_SECONDS}" \
      --retries "${BACKEND_PIP_RETRIES}" \
      --wheel-dir "${AGENTFLOW_WHEELHOUSE_DIR}" \
      "$@"
  fi
}

wheel_group_with_fallback() {
  group=$1
  shift
  if run_pip_wheel_group "${group}" "${BACKEND_PYPI_INDEX_PRIMARY}" primary "$@"; then
    echo "[agentflow-wheelhouse-script][${group}] complete via=primary"
    return 0
  fi
  for extra_index_url in ${BACKEND_PYPI_EXTRA_INDEX_URLS}; do
    if [ -n "${extra_index_url}" ] && [ "${extra_index_url}" != "${BACKEND_PYPI_INDEX_PRIMARY}" ]; then
      echo "[agentflow-wheelhouse-script][${group}] primary-failed extra=enabled"
      if run_pip_wheel_group "${group}" "${extra_index_url}" extra "$@"; then
        echo "[agentflow-wheelhouse-script][${group}] complete via=extra"
        return 0
      fi
    fi
  done
  if [ -n "${BACKEND_PYPI_INDEX_FALLBACK}" ] && [ "${BACKEND_PYPI_INDEX_FALLBACK}" != "${BACKEND_PYPI_INDEX_PRIMARY}" ]; then
    echo "[agentflow-wheelhouse-script][${group}] extra-failed fallback=enabled"
    run_pip_wheel_group "${group}" "${BACKEND_PYPI_INDEX_FALLBACK}" fallback "$@"
    echo "[agentflow-wheelhouse-script][${group}] complete via=fallback"
    return 0
  fi
  echo "[agentflow-wheelhouse-script][${group}] failed fallback=unavailable" >&2
  return 1
}

if [ "${dry_run}" -eq 1 ]; then
  echo "[agentflow-wheelhouse-script] dry-run wheelhouse=${AGENTFLOW_WHEELHOUSE_DIR}"
  echo "[agentflow-wheelhouse-script][build-backend] packages=hatchling>=1.27.0"
  echo "[agentflow-wheelhouse-script][runtime-deps] packages=${AGENTFLOW_P1_PYTHON_DEPS}"
  exit 0
fi

python -m pip --version
wheel_group_with_fallback build-backend 'hatchling>=1.27.0'
# Intentional word splitting: AGENTFLOW_P1_PYTHON_DEPS is a space-delimited build arg.
# Wheel top-level runtime dependencies one at a time so a flaky mirror for one
# dependency does not force all previously downloaded wheels to be discarded.
# shellcheck disable=SC2086
for runtime_dep in ${AGENTFLOW_P1_PYTHON_DEPS}; do
  wheel_group_with_fallback runtime-deps "${runtime_dep}"
done

count=$(find "${AGENTFLOW_WHEELHOUSE_DIR}" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ')
echo "[agentflow-wheelhouse-script] complete wheelhouse=${AGENTFLOW_WHEELHOUSE_DIR} wheels=${count}"
