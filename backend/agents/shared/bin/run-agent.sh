#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/opt/data}"
SEED_DIR="${HERMES_SEED_DIR:-/opt/seed}"

# Bootstrap: copy seed files into data dir if missing
if [ -d "${SEED_DIR}" ]; then
  for f in config.yaml .env.example SOUL.md; do
    if [ -f "${SEED_DIR}/${f}" ] && [ ! -f "${HERMES_HOME}/${f}" ]; then
      cp "${SEED_DIR}/${f}" "${HERMES_HOME}/${f}"
    fi
  done
  for d in skills memories sessions cron state; do
    if [ -d "${SEED_DIR}/${d}" ] && [ ! -d "${HERMES_HOME}/${d}" ]; then
      cp -r "${SEED_DIR}/${d}" "${HERMES_HOME}/${d}"
    fi
  done
fi

if [ -f "${HERMES_HOME}/.env" ]; then
  set -a
  . "${HERMES_HOME}/.env"
  set +a
fi

# Keep container alive for dispatch via docker exec
exec tail -f /dev/null
