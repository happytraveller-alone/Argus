#!/usr/bin/env bash
# scripts/cubesandbox-lib.sh — shared SSH + cubemaster primitives.
# Contract: functions return rc only. Stdout = command output. Caller maps rc → behavior.
# Sourced by argus-bootstrap.sh and argus-shutdown.sh.
#
# Note: callers should `set -euo pipefail`; lib does not enforce it.
#
# Required env vars (caller must export before sourcing or calling functions):
#   CUBE_SSH_HOST      — VM host (default: 127.0.0.1)
#   CUBE_SSH_PORT      — VM SSH port (default: 10022)
#   CUBE_VM_USER       — VM login user (default: opencloudos)
#   CUBE_VM_PASSWORD   — VM sudo password
#   CUBE_WORK_DIR      — scratch directory for askpass helper

# Guard against double-sourcing
[[ -n "${CUBESANDBOX_LIB_LOADED:-}" ]] && return 0

# ---------------------------------------------------------------------------
# Prefix-alias: .env uses CUBESANDBOX_* names; map to CUBE_* when unset.
# This lets argus-shutdown.sh (which sources .env) work without a wrapper.
# ---------------------------------------------------------------------------
: "${CUBE_SSH_HOST:=${CUBESANDBOX_SSH_HOST:-127.0.0.1}}"
: "${CUBE_SSH_PORT:=${CUBESANDBOX_SSH_PORT:-10022}}"
: "${CUBE_VM_USER:=${CUBESANDBOX_VM_USER:-opencloudos}}"
: "${CUBE_VM_PASSWORD:=${CUBESANDBOX_VM_PASSWORD:-opencloudos}}"
# NOTE: defaults to `.cubesandbox` (argus convention) so callers like argus-bootstrap.sh
# that don't `source .env` (they read via read_env_value and don't export) still get a
# usable value. Callers with a different convention should set CUBE_WORK_DIR explicitly.
: "${CUBE_WORK_DIR:=${CUBESANDBOX_WORK_DIR:-.cubesandbox}}"

# ---------------------------------------------------------------------------
# Internal: SSH options (mirrors cubesandbox-quickstart.sh::ssh_common_opts)
# ---------------------------------------------------------------------------
_cubesandbox_ssh_common_opts() {
  printf '%s\n' \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o ConnectTimeout=10 \
    -p "${CUBE_SSH_PORT:-10022}"
}

