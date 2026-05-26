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

Config forms:
  Numbered (canonical, supports multiple configs):
    LLM_1_PROVIDER, LLM_1_API_KEY, LLM_1_MODEL, LLM_1_BASE_URL
    LLM_2_PROVIDER, LLM_2_API_KEY, LLM_2_MODEL, LLM_2_BASE_URL
    ...

  Legacy bare keys (auto-promoted to LLM_1_* when no numbered config present):
    LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL

Precedence: numbered > bare (bare auto-promoted only when no numbered config present).
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

# Read a specific key from ENV_FILE. Strips comments, blank lines, and surrounding quotes.
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
            (substr(value, 1, 1) == "'" && substr(value, length(value), 1) == "'")) {
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

# Require a key to be present and non-empty. Prints the value on success.
require_key() {
  local key="$1"
  local label="$2"
  local value
  value="$(read_env_value "$key")"
  if [[ -z "$value" ]]; then
    fail "${label}Required env key $key is missing or empty."
  fi
  printf '%s' "$value"
}

validate_provider() {
  local provider="$1"
  local label="$2"
  case "$provider" in
    openai_compatible|anthropic_compatible)
      return 0
      ;;
    *)
      fail "${label}LLM_PROVIDER must be openai_compatible or anthropic_compatible."
      ;;
  esac
}

# Find all numeric indices used in LLM_N_PROVIDER keys. Prints sorted unique indices, one per line.
find_numbered_indices() {
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      if (match($0, /^[[:space:]]*LLM_([0-9]+)_PROVIDER[[:space:]]*=/)) {
        n = substr($0, RSTART, RLENGTH)
        gsub(/^[[:space:]]*LLM_/, "", n)
        gsub(/_PROVIDER[[:space:]]*=.*/, "", n)
        print n
      }
    }
  ' "$ENV_FILE" | sort -un
}

# Validate a single config block. label is the human-readable prefix like "[LLM 1] " or "[LLM 1 (legacy bare)] ".
# key_prefix is the env key prefix like "LLM_1_" or "LLM_" (for bare legacy).
validate_block() {
  local label="$1"
  local key_prefix="$2"

  local provider api_key model base_url
  provider="$(require_key "${key_prefix}PROVIDER" "$label")"
  validate_provider "$provider" "$label"

  api_key="$(require_key "${key_prefix}API_KEY" "$label")"
  model="$(require_key "${key_prefix}MODEL" "$label")"
  base_url="$(require_key "${key_prefix}BASE_URL" "$label")"

  for key_and_value in \
    "${key_prefix}API_KEY=$api_key" \
    "${key_prefix}MODEL=$model" \
    "${key_prefix}BASE_URL=$base_url"
  do
    local key="${key_and_value%%=*}"
    local value="${key_and_value#*=}"
    if is_placeholder_value "$value"; then
      fail "${label}${key} still contains a placeholder value."
    fi
  done
}

# Detect stacked bare LLM_PROVIDER lines (excludes LLM_N_PROVIDER).
check_stacked_bare_dup() {
  local count
  count="$(grep -Ec '^[[:space:]]*LLM_PROVIDER[[:space:]]*=' "$ENV_FILE" || true)"
  if [[ "$count" -gt 1 ]]; then
    printf '[argus-llm-config] Warning: detected %s stacked bare LLM_PROVIDER lines. Only the last is parsed by env-file injection. Convert to LLM_1_*/LLM_2_*/... to use all of them.\n' "$count" >&2
  fi
}

main() {
  parse_args "$@"
  ensure_template
  [[ -f "$ENV_FILE" ]] || fail "LLM env file does not exist. A template is available at $TEMPLATE_FILE."

  # Collect numbered indices (LLM_1_PROVIDER, LLM_2_PROVIDER, ...)
  local indices_raw
  indices_raw="$(find_numbered_indices)"

  local -a indices=()
  while IFS= read -r idx; do
    [[ -n "$idx" ]] && indices+=("$idx")
  done <<< "$indices_raw"

  if [[ "${#indices[@]}" -gt 0 ]]; then
    # Numbered configs present — validate each block
    for n in "${indices[@]}"; do
      validate_block "[LLM ${n}] " "LLM_${n}_"
    done
  else
    # No numbered configs — check for bare legacy keys
    local bare_provider
    bare_provider="$(read_env_value "LLM_PROVIDER")"
    if [[ -n "$bare_provider" ]]; then
      # Auto-promote bare keys as virtual LLM_1_* (no file rewrite)
      validate_block "[LLM 1 (legacy bare)] " "LLM_"
    else
      fail "LLM_PROVIDER 未配置 / not configured. Please set LLM_1_PROVIDER (numbered) or LLM_PROVIDER (legacy bare) in $ENV_FILE."
    fi
  fi

  # Dup-detection: warn on stacked bare LLM_PROVIDER lines (non-fatal)
  check_stacked_bare_dup

  log "LLM env config is valid: $ENV_FILE"
}

main "$@"
