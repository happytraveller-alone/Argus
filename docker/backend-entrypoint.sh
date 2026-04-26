#!/bin/sh
set -eu

scan_root="${SCAN_WORKSPACE_ROOT:-/tmp/Argus/scans}"
assets_root="/app/assets"
assets_archive="$assets_root/scan_rule_assets.tar.gz"
assets_dir="$assets_root/scan_rule_assets"

mkdir -p "$scan_root"
chown appuser:appgroup "$scan_root"
chmod 0775 "$scan_root"

docker_sock="/var/run/docker.sock"
if [ -S "$docker_sock" ]; then
  docker_sock_gid="$(stat -c '%g' "$docker_sock")"
  if ! id -G appuser | tr ' ' '\n' | grep -qx "$docker_sock_gid"; then
    docker_sock_group="$(getent group "$docker_sock_gid" | cut -d: -f1 || true)"
    if [ -z "$docker_sock_group" ]; then
      docker_sock_group="dockersock"
      if getent group "$docker_sock_group" >/dev/null; then
        docker_sock_group="dockersock$docker_sock_gid"
      fi
      groupadd --gid "$docker_sock_gid" "$docker_sock_group"
    fi
    usermod -aG "$docker_sock_group" appuser
  fi
fi

if [ ! -d "$assets_dir" ] && [ -f "$assets_archive" ]; then
  mkdir -p "$assets_root"
  tar -xzf "$assets_archive" -C "$assets_root"
fi

if [ "$#" -eq 0 ]; then
  set -- /usr/local/bin/backend
fi

exec su -s /bin/sh appuser -c 'exec "$@"' sh "$@"
