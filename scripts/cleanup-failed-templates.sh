#!/usr/bin/env bash
# One-time migration: delete all FAILED cubemaster templates on the guest VM,
# verify containerd snapshots are reclaimed, report disk space recovered.
# Idempotent — safe to run multiple times.
#
# Usage:
#   bash scripts/cleanup-failed-templates.sh
#
# Environment variables (all optional, defaults match cubesandbox-quickstart.sh):
#   CUBE_SSH_PORT      SSH port for the guest VM          (default: 10022)
#   CUBE_SSH_HOST      SSH host for the guest VM          (default: 127.0.0.1)
#   CUBE_VM_USER       SSH username                       (default: opencloudos)
#   CUBE_VM_PASSWORD   SSH password                       (default: opencloudos)
#   CUBE_WORK_DIR      Scratch directory for askpass      (default: <repo-root>/.cubesandbox)

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CUBE_SSH_PORT="${CUBE_SSH_PORT:-10022}"
CUBE_SSH_HOST="${CUBE_SSH_HOST:-127.0.0.1}"
CUBE_VM_USER="${CUBE_VM_USER:-opencloudos}"
CUBE_VM_PASSWORD="${CUBE_VM_PASSWORD:-opencloudos}"
CUBE_WORK_DIR="${CUBE_WORK_DIR:-${ROOT_DIR}/.cubesandbox}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { printf '[cleanup-failed] %s\n' "$*"; }
fail() { printf '[cleanup-failed] ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  if ! command -v "$1" > /dev/null 2>&1; then
    fail "required command not found: $1"
  fi
}

ssh_common_opts() {
  printf '%s\n' \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o ConnectTimeout=10 \
    -p "${CUBE_SSH_PORT}"
}

# Mirrors cubesandbox-quickstart.sh::remote_root exactly.
# Uses SSH_ASKPASS + setsid — no sshpass dependency.
remote_root() {
  local command="$1"
  need_cmd ssh
  need_cmd setsid
  mkdir -p "${CUBE_WORK_DIR}"
  local askpass="${CUBE_WORK_DIR}/.ssh-askpass.sh"
  cat > "${askpass}" << EOF
#!/usr/bin/env bash
printf '%s\n' '${CUBE_VM_PASSWORD}'
EOF
  chmod 700 "${askpass}"
  mapfile -t opts < <(ssh_common_opts)
  local ssh_status=0
  set +e
  DISPLAY="${DISPLAY:-cleanup-failed-templates}" \
    SSH_ASKPASS="${askpass}" \
    SSH_ASKPASS_REQUIRE=force \
    setsid -w ssh "${opts[@]}" "${CUBE_VM_USER}@${CUBE_SSH_HOST}" "sudo -i bash -s" <<< "${command}"
  ssh_status=$?
  set -e
  rm -f "${askpass}"
  return "${ssh_status}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  log "step 1/5: list all templates (client-side FAILED filter)"
  local list_json
  # --status flag does NOT exist in cubemastercli; filter client-side via Python.
  list_json="$(remote_root "cubemastercli tpl list --format json 2>/dev/null || cubemastercli tpl list")"

  local failed_ids
  failed_ids="$(printf '%s' "${list_json}" \
    | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
items = d.get("data", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
print("\n".join(t["template_id"] for t in items if str(t.get("status", "")).upper() == "FAILED"))
')"

  if [[ -z "${failed_ids}" ]]; then
    log "no FAILED templates found — nothing to clean"
    exit 0
  fi

  local count_found
  count_found="$(printf '%s\n' "${failed_ids}" | grep -c .)"
  log "found ${count_found} FAILED template(s)"

  log "step 2/5: disk usage before cleanup"
  local before_df
  before_df="$(remote_root "df -h /var/lib/containerd | tail -1")"
  log "before: ${before_df}"

  log "step 3/5: snapshot inventory before cleanup"
  # Cubelet uses 'default' namespace (verified: services/cubebox/destroy.go fallback).
  # Sum across all namespaces in case templates land elsewhere on this host.
  local before_snapshots
  before_snapshots="$(remote_root "for ns in \$(ctr namespaces ls -q 2>/dev/null); do ctr -n \"\$ns\" snapshots ls 2>/dev/null | tail -n +2; done | wc -l")"
  log "snapshots before (all namespaces): ${before_snapshots}"

  log "step 4/5: deleting FAILED templates (idempotent)"
  local cleanup_log="/tmp/cleanup-failed-templates-$$.log"
  local count=0
  while IFS= read -r tid; do
    [[ -z "${tid}" ]] && continue
    # Defense-in-depth: refuse template_ids that could break out of single
    # quotes when interpolated into the remote sudo bash payload.
    if [[ ! "${tid}" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$ ]]; then
      fail "refusing to delete: template id '${tid}' fails safety regex"
    fi
    log "deleting template ${tid}"
    local out
    local delete_ok=0
    set +e
    out="$(remote_root "cubemastercli template delete --template-id '${tid}'" 2>&1)"
    delete_ok=$?
    set -e
    printf '%s\n' "${out}" >> "${cleanup_log}"
    if [[ ${delete_ok} -ne 0 ]]; then
      if printf '%s' "${out}" | grep -qiE 'not found|does not exist'; then
        log "already gone (idempotent skip): ${tid}"
      else
        log "delete output: ${out}"
        fail "delete failed for template ${tid} — see ${cleanup_log}"
      fi
    else
      log "deleted: ${tid}"
    fi
    count=$((count + 1))
  done <<< "${failed_ids}"

  log "step 5/5: verify + report"
  local after_snapshots
  after_snapshots="$(remote_root "for ns in \$(ctr namespaces ls -q 2>/dev/null); do ctr -n \"\$ns\" snapshots ls 2>/dev/null | tail -n +2; done | wc -l")"
  local after_df
  after_df="$(remote_root "df -h /var/lib/containerd | tail -1")"

  log "------------------------------"
  log "deleted ${count} FAILED template(s)"
  log "snapshots: ${before_snapshots} -> ${after_snapshots}"
  log "disk before: ${before_df}"
  log "disk after:  ${after_df}"
  log "cleanup log: ${cleanup_log}"
  log "done."
}

main "$@"
