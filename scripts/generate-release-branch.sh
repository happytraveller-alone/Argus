#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR"
OUTPUT_DIR=""
VALIDATE="false"
ALLOWLIST_PATH="$ROOT_DIR/scripts/release-allowlist.txt"
TEMPLATE_DIR="$ROOT_DIR/scripts/release-templates"

usage() {
  cat <<'USAGE'
Usage: generate-release-branch.sh --output <dir> [--source <dir>] [--validate]

Generate a latest-only slim release tree from the checked-out repository.

Options:
  --output <dir>   Required. Destination directory for the generated release tree.
  --source <dir>   Override the source repository root. Defaults to the current checkout.
  --validate       Validate the generated tree after copying.
  -h, --help       Show this help text.
USAGE
}

log() {
  echo "[release-tree] $*"
}

die() {
  echo "[release-tree] $*" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

copy_allowlisted_entry() {
  local raw_line="$1"
  local src_rel dest_rel src_abs dest_abs

  if [[ "$raw_line" == *"=>"* ]]; then
    src_rel="$(trim "${raw_line%%=>*}")"
    dest_rel="$(trim "${raw_line#*=>}")"
  else
    src_rel="$(trim "$raw_line")"
    dest_rel="$src_rel"
  fi

  [[ -n "$src_rel" ]] || return 0

  src_abs="$SOURCE_DIR/$src_rel"
  dest_abs="$OUTPUT_DIR/$dest_rel"

  [[ -e "$src_abs" ]] || die "allowlisted path does not exist: $src_rel"

  mkdir -p "$(dirname "$dest_abs")"
  cp -R "$src_abs" "$dest_abs"
}

validate_release_tree() {
  local required_paths forbidden_paths rel_path

  required_paths=(
    "README.md"
    "README_EN.md"
    "docker-compose.yml"
    "docker-compose.hybrid.yml"
    "scripts/README-COMPOSE.md"
    "docker/backend.Dockerfile"
    "docker/frontend.Dockerfile"
    "docker/nexus-web.Dockerfile"
    "docker/env/backend/env.example"
    "backend/alembic.ini"
    "backend/pyproject.toml"
    "backend/requirements-heavy.txt"
    "backend/uv.lock"
    "backend/app/main.py"
    "backend/app/services/runner_preflight.py"
    "frontend/package.json"
    "frontend/pnpm-lock.yaml"
    "frontend/vite.config.ts"
    "frontend/src/app/main.tsx"
    "frontend/yasa-engine-overrides/src/config.ts"
    "nexus-web/dist/index.html"
    "nexus-web/nginx.conf"
    "nexus-itemDetail/dist/index.html"
    "nexus-itemDetail/nginx.conf"
  )
  forbidden_paths=(
    ".github"
    "deploy"
    "docs"
    "docker-compose.full.yml"
    "docker-compose.self-contained.yml"
    "backend/tests"
    "frontend/tests"
    "scripts/compose-up-local-build.sh"
    "scripts/compose-up-with-fallback.sh"
  )

  for rel_path in "${required_paths[@]}"; do
    [[ -e "$OUTPUT_DIR/$rel_path" ]] || die "missing required release path: $rel_path"
  done

  for rel_path in "${forbidden_paths[@]}"; do
    [[ ! -e "$OUTPUT_DIR/$rel_path" ]] || die "forbidden path present in release tree: $rel_path"
  done

  for rel_path in nexus-web nexus-itemDetail; do
    [[ -d "$OUTPUT_DIR/$rel_path/dist" ]] || die "missing runtime bundle dist directory: $rel_path/dist"
    [[ -f "$OUTPUT_DIR/$rel_path/nginx.conf" ]] || die "missing runtime bundle nginx config: $rel_path/nginx.conf"
    [[ "$(find "$OUTPUT_DIR/$rel_path" -mindepth 1 -maxdepth 1 | wc -l)" -eq 2 ]] || \
      die "runtime bundle contains unexpected top-level files: $rel_path"
    [[ ! -e "$OUTPUT_DIR/$rel_path/src" ]] || die "runtime bundle leaked source directory: $rel_path/src"
    [[ ! -e "$OUTPUT_DIR/$rel_path/node_modules" ]] || die "runtime bundle leaked node_modules: $rel_path/node_modules"
    [[ ! -e "$OUTPUT_DIR/$rel_path/tests" ]] || die "runtime bundle leaked tests directory: $rel_path/tests"
    [[ ! -e "$OUTPUT_DIR/$rel_path/package.json" ]] || die "runtime bundle leaked package.json: $rel_path/package.json"
  done

  if find "$OUTPUT_DIR" \
    \( -name '.github' -o -name 'tests' -o -name '__pycache__' -o -name '.pytest_cache' -o -name 'node_modules' \) \
    -print -quit | grep -q .; then
    die "release tree still contains test or dev residue"
  fi
}

clean_generated_tree() {
  find "$OUTPUT_DIR" \
    \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' \) \
    -exec rm -rf {} +
  find "$OUTPUT_DIR" \
    \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) \
    -delete
}

prune_nexus_runtime_bundle() {
  local bundle_root="$1"

  [[ -d "$bundle_root" ]] || return 0

  find "$bundle_root" -mindepth 1 -maxdepth 1 ! -name dist ! -name nginx.conf -exec rm -rf {} +

  [[ -d "$bundle_root/dist" ]] || die "nexus runtime bundle missing dist directory: ${bundle_root#$OUTPUT_DIR/}"
  [[ -f "$bundle_root/nginx.conf" ]] || die "nexus runtime bundle missing nginx.conf: ${bundle_root#$OUTPUT_DIR/}"
}

prune_release_tree() {
  rm -rf \
    "$OUTPUT_DIR/.github" \
    "$OUTPUT_DIR/deploy" \
    "$OUTPUT_DIR/docs" \
    "$OUTPUT_DIR/backend/tests" \
    "$OUTPUT_DIR/backend/docs" \
    "$OUTPUT_DIR/backend/.venv" \
    "$OUTPUT_DIR/backend/.pytest_cache" \
    "$OUTPUT_DIR/backend/.mypy_cache" \
    "$OUTPUT_DIR/backend/uploads" \
    "$OUTPUT_DIR/backend/log" \
    "$OUTPUT_DIR/backend/data" \
    "$OUTPUT_DIR/frontend/tests" \
    "$OUTPUT_DIR/frontend/docs" \
    "$OUTPUT_DIR/frontend/dist" \
    "$OUTPUT_DIR/frontend/node_modules"

  rm -f \
    "$OUTPUT_DIR/docker-compose.full.yml" \
    "$OUTPUT_DIR/docker-compose.self-contained.yml" \
    "$OUTPUT_DIR/docker-compose.release.yml" \
    "$OUTPUT_DIR/docker-compose.release-cython.yml" \
    "$OUTPUT_DIR/docker-compose.frontend-only.yml" \
    "$OUTPUT_DIR/docker-compose.podman.yml" \
    "$OUTPUT_DIR/backend/.env" \
    "$OUTPUT_DIR/backend/README.md" \
    "$OUTPUT_DIR/backend/SANDBOX_RUNNER_MIGRATION.md" \
    "$OUTPUT_DIR/backend/get-pip.py"

  prune_nexus_runtime_bundle "$OUTPUT_DIR/nexus-web"
  prune_nexus_runtime_bundle "$OUTPUT_DIR/nexus-itemDetail"

  rm -rf "$OUTPUT_DIR/scripts"
}

overlay_release_templates() {
  mkdir -p \
    "$OUTPUT_DIR/scripts" \
    "$OUTPUT_DIR/docker" \
    "$OUTPUT_DIR/backend/app/services"

  cp "$TEMPLATE_DIR/README.md" "$OUTPUT_DIR/README.md"
  cp "$TEMPLATE_DIR/README_EN.md" "$OUTPUT_DIR/README_EN.md"
  cp "$TEMPLATE_DIR/README-COMPOSE.md" "$OUTPUT_DIR/scripts/README-COMPOSE.md"
  cp "$TEMPLATE_DIR/docker-compose.release-slim.yml" "$OUTPUT_DIR/docker-compose.yml"
  cp "$TEMPLATE_DIR/docker-compose.hybrid.release-slim.yml" "$OUTPUT_DIR/docker-compose.hybrid.yml"
  cp "$TEMPLATE_DIR/backend.Dockerfile" "$OUTPUT_DIR/docker/backend.Dockerfile"
  cp "$TEMPLATE_DIR/runner_preflight.py" "$OUTPUT_DIR/backend/app/services/runner_preflight.py"
}

sanitize_release_tree() {
  python3 - "$OUTPUT_DIR" <<'PY'
from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path


root = Path(sys.argv[1])

LICENSE_PATTERNS = ("copyright", "license", "spdx")
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def preserve_header_lines(lines: list[str]) -> tuple[list[str], int]:
    kept: list[str] = []
    index = 0
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#!"):
            kept.append(line)
            continue
        if "coding" in stripped and stripped.startswith("#"):
            kept.append(line)
            continue
        if stripped.startswith("#") and any(token in stripped.lower() for token in LICENSE_PATTERNS):
            kept.append(line)
            continue
        if stripped == "":
            if kept:
                kept.append(line)
            continue
        return kept, index
    return kept, len(lines)


class StripDocstrings(ast.NodeTransformer):
    def _strip_body(self, body):
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
            if isinstance(body[0].value.value, str):
                body = body[1:]
        return body

    def visit_Module(self, node):
        node.body = self._strip_body(node.body)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        node.body = self._strip_body(node.body)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node):
        node.body = self._strip_body(node.body)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node):
        node.body = self._strip_body(node.body)
        self.generic_visit(node)
        return node


