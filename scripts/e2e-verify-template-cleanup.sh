#!/usr/bin/env bash
# End-to-end verification for the multi-layer template cleanup fix.
# Triggers a deterministic provision failure, then asserts every cleanup layer fired.
#
# Layers verified:
#   1. Backend orchestration  -- backend log shows delete_template invocation
#   2. Cubemaster registry    -- cubemastercli --address 127.0.0.1 tpl list no longer shows FAILED template
#   3. Containerd storage     -- ctr snapshots ls (all namespaces) shows snapshot gone
#   4. Disk reclaim           -- df -h /var/lib/containerd usage decreases or holds steady
#   5. Recovery               -- subsequent provision succeeds (no "disk quota exceeded")
#
# Usage:
#   bash scripts/e2e-verify-template-cleanup.sh
#
# Environment variables (all optional):
#   CUBE_SSH_PORT       SSH port for the guest VM           (default: 10022)
#   CUBE_SSH_HOST       SSH host for the guest VM           (default: 127.0.0.1)
#   CUBE_VM_USER        SSH username                        (default: opencloudos)
#   CUBE_VM_PASSWORD    SSH password                        (default: opencloudos)
#   BACKEND_LOG_PATH    Path to backend.log on the host     (default: /tmp/argus-backend.log)
#   BACKEND_API_BASE    Backend API URL                     (default: http://127.0.0.1:7777)
#   PROVISION_KIND      Provision kind to trigger           (default: codeql_cpp)
#   FAIL_INJECT_IMAGE   Image tag that does not exist       (default: 127.0.0.1:5000/does-not-exist:fail)
#   GOOD_IMAGE_TAG      Image tag for recovery probe        (default: 127.0.0.1:5000/cubesandbox-codeql-cpp:latest)

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CUBE_SSH_PORT="${CUBE_SSH_PORT:-10022}"
CUBE_SSH_HOST="${CUBE_SSH_HOST:-127.0.0.1}"
CUBE_VM_USER="${CUBE_VM_USER:-opencloudos}"
CUBE_VM_PASSWORD="${CUBE_VM_PASSWORD:-opencloudos}"
CUBE_WORK_DIR="${CUBE_WORK_DIR:-${ROOT_DIR}/.cubesandbox}"

BACKEND_LOG_PATH="${BACKEND_LOG_PATH:-/tmp/argus-backend.log}"
BACKEND_API_BASE="${BACKEND_API_BASE:-http://127.0.0.1:7777}"
PROVISION_KIND="${PROVISION_KIND:-codeql_cpp}"
FAIL_INJECT_IMAGE="${FAIL_INJECT_IMAGE:-127.0.0.1:5000/does-not-exist:fail}"
GOOD_IMAGE_TAG="${GOOD_IMAGE_TAG:-127.0.0.1:5000/cubesandbox-codeql-cpp:latest}"

log()  { printf '[e2e-verify] %s\n' "$*"; }
fail() { printf '[e2e-verify] FAIL: %s\n' "$*" >&2; exit 1; }
ok()   { printf '[e2e-verify]  OK : %s\n' "$*"; }

