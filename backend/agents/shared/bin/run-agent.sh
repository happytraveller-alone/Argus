#!/usr/bin/env bash
set -euo pipefail

# Container entrypoint wrapper for hermes agents.
# Loads env from HERMES_HOME/.env if present, then execs hermes.

HERMES_HOME="${HERMES_HOME:-/opt/data}"

if [ -f "${HERMES_HOME}/.env" ]; then
  # shellcheck disable=SC1091
  set -a
  . "${HERMES_HOME}/.env"
  set +a
fi

exec hermes "$@"