def sanitize_python(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    header, body_start = preserve_header_lines(lines)
    body = "".join(lines[body_start:])

    try:
        tree = ast.parse(body)
        tree = StripDocstrings().visit(tree)
        ast.fix_missing_locations(tree)
        sanitized = ast.unparse(tree)
        if sanitized and not sanitized.endswith("\n"):
            sanitized += "\n"
    except Exception:
        tokens: list[tokenize.TokenInfo] = []
        for token in tokenize.generate_tokens(io.StringIO(body).readline):
            if token.type == tokenize.COMMENT:
                continue
            tokens.append(token)
        sanitized = tokenize.untokenize(tokens)
        if sanitized and not sanitized.endswith("\n"):
            sanitized += "\n"

    path.write_text("".join(header) + sanitized, encoding="utf-8")


def sanitize_js_like(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    sanitized: list[str] = []
    in_block = False
    keep_block = False

    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if in_block:
            if keep_block:
                sanitized.append(line)
            if "*/" in stripped:
                in_block = False
                keep_block = False
            continue

        if stripped.startswith("/*"):
            in_block = True
            keep_block = any(token in lowered for token in LICENSE_PATTERNS)
            if keep_block:
                sanitized.append(line)
            if "*/" in stripped:
                in_block = False
                keep_block = False
            continue

        if stripped.startswith("//") and not any(token in lowered for token in LICENSE_PATTERNS):
            continue

        sanitized.append(line)

    path.write_text("\n".join(sanitized).rstrip() + "\n", encoding="utf-8")


for base in (root / "backend" / "app", root / "frontend"):
    if not base.exists():
        continue
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".py":
            sanitize_python(path)
        elif path.suffix in JS_EXTENSIONS:
            sanitize_js_like(path)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      [[ $# -ge 2 ]] || die "--output requires a value"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --source)
      [[ $# -ge 2 ]] || die "--source requires a value"
      SOURCE_DIR="$2"
      shift 2
      ;;
    --validate)
      VALIDATE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ -n "$OUTPUT_DIR" ]] || die "--output is required"
[[ -f "$ALLOWLIST_PATH" ]] || die "allowlist not found: $ALLOWLIST_PATH"

SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
OUTPUT_DIR="$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)"

case "$OUTPUT_DIR" in
  "$SOURCE_DIR"|"$SOURCE_DIR"/*)
    die "output directory must be outside the source tree"
    ;;
esac

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

while IFS= read -r line || [[ -n "$line" ]]; do
  line="$(trim "$line")"
  [[ -n "$line" ]] || continue
  [[ "${line:0:1}" == "#" ]] && continue
  copy_allowlisted_entry "$line"
done < "$ALLOWLIST_PATH"

prune_release_tree
overlay_release_templates
sanitize_release_tree
clean_generated_tree

if [[ "$VALIDATE" == "true" ]]; then
  validate_release_tree
  if command -v docker >/dev/null 2>&1; then
    (cd "$OUTPUT_DIR" && docker compose -f docker-compose.yml config >/dev/null)
    (cd "$OUTPUT_DIR" && docker compose -f docker-compose.yml -f docker-compose.hybrid.yml config >/dev/null)
  fi
fi

log "release tree generated at $OUTPUT_DIR"
