#!/usr/bin/env bash
# purge-cubesandbox.sh — one-shot cleanup for CubeSandbox runtime artifacts.
# Created: 2026-05-07 (cubesandbox removal mission)
# Spec: .omc/autopilot/spec.md AC7
#
# Cleans:
#   - cubemastercli template registry (best effort, requires WSL2 + cubemastercli on PATH)
#   - containerd snapshots under cube-sandbox/cubelet namespaces (best effort)
#   - local .cubesandbox/ working directory
#   - prompts user about docker volume backend_cubesandbox_data removal (TTY-guarded)
# Optional:
#   - third_party/cubesandbox submodule fully purged (rm -rf .git/modules)
#   - --drop-tables: DROP TABLE rust_cubesandbox_templates / rust_cubesandbox_tasks
#                    (Critic Revision #5 / decision H2)
#
# Default mode is --dry-run. Use --force to actually delete.

set -uo pipefail

DRY_RUN=true
KEEP_DATA=false
DROP_TABLES=false
FORCE=0

usage() {
  cat <<'EOF'
Usage: scripts/purge-cubesandbox.sh [--dry-run|--force] [--keep-data] [--drop-tables]

  --dry-run      Default. Print actions only, do not modify state.
  --force        Actually perform deletions.
  --keep-data    Skip rm -rf .cubesandbox/ (only purge templates and snapshots).
  --drop-tables  Drop rust_cubesandbox_* tables from the configured DATABASE_URL
                 (postgres or sqlite auto-detected). Honors NG3 — opt-in only.
  -h, --help     Show this help and exit.

Side effects when --force:
  cubemastercli --address 127.0.0.1 cubebox list  -> destroy each
  cubemastercli --address 127.0.0.1 template list -> delete each tpl-*
  ctr -n cube-sandbox snapshots ls/rm  (if ctr available)
  rm -rf .cubesandbox  (unless --keep-data)
  Prompt: docker volume rm backend_cubesandbox_data (TTY-guarded; skipped non-interactively)
  --drop-tables: psql / sqlite3 DROP TABLE IF EXISTS rust_cubesandbox_templates, rust_cubesandbox_tasks

Exit codes:
  0  ok (incl. dry-run)
  1  unexpected fatal error
  2  arg parse error
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)     DRY_RUN=true; shift ;;
    --force)       DRY_RUN=false; FORCE=1; shift ;;
    --keep-data)   KEEP_DATA=true; shift ;;
    --drop-tables) DROP_TABLES=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

log()  { echo "[purge-cubesandbox] $*"; }
warn() { echo "[purge-cubesandbox][warn] $*" >&2; }

run() {
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] $*"
  else
    log "$*"
    "$@" || warn "command failed (rc=$?), continuing: $*"
  fi
}

# ---- 1. cubemastercli cubeboxes + templates ----
if command -v cubemastercli >/dev/null 2>&1; then
  log "Listing active cubeboxes..."
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] cubemastercli --address 127.0.0.1 cubebox list"
  else
    boxes=$(cubemastercli --address 127.0.0.1 cubebox list 2>/dev/null \
      | awk 'NR>1 {print $1}' | grep -E '^[a-zA-Z0-9-]{8,}' || true)
    for b in $boxes; do
      run cubemastercli --address 127.0.0.1 cubebox destroy "$b"
    done
  fi

  log "Listing templates..."
  if [[ "$DRY_RUN" == true ]]; then
    log "[dry-run] cubemastercli --address 127.0.0.1 template list"
  else
    tpls=$(cubemastercli --address 127.0.0.1 template list 2>/dev/null \
      | awk 'NR>1 {print $1}' | grep -E '^tpl-' || true)
    for t in $tpls; do
      run cubemastercli --address 127.0.0.1 template delete "$t"
    done
  fi
else
  warn "cubemastercli not on PATH; skipping cubebox/template purge."
fi

# ---- 2. containerd snapshots ----
if command -v ctr >/dev/null 2>&1; then
  for ns in cube-sandbox cubelet k8s.io; do
    log "Listing ctr snapshots in namespace $ns..."
    if [[ "$DRY_RUN" == true ]]; then
      log "[dry-run] ctr -n $ns snapshots ls"
    else
      snaps=$(ctr -n "$ns" snapshots ls 2>/dev/null \
        | awk 'NR>1 {print $1}' | grep -i 'cube\|tpl-' || true)
      for s in $snaps; do
        run ctr -n "$ns" snapshots rm "$s"
      done
    fi
  done
else
  warn "ctr not on PATH; skipping containerd snapshot purge."
fi

# ---- 3. local .cubesandbox/ ----
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
WORK_DIR="$ROOT_DIR/.cubesandbox"
if [[ "$KEEP_DATA" == true ]]; then
  log "--keep-data set; skipping rm -rf $WORK_DIR."
elif [[ -d "$WORK_DIR" ]]; then
  run rm -rf "$WORK_DIR"
else
  log "$WORK_DIR not present; nothing to remove."
fi

# ---- 4. .git/modules cleanup ----
GIT_MOD="$ROOT_DIR/.git/modules/third_party/cubesandbox"
if [[ -d "$GIT_MOD" ]]; then
  run rm -rf "$GIT_MOD"
fi

# ---- 5. prompt for docker volume (TTY-guarded) ----
if [[ "$DRY_RUN" == true ]]; then
  log "[dry-run] would prompt: docker volume rm backend_cubesandbox_data"
elif [[ -t 0 ]] && [[ "${ARGUS_PURGE_AUTOYES:-0}" != "1" ]]; then
  read -r -p "Run docker volume rm backend_cubesandbox_data? [y/N] " ans
  if [[ "$ans" =~ ^[yY]$ ]]; then run docker volume rm backend_cubesandbox_data; fi
elif [[ "${ARGUS_PURGE_AUTOYES:-0}" == "1" ]]; then
  run docker volume rm backend_cubesandbox_data
else
  log "non-interactive shell; skipping volume prompt (run manually if needed)"
fi

# ---- 6. drop tables (Critic Revision #5 / decision H2 — opt-in only) ----
if [[ "$DROP_TABLES" == true ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    warn "DROP_TABLES requested but DATABASE_URL not set; skipping."
  else
    case "$DATABASE_URL" in
      postgres://*|postgresql://*)
        run psql "$DATABASE_URL" -c "DROP TABLE IF EXISTS rust_cubesandbox_templates; DROP TABLE IF EXISTS rust_cubesandbox_tasks;"
        ;;
      sqlite://*|sqlite:*)
        # Strip sqlite:// prefix
        sqlite_path="${DATABASE_URL#sqlite://}"
        sqlite_path="${sqlite_path#sqlite:}"
        run sqlite3 "$sqlite_path" "DROP TABLE IF EXISTS rust_cubesandbox_templates; DROP TABLE IF EXISTS rust_cubesandbox_tasks;"
        ;;
      *)
        warn "Unknown DATABASE_URL scheme; skipping DROP TABLE. Run manually."
        ;;
    esac
  fi
else
  log "DDL kept (NG3-honored). Pass --drop-tables to opt-in DROP."
fi

log "Done. Re-run with --force after reviewing dry-run output."
exit 0