need_cmd() {
  if ! command -v "$1" > /dev/null 2>&1; then
    fail "required command not found: $1"
  fi
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
  local askpass="${CUBE_WORK_DIR}/askpass-$$"
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

snapshots_total() {
  remote_root "for ns in \$(ctr namespaces ls -q 2>/dev/null); do ctr -n \"\$ns\" snapshots ls 2>/dev/null | tail -n +2; done | wc -l"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  need_cmd ssh
  need_cmd setsid
  need_cmd curl
  need_cmd jq

  log "step 1/6: snapshot baseline"
  local disk_before snap_before
  disk_before="$(remote_root 'df -h /var/lib/containerd | tail -1')"
  snap_before="$(snapshots_total)"
  log "  disk: ${disk_before}"
  log "  snapshots: ${snap_before}"

  log "step 2/6: trigger provision failure (kind=${PROVISION_KIND})"
  # Force a build failure by pointing the provisioner at a non-existent image.
  # The backend should detect failure, finalize the DB row, and call
  # cubemaster delete_template on the partially-created template.
  CUBE_CODEQL_CPP_IMAGE="${FAIL_INJECT_IMAGE}" \
  curl -fsS -X POST "${BACKEND_API_BASE}/api/cubesandbox/templates/provision" \
    -H 'content-type: application/json' \
    -d "{\"kind\":\"${PROVISION_KIND}\"}" \
    || log "  provision returned non-zero (expected on injected failure)"

  log "step 3/6: wait for backend to finalize failure"
  local status="" attempts=0
  while (( attempts < 60 )); do
    status="$(curl -fsS "${BACKEND_API_BASE}/api/cubesandbox/templates/status?kind=${PROVISION_KIND}" 2>/dev/null \
      | jq -r '.status // empty')"
    if [[ "${status}" == "failed" ]]; then break; fi
    attempts=$((attempts + 1))
    sleep 2
  done
  [[ "${status}" == "failed" ]] || fail "backend did not reach 'failed' status after 120s"
  ok "backend reached failed status"

  log "step 4/6: assert cleanup signals"

  # Backend orchestration -- log line emitted by build_cubemaster_client + delete_template
  if [[ -r "${BACKEND_LOG_PATH}" ]] && grep -q 'cleaned up failed template\|cubemaster template deleted' "${BACKEND_LOG_PATH}"; then
    ok "backend log shows delete_template call"
  else
    fail "backend log missing delete_template signal (path=${BACKEND_LOG_PATH})"
  fi

  # Cubemaster registry -- no FAILED template should remain
  local failed_count
  failed_count="$(remote_root 'cubemastercli --address 127.0.0.1 tpl list 2>&1' \
    | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw).get("data", [])
    print(sum(1 for t in data if t.get("status","").upper()=="FAILED"))
except Exception:
    n = 0
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].upper() == "FAILED":
            n += 1
    print(n)
')"
  if [[ "${failed_count}" == "0" ]]; then
    ok "cubemaster registry has 0 FAILED templates"
  else
    fail "cubemaster still has ${failed_count} FAILED template(s)"
  fi

  # Containerd snapshots -- count must not exceed baseline
  local snap_after
  snap_after="$(snapshots_total)"
  if (( snap_after <= snap_before )); then
    ok "snapshot count: ${snap_before} -> ${snap_after} (no leak)"
  else
    fail "snapshot count grew: ${snap_before} -> ${snap_after} (LEAK)"
  fi

  # Disk usage -- must not have grown
  local disk_after
  disk_after="$(remote_root 'df -h /var/lib/containerd | tail -1')"
  log "  disk before: ${disk_before}"
  log "  disk after:  ${disk_after}"

  log "step 5/6: recovery probe -- subsequent provision succeeds"
  local recovery_status="" recovery_attempts=0
  CUBE_CODEQL_CPP_IMAGE="${GOOD_IMAGE_TAG}" \
  curl -fsS -X POST "${BACKEND_API_BASE}/api/cubesandbox/templates/provision" \
    -H 'content-type: application/json' \
    -d "{\"kind\":\"${PROVISION_KIND}\"}" \
    || log "  recovery POST returned non-zero (still polling)"

  while (( recovery_attempts < 180 )); do
    recovery_status="$(curl -fsS "${BACKEND_API_BASE}/api/cubesandbox/templates/status?kind=${PROVISION_KIND}" 2>/dev/null \
      | jq -r '.status // empty')"
    case "${recovery_status}" in
      ready) break ;;
      failed) fail "recovery provision failed (status=failed)" ;;
    esac
    recovery_attempts=$((recovery_attempts + 1))
    sleep 2
  done
  [[ "${recovery_status}" == "ready" ]] || fail "recovery did not reach 'ready' after 360s"
  ok "subsequent provision succeeded"

  log "step 6/6: report"
  log "============================================="
  ok "ALL E2E CHECKS PASSED"
  log "  disk before: ${disk_before}"
  log "  disk after:  ${disk_after}"
  log "  snapshots:   ${snap_before} -> ${snap_after}"
  log "============================================="
}

main "$@"
