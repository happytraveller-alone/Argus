#!/usr/bin/env bash
# argus-shutdown.sh — Graceful Argus shutdown script.
#
# Usage:
#   ./argus-shutdown.sh [--soft|--hard|--full] [--dry-run] [--help]
#
# Modes:
#   --soft   Step 1 (interrupt scans) + Step 2 (compose down, preserve volumes)
#   --hard   (default) soft + Step 3 (delete cubemaster templates) + Step 4 (ctr orphan reclaim)
#   --full   hard + compose down --volumes (destroys postgres_data et al.)
#
# --dry-run  Print all planned ops without executing any destructive command.
# --help     Print this usage and exit 0.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
LIB="$ROOT/scripts/cubesandbox-lib.sh"
ENV_FILE="$ROOT/.env"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MODE="hard"
DRY_RUN=false

# ---------------------------------------------------------------------------
# Counters (for summary)
# ---------------------------------------------------------------------------
TEMPLATES_DELETED=0
SNAPSHOTS_CLEANED=0
ORPHAN_WARNINGS=0
SANDBOXES_DESTROYED=0
JOBS_UNSTUCK=0

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,1\}//'
  exit 0
}

for arg in "$@"; do
  case "$arg" in
    --soft)    MODE="soft" ;;
    --hard)    MODE="hard" ;;
    --full)    MODE="full" ;;
    --dry-run) DRY_RUN=true ;;
    --help|-h) usage ;;
    *)
      printf 'argus-shutdown: unknown argument: %s\n' "$arg" >&2
      printf 'Run with --help for usage.\n' >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()     { printf '[argus-shutdown] %s\n' "$*"; }
warn()    { printf '[argus-shutdown] WARNING: %s\n' "$*" >&2; ORPHAN_WARNINGS=$((ORPHAN_WARNINGS + 1)); }
die()     { printf '[argus-shutdown] ERROR: %s\n' "$*" >&2; exit 1; }

# run_cmd: honours --dry-run.
# Usage: run_cmd <description> cmd [args...]
run_cmd() {
  local desc="$1"; shift
  if [[ "$DRY_RUN" == true ]]; then
    printf '[dry-run] %s: %s\n' "$desc" "$*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Load .env (source env vars needed by lib and this script)
# ---------------------------------------------------------------------------
load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    # Export only VAR=value lines; skip comments and blanks.
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
  else
    warn ".env not found at $ENV_FILE; using defaults"
  fi
}

# ---------------------------------------------------------------------------
# Source lib (with double-source guard)
# ---------------------------------------------------------------------------
source_lib() {
  if [[ ! -f "$LIB" ]]; then
    die "cubesandbox-lib.sh not found at $LIB"
  fi
  # shellcheck source=scripts/cubesandbox-lib.sh
  source "$LIB"
}

