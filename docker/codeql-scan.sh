#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  codeql-scan --self-test
  codeql-scan --source DIR --queries DIR --database DIR --sarif FILE --summary FILE --events FILE
              --language LANG [--build-plan FILE] [--threads N] [--ram MB] [--allow-network]
USAGE
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

write_event() {
  local stage="$1"
  local event="$2"
  local message="$3"
  mkdir -p "$(dirname "$events_path")"
  local escaped
  escaped="$(printf '%s' "$message" | json_escape)"
  printf '{"ts":"%s","engine":"codeql","stage":"%s","event":"%s","message":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stage" "$event" "$escaped" >> "$events_path"
}

write_summary() {
  local status="$1"
  local reason="${2:-}"
  mkdir -p "$(dirname "$summary_path")"
  python3 - "$summary_path" "$status" "$reason" <<'PY'
import json, sys, time
path, status, reason = sys.argv[1:4]
payload = {"status": status, "engine": "codeql", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
if reason:
    payload["reason"] = reason
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
    handle.write("\n")
PY
}

self_test() {
  command -v python3 >/dev/null
  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codeql-self-test.XXXXXX")"
  events_path="$temp_dir/events.jsonl"
  summary_path="$temp_dir/summary.json"
  sarif_path="$temp_dir/results.sarif"
  write_event "self_test" "started" "CodeQL runner self-test started"
  if command -v codeql >/dev/null; then
    codeql version >/dev/null
    codeql resolve languages >/dev/null
    write_event "self_test" "codeql_available" "CodeQL CLI is available"
  else
    write_event "self_test" "codeql_unavailable" "CodeQL CLI not installed; script contract self-test only"
  fi
  python3 - "$sarif_path" <<'PY'
import json, sys
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL","rules":[]}},"results":[]}]}, handle)
PY
  write_summary "scan_completed"
  test -s "$events_path"
  test -s "$summary_path"
  test -s "$sarif_path"
  rm -rf "$temp_dir"
}

source_dir=""
queries_dir=""
database_dir=""
sarif_path=""
summary_path=""
events_path=""
build_plan_path=""
language=""
threads="0"
ram_mb="6144"
allow_network="false"

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) source_dir="$2"; shift 2 ;;
    --queries) queries_dir="$2"; shift 2 ;;
    --database) database_dir="$2"; shift 2 ;;
    --sarif) sarif_path="$2"; shift 2 ;;
    --summary) summary_path="$2"; shift 2 ;;
    --events) events_path="$2"; shift 2 ;;
    --build-plan) build_plan_path="$2"; shift 2 ;;
    --language) language="$2"; shift 2 ;;
    --threads) threads="$2"; shift 2 ;;
    --ram) ram_mb="$2"; shift 2 ;;
    --allow-network) allow_network="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in source_dir queries_dir database_dir sarif_path summary_path events_path language; do
  if [ -z "${!required}" ]; then
    echo "missing required argument: $required" >&2
    exit 2
  fi
done

mkdir -p "$(dirname "$sarif_path")" "$(dirname "$summary_path")" "$(dirname "$events_path")" "$database_dir"
write_event "extracting" "input_ready" "CodeQL source and query inputs resolved"

if ! command -v codeql >/dev/null; then
  write_event "failed" "codeql_unavailable" "CodeQL CLI is not installed in this runner image"
  write_summary "scan_failed" "CodeQL CLI unavailable"
  exit 127
fi

build_mode="none"
manual_command=""
working_directory="."
if [ -n "$build_plan_path" ] && [ -s "$build_plan_path" ]; then
  build_mode="$(python3 - "$build_plan_path" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    payload=json.load(handle)
print(payload.get('build_mode') or 'none')
PY
)"
  manual_command="$(python3 - "$build_plan_path" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    payload=json.load(handle)
commands=payload.get('commands') or []
print(commands[0] if commands else '')
PY
)"
  working_directory="$(python3 - "$build_plan_path" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    payload=json.load(handle)
print(payload.get('working_directory') or '.')
PY
)"
fi

validate_manual_build_command() {
  local command="$1"
  local workdir="$2"
  python3 - "$command" "$workdir" <<'PY'
import sys

command = sys.argv[1].strip()
workdir = sys.argv[2].strip().replace("\\", "/")
if not command:
    raise SystemExit("empty build command")
if len(command) > 1000:
    raise SystemExit("build command is too long")
if not workdir or workdir == ".":
    workdir = "."
if workdir.startswith("/") or "\0" in workdir or any(part == ".." for part in workdir.split("/")):
    raise SystemExit("working directory escapes the scan workspace")
lowered = command.lower()
denied_tokens = [
    "docker",
    "podman",
    "kubectl",
    "sudo",
    "su ",
    "ssh ",
    "scp ",
    "rsync ",
    "/var/run/docker.sock",
    "/etc/passwd",
    "/etc/shadow",
    "~/.ssh",
    "id_rsa",
    "aws_secret",
    "github_token",
    "argus_reset_import_token",
]
for token in denied_tokens:
    if token in lowered:
        raise SystemExit(f"denied token in build command: {token}")
denied_patterns = ["../", "> /", ">/", " 2>/", " >/", "rm -rf /", "mkfs", ":(){"]
for pattern in denied_patterns:
    if pattern in lowered:
        raise SystemExit(f"unsafe filesystem pattern in build command: {pattern}")
PY
}

write_event "database_create" "started" "creating CodeQL database with build_mode=$build_mode allow_network=$allow_network"
create_cmd=(codeql database create "$database_dir" --language "$language" --source-root "$source_dir" --overwrite)
case "$build_mode" in
  manual)
    if [ -z "$manual_command" ]; then
      write_event "database_create" "failed" "manual build mode requires a command"
      write_summary "scan_failed" "manual build mode requires a command"
      exit 1
    fi
    if ! validation_error="$(validate_manual_build_command "$manual_command" "$working_directory" 2>&1)"; then
      write_event "database_create" "failed" "manual build command rejected: $validation_error"
      write_summary "scan_failed" "manual build command rejected"
      exit 1
    fi
    create_cmd+=(--command "$manual_command")
    ;;
  autobuild)
    create_cmd+=(--build-mode autobuild)
    ;;
  none|*)
    create_cmd+=(--build-mode none)
    ;;
esac

set +e
"${create_cmd[@]}"
status=$?
set -e
if [ "$status" -ne 0 ]; then
  write_event "database_create" "command_exit" "database create failed with exit_code=$status"
  write_summary "scan_failed" "database create failed"
  exit "$status"
fi
write_event "database_create" "completed" "CodeQL database created"

write_event "database_analyze" "started" "running CodeQL database analyze"
analyze_cmd=(codeql database analyze "$database_dir" "$queries_dir" --format=sarifv2.1.0 --output "$sarif_path" --threads "$threads" --ram "$ram_mb")
set +e
"${analyze_cmd[@]}"
status=$?
set -e
if [ "$status" -ne 0 ]; then
  write_event "database_analyze" "command_exit" "database analyze failed with exit_code=$status"
  write_summary "scan_failed" "database analyze failed"
  exit "$status"
fi
write_event "database_analyze" "completed" "CodeQL SARIF generated"
write_summary "scan_completed"
