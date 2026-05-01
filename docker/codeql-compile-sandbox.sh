#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  codeql-compile-sandbox --self-test
  codeql-compile-sandbox --source DIR --summary FILE --events FILE --plan FILE --evidence DIR
                         --language cpp [--allow-network]
USAGE
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

write_event() {
  local stage="$1"
  local event="$2"
  local message="$3"
  local exit_code="${4:-}"
  mkdir -p "$(dirname "$events_path")"
  local escaped
  escaped="$(printf '%s' "$message" | json_escape)"
  if [ -n "$exit_code" ]; then
    printf '{"ts":"%s","engine":"codeql","sandbox":"compile","stage":"%s","event":"%s","exit_code":%s,"message":"%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stage" "$event" "$exit_code" "$escaped" >> "$events_path"
  else
    printf '{"ts":"%s","engine":"codeql","sandbox":"compile","stage":"%s","event":"%s","message":"%s"}\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$stage" "$event" "$escaped" >> "$events_path"
  fi
}

write_failure_summary() {
  local reason="$1"
  local category="${2:-compile_sandbox_failure}"
  mkdir -p "$(dirname "$summary_path")"
  python3 - "$summary_path" "$reason" "$category" <<'PY'
import json, sys, time
path, reason, category = sys.argv[1:4]
payload = {
    "status": "compile_failed",
    "engine": "codeql",
    "sandbox": "compile",
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "reason": reason,
    "diagnostic_category": category,
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, separators=(",", ":"))
    handle.write("\n")
PY
}

validate_manual_build_command() {
  local command="$1"
  local workdir="$2"
  python3 - "$command" "$workdir" <<'PY'
import sys

command = sys.argv[1].strip()
workdir = sys.argv[2].strip().replace('\\', '/')
if not command:
    raise SystemExit('empty build command')
if len(command) > 1000:
    raise SystemExit('build command is too long')
if not workdir or workdir == '.':
    workdir = '.'
if workdir.startswith('/') or '\0' in workdir or any(part == '..' for part in workdir.split('/')):
    raise SystemExit('working directory escapes the scan workspace')
lowered = command.lower()
denied_tokens = [
    'docker', 'podman', 'kubectl', 'sudo', 'su ', 'ssh ', 'scp ', 'rsync ',
    '/var/run/docker.sock', '/etc/passwd', '/etc/shadow', '~/.ssh', 'id_rsa',
    'aws_secret', 'github_token', 'argus_reset_import_token', 'sh -c', 'bash -c',
]
for token in denied_tokens:
    if token in lowered:
        raise SystemExit(f'denied token in build command: {token}')
denied_patterns = ['../', '> /', '>/', ' 2>/', ' >/', 'rm -rf /', 'mkfs', ':(){', '||', ';', '$(', '${', '|']
for pattern in denied_patterns:
    if pattern in lowered:
        raise SystemExit(f'unsafe filesystem pattern in build command: {pattern}')
PY
}

fingerprint_source() {
  python3 - "$source_dir" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
skip_dirs = {'.git', '.argus-codeql-build', '.argus-codeql-cmake-build', 'build', 'cmake-build-debug', 'cmake-build-release'}
h = hashlib.sha256()
for current, dirs, files in os.walk(root):
    dirs[:] = [d for d in sorted(dirs) if d not in skip_dirs]
    for name in sorted(files):
        path = os.path.join(current, name)
        rel = os.path.relpath(path, root).replace(os.sep, '/')
        if rel.startswith('.argus-codeql-'):
            continue
        h.update(rel.encode('utf-8') + b'\0')
        try:
            with open(path, 'rb') as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
        except OSError:
            continue
print('sha256:' + h.hexdigest())
PY
}

fingerprint_dependencies() {
  python3 - "$source_dir" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
interesting = [
    'CMakeLists.txt', 'Makefile', 'makefile', 'GNUmakefile', 'meson.build',
    'conanfile.txt', 'conanfile.py', 'vcpkg.json', 'compile_commands.json',
]
h = hashlib.sha256()
for name in interesting:
    path = os.path.join(root, name)
    if os.path.exists(path):
        h.update(name.encode('utf-8') + b'\0')
        with open(path, 'rb') as handle:
            h.update(handle.read())
print('sha256:' + h.hexdigest())
PY
}

detect_cpp_command() {
  python3 - "$source_dir" <<'PY'
import os, sys
root = sys.argv[1]
if os.path.exists(os.path.join(root, 'CMakeLists.txt')):
    print('cmake --build .argus-codeql-cmake-build --parallel 2 --clean-first')
    raise SystemExit
for name in ('Makefile', 'makefile', 'GNUmakefile'):
    if os.path.exists(os.path.join(root, name)):
        print('make -B -j2')
        raise SystemExit
cpp_exts = ('.cc', '.cpp', '.cxx')
c_exts = ('.c',)
cpp_files = []
c_files = []
for current, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in {'.git', 'build', '.argus-codeql-build', '.argus-codeql-cmake-build'}]
    for file in files:
        rel = os.path.relpath(os.path.join(current, file), root).replace(os.sep, '/')
        if rel.endswith(cpp_exts):
            cpp_files.append(rel)
        elif rel.endswith(c_exts):
            c_files.append(rel)
if cpp_files:
    print('c++ ' + ' '.join(cpp_files) + ' -o argus-codeql-cpp-smoke')
    raise SystemExit
