#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
BACKEND_ENV_FILE="$ROOT_DIR/docker/env/backend/.env"
CONFIG_FILE="${ARGUS_INTELLIGENT_AUDIT_ENV:-$ROOT_DIR/.argus-intelligent-audit.env}"
CONFIG_TEMPLATE_FILE="${CONFIG_FILE}.example"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-argus}"
DRY_RUN=false
WAIT_EXIT=false
STUB_DOCKER="${ARGUS_STUB_DOCKER:-false}"
DOCKER_SYSTEM_PRUNE="${ARGUS_DOCKER_SYSTEM_PRUNE:-true}"
WAIT_TIMEOUT="${ARGUS_WAIT_TIMEOUT:-120}"
WAIT_INTERVAL="${ARGUS_WAIT_INTERVAL:-2}"
FRONTEND_PORT="${Argus_FRONTEND_PORT:-13000}"
CACHE_SCOPE="argus-agentflow-$(date +%s)"

REQUIRED_CONFIG_KEYS=(
  SECRET_KEY
  LLM_PROVIDER
  LLM_API_KEY
  LLM_MODEL
  LLM_BASE_URL
  AGENT_ENABLED
  AGENT_MAX_ITERATIONS
  AGENT_TIMEOUT
)

usage() {
  cat <<USAGE
$SCRIPT_NAME - Argus reset/rebuild/start helper

Usage:
  ./$SCRIPT_NAME [--dry-run] [--wait-exit] [--help]

Shell support:
  Run directly from bash, zsh, or another shell as ./$SCRIPT_NAME.
  The implementation uses this file's Bash shebang; running "zsh $SCRIPT_NAME" is not supported.

Configuration:
  ARGUS_INTELLIGENT_AUDIT_ENV  Path to dedicated config file.
                                Default: $ROOT_DIR/.argus-intelligent-audit.env
  Interactive TTY runs copy/use the example config, prompt for required LLM values,
  auto-generate SECRET_KEY, hide LLM_API_KEY input, then fully overwrite
  docker/env/backend/.env from the validated dedicated config.
  CI=true or non-TTY runs never prompt; missing or placeholder config fails before Docker cleanup.

Destructive Docker cleanup default:
  By default this script runs: docker system prune -af --volumes
  WARNING: this can delete unused Docker images, containers, networks, cache, and volumes
  from other projects on this host. Set ARGUS_DOCKER_SYSTEM_PRUNE=false to skip it.

Start modes:
  Default:     docker compose up --build        (foreground; does not auto-exit on readiness)
  --wait-exit: docker compose up -d --build, poll http://127.0.0.1:$FRONTEND_PORT, then exit

Ports:
  Argus_FRONTEND_PORT           Frontend host port. Default: 13000

Test / verification:
  --dry-run                     Preview commands and skip backend env mutation.
  ARGUS_STUB_DOCKER=true        Print Docker/curl/env commands instead of running them.
  ARGUS_TEST_INTERACTIVE=true   Test-only: allow scripted interactive config without a TTY.
  ARGUS_TEST_SECRET_KEY=value   Test-only: deterministic generated SECRET_KEY.
USAGE
}

log() {
  printf '[argus-reset] %s\n' "$*"
}

fail() {
  printf '[argus-reset] ERROR: %s\n' "$*" >&2
  exit 1
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

quote_cmd() {
  local quoted=()
  local arg
  for arg in "$@"; do
    printf -v arg '%q' "$arg"
    quoted+=("$arg")
  done
  printf '%s' "${quoted[*]}"
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

write_config_template() {
  local target="$1"
  mkdir -p "$(dirname "$target")"
  cat > "$target" <<'TEMPLATE'
# Argus intelligent-audit / AgentFlow backend environment
# This file is the baseline for argus-reset-rebuild-start.sh interactive setup.
# The generated .argus-intelligent-audit.env fully overwrites docker/env/backend/.env
# after validation.

# Security: generated automatically by argus-reset-rebuild-start.sh in interactive mode.
SECRET_KEY=REPLACE_ME_WITH_RANDOM_SECRET
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=11520

# LLM / intelligent-audit required configuration.
LLM_PROVIDER=openai
LLM_API_KEY=REPLACE_ME_WITH_REAL_API_KEY
LLM_MODEL=REPLACE_ME_WITH_MODEL
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT=150
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096

# Agent audit defaults.
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENABLE_PARALLEL_ANALYSIS=true
ENABLE_PARALLEL_VERIFICATION=true
ANALYSIS_MAX_WORKERS=5
VERIFICATION_MAX_WORKERS=3

# Optional provider-specific settings can be added below when needed.
# OPENAI_API_KEY=
# OPENAI_BASE_URL=https://api.openai.com/v1
# OLLAMA_BASE_URL=http://localhost:11434/v1
TEMPLATE
}

ensure_template_file() {
  if [[ ! -f "$CONFIG_TEMPLATE_FILE" ]]; then
    write_config_template "$CONFIG_TEMPLATE_FILE"
    log "Wrote config template: $CONFIG_TEMPLATE_FILE"
  else
    log "Config template already exists: $CONFIG_TEMPLATE_FILE"
  fi
}

trim_value() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

env_value_for_key() {
  local file="$1" key="$2"
  local line raw_key raw_value found=""
  [[ -f "$file" ]] || { printf '%s' "$found"; return 0; }
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#${line%%[![:space:]]*}}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    [[ "$line" == *=* ]] || continue
    raw_key="${line%%=*}"
    raw_key="$(trim_value "$raw_key")"
    [[ "$raw_key" != "$key" ]] && continue
    raw_value="${line#*=}"
    found="$(trim_value "$raw_value")"
  done < "$file"
  printf '%s' "$found"
}

config_value_for_key() {
  env_value_for_key "$CONFIG_FILE" "$1"
}

template_value_for_key() {
  env_value_for_key "$CONFIG_TEMPLATE_FILE" "$1"
}

is_secret_key_name() {
  case "$1" in
    *KEY*|*Key*|*key*|SECRET*|*SECRET*|*secret*|*TOKEN*|*token*|*PASSWORD*|*password*) return 0 ;;
    *) return 1 ;;
  esac
}

