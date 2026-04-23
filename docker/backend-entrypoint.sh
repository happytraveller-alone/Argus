#!/bin/sh
set -eu

scan_root="${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}"

mkdir -p "$scan_root"
chown appuser:appgroup "$scan_root"
chmod 0775 "$scan_root"

if [ "$#" -eq 0 ]; then
  set -- /usr/local/bin/backend
fi

exec su -s /bin/sh appuser -c 'exec "$@"' sh "$@"