# ---------------------------------------------------------------------------
# STEP 1: Interrupt running scans (best-effort)
# ---------------------------------------------------------------------------
step1_interrupt_scans() {
  log "Step 1: Interrupt running scans (best-effort)"

  local backend_port="${Argus_BACKEND_PORT:-${BACKEND_PORT:-18000}}"
  local base_url="http://127.0.0.1:${backend_port}"

  # Health check — best-effort, must not abort script
  set +e
  local health_ok=false
  if curl -sf "${base_url}/health" >/dev/null 2>&1; then
    health_ok=true
  fi
  set -e

  if [[ "$health_ok" == false ]]; then
    warn "backend unreachable at ${base_url}; skipping task interrupts. Orphan sandboxes may persist; restart backend to reconcile."
    return 0
  fi

  log "  Backend reachable at ${base_url}"

  # Enumerate running opengrep tasks via GET /api/v1/static-tasks/tasks?status=running
  # Per AS-3: no Postgres task tables; tasks are in-memory in backend — use the list API.
  # Per AS-4: interrupting a task via the API calls cancel_*_scan which destroys sandbox.

  set +e

  # --- opengrep running tasks ---
  local og_response
  og_response=$(curl -sf "${base_url}/api/v1/static-tasks/tasks?status=running" 2>/dev/null) || og_response="[]"
  local og_ids
  og_ids=$(printf '%s' "$og_response" | grep -o '"taskId":"[^"]*"' | sed 's/"taskId":"//;s/"//' 2>/dev/null || true)

  for task_id in $og_ids; do
    log "  Interrupting opengrep task: $task_id"
    run_cmd "POST /api/v1/static-tasks/tasks/${task_id}/interrupt" \
      curl -sf -X POST "${base_url}/api/v1/static-tasks/tasks/${task_id}/interrupt" \
        -H 'Content-Type: application/json' >/dev/null 2>&1 \
      || warn "Failed to interrupt opengrep task $task_id (continuing)"
  done

  # --- codeql running tasks ---
  local cq_response
  cq_response=$(curl -sf "${base_url}/api/v1/static-tasks/codeql/tasks?status=running" 2>/dev/null) || cq_response="[]"
  local cq_ids
  cq_ids=$(printf '%s' "$cq_response" | grep -o '"taskId":"[^"]*"' | sed 's/"taskId":"//;s/"//' 2>/dev/null || true)

  for task_id in $cq_ids; do
    log "  Interrupting codeql task: $task_id"
    run_cmd "POST /api/v1/static-tasks/codeql/tasks/${task_id}/interrupt" \
      curl -sf -X POST "${base_url}/api/v1/static-tasks/codeql/tasks/${task_id}/interrupt" \
        -H 'Content-Type: application/json' >/dev/null 2>&1 \
      || warn "Failed to interrupt codeql task $task_id (continuing)"
  done

  # --- cubesandbox tasks (in-memory only) ---
  local cs_response
  cs_response=$(curl -sf "${base_url}/api/v1/cubesandbox-tasks/" 2>/dev/null) || cs_response="[]"
  local cs_ids
  cs_ids=$(printf '%s' "$cs_response" | grep -o '"taskId":"[^"]*"' | sed 's/"taskId":"//;s/"//' 2>/dev/null || true)

  for task_id in $cs_ids; do
    log "  Interrupting cubesandbox task: $task_id"
    run_cmd "POST /api/v1/cubesandbox-tasks/${task_id}/interrupt" \
      curl -sf -X POST "${base_url}/api/v1/cubesandbox-tasks/${task_id}/interrupt" \
        -H 'Content-Type: application/json' >/dev/null 2>&1 \
      || warn "Failed to interrupt cubesandbox task $task_id (continuing)"
  done

  set -e

  log "  Step 1 complete (sandbox cleanup handled by cancel_*_scan per AS-4)"
}

# ---------------------------------------------------------------------------
# STEP 2: Compose down
# ---------------------------------------------------------------------------
step2_compose_down() {
  log "Step 2: Docker Compose down"

  local -a extra_flags=()
  if [[ "$MODE" == "full" ]]; then
    extra_flags=(--volumes)
    log "  Mode=full: adding --volumes (postgres_data et al. will be destroyed)"
  fi

  run_cmd "docker compose down" \
    docker compose \
      --project-directory "$ROOT" \
      --file "$ROOT/docker-compose.yml" \
      --project-name argus \
      down \
      --remove-orphans \
      "${extra_flags[@]}" \
    || die "compose down failed — aborting"
}