is_placeholder_value() {
  local value="$(trim_value "$1")"
  local lower="${value,,}"
  [[ -z "$value" ]] && return 0
  case "$lower" in
    todo|tbd|replace_me|changeme|change_me|placeholder|dummy|example) return 0 ;;
    your-*|*your-api-key*|*your_api_key*|*sk-your*|*replace-me*|*replace_me*|*change-this*|*change_this*|*changethis*|*todo*|*tbd*) return 0 ;;
    *) return 1 ;;
  esac
}

validate_config() {
  [[ -f "$CONFIG_FILE" ]] || fail "Dedicated config is missing: $CONFIG_FILE. No Docker cleanup was performed."

  local key value missing=0
  for key in "${REQUIRED_CONFIG_KEYS[@]}"; do
    value="$(config_value_for_key "$key")"
    if is_placeholder_value "$value"; then
      printf '[argus-reset] ERROR: required config key %s is missing or placeholder-valued\n' "$key" >&2
      missing=1
    else
      if is_secret_key_name "$key"; then
        log "Config key $key is configured (redacted)."
      else
        log "Config key $key is configured."
      fi
    fi
  done
  [[ "$missing" -eq 0 ]] || fail "Invalid dedicated config: $CONFIG_FILE. No Docker cleanup was performed."
}

generate_secret_key() {
  if [[ -n "${ARGUS_TEST_SECRET_KEY:-}" ]]; then
    printf '%s' "$ARGUS_TEST_SECRET_KEY"
    return 0
  fi
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return 0
  fi
  if command -v od >/dev/null 2>&1 && [[ -r /dev/urandom ]]; then
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
    return 0
  fi
  fail "Unable to generate SECRET_KEY: openssl or /dev/urandom+od is required"
}

interactive_config_allowed() {
  if is_truthy "${ARGUS_TEST_INTERACTIVE:-false}"; then
    return 0
  fi
  if is_truthy "${CI:-false}"; then
    return 1
  fi
  [[ -t 0 && -t 1 ]]
}

prompt_default_for_key() {
  local key="$1" value
  value="$(config_value_for_key "$key")"
  if [[ -n "$value" ]] && ! is_placeholder_value "$value"; then
    printf '%s' "$value"
    return 0
  fi
  value="$(template_value_for_key "$key")"
  if [[ -n "$value" ]] && ! is_placeholder_value "$value"; then
    printf '%s' "$value"
  fi
}

prompt_value() {
  local key="$1" default_value="$2" value=""
  if [[ -n "$default_value" ]] && ! is_placeholder_value "$default_value"; then
    printf '[argus-reset] %s [%s]: ' "$key" "$default_value" >&2
  else
    printf '[argus-reset] %s: ' "$key" >&2
  fi
  IFS= read -r value || value=""
  value="$(trim_value "$value")"
  if [[ -z "$value" && -n "$default_value" ]] && ! is_placeholder_value "$default_value"; then
    value="$default_value"
  fi
  if is_placeholder_value "$value"; then
    fail "Required config key $key is missing or placeholder-valued. No Docker cleanup was performed."
  fi
  printf '%s' "$value"
}

prompt_secret_value() {
  local key="$1" existing_value="$2" value=""
  if [[ -n "$existing_value" ]] && ! is_placeholder_value "$existing_value"; then
    printf '[argus-reset] %s is already configured (redacted). Press Enter to keep it, or type a replacement: ' "$key" >&2
  else
    printf '[argus-reset] %s (hidden): ' "$key" >&2
  fi
  IFS= read -r -s value || value=""
  printf '\n' >&2
  value="$(trim_value "$value")"
  if [[ -z "$value" && -n "$existing_value" ]] && ! is_placeholder_value "$existing_value"; then
    value="$existing_value"
  fi
  if is_placeholder_value "$value"; then
    fail "Required secret config key $key is missing or placeholder-valued. No Docker cleanup was performed."
  fi
  printf '%s' "$value"
}

