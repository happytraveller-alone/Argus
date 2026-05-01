
test_compile_diagnostic_categories() {
  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codeql-compile-diagnostics.XXXXXX")"
  mkdir -p "$temp_dir/empty"
  if docker/codeql-compile-sandbox.sh --source "$temp_dir/empty" --summary "$temp_dir/summary.json" --events "$temp_dir/events.jsonl" --plan "$temp_dir/plan.json" --evidence "$temp_dir/evidence" --language cpp >/dev/null 2>&1; then
    echo "expected dependency/setup failure" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"dependency_setup_failure"' "$temp_dir/summary.json"

  mkdir -p "$temp_dir/bad/src"
  printf 'all:\n\tfalse\n' > "$temp_dir/bad/Makefile"
  if docker/codeql-compile-sandbox.sh --source "$temp_dir/bad" --summary "$temp_dir/build-summary.json" --events "$temp_dir/build-events.jsonl" --plan "$temp_dir/build-plan.json" --evidence "$temp_dir/build-evidence" --language cpp >/dev/null 2>&1; then
    echo "expected build command failure" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"build_command_failure"' "$temp_dir/build-summary.json"

  mkdir -p "$temp_dir/good/src"
  printf 'all:\n\tcc src/main.c -o app\n' > "$temp_dir/good/Makefile"
  printf 'int main(void) { return 0; }\n' > "$temp_dir/good/src/main.c"
  docker/codeql-compile-sandbox.sh --source "$temp_dir/good" --summary "$temp_dir/good-summary.json" --events "$temp_dir/good-events.jsonl" --plan "$temp_dir/good-plan.json" --evidence "$temp_dir/good-evidence" --language cpp >/dev/null
  grep -q '"status":"accepted"' "$temp_dir/good-plan.json"
  grep -q '"commands":\["make -B -j2"\]' "$temp_dir/good-plan.json"
  if python3 - "$temp_dir/good-plan.json" <<'PY'
import json, re, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    command = json.load(handle)["commands"][0]
raise SystemExit(0 if re.search(r'\$\{|\|\||;', command) else 1)
PY
  then
    echo "expected CodeQL argv-compatible build command without shell-only syntax" >&2
    exit 1
  fi

  if docker/codeql-compile-sandbox.sh --source "$temp_dir/bad" --summary "$temp_dir/lang-summary.json" --events "$temp_dir/lang-events.jsonl" --plan "$temp_dir/lang-plan.json" --evidence "$temp_dir/lang-evidence" --language python >/dev/null 2>&1; then
    echo "expected validator/language rejection" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"validator_rejection"' "$temp_dir/lang-summary.json"
  rm -rf "$temp_dir"
}

test_codeql_scan_diagnostic_categories() {
  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/codeql-scan-diagnostics.XXXXXX")"
  mkdir -p "$temp_dir/src" "$temp_dir/queries"
  printf '{"build_mode":"manual","commands":["docker build ."],"working_directory":"."}\n' > "$temp_dir/rejected-plan.json"
  if PATH="/usr/bin:/bin" docker/codeql-scan.sh --source "$temp_dir/src" --queries "$temp_dir/queries" --database "$temp_dir/db" --sarif "$temp_dir/results.sarif" --summary "$temp_dir/summary.json" --events "$temp_dir/events.jsonl" --language cpp --build-plan "$temp_dir/rejected-plan.json" >/dev/null 2>&1; then
    echo "expected missing CodeQL dependency failure before validation" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"dependency_setup_failure"' "$temp_dir/summary.json"

  local fake_bin="$temp_dir/bin"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/codeql" <<'SH'
#!/usr/bin/env sh
case "$1 $2" in
  "database create") exit "${FAKE_CODEQL_CREATE_EXIT:-0}" ;;
  "database analyze") exit "${FAKE_CODEQL_ANALYZE_EXIT:-0}" ;;
  *) exit 0 ;;
esac
SH
  chmod +x "$fake_bin/codeql"

  if PATH="$fake_bin:/usr/bin:/bin" docker/codeql-scan.sh --source "$temp_dir/src" --queries "$temp_dir/queries" --database "$temp_dir/db-reject" --sarif "$temp_dir/reject.sarif" --summary "$temp_dir/reject-summary.json" --events "$temp_dir/reject-events.jsonl" --language cpp --build-plan "$temp_dir/rejected-plan.json" >/dev/null 2>&1; then
    echo "expected validator rejection" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"validator_rejection"' "$temp_dir/reject-summary.json"

  printf '{"build_mode":"manual","commands":["make clean || true; make -j${CODEQL_COMPILE_JOBS:-2}"],"working_directory":"."}\n' > "$temp_dir/shell-plan.json"
  if PATH="$fake_bin:/usr/bin:/bin" docker/codeql-scan.sh --source "$temp_dir/src" --queries "$temp_dir/queries" --database "$temp_dir/db-shell" --sarif "$temp_dir/shell.sarif" --summary "$temp_dir/shell-summary.json" --events "$temp_dir/shell-events.jsonl" --language cpp --build-plan "$temp_dir/shell-plan.json" >/dev/null 2>&1; then
    echo "expected validator rejection for CodeQL argv-incompatible shell syntax" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"validator_rejection"' "$temp_dir/shell-summary.json"

  printf '{"build_mode":"manual","commands":["make -j2"],"working_directory":"."}\n' > "$temp_dir/ok-plan.json"
  if PATH="$fake_bin:/usr/bin:/bin" FAKE_CODEQL_CREATE_EXIT=9 docker/codeql-scan.sh --source "$temp_dir/src" --queries "$temp_dir/queries" --database "$temp_dir/db-create" --sarif "$temp_dir/create.sarif" --summary "$temp_dir/create-summary.json" --events "$temp_dir/create-events.jsonl" --language cpp --build-plan "$temp_dir/ok-plan.json" >/dev/null 2>&1; then
    echo "expected CodeQL capture failure" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"codeql_capture_failure"' "$temp_dir/create-summary.json"

  if PATH="$fake_bin:/usr/bin:/bin" FAKE_CODEQL_ANALYZE_EXIT=8 docker/codeql-scan.sh --source "$temp_dir/src" --queries "$temp_dir/queries" --database "$temp_dir/db-analyze" --sarif "$temp_dir/analyze.sarif" --summary "$temp_dir/analyze-summary.json" --events "$temp_dir/analyze-events.jsonl" --language cpp --build-plan "$temp_dir/ok-plan.json" >/dev/null 2>&1; then
    echo "expected CodeQL analyze failure" >&2
    exit 1
  fi
  grep -q '"diagnostic_category":"codeql_analyze_failure"' "$temp_dir/analyze-summary.json"
  rm -rf "$temp_dir"
}

test_compile_diagnostic_categories
test_codeql_scan_diagnostic_categories
