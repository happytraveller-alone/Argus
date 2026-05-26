#!/usr/bin/env bash
# argus-shutdown.sh — Graceful Argus shutdown script.
#
# Usage:
#   ./argus-shutdown.sh [--runtime docker|podman] [--soft|--hard|--full] [--dry-run] [--help]
#
# Modes:
#   --soft   Step 1 (interrupt scans) + Step 2 (compose down, preserve volumes)
#   --hard   (default) soft (same as soft; no additional steps)
#   --full   hard + compose down --volumes (destroys postgres_data et al.)
#
# --dry-run  Print all planned ops without executing any destructive command.
# --runtime  Explicit container runtime. Default: podman. Podman mode stops/removes
#            exact Argus-owned containers only and preserves Podman images/volumes.
#            Docker remains available as a local/dev fallback.
# --help     Print this usage and exit 0.

set -euo pipefail

export SUPPRESS_BOLTDB_WARNING=1

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
CONTAINER_RUNTIME="${ARGUS_CONTAINER_RUNTIME:-podman}"

# ---------------------------------------------------------------------------
# Counters (for summary)
# ---------------------------------------------------------------------------
ORPHAN_WARNINGS=0
PODMAN_PROJECT_LABEL="io.argus.project=argus"
PODMAN_RUNTIME_LABEL="io.argus.runtime=podman"
PODMAN_CONTAINER_NAMES=(argus-frontend argus-backend argus-redis argus-db)

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,1\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --soft)    MODE="soft"; shift ;;
    --hard)    MODE="hard"; shift ;;
    --full)    MODE="full"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --runtime=*) CONTAINER_RUNTIME="${1#--runtime=}"; shift ;;
    --runtime)
      [[ $# -ge 2 ]] || { printf 'argus-shutdown: --runtime requires a value (docker|podman)\n' >&2; exit 1; }
      CONTAINER_RUNTIME="$2"
      shift 2
      ;;
    --help|-h) usage ;;
    *)
      printf 'argus-shutdown: unknown argument: %s\n' "$1" >&2
      printf 'Run with --help for usage.\n' >&2
      exit 1
      ;;
  esac
done

case "$CONTAINER_RUNTIME" in
  docker|podman) ;;
  *)
    printf 'argus-shutdown: unknown runtime: %s\n' "$CONTAINER_RUNTIME" >&2
    printf 'Supported runtimes: docker podman\n' >&2
    exit 1
    ;;
esac

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

podman_container_has_required_labels() {
  local name="$1"
  local project_label runtime_label
  project_label="$(podman inspect --format '{{ index .Config.Labels "io.argus.project" }}' "$name" 2>/dev/null || true)"
  runtime_label="$(podman inspect --format '{{ index .Config.Labels "io.argus.runtime" }}' "$name" 2>/dev/null || true)"
  [[ "$project_label" == "argus" && "$runtime_label" == "podman" ]]
}

