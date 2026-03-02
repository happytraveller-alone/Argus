#!/usr/bin/env bash
set -euo pipefail

log_info() {
  echo "[INFO] $*"
}

log_warn() {
  echo "[WARN] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return
  fi
  log_error "docker compose (or docker-compose) not found"
  exit 127
}

require_positive_int() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1 ]; then
    log_error "${name} must be a positive integer, got: ${value}"
    exit 2
  fi
}

run_with_retries() {
  local phase="$1"
  local retry_count="$2"
  local dockerhub_mirror="$3"
  local ghcr_registry="$4"
  local uv_image="$5"
  local sandbox_base_image="$6"
  local sandbox_image="$7"

  local attempt=1
  local rc=1
  while [ "$attempt" -le "$retry_count" ]; do
    log_info "Phase=${phase} attempt ${attempt}/${retry_count}"
    log_info "DOCKERHUB_LIBRARY_MIRROR=${dockerhub_mirror}"
    log_info "GHCR_REGISTRY=${ghcr_registry}"
    log_info "UV_IMAGE=${uv_image}"
    log_info "SANDBOX_BASE_IMAGE=${sandbox_base_image}"
    log_info "SANDBOX_IMAGE=${sandbox_image}"

    set +e
    DOCKERHUB_LIBRARY_MIRROR="${dockerhub_mirror}" \
      GHCR_REGISTRY="${ghcr_registry}" \
      UV_IMAGE="${uv_image}" \
      SANDBOX_BASE_IMAGE="${sandbox_base_image}" \
      SANDBOX_IMAGE="${sandbox_image}" \
      "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}"
    rc=$?
    set -e
    if [ "${rc}" -eq 0 ]; then
      log_info "Phase=${phase} succeeded on attempt ${attempt}"
      return 0
    fi

    log_warn "Phase=${phase} failed on attempt ${attempt}, exit_code=${rc}"
    if [ "$attempt" -lt "$retry_count" ]; then
      log_info "Retrying in ${RETRY_INTERVAL_SECONDS}s..."
      sleep "${RETRY_INTERVAL_SECONDS}"
    fi
    attempt=$((attempt + 1))
  done

  return "${rc}"
}

detect_compose_cmd

if [ "$#" -eq 0 ]; then
  COMPOSE_ARGS=(up -d --build)
else
  COMPOSE_ARGS=("$@")
fi

CN_RETRY_COUNT="${CN_RETRY_COUNT:-3}"
OFFICIAL_RETRY_COUNT="${OFFICIAL_RETRY_COUNT:-3}"
RETRY_INTERVAL_SECONDS="${RETRY_INTERVAL_SECONDS:-5}"

require_positive_int "CN_RETRY_COUNT" "${CN_RETRY_COUNT}"
require_positive_int "OFFICIAL_RETRY_COUNT" "${OFFICIAL_RETRY_COUNT}"
require_positive_int "RETRY_INTERVAL_SECONDS" "${RETRY_INTERVAL_SECONDS}"

CN_DOCKERHUB_LIBRARY_MIRROR="${CN_DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}"
OFFICIAL_DOCKERHUB_LIBRARY_MIRROR="${OFFICIAL_DOCKERHUB_LIBRARY_MIRROR:-docker.io/library}"

CN_GHCR_REGISTRY="${CN_GHCR_REGISTRY:-ghcr.nju.edu.cn}"
OFFICIAL_GHCR_REGISTRY="${OFFICIAL_GHCR_REGISTRY:-ghcr.io}"

CN_UV_IMAGE="${CN_UV_IMAGE:-${CN_GHCR_REGISTRY}/astral-sh/uv:latest}"
OFFICIAL_UV_IMAGE="${OFFICIAL_UV_IMAGE:-${OFFICIAL_GHCR_REGISTRY}/astral-sh/uv:latest}"

CN_SANDBOX_BASE_IMAGE="${CN_SANDBOX_BASE_IMAGE:-docker.m.daocloud.io/python:3.11-bullseye}"
OFFICIAL_SANDBOX_BASE_IMAGE="${OFFICIAL_SANDBOX_BASE_IMAGE:-python:3.11-bullseye}"

DEEPAUDIT_IMAGE_TAG="${DEEPAUDIT_IMAGE_TAG:-latest}"
CN_SANDBOX_IMAGE="${CN_SANDBOX_IMAGE:-${CN_GHCR_REGISTRY}/lintsinghua/deepaudit-sandbox:${DEEPAUDIT_IMAGE_TAG}}"
OFFICIAL_SANDBOX_IMAGE="${OFFICIAL_SANDBOX_IMAGE:-${OFFICIAL_GHCR_REGISTRY}/lintsinghua/deepaudit-sandbox:${DEEPAUDIT_IMAGE_TAG}}"

log_info "Compose command: ${COMPOSE_BIN[*]}"
log_info "Compose args: ${COMPOSE_ARGS[*]}"

if run_with_retries \
  "CN" \
  "${CN_RETRY_COUNT}" \
  "${CN_DOCKERHUB_LIBRARY_MIRROR}" \
  "${CN_GHCR_REGISTRY}" \
  "${CN_UV_IMAGE}" \
  "${CN_SANDBOX_BASE_IMAGE}" \
  "${CN_SANDBOX_IMAGE}"; then
  exit 0
fi

log_warn "CN phase exhausted (${CN_RETRY_COUNT} attempts). Switching to OFFICIAL phase."

if run_with_retries \
  "OFFICIAL" \
  "${OFFICIAL_RETRY_COUNT}" \
  "${OFFICIAL_DOCKERHUB_LIBRARY_MIRROR}" \
  "${OFFICIAL_GHCR_REGISTRY}" \
  "${OFFICIAL_UV_IMAGE}" \
  "${OFFICIAL_SANDBOX_BASE_IMAGE}" \
  "${OFFICIAL_SANDBOX_IMAGE}"; then
  exit 0
fi

log_error "OFFICIAL phase exhausted (${OFFICIAL_RETRY_COUNT} attempts). Exiting with failure."
exit 1
