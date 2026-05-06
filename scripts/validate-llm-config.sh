#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/.argus-llm.env"
TEMPLATE_FILE="$ROOT_DIR/llm.env.example"
ENV_FILE="${ARGUS_LLM_ENV_FILE:-$DEFAULT_ENV_FILE}"

usage() {
  cat <<USAGE
$SCRIPT_NAME - validate Argus LLM bootstrap env

Usage:
  scripts/$SCRIPT_NAME [--env-file <path>]

Required keys:
  LLM_PROVIDER
  LLM_API_KEY
  LLM_MODEL
  LLM_BASE_URL
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
  fail "LLM env template does not exist: $TEMPLATE_FILE"
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

main() {
  parse_args "$@"
  ensure_template
  [[ -f "$ENV_FILE" ]] || fail "LLM env file does not exist. A template is available at $TEMPLATE_FILE."

  local provider api_key model base_url
  provider="$(require_key LLM_PROVIDER)"
  api_key="$(require_key LLM_API_KEY)"
  model="$(require_key LLM_MODEL)"
  base_url="$(require_key LLM_BASE_URL)"

  validate_provider "$provider"

  for key_and_value in \
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
