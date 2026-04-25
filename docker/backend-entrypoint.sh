#!/bin/sh
set -eu

scan_root="${SCAN_WORKSPACE_ROOT:-/tmp/Argus/scans}"
assets_root="/app/assets"
assets_archive="$assets_root/scan_rule_assets.tar.gz"
assets_dir="$assets_root/scan_rule_assets"

mkdir -p "$scan_root"
chown appuser:appgroup "$scan_root"
chmod 0775 "$scan_root"

if [ ! -d "$assets_dir" ] && [ -f "$assets_archive" ]; then
  mkdir -p "$assets_root"
  tar -xzf "$assets_archive" -C "$assets_root"
fi

if [ "$#" -eq 0 ]; then
  set -- /usr/local/bin/backend
fi

exec su -s /bin/sh appuser -c 'exec "$@"' sh "$@"
