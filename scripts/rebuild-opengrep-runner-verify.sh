#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${SCANNER_OPENGREP_IMAGE:-Argus/opengrep-runner-local:latest}"
UPLOADS_VOLUME="${ARGUS_BACKEND_UPLOADS_VOLUME:-argus_backend_uploads}"
OUTPUT_DIR=""
PROJECT_DIR=""
PROJECT_ARCHIVE=""
KEEP_WORKDIR=0
SKIP_BUILD=0
JOBS="${OPENGREP_SCAN_JOBS:-0}"
MAX_MEMORY="${OPENGREP_SCAN_MAX_MEMORY_MB:-2048}"
BUILD_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/rebuild-opengrep-runner-verify.sh [options]

Rebuild the local Opengrep runner image after rule edits, start the image, and
verify it by scanning a project source tree.

Target selection, first match wins:
  --project DIR          scan an existing extracted project directory
  --archive FILE         extract and scan a project archive
  --uploads-volume NAME  copy the newest imported archive from a Docker volume
                         (default: argus_backend_uploads)

Options:
  --image NAME           image tag to rebuild and run
                         (default: SCANNER_OPENGREP_IMAGE or Argus/opengrep-runner-local:latest)
  --output-dir DIR       directory for results.json, summary.json, and opengrep.log
                         (default: .omx/reports/opengrep-image-verify-<timestamp>)
  --jobs N              opengrep jobs; 0 means half of host cores, minimum 1
                         (default: OPENGREP_SCAN_JOBS or 0)
  --max-memory MB       opengrep --max-memory value
                         (default: OPENGREP_SCAN_MAX_MEMORY_MB or 2048)
  --build-arg KEY=VAL   pass an extra docker build argument; repeatable
  --no-build            skip docker build, but still run image self-test and scan
  --keep-workdir        keep temporary extracted project files for inspection
  -h, --help            show this help

Examples:
  scripts/rebuild-opengrep-runner-verify.sh --project /path/to/source
  scripts/rebuild-opengrep-runner-verify.sh --archive /tmp/project.zip
  scripts/rebuild-opengrep-runner-verify.sh --uploads-volume argus_backend_uploads
EOF
}

log() {
  printf '[opengrep-verify] %s\n' "$*"
}

