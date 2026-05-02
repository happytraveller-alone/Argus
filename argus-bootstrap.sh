#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
LLM_CONFIG_VALIDATOR="$ROOT_DIR/scripts/validate-llm-config.sh"
ARGUS_ENV_EXAMPLE="$ROOT_DIR/env.example"
ARGUS_ENV_FILE="${ARGUS_ENV_FILE:-$ROOT_DIR/.env}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-argus}"
DRY_RUN=false
WAIT_EXIT=false
RUN_MODE=default
SUPPORTED_RUN_MODES="default keep-cache aggressive"
STUB_DOCKER="${ARGUS_STUB_DOCKER:-false}"
DOCKER_SYSTEM_PRUNE="${ARGUS_DOCKER_SYSTEM_PRUNE:-true}"
WAIT_TIMEOUT="${ARGUS_WAIT_TIMEOUT:-120}"
WAIT_INTERVAL="${ARGUS_WAIT_INTERVAL:-2}"
FRONTEND_PORT="${Argus_FRONTEND_PORT:-13000}"
BACKEND_PORT="${Argus_BACKEND_PORT:-18000}"
BACKEND_HEALTH_URL="${ARGUS_BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/health}"
BACKEND_IMPORT_URL="${ARGUS_BACKEND_IMPORT_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/system-config/import-env}"
ARGUS_RESET_IMPORT_TOKEN=""

print_banner() {
  cat <<'BANNER'
  ___
 / _ |  ARGUS Bootstrap
/ __ |  Environment + LLM Runtime
/_/ |_|  Developer: happytraveller

为保护作者仓库开发成果/专利，未经作者授权不得商用；如需商用请联系作者。
作者/开发者: happytraveller
商业联系: 18630897985 | happytraveller@163.com
BANNER
}

usage() {
  print_banner
  cat <<USAGE
$SCRIPT_NAME - Argus bootstrap helper

Usage:
  ./$SCRIPT_NAME [--dry-run] [--wait-exit] [--help] -- <mode>
  ./$SCRIPT_NAME
  ./$SCRIPT_NAME -- default
  ./$SCRIPT_NAME -- keep-cache
  ./$SCRIPT_NAME -- aggressive
  ./$SCRIPT_NAME --wait-exit -- default

Shell support:
  Compatible with both bash and zsh. Run as ./$SCRIPT_NAME or via
  bash $SCRIPT_NAME / zsh $SCRIPT_NAME.

Environment:
  Root env template: env.example
  Runtime env file:  .env
  First run without .env copies env.example to .env, prints the required
  follow-up command, and exits before Docker cleanup/startup. Fill .env, or run
  scripts/validate-llm-config.sh --env-file ./.env to confirm the LLM config,
  then run ./$SCRIPT_NAME again.

Run modes:
  default      Safe default. Preserve data volumes and Docker image/build cache.
               No mode and "-- default" are equivalent.
  keep-cache   Remove this Compose project's managed volumes with
               docker compose down --volumes --remove-orphans, including runtime
               and dependency volumes declared by docker-compose.yml, while preserving
               Docker image/build cache.
  aggressive   Explicit destructive cleanup. Remove Compose-managed volumes and run
               docker system prune -af --volumes unless ARGUS_DOCKER_SYSTEM_PRUNE=false.
               This is the only mode allowed to perform global Docker prune.

Docker cleanup precedence:
  default and keep-cache never run global Docker prune, even when
  ARGUS_DOCKER_SYSTEM_PRUNE=true.
  ARGUS_DOCKER_SYSTEM_PRUNE=false disables only aggressive-mode global Docker prune.

Start modes:
  Default:     docker compose up -d --build, poll backend, import LLM env, then docker compose logs -f
               Ctrl-C/SIGTERM stops the Compose stack before exiting.
  --wait-exit: docker compose up -d --build, poll backend, import LLM env, poll http://127.0.0.1:$FRONTEND_PORT, then exit

Ports:
  Argus_FRONTEND_PORT           Frontend host port. Default: 13000

Test / verification:
  --dry-run                     Preview commands and skip Docker/curl execution.
  ARGUS_STUB_DOCKER=true        Print Docker/curl/env commands instead of running them.
  scripts/validate-llm-config.sh --env-file <path>
                                Validate the root env file without starting Docker.
USAGE
}

log() {
  printf '[argus-bootstrap] %s\n' "$*"
}

fail() {
  printf '[argus-bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

quote_cmd() {
  local quoted=()
  local arg
  for arg in "$@"; do
    printf -v arg '%q' "$arg"
    quoted+=("$arg")
  done
  redact_arg_for_log "${quoted[*]}"
}

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|y|Y|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

is_falsey() {
  case "${1:-}" in
    0|false|FALSE|no|NO|n|N|off|OFF) return 0 ;;
    *) return 1 ;;
  esac
}