# ---------------------------------------------------------------------------
# cubesandbox_remote_root <command>
#   SSH into the cubesandbox VM and run <command> as root via sudo.
#   Uses setsid + ssh-askpass to supply CUBE_VM_PASSWORD non-interactively.
#   Returns: ssh exit code. Stdout/stderr pass through.
# ---------------------------------------------------------------------------
cubesandbox_remote_root() {
  local command="$1"
  local host="${CUBE_SSH_HOST:-127.0.0.1}"
  local user="${CUBE_VM_USER:-opencloudos}"
  local work_dir="${CUBE_WORK_DIR:?CUBE_WORK_DIR must be set}"

  command -v ssh   >/dev/null 2>&1 || { printf 'cubesandbox-lib: ssh not found\n' >&2; return 127; }
  command -v setsid >/dev/null 2>&1 || { printf 'cubesandbox-lib: setsid not found\n' >&2; return 127; }

  mkdir -p "$work_dir"
  local askpass="${work_dir}/.ssh-askpass.sh"
  # Ensure askpass is removed on any exit path (normal, SIGINT, set -e abort, SIGTERM)
  # shellcheck disable=SC2064
  trap "rm -f -- \"$askpass\"" RETURN INT TERM EXIT
  # Write askpass helper — single-quoted password to avoid expansion inside EOF
  cat >"$askpass" <<ASKEOF
#!/usr/bin/env bash
printf '%s\n' '${CUBE_VM_PASSWORD:-}'
ASKEOF
  chmod 700 "$askpass"

  local -a opts
  mapfile -t opts < <(_cubesandbox_ssh_common_opts)

  local rc=0
  DISPLAY="${DISPLAY:-cubesandbox-lib}" \
    SSH_ASKPASS="$askpass" \
    SSH_ASKPASS_REQUIRE=force \
    setsid -w ssh "${opts[@]}" "${user}@${host}" "sudo -i bash -s" <<<"$command" || rc=$?

  rm -f -- "$askpass"
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_template_list [--json]
#   List cubemaster templates via cubemastercli over SSH.
#   --json: request JSON output; falls back to tabular on rc≠0.
#   Returns: 0 on success, non-zero on transport/tool failure.
#   Stdout: raw cubemastercli output.
# ---------------------------------------------------------------------------
cubesandbox_template_list() {
  local json_flag=""
  [[ "${1:-}" == "--json" ]] && json_flag=" --json"

  local rc=0
  if [[ -n "$json_flag" ]]; then
    cubesandbox_remote_root "cubemastercli --address 127.0.0.1 tpl list --json" || rc=$?
    if [[ $rc -ne 0 ]]; then
      # Fallback to tabular
      cubesandbox_remote_root "cubemastercli --address 127.0.0.1 tpl list" || rc=$?
    fi
  else
    cubesandbox_remote_root "cubemastercli --address 127.0.0.1 tpl list" || rc=$?
  fi
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_template_delete <template_id>
#   Delete a cubemaster template by ID.
#   Treats rc=0 and rc=130404 (already gone) as success → returns 0.
#   All other non-zero rc values are returned as-is. Does NOT call fail/exit.
#   Returns: 0 on success or already-gone, original rc otherwise.
# ---------------------------------------------------------------------------
cubesandbox_template_delete() {
  local template_id="${1:?cubesandbox_template_delete: template_id required}"
  if ! cubesandbox_template_id_safe "$template_id"; then
    printf 'cubesandbox-lib: cubesandbox_template_delete: unsafe template_id %q — refusing\n' "$template_id" >&2
    return 2
  fi
  local rc=0
  cubesandbox_remote_root "cubemastercli --address 127.0.0.1 template delete --template-id '${template_id}'" || rc=$?
  if [[ $rc -eq 0 || $rc -eq 130404 ]]; then
    return 0
  fi
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_sandbox_delete <sandbox_id>
#   Delete a cubemaster sandbox via the REST API.
#   Calls `curl -X DELETE http://127.0.0.1:23000/cube/sandbox` with JSON body
#   over remote_root (cubemaster API is on the VM).
#   Returns: curl exit code. HTTP 4xx/5xx are surfaced via stderr; caller decides.
# ---------------------------------------------------------------------------
cubesandbox_sandbox_delete() {
  local sandbox_id="${1:?cubesandbox_sandbox_delete: sandbox_id required}"
  if ! cubesandbox_id_safe "$sandbox_id"; then
    printf 'cubesandbox-lib: cubesandbox_sandbox_delete: unsafe sandbox_id %q — refusing\n' "$sandbox_id" >&2
    return 2
  fi
  local body
  # Prefer jq for safe JSON construction; fall back to printf (safe: id is already validated above)
  if command -v jq >/dev/null 2>&1; then
    body="$(jq -nc --arg id "$sandbox_id" '{"request_id":"argus-shutdown","sandbox_id":$id}')"
  else
    body="$(printf '{"request_id":"argus-shutdown","sandbox_id":"%s"}' "$sandbox_id")"
  fi
  local rc=0
  cubesandbox_remote_root "curl -s -o /dev/stderr -w '%{http_code}' -X DELETE http://127.0.0.1:23000/cube/sandbox -H 'Content-Type: application/json' -d '${body}'" || rc=$?
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_ctr_snapshot_list
#   List containerd snapshots in the cubesandbox namespace via ctr.
#   Returns: rc from remote ssh+ctr. Stdout: raw snapshot list.
# ---------------------------------------------------------------------------
cubesandbox_ctr_snapshot_list() {
  local rc=0
  cubesandbox_remote_root "ctr -n cubesandbox snapshots ls" || rc=$?
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_ctr_snapshot_rm <key>
#   Remove a single containerd snapshot by key in the cubesandbox namespace.
#   Returns: rc from remote ssh+ctr. Non-zero = caller logs WARNING and continues.
# ---------------------------------------------------------------------------
cubesandbox_ctr_snapshot_rm() {
  local key="${1:?cubesandbox_ctr_snapshot_rm: key required}"
  if ! cubesandbox_id_safe "$key"; then
    printf 'cubesandbox-lib: cubesandbox_ctr_snapshot_rm: unsafe snapshot key %q — refusing\n' "$key" >&2
    return 2
  fi
  local rc=0
  cubesandbox_remote_root "ctr -n cubesandbox snapshots rm '${key}'" || rc=$?
  return "$rc"
}

# ---------------------------------------------------------------------------
# cubesandbox_id_safe <id>
#   Generic validation predicate for sandbox IDs and snapshot keys.
#   Returns 0 if <id> matches safe pattern (alphanum, dot, underscore, hyphen,
#   colon, slash — covers containerd snapshot keys like "sha256:...").
#   1 otherwise. Does NOT output anything. Caller checks rc.
# ---------------------------------------------------------------------------
cubesandbox_id_safe() {
  local id="${1:-}"
  [[ -n "$id" && "$id" =~ ^[A-Za-z0-9][A-Za-z0-9_./:@-]{1,255}$ ]]
}

# ---------------------------------------------------------------------------
# cubesandbox_template_id_safe <id>
#   Validation predicate: returns 0 if <id> matches safe template ID pattern,
#   1 otherwise. Pattern: must start with "tpl-" followed by 1-124 alphanum/_/-
#   chars (rejects tabular header "TEMPLATE_ID" and other non-template strings).
#   Does NOT output anything. Caller checks rc.
# ---------------------------------------------------------------------------
cubesandbox_template_id_safe() {
  local id="${1:-}"
  [[ "$id" =~ ^tpl-[A-Za-z0-9_-]{1,124}$ ]]
}

# ---------------------------------------------------------------------------
# Sentinel: sourced successfully
# ---------------------------------------------------------------------------
export CUBESANDBOX_LIB_LOADED=1
