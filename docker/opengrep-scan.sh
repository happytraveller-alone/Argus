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

  local stage_rules_dir="$temp_dir/stage-rules"
  local stage_selected_dir="$temp_dir/stage-selected"
  local stage_list="$temp_dir/stage-rules.txt"
  mkdir -p "$stage_rules_dir"
  printf 'one\n' > "$stage_rules_dir/one.yml"
  printf 'two\n' > "$stage_rules_dir/two.yml"
  printf 'three\n' > "$stage_rules_dir/three.yml"
  printf '%s\n' \
    "$stage_rules_dir/one.yml" \
    "$stage_rules_dir/two.yml" \
    "$stage_rules_dir/three.yml" > "$stage_list"
  stage_rule_range "$stage_list" 1 2 "$stage_selected_dir"
  test ! -e "$stage_selected_dir/rule-000000.yaml"
  grep -q '^two$' "$stage_selected_dir/rule-000001.yaml"
  grep -q '^three$' "$stage_selected_dir/rule-000002.yaml"

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

recover_results_json_to() {
  local source_path="$1"
  local source_label="$2"
  local target_path="$3"
  local scan_log_path="$4"
  local recovered_path="${target_path}.recovered"

  if ! grep -q '"results"' "$source_path" 2>/dev/null; then
    return 1
  fi

  rm -f "$recovered_path"
  if recover_json_document "$source_path" "$recovered_path"; then
    mv "$recovered_path" "$target_path"
    printf 'recovered opengrep JSON results from %s\n' "$source_label" >> "$scan_log_path"
    return 0
  fi

  rm -f "$recovered_path"
  return 1
}

zero_finding_summary_seen() {
  local stdout_path="$1"
  local scan_log_path="$2"

  grep -qE "Ran .* rules? on .* files?: 0 finding|Nothing to scan" \
    "$stdout_path" "$scan_log_path" 2>/dev/null
}

resource_failure_seen() {
  local scan_status="$1"
  local stdout_path="$2"
  local scan_log_path="$3"

  case "$scan_status" in
    137|141) return 0 ;;
  esac

  grep -qE "SIGPIPE|RPC\\.write_packet|Broken pipe|opengrep-core exited with -9|exited with -9|Killed" \
    "$stdout_path" "$scan_log_path" 2>/dev/null
}

run_opengrep_once() {
  local result_path="$1"
  local stdout_path="$2"
  local scan_log_path="$3"
  shift 3
  local scan_configs=("$@")
  local cmd=(opengrep scan --disable-version-check --jobs "$jobs" --max-memory "$max_memory")

  for config_path in "${scan_configs[@]}"; do
    cmd+=(--config "$config_path")
  done
  cmd+=(--json --output "$result_path" "$target_dir")

  "${cmd[@]}" > "$stdout_path" 2>> "$scan_log_path"
  local scan_status=$?

  return "$scan_status"
}

recover_scan_result() {
  local result_path="$1"
  local stdout_path="$2"
  local scan_log_path="$3"

  if ! results_json_ready "$result_path"; then
    recover_results_json_to "$result_path" "output file" "$result_path" "$scan_log_path" || true
  fi

  if ! results_json_ready "$result_path"; then
    recover_results_json_to "$stdout_path" "stdout" "$result_path" "$scan_log_path" || true
  fi

  if ! results_json_ready "$result_path"; then
    recover_results_json_to "$scan_log_path" "log" "$result_path" "$scan_log_path" || true
  fi
}

collect_rule_files() {
  local list_path="$1"
  shift

  : > "$list_path"
  for config_path in "$@"; do
    if [ -f "$config_path" ]; then
      printf '%s\n' "$config_path" >> "$list_path"
    elif [ -d "$config_path" ]; then
      find "$config_path" -type f \( -name '*.yml' -o -name '*.yaml' \) >> "$list_path"
    fi
  done
  sort -u "$list_path" -o "$list_path"
}

stage_rule_range() {
  local list_path="$1"
  local start="$2"
  local count="$3"
  local selected_dir="$4"
  local end=$((start + count))
  local offset=0
  local source
  local target

  mkdir -p "$selected_dir"
  while IFS= read -r source; do
    [ -n "$source" ] || continue
    target="$(printf '%s/rule-%06d.yaml' "$selected_dir" "$((start + offset))")"
    cp -p -- "$source" "$target"
    offset=$((offset + 1))
  done < <(awk -v start="$start" -v end="$end" 'NR > start && NR <= end { print }' "$list_path")
}