redact_arg_for_log() {
  local arg="$1"
  if [[ -n "${ARGUS_RESET_IMPORT_TOKEN:-}" ]]; then
    arg="${arg//${ARGUS_RESET_IMPORT_TOKEN}/<redacted-import-token>}"
  fi
  printf '%s' "$arg"
}

run_cmd() {
  if "$DRY_RUN"; then
    printf '[dry-run] %s\n' "$(quote_cmd "$@")"
    return 0
  fi
  if is_truthy "$STUB_DOCKER" && [[ "${1:-}" =~ ^(docker|curl|env)$ ]]; then
    printf '[stub] %s\n' "$(quote_cmd "$@")"
    return 0
  fi
  "$@"
}

run_compose() {
  local cmd=(docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" "$@")
  run_cmd "${cmd[@]}"
}

validate_llm_config() {
  [[ -x "$LLM_CONFIG_VALIDATOR" ]] || fail "LLM config validator is missing or not executable: $LLM_CONFIG_VALIDATOR"
  ensure_root_env_file
  "$LLM_CONFIG_VALIDATOR" --env-file "$ARGUS_ENV_FILE"
}

ensure_root_env_file() {
  if [[ -f "$ARGUS_ENV_FILE" ]]; then
    return 0
  fi
  [[ -f "$ARGUS_ENV_EXAMPLE" ]] || fail "Root env template is missing: $ARGUS_ENV_EXAMPLE"
  cp "$ARGUS_ENV_EXAMPLE" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  log "Created .env from env.example: $ARGUS_ENV_FILE"
  cat >&2 <<MESSAGE
[argus-bootstrap] 请填写 .env 后再次运行 ./argus-bootstrap.sh。
[argus-bootstrap] 也可以先运行 ./scripts/validate-llm-config.sh --env-file ./.env 确认配置无误后再运行脚本。
MESSAGE
  exit 1
}

generate_import_token() {
  if [[ -n "${ARGUS_TEST_IMPORT_TOKEN:-}" ]]; then
    ARGUS_RESET_IMPORT_TOKEN="$ARGUS_TEST_IMPORT_TOKEN"
  elif command -v openssl >/dev/null 2>&1; then
    ARGUS_RESET_IMPORT_TOKEN="$(openssl rand -hex 32)"
  elif command -v od >/dev/null 2>&1 && [[ -r /dev/urandom ]]; then
    ARGUS_RESET_IMPORT_TOKEN="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  else
    fail "Unable to generate ARGUS_RESET_IMPORT_TOKEN: openssl or /dev/urandom+od is required"
  fi
  [[ -n "$ARGUS_RESET_IMPORT_TOKEN" ]] || fail "Generated ARGUS_RESET_IMPORT_TOKEN is empty"
  log "Generated per-run ARGUS_RESET_IMPORT_TOKEN (redacted)."
}

require_real_tools() {
  [[ -f "$COMPOSE_FILE" ]] || fail "docker-compose.yml not found at repo root: $COMPOSE_FILE"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub mode: skipping Docker daemon/tool preflight."
    return 0
  fi
  command -v docker >/dev/null 2>&1 || fail "docker CLI not found"
  docker compose version >/dev/null || fail "docker compose plugin is not available"
  docker info >/dev/null || fail "Docker daemon is not reachable"
  command -v curl >/dev/null 2>&1 || fail "curl not found"
}

compose_down() {
  local volume_mode="${1:-preserve-volumes}"
  log "Stopping/removing this Argus Compose project before mode-specific cleanup."
  if [[ "$volume_mode" == "delete-volumes" ]]; then
    run_compose down --volumes --remove-orphans
  else
    run_compose down --remove-orphans
  fi
}

prune_docker_system() {
  if is_falsey "$DOCKER_SYSTEM_PRUNE"; then
    log "Skipping global Docker prune because ARGUS_DOCKER_SYSTEM_PRUNE=false."
    return 0
  fi
  log "WARNING: running docker system prune -af --volumes; this can delete unused Docker resources and volumes from other projects."
  run_cmd docker system prune -af --volumes
}

cleanup_for_run_mode() {
  case "$RUN_MODE" in
    default)
      log "Default mode: preserving data volumes and Docker image/build cache; global Docker prune skipped."
      compose_down preserve-volumes
      ;;
    keep-cache)
      log "keep-cache mode: removing this Compose project's managed volumes while preserving Docker image/build cache."
      log "Managed volumes include application, runtime, and dependency volumes declared by docker-compose.yml."
      compose_down delete-volumes
      log "Global Docker prune skipped for cache-preserving mode."
      ;;
    aggressive)
      log "WARNING: aggressive mode enabled; Compose-managed volumes and global Docker cache may be removed."
      compose_down delete-volumes
      prune_docker_system
      ;;
    *)
      fail "Unsupported run mode reached cleanup dispatcher: $RUN_MODE"
      ;;
  esac
}

compose_up_detached() {
  log "Starting Argus detached"
  run_cmd env \
    "ARGUS_ENV_FILE=$ARGUS_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build
}