die() {
  printf '[opengrep-verify] error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

abs_path() {
  local value="$1"
  if [[ "$value" = /* ]]; then
    printf '%s\n' "$value"
  else
    printf '%s/%s\n' "$PWD" "$value"
  fi
}

timestamp_utc() {
  date -u +%Y%m%dT%H%M%SZ
}

resolve_jobs() {
  local requested="$1"
  if [[ "$requested" != "0" ]]; then
    printf '%s\n' "$requested"
    return 0
  fi

  local cores
  cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || printf '2')"
  if [[ ! "$cores" =~ ^[0-9]+$ ]] || [ "$cores" -lt 1 ]; then
    cores=2
  fi

  local half=$((cores / 2))
  if [ "$half" -lt 1 ]; then
    half=1
  fi
  printf '%s\n' "$half"
}

build_runner_image() {
  local cmd=(docker build -f "$ROOT_DIR/docker/opengrep-runner.Dockerfile" -t "$IMAGE")
  local build_arg
  for build_arg in "${BUILD_ARGS[@]}"; do
    cmd+=(--build-arg "$build_arg")
  done
  cmd+=("$ROOT_DIR")

  log "building image: $IMAGE"
  "${cmd[@]}"
}

run_image_self_test() {
  log "running image self-test"
  docker run --rm "$IMAGE" opengrep-scan --self-test
}

copy_latest_uploaded_archive() {
  local destination_dir="$1"

  docker volume inspect "$UPLOADS_VOLUME" >/dev/null 2>&1 ||
    die "Docker volume not found: $UPLOADS_VOLUME"

  mkdir -p "$destination_dir"

  local copied_name
  set +e
  copied_name="$(
    docker run --rm \
      -v "$UPLOADS_VOLUME:/uploads:ro" \
      -v "$destination_dir:/out" \
      "$IMAGE" \
      bash -lc '
        set -Eeuo pipefail
        found="$(
          find /uploads -type f \
            \( -iname "*.archive" -o -iname "*.zip" -o -iname "*.tar" -o -iname "*.tar.gz" -o -iname "*.tgz" -o -iname "*.tar.xz" -o -iname "*.txz" -o -iname "*.tar.bz2" -o -iname "*.tbz2" -o -iname "*.tbz" \) \
            -printf "%T@ %p\n" 2>/dev/null \
            | sort -nr \
            | head -n 1 \
            | cut -d" " -f2-
        )"
        [ -n "$found" ] || exit 12
        base="$(basename "$found")"
        cp -- "$found" "/out/$base"
        printf "%s\n" "$base"
      '
  )"
  local status=$?
  set -e

  if [ "$status" -eq 12 ]; then
    die "no imported project archive found in Docker volume: $UPLOADS_VOLUME"
  fi
  if [ "$status" -ne 0 ]; then
    die "failed to copy latest archive from Docker volume: $UPLOADS_VOLUME"
  fi

  printf '%s/%s\n' "$destination_dir" "$copied_name"
}

extract_archive() {
  local archive_path="$1"
  local destination_dir="$2"

  mkdir -p "$destination_dir"
  python3 - "$archive_path" "$destination_dir" <<'PY'
import pathlib
import shutil
import sys
import tarfile
import zipfile

archive = pathlib.Path(sys.argv[1]).resolve()
destination = pathlib.Path(sys.argv[2]).resolve()
destination.mkdir(parents=True, exist_ok=True)

def safe_target(name: str) -> pathlib.Path:
    target = (destination / name).resolve()
    if target != destination and destination not in target.parents:
        raise SystemExit(f"archive entry escapes destination: {name}")
    return target

if zipfile.is_zipfile(archive):
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            target = safe_target(entry.filename)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    raise SystemExit(0)

if tarfile.is_tarfile(archive):
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            safe_target(member.name)
        bundle.extractall(destination)
    raise SystemExit(0)

raise SystemExit(f"unsupported or invalid archive: {archive}")
PY
}

pick_scan_root() {
  local extracted_dir="$1"
  local entry_count
  entry_count="$(find "$extracted_dir" -mindepth 1 -maxdepth 1 -printf '.' | wc -c | tr -d ' ')"

  if [ "$entry_count" = "1" ]; then
    local only_entry
    only_entry="$(find "$extracted_dir" -mindepth 1 -maxdepth 1 -type d -print -quit)"
    if [ -n "$only_entry" ]; then
      printf '%s\n' "$only_entry"
      return 0
    fi
  fi

  printf '%s\n' "$extracted_dir"
}

results_json_ready() {
  local output_path="$1"
  python3 - "$output_path" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    raise SystemExit(1)

raise SystemExit(0 if isinstance(payload.get("results"), list) else 1)
PY
}

print_scan_summary() {
  local output_path="$1"
  local summary_path="$2"
  python3 - "$output_path" "$summary_path" <<'PY'
import json
import sys

output_path, summary_path = sys.argv[1], sys.argv[2]
with open(output_path, "r", encoding="utf-8") as handle:
    results_payload = json.load(handle)
try:
    with open(summary_path, "r", encoding="utf-8") as handle:
        summary_payload = json.load(handle)
except Exception:
    summary_payload = {}

print(f"status={summary_payload.get('status', 'unknown')}")
print(f"findings={len(results_payload.get('results') or [])}")
print(f"results={output_path}")
print(f"summary={summary_path}")
PY
}

run_scan() {
  local target_dir="$1"
  local output_dir="$2"
  local effective_jobs="$3"
  local results_path="$output_dir/results.json"
  local summary_path="$output_dir/summary.json"
  local log_path="$output_dir/opengrep.log"

  mkdir -p "$output_dir"
  log "scanning target: $target_dir"

  set +e
  docker run --rm \
    -e "OPENGREP_SCAN_JOBS=$effective_jobs" \
    -e "OPENGREP_SCAN_MAX_MEMORY_MB=$MAX_MEMORY" \
    -v "$target_dir:/scan/source:ro" \
    -v "$output_dir:/scan/output" \
    "$IMAGE" \
    opengrep-scan \
      --target /scan/source \
      --output /scan/output/results.json \
      --summary /scan/output/summary.json \
      --log /scan/output/opengrep.log \
      --jobs "$effective_jobs" \
      --max-memory "$MAX_MEMORY"
  local scan_status=$?
  set -e

  if results_json_ready "$results_path" && { [ "$scan_status" -eq 0 ] || [ "$scan_status" -eq 1 ]; }; then
    log "scan completed with scanner exit status: $scan_status"
    print_scan_summary "$results_path" "$summary_path"
    return 0
  fi

  if [ -s "$log_path" ]; then
    printf '\n[opengrep-verify] opengrep log tail:\n' >&2
    tail -n 80 "$log_path" >&2 || true
  fi
  return "$scan_status"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)
      PROJECT_DIR="$(abs_path "${2:?missing --project value}")"
      shift 2
      ;;
    --archive)
      PROJECT_ARCHIVE="$(abs_path "${2:?missing --archive value}")"
      shift 2
      ;;
    --uploads-volume)
      UPLOADS_VOLUME="${2:?missing --uploads-volume value}"
      shift 2
      ;;
    --image)
      IMAGE="${2:?missing --image value}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$(abs_path "${2:?missing --output-dir value}")"
      shift 2
      ;;
    --jobs)
      JOBS="${2:?missing --jobs value}"
      shift 2
      ;;
    --max-memory)
      MAX_MEMORY="${2:?missing --max-memory value}"
      shift 2
      ;;
    --build-arg)
      BUILD_ARGS+=("${2:?missing --build-arg value}")
      shift 2
      ;;
    --no-build)
      SKIP_BUILD=1
      shift
      ;;
    --keep-workdir)
      KEEP_WORKDIR=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_command docker
require_command python3

if [[ ! "$JOBS" =~ ^[0-9]+$ ]] || [ "$JOBS" -lt 0 ]; then
  die "--jobs must be a non-negative integer"
fi
if [[ ! "$MAX_MEMORY" =~ ^[0-9]+$ ]] || [ "$MAX_MEMORY" -lt 1 ]; then
  die "--max-memory must be a positive integer"
fi

if [ -z "$OUTPUT_DIR" ]; then
  OUTPUT_DIR="$ROOT_DIR/.omx/reports/opengrep-image-verify-$(timestamp_utc)"
fi
mkdir -p "$OUTPUT_DIR"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/argus-opengrep-image-verify.XXXXXX")"
cleanup() {
  if [ "$KEEP_WORKDIR" -eq 0 ]; then
    rm -rf "$WORKDIR"
  else
    log "kept workdir: $WORKDIR"
  fi
}
trap cleanup EXIT

if [ "$SKIP_BUILD" -eq 0 ]; then
  build_runner_image
else
  log "skipping image build: $IMAGE"
fi

run_image_self_test

if [ -n "$PROJECT_DIR" ]; then
  [ -d "$PROJECT_DIR" ] || die "project directory not found: $PROJECT_DIR"
  SCAN_TARGET="$PROJECT_DIR"
elif [ -n "$PROJECT_ARCHIVE" ]; then
  [ -f "$PROJECT_ARCHIVE" ] || die "project archive not found: $PROJECT_ARCHIVE"
  log "extracting archive: $PROJECT_ARCHIVE"
  extract_archive "$PROJECT_ARCHIVE" "$WORKDIR/source"
  SCAN_TARGET="$(pick_scan_root "$WORKDIR/source")"
else
  log "copying latest imported archive from Docker volume: $UPLOADS_VOLUME"
  UPLOADED_ARCHIVE="$(copy_latest_uploaded_archive "$WORKDIR/uploaded")"
  log "extracting uploaded archive: $UPLOADED_ARCHIVE"
  extract_archive "$UPLOADED_ARCHIVE" "$WORKDIR/source"
  SCAN_TARGET="$(pick_scan_root "$WORKDIR/source")"
fi

EFFECTIVE_JOBS="$(resolve_jobs "$JOBS")"
log "using jobs=$EFFECTIVE_JOBS max_memory_mb=$MAX_MEMORY"
run_scan "$SCAN_TARGET" "$OUTPUT_DIR" "$EFFECTIVE_JOBS"
