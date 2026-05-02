#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/.argus-intelligent-audit.env"
TEMPLATE_FILE="$ROOT_DIR/.argus-intelligent-audit.env.example"
SOURCE_TEMPLATE="$ROOT_DIR/docker/env/backend/env.example"
ENV_FILE="${ARGUS_INTELLIGENT_AUDIT_ENV:-$DEFAULT_ENV_FILE}"

usage() {
  cat <<USAGE
$SCRIPT_NAME - validate Argus LLM bootstrap env

Usage:
  scripts/$SCRIPT_NAME [--env-file <path>]

Required keys:
  SECRET_KEY
  LLM_PROVIDER
  LLM_API_KEY
  LLM_MODEL
  LLM_BASE_URL
  AGENT_ENABLED
  AGENT_MAX_ITERATIONS
  AGENT_TIMEOUT
USAGE
}

fail() {
  printf '[argus-llm-config] ERROR: %s\n' "$*" >&2
  printf '[argus-llm-config] 请重新配置 %s 后再运行 ./argus-bootstrap.sh。\n' "$ENV_FILE" >&2
  exit 1
}

log() {
  printf '[argus-llm-config] %s\n' "$*"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --env-file)
        [[ $# -ge 2 ]] || fail "--env-file requires a path"
        ENV_FILE="$2"
        shift 2
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

ensure_template() {
  if [[ -f "$TEMPLATE_FILE" ]]; then
    return 0
  fi
  if [[ -f "$SOURCE_TEMPLATE" ]]; then
    cp "$SOURCE_TEMPLATE" "$TEMPLATE_FILE"
    log "Created template: $TEMPLATE_FILE"
    return 0
  fi
  cat > "$TEMPLATE_FILE" <<'ENV'
SECRET_KEY=your-super-secret-key-change-this-in-production
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENV
  log "Created minimal template: $TEMPLATE_FILE"
}

read_env_value() {
  local key="$1"
  awk -v key="$key" '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    index($0, "=") == 0 { next }
    {
      split($0, parts, "=")
      k = parts[1]
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      if (k == key) {
        value = substr($0, index($0, "=") + 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        if ((substr(value, 1, 1) == "\"" && substr(value, length(value), 1) == "\"") ||
            (substr(value, 1, 1) == "'"'"'" && substr(value, length(value), 1) == "'"'"'")) {
          value = substr(value, 2, length(value) - 2)
        }
        found = value
      }
    }
    END {
      if (found != "") {
        print found
      }
    }
  ' "$ENV_FILE"
}

is_placeholder_value() {
  local value="$1"
  case "$value" in
    ""|\
    your-*|\
    *your-api-key*|\
    *your_proxy*|\
    *your-proxy*|\
    *change-this*|\
    *change_this*|\
    *CHANGE_ME*|\
    *REPLACE_ME*|\
    sk-your-api-key|\
    your-super-secret-key-change-this-in-production)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_key() {
  local key="$1"
  local value
  value="$(read_env_value "$key")"
  if [[ -z "$value" ]]; then
    fail "Required env key $key is missing or empty."
  fi
  printf '%s' "$value"
}

validate_provider() {
  local provider="$1"
  case "$provider" in
    openai_compatible|anthropic_compatible)
      return 0
      ;;
    *)
      fail "LLM_PROVIDER must be openai_compatible or anthropic_compatible."
      ;;
  esac
}

validate_boolean_true() {
  local key="$1"
  local value="$2"
  case "$value" in
    true|TRUE|1|yes|YES|on|ON)
      return 0
      ;;
    *)
      fail "$key must be enabled before bootstrap."
      ;;
  esac
}

validate_positive_int() {
  local key="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value <= 0 )); then
    fail "$key must be a positive integer."
  fi
}

main() {
  parse_args "$@"
  ensure_template
  [[ -f "$ENV_FILE" ]] || fail "LLM env file does not exist. A template is available at $TEMPLATE_FILE."

  local secret_key provider api_key model base_url agent_enabled max_iterations agent_timeout
  secret_key="$(require_key SECRET_KEY)"
  provider="$(require_key LLM_PROVIDER)"
  api_key="$(require_key LLM_API_KEY)"
  model="$(require_key LLM_MODEL)"
  base_url="$(require_key LLM_BASE_URL)"
  agent_enabled="$(require_key AGENT_ENABLED)"
  max_iterations="$(require_key AGENT_MAX_ITERATIONS)"
  agent_timeout="$(require_key AGENT_TIMEOUT)"

  validate_provider "$provider"
  validate_boolean_true AGENT_ENABLED "$agent_enabled"
  validate_positive_int AGENT_MAX_ITERATIONS "$max_iterations"
  validate_positive_int AGENT_TIMEOUT "$agent_timeout"

  for key_and_value in \
    "SECRET_KEY=$secret_key" \
    "LLM_API_KEY=$api_key" \
    "LLM_MODEL=$model" \
    "LLM_BASE_URL=$base_url"
  do
    local key="${key_and_value%%=*}"
    local value="${key_and_value#*=}"
    if is_placeholder_value "$value"; then
      fail "$key still contains a placeholder value."
    fi
  done

  log "LLM env config is valid: $ENV_FILE"
}

main "$@"