# ---------------------------------------------------------------------------
# STEP 2.5: Cubemaster state cleanup (sandboxes + stuck build jobs)
#
# Why: cubemaster blocks `template delete` when (a) a cubebox sandbox still
# references the template ("template is still in use") or (b) a row in
# t_cube_template_image_job sits at status PENDING/RUNNING ("build job is
# still active"). After argus is shut down, leaked sandbox sessions and
# half-finished build jobs are exactly what's left over. Clearing them here
# unblocks step3_delete_templates.
#
# Best-effort: if the VM is unreachable or the MySQL container is missing,
# warn and continue — step 3 will report any remaining failures.
# ---------------------------------------------------------------------------
step2_5_cleanup_cubemaster_state() {
  log "Step 2.5: Cubemaster state cleanup (sandboxes + stuck build jobs)"

  # --- A. Destroy every active cubebox sandbox ---
  local list_raw
  set +e
  list_raw=$(cubesandbox_remote_root "cubemastercli --address 127.0.0.1 cubebox list 2>&1" 2>/dev/null)
  local list_rc=$?
  set -e

  if [[ $list_rc -ne 0 ]]; then
    warn "cubebox list failed (rc=$list_rc); skipping sandbox destroy. Step 3 may fail with 'template is still in use'."
  else
    local sb_ids
    sb_ids=$(printf '%s\n' "$list_raw" | awk '/^[0-9a-f]{32}/ {print $1}' | sort -u)
    if [[ -z "$sb_ids" ]]; then
      log "  No active sandboxes to destroy."
    else
      local sb_count=0
      while IFS= read -r sb; do
        [[ -z "$sb" ]] && continue
        log "  Destroying sandbox: $sb"
        set +e
        run_cmd "cubebox destroy $sb" \
          cubesandbox_remote_root "cubemastercli --address 127.0.0.1 cubebox destroy $sb 2>&1"
        local d_rc=$?
        set -e
        if [[ $d_rc -eq 0 ]]; then
          sb_count=$((sb_count + 1))
        else
          warn "Sandbox destroy failed for $sb (rc=$d_rc); continuing"
        fi
      done <<< "$sb_ids"
      SANDBOXES_DESTROYED=$((SANDBOXES_DESTROYED + sb_count))
      log "  Destroyed $sb_count sandbox(es)."
    fi
  fi

  # --- B. Mark stuck PENDING/RUNNING build jobs as FAILED ---
  # MySQL is in container `cube-sandbox-mysql` on the VM (see
  # cubesandbox/CubeMaster/support/docker-compose.yaml). cube_mvp.t_cube_template_image_job
  # holds template build jobs; rows stuck at PENDING/RUNNING block delete.
  local sql='UPDATE t_cube_template_image_job SET status=\"FAILED\", updated_at=NOW() WHERE status IN (\"PENDING\",\"RUNNING\")'
  local jobs_unstuck_raw
  set +e
  jobs_unstuck_raw=$(cubesandbox_remote_root "docker exec cube-sandbox-mysql mysql -ucube -pcube_pass cube_mvp -sN -e 'SELECT COUNT(*) FROM t_cube_template_image_job WHERE status IN (\"PENDING\",\"RUNNING\")' 2>/dev/null" 2>/dev/null)
  local count_rc=$?
  set -e
  local stuck_count=0
  if [[ $count_rc -eq 0 ]] && [[ "$jobs_unstuck_raw" =~ ^[0-9]+$ ]]; then
    stuck_count="$jobs_unstuck_raw"
  fi

  if [[ "$stuck_count" -eq 0 ]]; then
    log "  No stuck build jobs (PENDING/RUNNING) to clear."
  else
    log "  Clearing $stuck_count stuck build job(s)..."
    set +e
    run_cmd "mysql update stuck jobs -> FAILED" \
      cubesandbox_remote_root "docker exec cube-sandbox-mysql mysql -ucube -pcube_pass cube_mvp -e \"${sql}\" 2>&1"
    local sql_rc=$?
    set -e
    if [[ $sql_rc -eq 0 ]]; then
      JOBS_UNSTUCK=$((JOBS_UNSTUCK + stuck_count))
      log "  Cleared $stuck_count stuck build job(s)."
    else
      warn "MySQL job-cleanup failed (rc=$sql_rc); step 3 may fail with 'build job is still active'."
    fi
  fi

  log "  Step 2.5 complete: sandboxes_destroyed=$SANDBOXES_DESTROYED jobs_unstuck=$JOBS_UNSTUCK"
}

