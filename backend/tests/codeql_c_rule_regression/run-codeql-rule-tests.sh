#!/usr/bin/env bash
set -euo pipefail

TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$TEST_DIR/../../.." && pwd)
CODEQL_BIN=${CODEQL_BIN:-codeql}
CODEQL_SEARCH_PATH=${CODEQL_SEARCH_PATH:-}
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/argus-codeql-c-rules.XXXXXX")

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

query_args=()
if [[ -n "$CODEQL_SEARCH_PATH" ]]; then
  query_args+=(--search-path="$CODEQL_SEARCH_PATH")
fi

assert_contains() {
  local needle=$1
  local file=$2
  local label=$3

  if ! grep -Fq "$needle" "$file"; then
    echo "FAIL: expected $label to contain: $needle" >&2
    echo "--- $label output ---" >&2
    cat "$file" >&2
    exit 1
  fi
}

assert_not_contains() {
  local needle=$1
  local file=$2
  local label=$3

  if grep -Fq "$needle" "$file"; then
    echo "FAIL: expected $label not to contain: $needle" >&2
    echo "--- $label output ---" >&2
    cat "$file" >&2
    exit 1
  fi
}

run_query() {
  local pack=$1
  local query_name=$2
  local output_csv=$3
  local query_path="$REPO_ROOT/backend/assets/scan_rule_assets/rules_codeql/$pack/queries/${query_name}.ql"
  local bqrs_file="$TMP_DIR/${pack}-${query_name}.bqrs"

  "$CODEQL_BIN" query run "$query_path" \
    --database="$TMP_DIR/db" \
    "${query_args[@]}" \
    --output="$bqrs_file"

  "$CODEQL_BIN" bqrs decode "$bqrs_file" \
    --format=csv \
    --output="$output_csv"
}

run_pack_compile_smoke() {
  local pack=$1
  local query_dir="$REPO_ROOT/backend/assets/scan_rule_assets/rules_codeql/$pack/queries"
  local query_name
  for query_path in "$query_dir"/*.ql; do
    query_name=$(basename "$query_path" .ql)
    run_query "$pack" "$query_name" "$TMP_DIR/${pack}-${query_name}.csv"
  done
}

"$CODEQL_BIN" database create "$TMP_DIR/db" \
  --language=cpp \
  --source-root="$TEST_DIR" \
  --command="gcc -c security_regression.c -o $TMP_DIR/security_regression.o" \
  --overwrite

run_pack_compile_smoke c
run_pack_compile_smoke cpp

assert_contains "command-line argument" "$TMP_DIR/c-IntegerOverflowTainted.csv" "c/IntegerOverflowTainted"
assert_contains "might overflow" "$TMP_DIR/c-IntegerOverflowTainted.csv" "c/IntegerOverflowTainted"

assert_contains "strcpy" "$TMP_DIR/c-UncheckedStringCopyLength.csv" "c/UncheckedStringCopyLength"
assert_contains "strcat" "$TMP_DIR/c-UncheckedStringCopyLength.csv" "c/UncheckedStringCopyLength"
assert_not_contains "strncpy" "$TMP_DIR/c-UncheckedStringCopyLength.csv" "c/UncheckedStringCopyLength"
assert_not_contains "strncat" "$TMP_DIR/c-UncheckedStringCopyLength.csv" "c/UncheckedStringCopyLength"

assert_contains "memcpy" "$TMP_DIR/c-BadlyBoundedWrite.csv" "c/BadlyBoundedWrite"
assert_contains "strncpy" "$TMP_DIR/c-BadlyBoundedWrite.csv" "c/BadlyBoundedWrite"
assert_contains "strncpy" "$TMP_DIR/c-StrncpyFlippedArgs.csv" "c/StrncpyFlippedArgs"
assert_contains "sizeof" "$TMP_DIR/c-SuspiciousAddWithSizeof.csv" "c/SuspiciousAddWithSizeof"
assert_contains "free" "$TMP_DIR/c-DoubleFree.csv" "c/DoubleFree"
assert_contains "free" "$TMP_DIR/c-UseAfterFree.csv" "c/UseAfterFree"
assert_contains "stack-allocated memory" "$TMP_DIR/c-ReturnStackAllocatedMemory.csv" "c/ReturnStackAllocatedMemory"

assert_contains "memcpy" "$TMP_DIR/cpp-BadlyBoundedWrite.csv" "cpp/BadlyBoundedWrite"
assert_contains "free" "$TMP_DIR/cpp-DoubleFree.csv" "cpp/DoubleFree"
assert_contains "free" "$TMP_DIR/cpp-UseAfterFree.csv" "cpp/UseAfterFree"
assert_contains "sizeof" "$TMP_DIR/cpp-SuspiciousAddWithSizeof.csv" "cpp/SuspiciousAddWithSizeof"

echo "PASS: CodeQL C/C++ memory rule regression tests passed"
