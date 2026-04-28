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
STUB_DOCKER="${ARGUS_STUB_DOCKER:-false}"
RESET_VOLUMES="${ARGUS_RESET_VOLUMES:-preserve}"
BUILDX_PRUNE="${ARGUS_BUILDX_PRUNE:-false}"
BACKEND_PORT="${Argus_BACKEND_PORT:-18000}"
FRONTEND_PORT="${Argus_FRONTEND_PORT:-13000}"
CACHE_SCOPE="argus-agentflow-$(date +%s)"

BUILT_SERVICES=(agentflow-runner opengrep-runner backend frontend)
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
$SCRIPT_NAME - Argus-only reset/rebuild/start helper

Usage:
  bash $SCRIPT_NAME [--dry-run] [--help]

Required config:
  ARGUS_INTELLIGENT_AUDIT_ENV  Path to dedicated config file.
                                Default: $ROOT_DIR/.argus-intelligent-audit.env

Safe defaults:
  ARGUS_RESET_VOLUMES=preserve  Preserve data volumes by default.
  ARGUS_RESET_VOLUMES=delete    Delete Argus Compose volumes only after exact-name preview.
  ARGUS_BUILDX_PRUNE=false      Skip global Buildx cache prune by default.
  ARGUS_BUILDX_PRUNE=true       Run: docker buildx prune -a -f

Ports (compose-correct case-sensitive names):
  Argus_BACKEND_PORT            Backend host port. Default: 18000
  Argus_FRONTEND_PORT           Frontend host port. Default: 13000

Behavior:
  - Validates the dedicated intelligent-audit config before any Docker cleanup.
  - Missing config writes a template/example and exits before cleanup.
  - Fully overwrites docker/env/backend/.env from the validated dedicated config.
  - Stops/removes only this Argus Compose project.
  - Removes only locally built Argus service images: ${BUILT_SERVICES[*]}.
  - Does not remove third-party/base images such as Postgres, Redis, or Adminer.
  - Starts with: docker compose up -d --build --wait

Test-only:
  ARGUS_STUB_DOCKER=true        Execute file operations but print Docker/curl commands instead of running them.
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

compose_cmd_base() {
  printf '%s\n' docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME"
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
# Copy this template to .argus-intelligent-audit.env and replace every placeholder.
# This file is authoritative for argus-reset-rebuild-start.sh and fully overwrites
# docker/env/backend/.env after validation.

# Security: required because backend .env is fully overwritten.
# Generate with: openssl rand -hex 32
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

config_value_for_key() {
  local key="$1"
  local line raw_key raw_value found=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#${line%%[![:space:]]*}}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    raw_key="${line%%=*}"
    raw_key="$(trim_value "$raw_key")"
    [[ "$raw_key" != "$key" ]] && continue
    raw_value="${line#*=}"
    found="$(trim_value "$raw_value")"
  done < "$CONFIG_FILE"
  printf '%s' "$found"
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
  [[ -f "$CONFIG_FILE" ]] || {
    ensure_template_file
    fail "Dedicated config is missing: $CONFIG_FILE. Fill the template and rerun; no Docker cleanup was performed."
  }

  local key value missing=0
  for key in "${REQUIRED_CONFIG_KEYS[@]}"; do
    value="$(config_value_for_key "$key")"
    if is_placeholder_value "$value"; then
      printf '[argus-reset] ERROR: required config key %s is missing or placeholder-valued\n' "$key" >&2
      missing=1
    else
      if [[ "$key" == *KEY* || "$key" == SECRET* || "$key" == *TOKEN* ]]; then
        log "Config key $key is configured (redacted)."
      else
        log "Config key $key is configured."
      fi
    fi
  done
  [[ "$missing" -eq 0 ]] || fail "Invalid dedicated config: $CONFIG_FILE. No Docker cleanup was performed."
}

materialize_backend_env() {
  mkdir -p "$(dirname "$BACKEND_ENV_FILE")"
  if "$DRY_RUN"; then
    printf '[dry-run] cp %s %s\n' "$(printf '%q' "$CONFIG_FILE")" "$(printf '%q' "$BACKEND_ENV_FILE")"
  else
    cp "$CONFIG_FILE" "$BACKEND_ENV_FILE"
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
  command -v curl >/dev/null 2>&1 || fail "curl not found"
  docker compose version >/dev/null || fail "docker compose plugin is not available"
  docker info >/dev/null || fail "Docker daemon is not reachable"
  docker buildx version >/dev/null || fail "docker buildx is not available"
}

preview_volume_deletion() {
  local agentflow_volume="${AGENTFLOW_RUNNER_WORK_VOLUME:-Argus_agentflow_runner_work}"
  local scan_volume="${SCAN_WORKSPACE_VOLUME:-Argus_scan_workspace}"
  local volumes=(
    "$agentflow_volume"
    "${PROJECT_NAME}_postgres_data"
    "${PROJECT_NAME}_backend_uploads"
    "${PROJECT_NAME}_backend_runtime_data"
    "$scan_volume"
    "${PROJECT_NAME}_redis_data"
    "${PROJECT_NAME}_frontend_node_modules"
    "${PROJECT_NAME}_frontend_pnpm_store"
  )
  log "ARGUS_RESET_VOLUMES=delete: the following Argus volume names may be deleted:"
  printf '  - %s\n' "${volumes[@]}"
  log "Warning: $agentflow_volume and $scan_volume are explicit Compose volume names and may be shared across checkouts unless overridden."
}

compose_down() {
  case "$RESET_VOLUMES" in
    preserve|keep|false|0|no|NO)
      log "Stopping/removing Argus Compose containers and networks; preserving volumes."
      run_compose down --remove-orphans
      ;;
    delete)
      preview_volume_deletion
      run_compose down --remove-orphans --volumes
      ;;
    *)
      fail "Unsupported ARGUS_RESET_VOLUMES=$RESET_VOLUMES (use preserve or delete)"
      ;;
  esac
}