if c_files:
    print('cc ' + ' '.join(c_files) + ' -o argus-codeql-c-smoke')
    raise SystemExit
raise SystemExit('no C/C++ build inputs detected')
PY
}

self_test() {
  command -v python3 >/dev/null
  command -v sh >/dev/null
  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codeql-compile-self-test.XXXXXX")"
  mkdir -p "$temp_dir/src"
  printf 'int main(void) { return 0; }\n' > "$temp_dir/src/main.c"
  events_path="$temp_dir/events.jsonl"
  summary_path="$temp_dir/summary.json"
  plan_path="$temp_dir/build-plan.json"
  evidence_dir="$temp_dir/evidence"
  source_dir="$temp_dir/src"
  language="cpp"
  run_compile_sandbox
  test -s "$events_path"
  test -s "$summary_path"
  test -s "$plan_path"
  rm -rf "$temp_dir"
}

run_compile_sandbox() {
  mkdir -p "$(dirname "$summary_path")" "$(dirname "$events_path")" "$(dirname "$plan_path")" "$evidence_dir"
  write_event "compile_sandbox" "started" "CodeQL compile sandbox started for language=$language"
  if [ "$language" != "cpp" ]; then
    write_event "compile_sandbox" "failed" "only C/C++ language is supported by this compile-sandbox slice"
    write_failure_summary "only C/C++ language is supported by this compile-sandbox slice" "validator_rejection"
    return 2
  fi
  local command
  if ! command="$(detect_cpp_command 2>&1)"; then
    write_event "compile_sandbox" "failed" "$command"
    write_failure_summary "$command" "dependency_setup_failure"
    return 1
  fi
  if ! validation_error="$(validate_manual_build_command "$command" "." 2>&1)"; then
    write_event "compile_sandbox" "validator_rejected" "$validation_error"
    write_failure_summary "manual build command rejected: $validation_error" "validator_rejection"
    return 1
  fi

  local stdout_path="$evidence_dir/compile-stdout.txt"
  local stderr_path="$evidence_dir/compile-stderr.txt"
  if [ -f "$source_dir/CMakeLists.txt" ]; then
    write_event "compile_sandbox" "cmake_configure_started" "configuring CMake build directory for CodeQL replay"
    set +e
    (cd "$source_dir" && rm -rf .argus-codeql-cmake-build && cmake -S . -B .argus-codeql-cmake-build) >>"$stdout_path" 2>>"$stderr_path"
    local configure_status=$?
    set -e
    if [ "$configure_status" -ne 0 ]; then
      write_event "compile_sandbox" "cmake_configure_exit" "CMake configure failed" "$configure_status"
      write_failure_summary "CMake configure failed with exit_code=$configure_status" "build_command_failure"
      return "$configure_status"
    fi
    write_event "compile_sandbox" "cmake_configure_exit" "CMake configure completed" 0
  fi
  write_event "compile_sandbox" "command_started" "$command"
  set +e
  (cd "$source_dir" && sh -lc "$command") >"$stdout_path" 2>"$stderr_path"
  local status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    write_event "compile_sandbox" "command_exit" "compile command failed" "$status"
    write_failure_summary "compile command failed with exit_code=$status" "build_command_failure"
    return "$status"
  fi
  write_event "compile_sandbox" "command_exit" "compile command completed" 0

  local source_fp dep_fp generated_at
  source_fp="$(fingerprint_source)"
  dep_fp="$(fingerprint_dependencies)"
  generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$summary_path" "$plan_path" "$language" "$command" "$source_fp" "$dep_fp" "$stdout_path" "$stderr_path" "$generated_at" "$allow_network" <<'PY'
import json, os, sys
summary_path, plan_path, language, command, source_fp, dep_fp, stdout_path, stderr_path, generated_at, allow_network = sys.argv[1:]
evidence = {
    "artifacts_role": "evidence_only",
    "stdout_path": stdout_path,
    "stderr_path": stderr_path,
    "diagnostic_files": [stdout_path, stderr_path],
    "detection_strategy": "cmake_make_or_direct_cpp_compile",
}
plan = {
    "engine": "codeql",
    "sandbox": "compile",
    "language": language,
    "target_path": ".",
    "build_mode": "manual",
    "commands": [command],
    "working_directory": ".",
    "allow_network": allow_network == "true",
    "query_suite": None,
    "source_fingerprint": source_fp,
    "dependency_fingerprint": dep_fp,
    "status": "accepted",
    "evidence_json": evidence,
    "generated_at": generated_at,
}
summary = dict(plan)
summary["status"] = "compile_completed"
for path, payload in ((summary_path, summary), (plan_path, plan)):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
PY
  write_event "compile_sandbox" "completed" "compile sandbox persisted an accepted C/C++ recipe"
}

source_dir=""
summary_path=""
events_path=""
plan_path=""
evidence_dir=""
language=""
allow_network="false"

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) source_dir="$2"; shift 2 ;;
    --summary) summary_path="$2"; shift 2 ;;
    --events) events_path="$2"; shift 2 ;;
    --plan) plan_path="$2"; shift 2 ;;
    --evidence) evidence_dir="$2"; shift 2 ;;
    --language) language="$2"; shift 2 ;;
    --allow-network) allow_network="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in source_dir summary_path events_path plan_path evidence_dir language; do
  if [ -z "${!required}" ]; then
    echo "missing required argument: $required" >&2
    exit 2
  fi
done

run_compile_sandbox