# ---------------------------------------------------------------------------
# STEP 3: Delete all cubemaster templates (--hard and --full)
# ---------------------------------------------------------------------------
step3_delete_templates() {
  log "Step 3: Delete cubemaster templates"

  # List templates (tabular output; skip header lines)
  local list_output
  set +e
  list_output=$(cubesandbox_template_list 2>/dev/null)
  local list_rc=$?
  set -e

  if [[ $list_rc -ne 0 ]]; then
    warn "cubesandbox_template_list failed (rc=$list_rc); skipping template deletion"
    return 0
  fi

  if [[ -z "$list_output" ]]; then
    log "  No templates found"
    return 0
  fi

  # Parse template IDs: first token on each non-header line.
  # cubemastercli output: TEMPLATE_ID | STATUS | CREATED_AT | IMAGE_INFO (tabular)
  # cubesandbox_template_id_safe rejects the header word and any non-tpl- token.
  while IFS= read -r line; do
    # Skip blank lines and separator lines.
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*[-+]+ ]] && continue

    local tpl_id
    tpl_id=$(printf '%s' "$line" | awk '{print $1}')
    [[ -z "$tpl_id" ]] && continue

    if ! cubesandbox_template_id_safe "$tpl_id"; then
      warn "Skipping unsafe template ID: $tpl_id"
      continue
    fi

    log "  Deleting template: $tpl_id"
    set +e
    run_cmd "cubesandbox_template_delete $tpl_id" \
      cubesandbox_template_delete "$tpl_id"
    local del_rc=$?
    set -e

    if [[ $del_rc -eq 0 ]]; then
      TEMPLATES_DELETED=$((TEMPLATES_DELETED + 1))
    else
      warn "Template delete failed for $tpl_id (rc=$del_rc); continuing"
    fi
  done <<< "$list_output"

  log "  Step 3 complete: $TEMPLATES_DELETED template(s) deleted"
}

# ---------------------------------------------------------------------------
# STEP 4: ctr snapshot orphan reclaim (--hard and --full)
# ---------------------------------------------------------------------------
step4_reclaim_snapshots() {
  log "Step 4: ctr snapshot orphan reclaim"

  local snap_output
  set +e
  snap_output=$(cubesandbox_ctr_snapshot_list 2>/dev/null)
  local snap_rc=$?
  set -e

  if [[ $snap_rc -ne 0 ]]; then
    warn "cubesandbox_ctr_snapshot_list failed (rc=$snap_rc); skipping snapshot reclaim"
    return 0
  fi

  if [[ -z "$snap_output" ]]; then
    log "  No snapshots found"
    return 0
  fi

  # Parse snapshot keys: first token on each non-header line.
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*[-+]+ ]] && continue
    [[ "$line" =~ ^[[:space:]]*KEY ]] && continue
    [[ "$line" =~ ^[[:space:]]*key ]] && continue

    local snap_key
    snap_key=$(printf '%s' "$line" | awk '{print $1}')
    [[ -z "$snap_key" ]] && continue

    log "  Removing snapshot: $snap_key"
    set +e
    run_cmd "cubesandbox_ctr_snapshot_rm $snap_key" \
      cubesandbox_ctr_snapshot_rm "$snap_key"
    local rm_rc=$?
    set -e

    if [[ $rm_rc -eq 0 ]]; then
      SNAPSHOTS_CLEANED=$((SNAPSHOTS_CLEANED + 1))
    else
      warn "Snapshot remove failed for $snap_key (rc=$rm_rc); continuing"
    fi
  done <<< "$snap_output"

  log "  Step 4 complete: $SNAPSHOTS_CLEANED snapshot(s) cleaned"
}

# ---------------------------------------------------------------------------
# STEP 5: Report summary
# ---------------------------------------------------------------------------
step5_report() {
  log "Summary: mode=$MODE dry-run=$DRY_RUN | sandboxes_destroyed=$SANDBOXES_DESTROYED jobs_unstuck=$JOBS_UNSTUCK templates_deleted=$TEMPLATES_DELETED snapshots_cleaned=$SNAPSHOTS_CLEANED orphan_warnings=$ORPHAN_WARNINGS"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "Starting argus shutdown (mode=$MODE, dry-run=$DRY_RUN)"

  load_env
  source_lib

  # Step 1: interrupt running scans (best-effort, never aborts)
  step1_interrupt_scans

  # Step 2: compose down (always; --full adds --volumes)
  step2_compose_down

  # Steps 2.5+3+4: only for hard/full
  if [[ "$MODE" == "hard" || "$MODE" == "full" ]]; then
    step2_5_cleanup_cubemaster_state
    step3_delete_templates
    step4_reclaim_snapshots
  fi

  step5_report
  log "Shutdown complete."
}

main "$@"
