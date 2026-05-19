#!/bin/sh
set -eu

scan_root="${SCAN_WORKSPACE_ROOT:-/tmp/Argus/scans}"
runtime_home="${ARGUS_BACKEND_HOME:-/app/data/runtime/home}"
assets_root="/app/assets"
assets_archive="$assets_root/scan_rule_assets.tar.gz"
assets_dir="$assets_root/scan_rule_assets"

mkdir -p "$scan_root"
chown appuser:appgroup "$scan_root"
chmod 0775 "$scan_root"
mkdir -p "$runtime_home"
chown appuser:appgroup "$runtime_home"
chmod 0700 "$runtime_home"

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

podman_sock="${CONTAINER_HOST:-}"
podman_sock="${podman_sock#unix://}"
if [ -n "$podman_sock" ] && [ -S "$podman_sock" ]; then
  podman_sock_gid="$(stat -c '%g' "$podman_sock")"
  if ! id -G appuser | tr ' ' '\n' | grep -qx "$podman_sock_gid"; then
    podman_sock_group="$(getent group "$podman_sock_gid" | cut -d: -f1 || true)"
    if [ -z "$podman_sock_group" ]; then
      podman_sock_group="podmansock"
      if getent group "$podman_sock_group" >/dev/null; then
        podman_sock_group="podmansock$podman_sock_gid"
      fi
      groupadd --gid "$podman_sock_gid" "$podman_sock_group"
    fi
    usermod -aG "$podman_sock_group" appuser
  fi
fi

for a3s_device in /dev/kvm /dev/vhost-vsock; do
  if [ -e "$a3s_device" ]; then
    device_gid="$(stat -c '%g' "$a3s_device")"
    if ! id -G appuser | tr ' ' '\n' | grep -qx "$device_gid"; then
      device_group="$(getent group "$device_gid" | cut -d: -f1 || true)"
      if [ -z "$device_group" ]; then
        device_group="a3sdevice$device_gid"
        groupadd --gid "$device_gid" "$device_group"
      fi
      usermod -aG "$device_group" appuser
    fi
  fi
done

if [ ! -d "$assets_dir" ] && [ -f "$assets_archive" ]; then
  mkdir -p "$assets_root"
  tar --no-same-owner --no-same-permissions -xzf "$assets_archive" -C "$assets_root"
fi

if [ "$#" -eq 0 ]; then
  set -- /usr/local/bin/backend
fi

export HOME="$runtime_home"
exec su -m -s /bin/sh appuser -c 'exec "$@"' sh "$@"
