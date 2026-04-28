#!/bin/sh
set -eu

group=$1
wheel_dir=$2
shift 2

extra_flags=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--" ]; then
    shift
    break
  fi
  extra_flags="${extra_flags} $1"
  shift
done

if [ "$#" -eq 0 ]; then
  echo "[agentflow-wheelhouse][${group}] no-packages" >&2
  exit 2
fi

mkdir -p "${wheel_dir}" /opt/agentflow-local-wheelhouse

local_count=$(find /opt/agentflow-local-wheelhouse -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ')
if [ "${AGENTFLOW_USE_LOCAL_WHEELHOUSE:-auto}" != "never" ] && [ "${local_count}" -gt 0 ]; then
  echo "[agentflow-wheelhouse][${group}] local-wheelhouse-hit files=${local_count}"
  # Intentional word splitting: Docker build args provide pip option fragments.
  # shellcheck disable=SC2086
  if python -m pip wheel ${extra_flags} --no-index --find-links=/opt/agentflow-local-wheelhouse --timeout "${BACKEND_PIP_TIMEOUT_SECONDS}" --retries "${BACKEND_PIP_RETRIES}" --wheel-dir "${wheel_dir}" "$@"; then
    exit 0
  fi
  echo "[agentflow-wheelhouse][${group}] local-wheelhouse-miss files=${local_count}"
else
  echo "[agentflow-wheelhouse][${group}] local-wheelhouse-miss files=${local_count}"
fi

run_network_wheel() {
  index_url=$1
  index_label=$2
  shift 2
  echo "[agentflow-wheelhouse][${group}] network-fallback index=${index_label} url=${index_url:-pip-default}"
  if [ -n "${index_url}" ]; then
    # Intentional word splitting: Docker build args provide pip option fragments.
    # shellcheck disable=SC2086
    python -m pip wheel ${extra_flags} --find-links=/opt/agentflow-local-wheelhouse --index-url "${index_url}" --timeout "${BACKEND_PIP_TIMEOUT_SECONDS}" --retries "${BACKEND_PIP_RETRIES}" --wheel-dir "${wheel_dir}" "$@"
  else
    # Intentional word splitting: Docker build args provide pip option fragments.
    # shellcheck disable=SC2086
    python -m pip wheel ${extra_flags} --find-links=/opt/agentflow-local-wheelhouse --timeout "${BACKEND_PIP_TIMEOUT_SECONDS}" --retries "${BACKEND_PIP_RETRIES}" --wheel-dir "${wheel_dir}" "$@"
  fi
}

if run_network_wheel "${BACKEND_PYPI_INDEX_PRIMARY:-}" primary "$@"; then
  exit 0
fi

for extra_index_url in ${BACKEND_PYPI_EXTRA_INDEX_URLS:-}; do
  if [ -n "${extra_index_url}" ] && [ "${extra_index_url}" != "${BACKEND_PYPI_INDEX_PRIMARY:-}" ]; then
    if run_network_wheel "${extra_index_url}" extra "$@"; then
      exit 0
    fi
  fi
done

if [ -n "${BACKEND_PYPI_INDEX_FALLBACK:-}" ] && [ "${BACKEND_PYPI_INDEX_FALLBACK}" != "${BACKEND_PYPI_INDEX_PRIMARY:-}" ]; then
  run_network_wheel "${BACKEND_PYPI_INDEX_FALLBACK}" fallback "$@"
  exit 0
fi

exit 1
