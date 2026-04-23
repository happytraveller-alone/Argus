#!/bin/sh
set -e
test -d /opt/data || exit 1
test -w /opt/data || exit 1
test -f /opt/data/config.yaml || exit 1
test -f /opt/data/SOUL.md || exit 1
/opt/hermes/.venv/bin/hermes --version >/dev/null 2>&1 || exit 1
exit 0
