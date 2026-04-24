#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${ROOT_DIR}"
ERROR_TEXT="Hermes source snapshot missing: initialize submodules recursively or include Hermes source in the release tree"

usage() {
  cat <<'USAGE'
Usage: hermes-agent-submodule-check.sh [--source-root <dir>] [--print-upstream-sha|--print-recursive-status|--print-source-digest]
USAGE
}

die_missing() {
  echo "${ERROR_TEXT}" >&2
  exit 1
}

normalize_recursive_status() {
  git -C "${SOURCE_ROOT}" submodule status --recursive | python -c '
import sys
parts = []
for raw in sys.stdin:
    line = raw.rstrip("\n")
    if not line:
        continue
    status = line[0]
    if status in "+-U":
        raise SystemExit(1)
    sha = line[1:41].strip()
    path = line[42:].split(" ", 1)[0].strip()
    parts.append(f"{path}={sha}")
print(";".join(parts))
'
}

compute_source_digest() {
  python - <<'PY'
from pathlib import Path
import hashlib
root = Path("third_party/hermes-agent")
files = []
for p in sorted(x for x in root.rglob("*") if x.is_file() and ".git" not in x.parts):
    rel = p.as_posix()
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    files.append(f"{rel}\0{h}\n")
print("sha256:" + hashlib.sha256("".join(files).encode()).hexdigest())
PY
}

ensure_snapshot() {
  local repo_root="${SOURCE_ROOT}"
  local hermes_dir="${repo_root}/third_party/hermes-agent"
  local tinker_dir="${hermes_dir}/tinker-atropos"

  [[ -f "${hermes_dir}/Dockerfile" ]] || die_missing
  [[ -f "${hermes_dir}/docker/entrypoint.sh" ]] || die_missing
  [[ -f "${hermes_dir}/.env.example" ]] || die_missing
  [[ -f "${hermes_dir}/cli-config.yaml.example" ]] || die_missing
  [[ -f "${hermes_dir}/docker/SOUL.md" ]] || die_missing
  [[ -f "${hermes_dir}/tools/skills_sync.py" ]] || die_missing
  [[ -d "${tinker_dir}" ]] || die_missing

  if [[ -d "${repo_root}/.git" || -f "${repo_root}/.git" ]]; then
    normalize_recursive_status >/dev/null || die_missing
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root)
      SOURCE_ROOT="$(cd "$2" && pwd)"
      shift 2
      ;;
    --print-upstream-sha)
      ensure_snapshot
      git -C "${SOURCE_ROOT}/third_party/hermes-agent" rev-parse HEAD
      exit 0
      ;;
    --print-recursive-status)
      ensure_snapshot
      normalize_recursive_status
      exit 0
      ;;
    --print-source-digest)
      ensure_snapshot
      (
        cd "${SOURCE_ROOT}"
        compute_source_digest
      )
      exit 0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
done

ensure_snapshot
