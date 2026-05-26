#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${SCANNER_JOERN_IMAGE:-ghcr.nju.edu.cn/joernio/joern:nightly}"
FIXTURE_DIR="$ROOT_DIR/backend/tests/fixtures/joern/libplist-cve-2017-6439"
OUTPUT_DIR=""
NO_PULL=0
KEEP_WORKDIR=0

usage() {
  cat <<'EOF'
Usage:
  scripts/rebuild-joern-runner-verify.sh [options]

Run the configured Joern container image against the committed libplist
CVE-2017-6439 fixture and verify Argus-owned output artifacts.

Options:
  --fixture DIR      fixture root with manifest.json and src/ (default: backend/tests/fixtures/joern/libplist-cve-2017-6439)
  --image NAME       Joern image to pull/run (default: SCANNER_JOERN_IMAGE or ghcr.nju.edu.cn/joernio/joern:nightly)
  --output-dir DIR   output directory for summary.json, graph-proof.json, findings.json, joern.log
                     (default: .omx/reports/joern-image-verify-<timestamp>)
  --no-pull          skip podman pull and use an already-present local image
  --keep-workdir     keep temporary wrapper/query workspace for inspection
  -h, --help         show this help

This script never downloads the fixture. It only reads committed fixture files.
EOF
}

log() {
  printf '[joern-verify] %s\n' "$*"
}

die() {
  printf '[joern-verify] error: %s\n' "$*" >&2
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

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fixture)
      FIXTURE_DIR="$(abs_path "${2:?missing --fixture value}")"
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
    --no-pull)
      NO_PULL=1
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

require_command podman
require_command python3

[ -d "$FIXTURE_DIR/src" ] || die "fixture src directory not found: $FIXTURE_DIR/src"
[ -f "$FIXTURE_DIR/manifest.json" ] || die "fixture manifest not found: $FIXTURE_DIR/manifest.json"

if [ -z "$OUTPUT_DIR" ]; then
  OUTPUT_DIR="$ROOT_DIR/.omx/reports/joern-image-verify-$(timestamp_utc)"
fi
mkdir -p "$OUTPUT_DIR"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/argus-joern-image-verify.XXXXXX")"
cleanup() {
  if [ "$KEEP_WORKDIR" -eq 0 ]; then
    rm -rf "$WORKDIR"
  else
    log "kept workdir: $WORKDIR"
  fi
}
trap cleanup EXIT

if [ "$NO_PULL" -eq 0 ]; then
  log "pulling image: $IMAGE"
  podman pull "$IMAGE"
else
  log "skipping image pull: $IMAGE"
fi

QUERY_SRC="$ROOT_DIR/backend/assets/scan_rule_assets/rules_joern/c/argus-joern-scan.sc"
[ -f "$QUERY_SRC" ] || die "Joern query asset not found: $QUERY_SRC"
mkdir -p "$WORKDIR/joern-queries/c"
cp "$QUERY_SRC" "$WORKDIR/joern-queries/c/argus-joern-scan.sc"
cat > "$WORKDIR/argus-joern-wrapper.sh" <<'WRAPPER'
#!/bin/sh
set -eu
SOURCE_DIR="${JOERN_SOURCE_DIR:-/scan/source}"
OUTPUT_DIR="${JOERN_OUTPUT_DIR:-/scan/output}"
QUERY_DIR="${JOERN_QUERY_DIR:-/scan/joern-queries}"
CPG_PATH="$OUTPUT_DIR/cpg.bin"
GRAPH_PROOF_PATH="$OUTPUT_DIR/graph-proof.json"
FINDINGS_PATH="$OUTPUT_DIR/findings.json"
SUMMARY_PATH="$OUTPUT_DIR/summary.json"
LOG_PATH="$OUTPUT_DIR/joern.log"
mkdir -p "$OUTPUT_DIR"
: > "$LOG_PATH"
printf 'Argus Joern live verification starting\n' >> "$LOG_PATH"
joern-parse "$SOURCE_DIR" --out "$CPG_PATH" >> "$LOG_PATH" 2>&1
joern --script "$QUERY_DIR/c/argus-joern-scan.sc" \
  --param cpgFile="$CPG_PATH" \
  --param sourceDir="$SOURCE_DIR" \
  --param graphProofOut="$GRAPH_PROOF_PATH" \
  --param findingsOut="$FINDINGS_PATH" \
  >> "$LOG_PATH" 2>&1
python3 - <<'PY' "$SUMMARY_PATH" "$GRAPH_PROOF_PATH" "$FINDINGS_PATH"
import json, sys
summary, graph, findings = sys.argv[1:]
def count_findings(path):
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    items = data.get('findings', []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise ValueError('findings.json field "findings" must be an array')
    return len(items)
with open(summary, 'w', encoding='utf-8') as fh:
    json.dump({
        'status': 'scan_completed',
        'engine': 'joern',
        'schema_version': 'argus.joern.v1',
        'scanner': 'joern',
        'cpg_path': 'output/cpg.bin',
        'graph_proof_path': 'output/graph-proof.json',
        'findings_path': 'output/findings.json',
        'finding_count': count_findings(findings),
    }, fh, sort_keys=True)
    fh.write('\n')
PY
WRAPPER
chmod +x "$WORKDIR/argus-joern-wrapper.sh"

log "running Joern fixture scan: $FIXTURE_DIR"
podman run --rm \
  --network none \
  -e JOERN_SOURCE_DIR=/scan/source \
  -e JOERN_OUTPUT_DIR=/scan/output \
  -e JOERN_QUERY_DIR=/scan/joern-queries \
  -v "$FIXTURE_DIR/src:/scan/source:ro" \
  -v "$WORKDIR:/scan/workspace:ro" \
  -v "$WORKDIR/joern-queries:/scan/joern-queries:ro" \
  -v "$OUTPUT_DIR:/scan/output:rw" \
  "$IMAGE" \
  /bin/sh /scan/workspace/argus-joern-wrapper.sh

python3 - "$FIXTURE_DIR/manifest.json" "$OUTPUT_DIR" <<'PY'
import json, pathlib, sys
manifest_path = pathlib.Path(sys.argv[1])
output_dir = pathlib.Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
summary = json.loads((output_dir / 'summary.json').read_text(encoding='utf-8'))
graph = json.loads((output_dir / 'graph-proof.json').read_text(encoding='utf-8'))
findings = json.loads((output_dir / 'findings.json').read_text(encoding='utf-8'))
expected = manifest['expected']
files = [str(item) for item in graph.get('files') or []]
functions = [str(item) for item in graph.get('functions') or []]
if not any(expected['graph_proof']['files_contains'] in item for item in files):
    raise SystemExit('graph proof missing expected fixture file')
if expected['graph_proof']['functions_contains'] not in functions:
    raise SystemExit('graph proof missing expected vulnerable function')
items = findings.get('findings') or []
match = None
for item in items:
    if expected['rule_id'] == item.get('rule_id') and expected['cve'][0] in (item.get('cve') or []) and expected['cwe'][0] in (item.get('cwe') or []):
        match = item
        break
if match is None:
    raise SystemExit('findings missing expected CVE/CWE rule hit')
if expected['function'] != match.get('function'):
    raise SystemExit('finding missing expected function')
print(f"status={summary.get('status')}")
print(f"findings={len(items)}")
print(f"graph={output_dir / 'graph-proof.json'}")
print(f"findings_path={output_dir / 'findings.json'}")
PY
