#!/bin/sh
# Role-specific initialization: override SOUL.md and config.yaml from seed mount
# Runs after the official entrypoint has bootstrapped defaults into /opt/data
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
SEED_DIR="${HERMES_SEED_DIR:-/opt/seed}"

if [ -d "${SEED_DIR}" ]; then
  for f in SOUL.md config.yaml; do
    if [ -f "${SEED_DIR}/${f}" ]; then
      cp "${SEED_DIR}/${f}" "${HERMES_HOME}/${f}"
    fi
  done
fi
