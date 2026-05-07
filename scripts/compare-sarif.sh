#!/usr/bin/env bash
# compare-sarif.sh — SARIF findings equivalence comparator
#
# Usage: compare-sarif.sh <sarif1> <sarif2>
#
# Exit codes:
#   0 — fully equivalent (tuples + messages)
#   1 — tuple set differs  (rule_id / path / line / severity mismatch)
#   2 — tuples equivalent but message set differs
#
# AC7: message comparison is ORDER-INDEPENDENT (sort both sides before diff).

set -euo pipefail

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
    echo "Usage: $(basename "$0") <sarif1.json> <sarif2.json>" >&2
    exit 1
}

# Extract (rule_id, path, line, severity) tuples from a SARIF file.
# Outputs one JSON object per line, sorted and deduplicated.
extract_tuples() {
    local file="$1"
    jq -S -c '
      .runs[]?.results[]?
      | {
          rule_id:  (.ruleId // ""),
          path:     (.locations[0]?.physicalLocation?.artifactLocation?.uri // ""),
          line:     (.locations[0]?.physicalLocation?.region?.startLine // 0),
          severity: (.level // "warning")
        }
    ' "$file" | sort -u
}

# Extract message texts from a SARIF file.
# Outputs one string per line, sorted and deduplicated.
extract_messages() {
    local file="$1"
    jq -r '
      .runs[]?.results[]?
      | (.message.text // .message.markdown // "")
    ' "$file" | sort -u
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

[[ $# -eq 2 ]] || usage

SARIF1="$1"
SARIF2="$2"

[[ -f "$SARIF1" ]] || die "File not found: $SARIF1"
[[ -f "$SARIF2" ]] || die "File not found: $SARIF2"

command -v jq >/dev/null 2>&1 || die "jq is required but not found in PATH"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

TUPLES1="$TMP_DIR/tuples1.txt"
TUPLES2="$TMP_DIR/tuples2.txt"
MSGS1="$TMP_DIR/msgs1.txt"
MSGS2="$TMP_DIR/msgs2.txt"

extract_tuples "$SARIF1" > "$TUPLES1"
extract_tuples "$SARIF2" > "$TUPLES2"

# ---- tuple comparison ----
if ! diff -u "$TUPLES1" "$TUPLES2" > "$TMP_DIR/tuple_diff.txt" 2>&1; then
    echo "FAIL: tuple sets differ"
    echo "--- $SARIF1 (tuples)"
    echo "+++ $SARIF2 (tuples)"
    cat "$TMP_DIR/tuple_diff.txt"
    exit 1
fi

echo "PASS: tuple sets are equivalent"

# ---- message comparison (AC7: order-independent) ----
extract_messages "$SARIF1" > "$MSGS1"
extract_messages "$SARIF2" > "$MSGS2"

if ! diff -u "$MSGS1" "$MSGS2" > "$TMP_DIR/msg_diff.txt" 2>&1; then
    echo "WARN: tuples match but message sets differ"
    echo "--- $SARIF1 (messages)"
    echo "+++ $SARIF2 (messages)"
    cat "$TMP_DIR/msg_diff.txt"
    exit 2
fi

echo "PASS: message sets are equivalent"
echo "PASS: SARIF files are fully equivalent"
exit 0
