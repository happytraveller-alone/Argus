#!/bin/sh
set -e
test -d /opt/data || exit 1
test -w /opt/data || exit 1
test -f /opt/data/config.yaml || exit 1
command -v hermes >/dev/null 2>&1 && hermes --version >/dev/null 2>&1 || true
exit 0
