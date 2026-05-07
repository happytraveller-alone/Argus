#!/usr/bin/env bash
# argus-shutdown.sh — Graceful Argus shutdown script.
#
# Usage:
#   ./argus-shutdown.sh [--soft|--hard|--full] [--dry-run] [--help]
#
# Modes:
#   --soft   Step 1 (interrupt scans) + Step 2 (compose down, preserve volumes)
#   --hard   (default) soft (same as soft; no additional steps)
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
ENV_FILE="$ROOT/.env"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MODE="hard"
DRY_RUN=false

# ---------------------------------------------------------------------------
# Counters (for summary)
# ---------------------------------------------------------------------------
ORPHAN_WARNINGS=0

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

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

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
# STEP 5: Report summary
# ---------------------------------------------------------------------------
step5_report() {
  log "Summary: mode=$MODE dry-run=$DRY_RUN | orphan_warnings=$ORPHAN_WARNINGS"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  log "Starting argus shutdown (mode=$MODE, dry-run=$DRY_RUN)"

  load_env

  # Step 1: interrupt running scans (best-effort, never aborts)
  step1_interrupt_scans

  # Step 2: compose down (always; --full adds --volumes)
  step2_compose_down

  step5_report
  log "Shutdown complete."
}

main "$@"
