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

ARTIFACT_DIR="$(cd "$ARTIFACT_DIR" && pwd)"
mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

if [[ -z "$VERSION" ]]; then
  SOURCE_FILE="$(ls "$ARTIFACT_DIR"/deepaudit-source-v*.tar.gz | sort | tail -n1)"
  VERSION="$(basename "$SOURCE_FILE" | sed -E 's/deepaudit-source-v(.*)\.tar\.gz/\1/')"
fi

TAG_PREFIX="v${VERSION}"

SOURCE_PKG="${ARTIFACT_DIR}/deepaudit-source-${TAG_PREFIX}.tar.gz"
DOCKER_PKG="${ARTIFACT_DIR}/deepaudit-docker-${TAG_PREFIX}.tar.gz"

log "version: ${VERSION}"

if [[ "$SKIP_VERIFY" != "true" ]]; then
  (cd "$ARTIFACT_DIR" && sha256sum -c checksums.txt)
fi

log "extract source"
tar -xzf "$SOURCE_PKG" -C "$TARGET_DIR"

log "extract docker layout"
tar -xzf "$DOCKER_PKG" -C "$TARGET_DIR"

ensure_backend_env

if [[ "$START_STACK" == "true" ]]; then
  docker compose \
    -f "${TARGET_DIR}/docker-compose.yml" \
    -f "${TARGET_DIR}/docker-compose.build.yml" \
    up -d --build
fi

log "done"