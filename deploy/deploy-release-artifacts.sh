#!/usr/bin/env bash

set -euo pipefail

ARTIFACT_DIR=""
TARGET_DIR=""
VERSION=""
SKIP_VERIFY="false"
START_STACK="true"
DOCKER_BIN="${DOCKER_BIN:-docker}"

log() {
  echo "[deploy-release] $*"
}

die() {
  echo "[deploy-release] $*" >&2
  exit 1
}

ensure_backend_env() {
  local env_dir="${TARGET_DIR}/backend"
  local env_file="${env_dir}/.env"

  if [[ -f "$env_file" ]]; then
    log ".env already exists"
    return
  fi

  mkdir -p "$env_dir"

  for tpl in ".env.example" ".env.template" ".env.sample"; do
    if [[ -f "${env_dir}/${tpl}" ]]; then
      cp "${env_dir}/${tpl}" "$env_file"
      log "created .env from ${tpl}"
      return
    fi
  done

  : > "$env_file"
  log "created empty .env (no template found)"
}

extract_frontend_bundle() {
  local pkg_path="$1"
  local bundle_dir="${TARGET_DIR}/deploy/runtime/frontend"

  rm -rf "$bundle_dir"
  mkdir -p "$bundle_dir"

  tar -xzf "$pkg_path" -C "$bundle_dir"

  [[ -f "${bundle_dir}/site/index.html" ]] || die "frontend bundle missing site/index.html"
  [[ -f "${bundle_dir}/nginx/default.conf" ]] || die "frontend bundle missing nginx/default.conf"
}

find_latest_artifact() {
  local pattern="$1"
  local latest

  latest="$(find "$ARTIFACT_DIR" -maxdepth 1 -type f -iname "$pattern" | LC_ALL=C sort | tail -n 1)"
  [[ -n "$latest" ]] || die "artifact not found for pattern: ${pattern}"

  printf '%s\n' "$latest"
}

resolve_artifact() {
  local kind="$1"
  local tag="$2"
  local preferred="${ARTIFACT_DIR}/vulhunter-${kind}-${tag}.tar.gz"

  if [[ -f "$preferred" ]]; then
    printf '%s\n' "$preferred"
    return
  fi

  find_latest_artifact "*-${kind}-${tag}.tar.gz"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifacts)
      ARTIFACT_DIR="$2"
      shift 2
      ;;
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    --skip-verify)
      SKIP_VERIFY="true"
      shift
      ;;
    --no-up)
      START_STACK="false"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

[[ -n "$ARTIFACT_DIR" ]] || die "--artifacts is required"
[[ -n "$TARGET_DIR" ]] || die "--target is required"

ARTIFACT_DIR="$(cd "$ARTIFACT_DIR" && pwd)"
mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

if [[ -z "$VERSION" ]]; then
  SOURCE_FILE="$(find_latest_artifact '*-source-v*.tar.gz')"
  VERSION="$(basename "$SOURCE_FILE" | sed -E 's/.*-source-v(.*)\.tar\.gz/\1/')"
fi

TAG_PREFIX="v${VERSION}"
SOURCE_PKG="$(resolve_artifact source "$TAG_PREFIX")"
DOCKER_PKG="$(resolve_artifact docker "$TAG_PREFIX")"
FRONTEND_PKG="$(resolve_artifact frontend "$TAG_PREFIX")"

log "version: ${VERSION}"

if [[ "$SKIP_VERIFY" != "true" ]]; then
  (cd "$ARTIFACT_DIR" && sha256sum -c checksums.txt)
fi

log "extract source"
tar -xzf "$SOURCE_PKG" -C "$TARGET_DIR"

log "extract docker layout"
tar -xzf "$DOCKER_PKG" -C "$TARGET_DIR"

log "extract frontend bundle"
extract_frontend_bundle "$FRONTEND_PKG"

ensure_backend_env

if [[ "$START_STACK" == "true" ]]; then
  "$DOCKER_BIN" compose \
    -f "${TARGET_DIR}/docker-compose.yml" \
    -f "${TARGET_DIR}/docker-compose.full.yml" \
    -f "${TARGET_DIR}/deploy/compose/docker-compose.release-static-frontend.yml" \
    up -d --build
fi

log "done"
