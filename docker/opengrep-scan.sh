#!/usr/bin/env bash
set -Eeuo pipefail

RULES_ROOT="${OPENGREP_RULES_ROOT:-/opt/opengrep/rules}"

usage() {
  cat <<'EOF'
Usage:
  opengrep-scan --self-test
  opengrep-scan --target DIR --output FILE --summary FILE [--log FILE]
               [--manifest FILE] [--config DIR] [--jobs N] [--max-memory MB]
EOF
}

self_test() {
  command -v opengrep >/dev/null
  test -d "$RULES_ROOT/rules_opengrep"
  test -d "$RULES_ROOT/rules_from_patches"
  opengrep --version >/dev/null

  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/opengrep-self-test.XXXXXX")"
  local valid_output="$temp_dir/results.json"
  local invalid_output="$temp_dir/results-invalid.json"
  local summary_path="$temp_dir/summary.json"
  local summary_invalid_path="$temp_dir/summary-invalid.json"

  printf '{"results":[]}\n' > "$valid_output"
  printf '{"results":' > "$invalid_output"

  results_json_ready "$valid_output"
  ! results_json_ready "$invalid_output"

  json_summary "scan_summary_observed" "$invalid_output" "$temp_dir/opengrep.log" "$summary_invalid_path"
  test ! -e "$summary_invalid_path"

  json_summary "scan_summary_observed" "$valid_output" "$temp_dir/opengrep.log" "$summary_path"
  test -s "$summary_path"

  rm -rf "$temp_dir"
}

results_json_ready() {
  local output_path="$1"

  if [ ! -s "$output_path" ]; then
    return 1
  fi

  python - "$output_path" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception:
    raise SystemExit(1)

raise SystemExit(0 if isinstance(payload.get("results"), list) else 1)
PY
}

json_summary() {
  local status="$1"
  local output_path="$2"
  local log_path="$3"
  local summary_path="$4"

  if [ -s "$summary_path" ]; then
    return 0
  fi
  if ! results_json_ready "$output_path"; then
    return 0
  fi

  mkdir -p "$(dirname "$summary_path")"
  printf '{"status":"%s","results_path":"%s","log_path":"%s"}\n' \
    "$status" "$output_path" "$log_path" > "$summary_path"
}

stage_manifest_rules() {
  local manifest_path="$1"
  local selected_root="$2"
  local count=0

  while IFS= read -r relative_path || [ -n "$relative_path" ]; do
    relative_path="${relative_path#./}"
    case "$relative_path" in
      ""|\#*) continue ;;
      /*|*../*) echo "invalid rule path in manifest: $relative_path" >&2; return 2 ;;
    esac

    local source_path="$RULES_ROOT/$relative_path"
    if [ ! -f "$source_path" ]; then
      echo "missing image rule asset: $relative_path" >&2
      return 2
    fi

    local target_path="$selected_root/$relative_path"
    mkdir -p "$(dirname "$target_path")"
    ln -sf "$source_path" "$target_path"
    count=$((count + 1))
  done < "$manifest_path"

  if [ "$count" -eq 0 ]; then
    echo "rule manifest is empty: $manifest_path" >&2
    return 2
  fi
}

manifest_path=""
target_dir=""
output_path=""
summary_path=""
log_path=""
jobs="${OPENGREP_SCAN_JOBS:-1}"
max_memory="${OPENGREP_SCAN_MAX_MEMORY_MB:-384}"
config_paths=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --self-test)
      self_test
      exit 0
      ;;
    --manifest)
      manifest_path="${2:?missing --manifest value}"
      shift 2
      ;;
    --config)
      config_paths+=("${2:?missing --config value}")
      shift 2
      ;;
    --target)
      target_dir="${2:?missing --target value}"
      shift 2
      ;;
    --output)
      output_path="${2:?missing --output value}"
      shift 2
      ;;
    --summary)
      summary_path="${2:?missing --summary value}"
      shift 2
      ;;
    --log)
      log_path="${2:?missing --log value}"
      shift 2
      ;;
    --jobs)
      jobs="${2:?missing --jobs value}"
      shift 2
      ;;
    --max-memory)
      max_memory="${2:?missing --max-memory value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$target_dir" ] || [ -z "$output_path" ] || [ -z "$summary_path" ]; then
  usage >&2
  exit 2
fi

if [ -z "$log_path" ]; then
  log_path="$(dirname "$output_path")/opengrep.log"
fi

mkdir -p "$(dirname "$output_path")" "$(dirname "$summary_path")" "$(dirname "$log_path")"
rm -f "$output_path" "$summary_path"
: > "$log_path"

selected_root=""
summary_seen_file="$(mktemp "${TMPDIR:-/tmp}/opengrep-summary-seen.XXXXXX")"
summary_watcher_pid=""
rm -f "$summary_seen_file"
cleanup() {
  if [ -n "${summary_watcher_pid:-}" ]; then
    kill "$summary_watcher_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$selected_root" ] && [ -d "$selected_root" ]; then
    rm -rf "$selected_root"
  fi
  rm -f "$summary_seen_file"
}
trap cleanup EXIT

if [ -n "$manifest_path" ]; then
  selected_root="$(mktemp -d "${TMPDIR:-/tmp}/opengrep-selected.XXXXXX")"
  stage_manifest_rules "$manifest_path" "$selected_root"
  config_paths+=("$selected_root")
fi

if [ "${#config_paths[@]}" -eq 0 ]; then
  config_paths+=("$RULES_ROOT")
fi

cmd=(opengrep scan --disable-version-check --jobs "$jobs" --max-memory "$max_memory")
for config_path in "${config_paths[@]}"; do
  cmd+=(--config "$config_path")
done
cmd+=(--json --output "$output_path" "$target_dir")

(
  while true; do
    if [ -f "$summary_seen_file" ]; then
      json_summary "scan_summary_observed" "$output_path" "$log_path" "$summary_path"
      if [ -s "$summary_path" ]; then
        exit 0
      fi
    fi
    sleep 0.1
  done
) &
summary_watcher_pid=$!

set +e
"${cmd[@]}" 2>&1 | while IFS= read -r line; do
  printf '%s\n' "$line"
  printf '%s\n' "$line" >> "$log_path"
  if [[ "$line" == *"Scan Summary"* ]]; then
    : > "$summary_seen_file"
    json_summary "scan_summary_observed" "$output_path" "$log_path" "$summary_path"
  elif [[ "$line" =~ Ran[[:space:]][0-9]+[[:space:]]+rules ]]; then
    : > "$summary_seen_file"
    json_summary "scan_summary_observed" "$output_path" "$log_path" "$summary_path"
  fi
done
status=${PIPESTATUS[0]}
set -e

kill "$summary_watcher_pid" >/dev/null 2>&1 || true
wait "$summary_watcher_pid" >/dev/null 2>&1 || true
json_summary "scan_completed" "$output_path" "$log_path" "$summary_path"
exit "$status"