write_generated_config() {
  local tmp_file="$1"
  shift
  declare -A replacements=()
  local pair key value line
  for pair in "$@"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    replacements["$key"]="$value"
  done

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([[:space:]]*)([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[2]}"
      if [[ -v "replacements[$key]" ]]; then
        printf '%s%s=%s\n' "${BASH_REMATCH[1]}" "$key" "${replacements[$key]}"
        continue
      fi
    fi
    printf '%s\n' "$line"
  done < "$CONFIG_TEMPLATE_FILE" > "$tmp_file"
}

run_interactive_config() {
  ensure_template_file
  log "Interactive TTY configuration enabled; required values will be written to $CONFIG_FILE."
  log "SECRET_KEY will be generated automatically; LLM_API_KEY input is hidden."

  local secret_key llm_provider llm_api_key llm_model llm_base_url
  secret_key="$(generate_secret_key)"
  llm_provider="$(prompt_value LLM_PROVIDER "$(prompt_default_for_key LLM_PROVIDER)")"
  llm_api_key="$(prompt_secret_value LLM_API_KEY "$(config_value_for_key LLM_API_KEY || true)")"
  llm_model="$(prompt_value LLM_MODEL "$(prompt_default_for_key LLM_MODEL)")"
  llm_base_url="$(prompt_value LLM_BASE_URL "$(prompt_default_for_key LLM_BASE_URL)")"

  local tmp_file
  tmp_file="$(mktemp "${CONFIG_FILE}.tmp.XXXXXX")"
  chmod 600 "$tmp_file" 2>/dev/null || true
  write_generated_config "$tmp_file" \
    "SECRET_KEY=$secret_key" \
    "LLM_PROVIDER=$llm_provider" \
    "LLM_API_KEY=$llm_api_key" \
    "LLM_MODEL=$llm_model" \
    "LLM_BASE_URL=$llm_base_url"
  mv "$tmp_file" "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE" 2>/dev/null || true
  log "Wrote dedicated config: $CONFIG_FILE"
}

prepare_config() {
  if interactive_config_allowed; then
    run_interactive_config
  else
    if [[ ! -f "$CONFIG_FILE" ]]; then
      ensure_template_file
      fail "Dedicated config is missing: $CONFIG_FILE. Fill it or run interactively from a TTY; no Docker cleanup was performed."
    fi
  fi
  validate_config
}

materialize_backend_env() {
  mkdir -p "$(dirname "$BACKEND_ENV_FILE")"
  if "$DRY_RUN"; then
    printf '[dry-run] cp %s %s\n' "$(printf '%q' "$CONFIG_FILE")" "$(printf '%q' "$BACKEND_ENV_FILE")"
  else
    cp "$CONFIG_FILE" "$BACKEND_ENV_FILE"
    chmod 600 "$BACKEND_ENV_FILE" 2>/dev/null || true
    log "Fully overwrote docker/env/backend/.env from dedicated config."
  fi
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
  if "$WAIT_EXIT"; then
    command -v curl >/dev/null 2>&1 || fail "curl not found"
  fi
}

compose_down() {
  log "Stopping/removing this Argus Compose project before global Docker prune."
  run_compose down --remove-orphans
}

prune_docker_system() {
  if is_falsey "$DOCKER_SYSTEM_PRUNE"; then
    log "Skipping docker system prune -af --volumes because ARGUS_DOCKER_SYSTEM_PRUNE=false."
    return 0
  fi
  log "WARNING: running docker system prune -af --volumes; this can delete unused Docker resources and volumes from other projects."
  run_cmd docker system prune -af --volumes
}

compose_up_foreground() {
  log "Starting Argus in foreground with fresh AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE"
  log "Default foreground mode does not auto-exit after readiness; use --wait-exit for detached readiness polling."
  run_cmd env "AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE" docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up --build
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

compose_up_wait_exit() {
  log "Starting Argus detached with fresh AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE"
  run_cmd env "AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE" docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build
  wait_for_frontend
}

start_stack() {
  if "$WAIT_EXIT"; then
    compose_up_wait_exit
    log "Complete. Frontend: http://127.0.0.1:$FRONTEND_PORT"
  else
    compose_up_foreground
    log "Compose foreground command exited. Frontend port: $FRONTEND_PORT"
  fi
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
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  log "Argus reset/rebuild/start beginning. Project: $PROJECT_NAME"
  require_real_tools
  prepare_config
  materialize_backend_env
  compose_down
  prune_docker_system
  start_stack
}

main "$@"