wait_for_backend() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Stub/dry-run: checking backend readiness once at $BACKEND_HEALTH_URL."
    run_cmd curl -fsS "$BACKEND_HEALTH_URL"
    return 0
  fi

  local start now elapsed
  start="$(date +%s)"
  log "Waiting up to ${WAIT_TIMEOUT}s for backend readiness: $BACKEND_HEALTH_URL"
  while true; do
    if curl -fsS "$BACKEND_HEALTH_URL" >/dev/null; then
      log "Backend is reachable: $BACKEND_HEALTH_URL"
      return 0
    fi
    now="$(date +%s)"
    elapsed=$((now - start))
    if (( elapsed >= WAIT_TIMEOUT )); then
      fail "Backend did not become reachable within ${WAIT_TIMEOUT}s: $BACKEND_HEALTH_URL"
    fi
    sleep "$WAIT_INTERVAL"
  done
}

import_backend_env() {
  log "Importing dedicated LLM config into backend system-config via protected reset endpoint."
  local response
  if [[ -n "${ARGUS_TEST_IMPORT_RESPONSE:-}" ]]; then
    response="$ARGUS_TEST_IMPORT_RESPONSE"
    printf '%s
' "$response"
  elif "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_cmd curl -fsS -X POST -H "X-Argus-Reset-Import-Token: $ARGUS_RESET_IMPORT_TOKEN" "$BACKEND_IMPORT_URL"
    return 0
  elif response="$(curl -fsS -X POST -H "X-Argus-Reset-Import-Token: $ARGUS_RESET_IMPORT_TOKEN" "$BACKEND_IMPORT_URL")"; then
    printf '%s
' "$response"
  else
    fail "backend LLM env import/test failed. 请重新配置 $ARGUS_ENV_FILE 后再运行 bootstrap。"
  fi

  if printf '%s' "$response" | grep -Eq '"success"[[:space:]]*:[[:space:]]*false'; then
    fail "backend LLM env import/test returned failure. 请重新配置 $ARGUS_ENV_FILE 后再运行 bootstrap。"
  fi
  log "Backend LLM env import/test succeeded; response was sanitized by backend."
}

follow_foreground_logs() {
  log "Following Compose logs in foreground. Ctrl-C/SIGTERM stops the Compose stack before exiting."
  _argus_stop_on_signal() {
    log "Signal received; stopping Argus Compose project before exit."
    run_compose down --remove-orphans
    exit 130
  }
  trap _argus_stop_on_signal INT TERM
  local logs_rc=0
  if run_compose logs -f; then
    logs_rc=0
  else
    logs_rc=$?
  fi
  trap - INT TERM
  return "$logs_rc"
}

wait_for_frontend() {
  local url="http://127.0.0.1:${FRONTEND_PORT}"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Stub/dry-run wait-exit: checking frontend readiness once at $url."
    run_cmd curl -fsS "$url"
    return 0
  fi

  local start now elapsed
  start="$(date +%s)"
  log "Waiting up to ${WAIT_TIMEOUT}s for frontend readiness: $url"
  while true; do
    if curl -fsS "$url" >/dev/null; then
      log "Frontend is reachable: $url"
      return 0
    fi
    now="$(date +%s)"
    elapsed=$((now - start))
    if (( elapsed >= WAIT_TIMEOUT )); then
      fail "Frontend did not become reachable within ${WAIT_TIMEOUT}s: $url"
    fi
    sleep "$WAIT_INTERVAL"
  done
}

start_stack() {
  compose_up_detached
  wait_for_backend
  import_backend_env
  if "$WAIT_EXIT"; then
    wait_for_frontend
    log "Complete. Frontend: http://127.0.0.1:$FRONTEND_PORT"
  else
    follow_foreground_logs
    log "Compose foreground log-follow exited. Frontend port: $FRONTEND_PORT"
  fi
}

supported_run_modes() {
  printf '%s' "$SUPPORTED_RUN_MODES"
}

is_supported_run_mode() {
  case "$1" in
    default|keep-cache|aggressive) return 0 ;;
    *) return 1 ;;
  esac
}

set_run_mode() {
  local mode="$1"
  if ! is_supported_run_mode "$mode"; then
    fail "Unknown run mode: $mode. Supported run modes: $(supported_run_modes)"
  fi
  RUN_MODE="$mode"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --wait-exit|--detach-wait)
        WAIT_EXIT=true
        shift
        ;;
      --)
        shift
        if [[ $# -eq 0 ]]; then
          RUN_MODE=default
          return 0
        fi
        if [[ $# -gt 1 ]]; then
          fail "Expected at most one run mode after --. Supported run modes: $(supported_run_modes)"
        fi
        set_run_mode "$1"
        shift
        return 0
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  print_banner
  log "Argus bootstrap beginning. Project: $PROJECT_NAME"
  log "Run mode: $RUN_MODE"
  validate_llm_config
  require_real_tools
  generate_import_token
  cleanup_for_run_mode
  start_stack
}

main "$@"
