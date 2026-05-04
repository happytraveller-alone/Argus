#!/usr/bin/env bash
# Diagnostic probe: dump the disk footprint of the codeql-cpp image so we can
# see exactly which directories push the rootfs over the 8 GiB ext4 budget.
#
# Two modes:
#   local-build   Runs against the WSL-local image (argus/cubesandbox-codeql-cpp:latest).
#                 Cheap, no VM needed.
#   guest-vm      SSH to the cubesandbox guest VM and probe the registry image
#                 used during provision. Requires SSH credentials matching
#                 cubesandbox-quickstart.sh.
#
# Usage:
#   bash scripts/probe-codeql-cpp-rootfs-sizes.sh local-build [image]
#   bash scripts/probe-codeql-cpp-rootfs-sizes.sh guest-vm   [image]
#
# Default image: argus/cubesandbox-codeql-cpp:latest (local) or
#                127.0.0.1:5000/cubesandbox-codeql-cpp:latest (guest).

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CUBE_SSH_PORT="${CUBE_SSH_PORT:-10022}"
CUBE_SSH_HOST="${CUBE_SSH_HOST:-127.0.0.1}"
CUBE_VM_USER="${CUBE_VM_USER:-opencloudos}"
CUBE_VM_PASSWORD="${CUBE_VM_PASSWORD:-opencloudos}"
CUBE_WORK_DIR="${CUBE_WORK_DIR:-${ROOT_DIR}/.cubesandbox}"

log()  { printf '[probe] %s\n' "$*"; }
fail() { printf '[probe] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<USAGE
Usage:
  $0 local-build [image]
  $0 guest-vm    [image]
USAGE
  exit 2
}

ssh_common_opts() {
  printf '%s\n' \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR \
    -o ConnectTimeout=8
}

remote_root() {
  local cmd="$1"
  mkdir -p "${CUBE_WORK_DIR}"
  local askpass="${CUBE_WORK_DIR}/probe-askpass-$$"
  printf '#!/usr/bin/env bash\nprintf "%%s" "%s"\n' "${CUBE_VM_PASSWORD}" > "${askpass}"
  chmod 700 "${askpass}"
  trap 'rm -f "${askpass}"' RETURN
  SSH_ASKPASS="${askpass}" \
    SSH_ASKPASS_REQUIRE=force \
    DISPLAY=:0 \
    setsid -w ssh \
      $(ssh_common_opts) \
      -p "${CUBE_SSH_PORT}" \
      "${CUBE_VM_USER}@${CUBE_SSH_HOST}" \
      "sudo -n bash -c $(printf '%q' "${cmd}")"
}

probe_payload() {
  # Bash payload run INSIDE the codeql-cpp container.
  cat <<'EOF'
set -e
echo "==== rootfs total ===="
du -sh / 2>/dev/null || true
echo
echo "==== top-level (depth 1) ===="
du -h --max-depth=1 / 2>/dev/null | sort -h | tail -25
echo
echo "==== /usr depth 2 ===="
du -h --max-depth=2 /usr 2>/dev/null | sort -h | tail -25
echo
echo "==== /opt depth 2 ===="
du -h --max-depth=2 /opt 2>/dev/null | sort -h | tail -25
echo
echo "==== Python site-packages > 50MB ===="
for r in /usr/lib/python3*/dist-packages /usr/local/lib/python3*/dist-packages /usr/local/lib/python3*/site-packages; do
  [ -d "$r" ] || continue
  du -sm "$r"/* 2>/dev/null | awk '$1 >= 50 {print}' | sort -nr | head -25
done
echo
echo "==== node_modules ===="
for n in /usr/local/lib/node_modules /usr/lib/node_modules; do
  [ -d "$n" ] && du -sh "$n" 2>/dev/null
done
echo
echo "==== JVMs and Java runtimes ===="
ls -1d /usr/lib/jvm/* /opt/java* /opt/jdk* /opt/jre* 2>/dev/null || echo "(none)"
echo
echo "==== /opt/codeql breakdown ===="
[ -d /opt/codeql/codeql ] && du -h --max-depth=2 /opt/codeql/codeql 2>/dev/null | sort -h | tail -20
echo
echo "==== caches ===="
for c in /root/.cache /home/user/.cache /var/cache /tmp; do
  [ -d "$c" ] && du -sh "$c" 2>/dev/null
done
EOF
}

run_local() {
  local image="${1:-argus/cubesandbox-codeql-cpp:latest}"
  command -v docker >/dev/null || fail "docker not on PATH"
  log "probing local image: ${image}"
  docker run --rm --entrypoint /bin/bash "${image}" -c "$(probe_payload)"
}

run_guest() {
  local image="${1:-127.0.0.1:5000/cubesandbox-codeql-cpp:latest}"
  command -v ssh >/dev/null || fail "ssh not on PATH"
  command -v setsid >/dev/null || fail "setsid not on PATH"
  log "probing guest VM image: ${image}"
  # Pipe the payload via stdin so we don't need to escape it twice.
  local payload
  payload="$(probe_payload)"
  remote_root "docker run --rm --entrypoint /bin/bash '${image}' -c $(printf '%q' "${payload}")"
}

main() {
  local mode="${1:-}"
  case "${mode}" in
    local-build) shift; run_local "$@" ;;
    guest-vm)    shift; run_guest "$@" ;;
    -h|--help|help) usage ;;
    *) usage ;;
  esac
}

main "$@"