stub_image_ref_for_service() {
  local service="$1"
  local override_var=""
  case "$service" in
    agentflow-runner) override_var="ARGUS_STUB_IMAGE_REF_AGENTFLOW_RUNNER" ;;
    opengrep-runner) override_var="ARGUS_STUB_IMAGE_REF_OPENGREP_RUNNER" ;;
    backend) override_var="ARGUS_STUB_IMAGE_REF_BACKEND" ;;
    frontend) override_var="ARGUS_STUB_IMAGE_REF_FRONTEND" ;;
    *) return 1 ;;
  esac

  if [[ -n "${!override_var:-}" ]]; then
    printf '%s' "${!override_var}"
    return 0
  fi

  case "$service" in
    agentflow-runner) printf 'argus/agentflow-runner:stub' ;;
    opengrep-runner) printf 'Argus/opengrep-runner-local:stub' ;;
    backend) printf '%s-backend:stub' "$PROJECT_NAME" ;;
    frontend) printf '%s-frontend:stub' "$PROJECT_NAME" ;;
    *) return 1 ;;
  esac
}

image_ref_for_service() {
  local service="$1"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_compose images "$service" >/dev/null
    stub_image_ref_for_service "$service"
    return 0
  fi

  docker compose \
    --project-directory "$ROOT_DIR" \
    --file "$COMPOSE_FILE" \
    --project-name "$PROJECT_NAME" \
    images "$service" --format '{{.Repository}}:{{.Tag}}' | tail -n 1
}

is_allowed_image_ref() {
  local service="$1"
  local image_ref="$2"
  case "$service:$image_ref" in
    agentflow-runner:argus/agentflow-runner:*) return 0 ;;
    opengrep-runner:Argus/opengrep-runner-local:*) return 0 ;;
    backend:"${PROJECT_NAME}"-backend:*) return 0 ;;
    frontend:"${PROJECT_NAME}"-frontend:*) return 0 ;;
    *) return 1 ;;
  esac
}

remove_built_images() {
  local service image_ref
  log "Removing allowlisted locally built Argus images only: ${BUILT_SERVICES[*]}"
  for service in "${BUILT_SERVICES[@]}"; do
    image_ref="$(image_ref_for_service "$service")"
    if [[ -z "$image_ref" || "$image_ref" == '<none>:<none>' ]]; then
      log "No local image found for service $service; skipping."
      continue
    fi
    if ! is_allowed_image_ref "$service" "$image_ref"; then
      fail "Refusing to remove non-allowlisted image for $service: $image_ref"
    fi
    run_cmd docker image rm "$image_ref"
  done
}

maybe_prune_buildx() {
  if is_truthy "$BUILDX_PRUNE"; then
    log "ARGUS_BUILDX_PRUNE=true: running global Buildx prune after Argus cleanup."
    run_cmd docker buildx prune -a -f
  else
    log "Skipping docker buildx prune -a -f (set ARGUS_BUILDX_PRUNE=true to enable)."
  fi
}

compose_up() {
  log "Starting Argus with fresh AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE"
  run_cmd env "AGENTFLOW_BUILD_CACHE_SCOPE=$CACHE_SCOPE" docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build --wait
}

verify_reachability() {
  log "Checking Compose service status."
  run_compose ps
  log "Checking backend reachability on port $BACKEND_PORT."
  run_cmd curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health"
  log "Checking frontend reachability on port $FRONTEND_PORT."
  run_cmd curl -fsS "http://127.0.0.1:${FRONTEND_PORT}"
}

main() {
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
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done

  log "Argus reset/rebuild/start beginning. Project: $PROJECT_NAME"
  require_real_tools
  validate_config
  materialize_backend_env
  compose_down
  remove_built_images
  maybe_prune_buildx
  compose_up
  verify_reachability
  log "Complete. Backend: http://127.0.0.1:$BACKEND_PORT ; Frontend: http://127.0.0.1:$FRONTEND_PORT"
}

main "$@"