merge_batch_results() {
  local merged_output_path="$1"
  shift

  python3 - "$merged_output_path" "$@" <<'PY'
import json
import sys

target = sys.argv[1]
sources = sys.argv[2:]
merged = {
    "version": "opengrep-batched",
    "results": [],
    "errors": [],
    "paths": {"scanned": []},
    "skipped_rules": [],
}
scanned = set()

for source in sources:
    with open(source, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    merged["results"].extend(payload.get("results") or [])
    merged["errors"].extend(payload.get("errors") or [])
    merged["skipped_rules"].extend(payload.get("skipped_rules") or [])
    for path in ((payload.get("paths") or {}).get("scanned") or []):
        scanned.add(path)

merged["paths"]["scanned"] = sorted(scanned)
with open(target, "w", encoding="utf-8") as output:
    json.dump(merged, output, separators=(",", ":"))
    output.write("\n")
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

  local effective_status="$status"
  local reason=""
  if ! results_json_ready "$output_path"; then
    effective_status="scan_failed"
    if grep -qE "SIGPIPE|RPC\\.write_packet|Broken pipe|opengrep-core exited with -9|exited with -9|Killed" "$log_path" 2>/dev/null; then
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
jobs="${OPENGREP_SCAN_JOBS:-8}"
max_memory="${OPENGREP_SCAN_MAX_MEMORY_MB:-2048}"
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
batch_root=""
cleanup() {
  if [ -n "$selected_root" ] && [ -d "$selected_root" ]; then
    rm -rf "$selected_root"
  fi
  if [ -n "$batch_root" ] && [ -d "$batch_root" ]; then
    rm -rf "$batch_root"
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

set +e
run_opengrep_once "$output_path" "$stdout_capture" "$log_path" "${config_paths[@]}"
status=$?
set -e
recover_scan_result "$output_path" "$stdout_capture" "$log_path"

if ! results_json_ready "$output_path" && [ "$status" -eq 0 ]; then
  if resource_failure_seen "$status" "$stdout_capture" "$log_path"; then
    printf 'SIGPIPE detected: opengrep RPC subprocess likely killed by OOM\n' >> "$log_path"
    printf 'Rule count and memory limit may be insufficient\n' >> "$log_path"
    status=141
  elif zero_finding_summary_seen "$stdout_capture" "$log_path"; then
    printf '{"results":[]}\n' > "$output_path"
    printf 'opengrep exited 0 with 0 findings; synthesized empty results\n' >> "$log_path"
  fi
fi

batch_outputs=()

scan_rule_range() {
  local list_path="$1"
  local start="$2"
  local count="$3"
  local selected_dir="$batch_root/config-${start}-${count}"
  local batch_output="$batch_root/results-${start}-${count}.json"
  local batch_stdout="$batch_root/stdout-${start}-${count}.txt"

  rm -rf "$selected_dir"
  stage_rule_range "$list_path" "$start" "$count" "$selected_dir"
  : > "$batch_stdout"

  set +e
  run_opengrep_once "$batch_output" "$batch_stdout" "$log_path" "$selected_dir"
  local batch_status=$?
  set -e
  recover_scan_result "$batch_output" "$batch_stdout" "$log_path"

  if results_json_ready "$batch_output" && { [ "$batch_status" -eq 0 ] || [ "$batch_status" -eq 1 ]; }; then
    batch_outputs+=("$batch_output")
    return 0
  fi

  if [ "$count" -le 1 ]; then
    local failed_rule
    failed_rule="$(sed -n "$((start + 1))p" "$list_path" 2>/dev/null || true)"
    printf 'opengrep single-rule batch failed: rule=%s status=%s\n' "$failed_rule" "$batch_status" >> "$log_path"
    if [ -s "$batch_stdout" ]; then
      {
        printf '\n--- failed batch stdout tail ---\n'
        tail -c 4000 "$batch_stdout" || true
        printf '\n--- end failed batch stdout tail ---\n'
      } >> "$log_path"
    fi
    return 1
  fi

  local left=$((count / 2))
  local right=$((count - left))
  scan_rule_range "$list_path" "$start" "$left" && \
    scan_rule_range "$list_path" "$((start + left))" "$right"
}

run_batched_scan() {
  local list_path="$batch_root/rules.txt"
  local total_rules
  local batch_size="${OPENGREP_SCAN_BATCH_SIZE:-128}"

  collect_rule_files "$list_path" "${config_paths[@]}"
  total_rules="$(wc -l < "$list_path" | tr -d ' ')"
  if [ "$total_rules" -le 1 ]; then
    return 1
  fi

  if [ "$batch_size" -lt 1 ]; then
    batch_size=1
  fi

  printf 'retrying opengrep scan in rule batches: rules=%s batch_size=%s\n' "$total_rules" "$batch_size" >> "$log_path"
  batch_outputs=()

  local start=0
  local count
  while [ "$start" -lt "$total_rules" ]; do
    count="$batch_size"
    if [ $((start + count)) -gt "$total_rules" ]; then
      count=$((total_rules - start))
    fi
    scan_rule_range "$list_path" "$start" "$count" || return 1
    start=$((start + count))
  done

  merge_batch_results "$output_path" "${batch_outputs[@]}"
  printf 'merged opengrep JSON results from %s rule batches\n' "${#batch_outputs[@]}" >> "$log_path"
}

if ! results_json_ready "$output_path"; then
  batch_root="$(mktemp -d "${TMPDIR:-/tmp}/opengrep-batches.XXXXXX")"
  if run_batched_scan; then
    status=0
  elif [ "$status" -eq 0 ]; then
    printf 'opengrep exited 0 but produced no valid output\n' >> "$log_path"
    status=1
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