step2_podman_down() {
  log "Step 2: Podman targeted stop/remove (preserve images and volumes)"
  if [[ "$MODE" == "full" ]]; then
    log "  Mode=full under Podman: preserving Podman volumes and images by plan."
  fi

  local stop_timeout=15
  local name

  # Phase A: Stop and remove known named containers
  for name in "${PODMAN_CONTAINER_NAMES[@]}"; do
    if [[ "$DRY_RUN" == true ]]; then
      run_cmd "podman stop ${name}" podman stop -t "$stop_timeout" "$name"
      run_cmd "podman rm -f ${name}" podman rm -f "$name"
      continue
    fi
    if ! podman container exists "$name" 2>/dev/null; then
      log "  ${name}: not present; skipping."
      continue
    fi
    if ! podman_container_has_required_labels "$name"; then
      warn "skipping ${name}: missing required ${PODMAN_PROJECT_LABEL} and ${PODMAN_RUNTIME_LABEL} labels"
      continue
    fi
    log "  Stopping ${name}..."
    podman stop -t "$stop_timeout" "$name" 2>/dev/null || true
    podman rm -f "$name" 2>/dev/null || true
  done

  # Phase B: Catch orphan containers with argus label not in the known list
  local orphans
  orphans="$(podman ps -a --filter "label=io.argus.project=argus" --format '{{.Names}}' 2>/dev/null || true)"
  if [[ -n "$orphans" ]]; then
    local orphan
    while IFS= read -r orphan; do
      [[ -z "$orphan" ]] && continue
      # Skip if already handled in Phase A
      local known=false
      for name in "${PODMAN_CONTAINER_NAMES[@]}"; do
        [[ "$orphan" == "$name" ]] && known=true && break
      done
      if [[ "$known" == true ]]; then continue; fi
      log "  Orphan argus container found: ${orphan}; stopping and removing."
      if [[ "$DRY_RUN" == true ]]; then
        run_cmd "podman stop orphan ${orphan}" podman stop -t "$stop_timeout" "$orphan"
        run_cmd "podman rm -f orphan ${orphan}" podman rm -f "$orphan"
      else
        podman stop -t "$stop_timeout" "$orphan" 2>/dev/null || true
        podman rm -f "$orphan" 2>/dev/null || true
      fi
      ORPHAN_WARNINGS=$((ORPHAN_WARNINGS + 1))
    done <<< "$orphans"
  fi

  log "  Step 2 complete: all argus containers stopped and removed."
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
# STEP 1: Force-cancel running scans (best-effort)
# ---------------------------------------------------------------------------
extract_task_ids() {
  grep -o '"taskId":"[^"]*"\|"task_id":"[^"]*"\|"id":"[^"]*"' \
    | sed 's/"taskId":"//;s/"task_id":"//;s/"id":"//;s/"//' 2>/dev/null || true
}

extract_cancellable_intelligent_task_ids() {
  python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(0)

if isinstance(payload, dict):
    payload = payload.get("items") or payload.get("tasks") or payload.get("data") or []

for item in payload if isinstance(payload, list) else []:
    if not isinstance(item, dict):
        continue
    status = str(item.get("status") or "").lower()
    if status not in {"pending", "running"}:
        continue
    task_id = item.get("taskId") or item.get("task_id") or item.get("id")
    if task_id:
        print(task_id)
' 2>/dev/null || true
}

interrupt_running_scan_engine() {
  local engine="$1"
  local list_path="$2"
  local interrupt_path_template="$3"
  local base_url="$4"
  local response ids task_id interrupt_path

  response=$(curl -sf "${base_url}${list_path}" 2>/dev/null) || response="[]"
  ids=$(printf '%s' "$response" | extract_task_ids)

  if [[ -z "$ids" ]]; then
    log "  No running ${engine} scan tasks found."
    return 0
  fi

  for task_id in $ids; do
    interrupt_path="${interrupt_path_template//\{task_id\}/$task_id}"
    log "  Force-cancelling ${engine} scan task: $task_id"
    if [[ "$DRY_RUN" == true ]]; then
      run_cmd "POST ${interrupt_path}" \
        curl -sf -X POST "${base_url}${interrupt_path}" \
          -H 'Content-Type: application/json'
    else
      run_cmd "POST ${interrupt_path}" \
        curl -sf -X POST "${base_url}${interrupt_path}" \
          -H 'Content-Type: application/json' >/dev/null 2>&1 \
        || warn "Failed to cancel ${engine} scan task $task_id (continuing)"
    fi
  done
}

interrupt_intelligent_scan_tasks() {
  local base_url="$1"
  local response ids task_id interrupt_path

  response=$(curl -sf "${base_url}/api/v1/intelligent-tasks?limit=200" 2>/dev/null) || response="[]"
  ids=$(printf '%s' "$response" | extract_cancellable_intelligent_task_ids)

  if [[ -z "$ids" ]]; then
    log "  No running intelligent scan tasks found."
    return 0
  fi

  for task_id in $ids; do
    interrupt_path="/api/v1/intelligent-tasks/${task_id}/cancel"
    log "  Force-cancelling intelligent scan task: $task_id"
    if [[ "$DRY_RUN" == true ]]; then
      run_cmd "POST ${interrupt_path}" \
        curl -sf -X POST "${base_url}${interrupt_path}" \
          -H 'Content-Type: application/json'
    else
      run_cmd "POST ${interrupt_path}" \
        curl -sf -X POST "${base_url}${interrupt_path}" \
          -H 'Content-Type: application/json' >/dev/null 2>&1 \
        || warn "Failed to cancel intelligent scan task $task_id (continuing)"
    fi
  done
}

step1_interrupt_scans() {
  log "Step 1: Force-cancel all running scans (best-effort)"

  local backend_port="${Argus_BACKEND_PORT:-${BACKEND_PORT:-18000}}"
  local base_url="http://127.0.0.1:${backend_port}"

  # Health check — best-effort, must not abort script.
  set +e
  local health_ok=false
  if curl -sf "${base_url}/health" >/dev/null 2>&1; then
    health_ok=true
  fi

  if [[ "$health_ok" == false ]]; then
    set -e
    warn "backend unreachable at ${base_url}; skipping task cancellation. Orphan scan containers may persist; restart backend to reconcile."
    return 0
  fi

  log "  Backend reachable at ${base_url}"

  interrupt_running_scan_engine \
    "opengrep" \
    "/api/v1/static-tasks/tasks?status=running" \
    "/api/v1/static-tasks/tasks/{task_id}/interrupt" \
    "$base_url"
  interrupt_running_scan_engine \
    "codeql" \
    "/api/v1/static-tasks/codeql/tasks?status=running" \
    "/api/v1/static-tasks/codeql/tasks/{task_id}/interrupt" \
    "$base_url"
  interrupt_running_scan_engine \
    "joern" \
    "/api/v1/static-tasks/joern/tasks?status=running" \
    "/api/v1/static-tasks/joern/tasks/{task_id}/interrupt" \
    "$base_url"
  interrupt_intelligent_scan_tasks "$base_url"

  set -e

  log "  Step 1 complete (running scan cancellation requested before container shutdown)"
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
  log "Starting argus shutdown (mode=$MODE, runtime=$CONTAINER_RUNTIME, dry-run=$DRY_RUN)"

  load_env

  # Step 1: interrupt running scans (best-effort, never aborts)
  step1_interrupt_scans

  # Step 2: runtime shutdown
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
    if [[ "$DRY_RUN" != true ]]; then
      command -v podman >/dev/null 2>&1 || die "podman CLI not found"
    fi
    step2_podman_down
  else
    step2_compose_down
  fi

  step5_report
  log "Shutdown complete."
}

main "$@"
