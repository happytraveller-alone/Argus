#!/usr/bin/env bash
set -Eeuo pipefail

RULES_ROOT="${OPENGREP_RULES_ROOT:-/opt/opengrep/rules}"
RULES_ARCHIVE="${OPENGREP_RULES_ARCHIVE:-/opt/opengrep/rules.tar.gz}"

usage() {
  cat <<'EOF'
Usage:
  opengrep-scan --self-test
  opengrep-scan --target DIR --output FILE --summary FILE [--log FILE]
               [--manifest FILE] [--config DIR] [--jobs N] [--max-memory MB]
EOF
}

self_test() {
  ensure_rules_root
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

  json_summary "scan_completed" "$invalid_output" "$temp_dir/opengrep.log" "$summary_invalid_path"
  test -s "$summary_invalid_path"
  grep -q '"status":"scan_failed"' "$summary_invalid_path"

  json_summary "scan_completed" "$valid_output" "$temp_dir/opengrep.log" "$summary_path"
  test -s "$summary_path"
  grep -q '"status":"scan_completed"' "$summary_path"

  local sigpipe_log="$temp_dir/sigpipe.log"
  printf 'SIGPIPE signal intercepted\n' > "$sigpipe_log"
  local sigpipe_summary="$temp_dir/summary-sigpipe.json"
  json_summary "scan_completed" "$invalid_output" "$sigpipe_log" "$sigpipe_summary"
  grep -q '"status":"scan_failed"' "$sigpipe_summary"
  grep -q 'SIGPIPE/OOM' "$sigpipe_summary"

  rm -rf "$temp_dir"
}

ensure_rules_root() {
  if [ -d "$RULES_ROOT/rules_opengrep" ] && [ -d "$RULES_ROOT/rules_from_patches" ]; then
    return 0
  fi

  if [ ! -f "$RULES_ARCHIVE" ]; then
    echo "missing rule archive: $RULES_ARCHIVE" >&2
    return 1
  fi

  mkdir -p "$RULES_ROOT"
  tar -xzf "$RULES_ARCHIVE" -C "$RULES_ROOT"
}

results_json_ready() {
  local output_path="$1"

  if [ ! -s "$output_path" ]; then
    return 1
  fi

  python3 - "$output_path" <<'PY'
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

recover_json_document() {
  local input_path="$1"
  local output_path="$2"

  if [ ! -s "$input_path" ]; then
    return 1
  fi

  python3 - "$input_path" "$output_path" <<'PY'
import json
import sys

source_path, target_path = sys.argv[1], sys.argv[2]
with open(source_path, "r", encoding="utf-8", errors="replace") as handle:
    text = handle.read()

decoder = json.JSONDecoder()
for index, char in enumerate(text):
    if char != "{":
        continue
    try:
        payload, _ = decoder.raw_decode(text[index:])
    except json.JSONDecodeError:
        continue
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        with open(target_path, "w", encoding="utf-8") as output:
            json.dump(payload, output, separators=(",", ":"))
            output.write("\n")
        raise SystemExit(0)

raise SystemExit(1)
PY
}

recover_results_json_from() {
  local source_path="$1"
  local source_label="$2"
  local recovered_path="${output_path}.recovered"

  if ! grep -q '"results"' "$source_path" 2>/dev/null; then
    return 1
  fi

  rm -f "$recovered_path"
  if recover_json_document "$source_path" "$recovered_path"; then
    mv "$recovered_path" "$output_path"
    printf 'recovered opengrep JSON results from %s\n' "$source_label" >> "$log_path"
    return 0
  fi

  rm -f "$recovered_path"
  return 1
}

json_summary() {
  local status="$1"
  local output_path="$2"
  local log_path="$3"
  local summary_path="$4"

  if [ -s "$summary_path" ]; then
    return 0
  fi

  local effective_status="$status"
  local reason=""
  if ! results_json_ready "$output_path"; then
    effective_status="scan_failed"
    if grep -q "SIGPIPE\|RPC.write_packet\|Broken pipe" "$log_path" 2>/dev/null; then
      reason="SIGPIPE/OOM: opengrep subprocess crashed, likely insufficient memory for rule count"
    elif [ ! -s "$output_path" ]; then
      reason="opengrep produced no output file"
    else
      reason="output file exists but contains invalid JSON structure"
    fi
  fi

  mkdir -p "$(dirname "$summary_path")"
  printf '{"status":"%s","reason":"%s","results_path":"%s","log_path":"%s"}\n' \
    "$effective_status" "$reason" "$output_path" "$log_path" > "$summary_path"
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
jobs="${OPENGREP_SCAN_JOBS:-4}"
max_memory="${OPENGREP_SCAN_MAX_MEMORY_MB:-1536}"
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

ensure_rules_root

if [ -z "$log_path" ]; then
  log_path="$(dirname "$output_path")/opengrep.log"
fi

mkdir -p "$(dirname "$output_path")" "$(dirname "$summary_path")" "$(dirname "$log_path")"
rm -f "$output_path" "$summary_path"
: > "$log_path"
stdout_capture="${output_path}.stdout"
rm -f "$stdout_capture"

selected_root=""
cleanup() {
  if [ -n "$selected_root" ] && [ -d "$selected_root" ]; then
    rm -rf "$selected_root"
  fi
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

set +e
"${cmd[@]}" > "$stdout_capture" 2>> "$log_path"
status=$?
set -e

if ! results_json_ready "$output_path"; then
  recover_results_json_from "$output_path" "output file" || true
fi

if ! results_json_ready "$output_path"; then
  recover_results_json_from "$stdout_capture" "stdout" || true
fi

if ! results_json_ready "$output_path"; then
  recover_results_json_from "$log_path" "log" || true
fi

if ! results_json_ready "$output_path" && [ "$status" -eq 0 ]; then
  if grep -q "SIGPIPE\|RPC.write_packet\|Broken pipe" "$log_path" 2>/dev/null; then
    printf 'SIGPIPE detected: opengrep RPC subprocess likely killed by OOM\n' >> "$log_path"
    printf 'Rule count and memory limit may be insufficient\n' >> "$log_path"
    status=141
  else
    printf '{"results":[]}\n' > "$output_path"
    printf 'opengrep exited 0 with no findings; synthesized empty results\n' >> "$log_path"
  fi
fi

if ! results_json_ready "$output_path" && [ -s "$stdout_capture" ]; then
  {
    printf '\n--- opengrep stdout tail ---\n'
    tail -c 4000 "$stdout_capture" || true
    printf '\n--- end opengrep stdout tail ---\n'
  } >> "$log_path"
fi

json_summary "scan_completed" "$output_path" "$log_path" "$summary_path"
exit "$status"
