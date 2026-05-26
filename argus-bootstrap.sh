#!/usr/bin/env bash
set -Eeuo pipefail

# Strip host proxy env vars early: container builds cannot reach host-only
# proxies (e.g. 127.0.0.1:7897) and would fail with connection refused.
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY 2>/dev/null || true

export SUPPRESS_BOLTDB_WARNING=1

SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
LLM_CONFIG_VALIDATOR="$ROOT_DIR/scripts/validate-llm-config.sh"
ARGUS_ENV_FILE="${ARGUS_ENV_FILE:-$ROOT_DIR/.env}"
ARGUS_LLM_ENV_EXAMPLE="$ROOT_DIR/llm.env.example"
ARGUS_LLM_ENV_FILE="${ARGUS_LLM_ENV_FILE:-$ROOT_DIR/.argus-llm.env}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-argus}"
DRY_RUN=false
WAIT_EXIT=false
RUN_MODE=default
CONTAINER_RUNTIME="${ARGUS_CONTAINER_RUNTIME:-podman}"
SUPPORTED_RUN_MODES="default keep-cache aggressive"
SUPPORTED_CONTAINER_RUNTIMES="docker podman"
STUB_DOCKER="${ARGUS_STUB_DOCKER:-false}"
DOCKER_SYSTEM_PRUNE="${ARGUS_DOCKER_SYSTEM_PRUNE:-true}"
WAIT_TIMEOUT="${ARGUS_WAIT_TIMEOUT:-120}"
WAIT_INTERVAL="${ARGUS_WAIT_INTERVAL:-2}"
FRONTEND_PORT="${Argus_FRONTEND_PORT:-13000}"
BACKEND_PORT="${Argus_BACKEND_PORT:-18000}"
ARGUS_PORT_AUTO_FREE="${ARGUS_PORT_AUTO_FREE:-true}"
ARGUS_PORT_FREE_GRACE="${ARGUS_PORT_FREE_GRACE:-2}"
CUBE_PORT_AUTO_FREE="${CUBE_PORT_AUTO_FREE:-true}"
CUBE_DISABLE_WEBUI="${CUBE_DISABLE_WEBUI:-true}"
BACKEND_HEALTH_URL="${ARGUS_BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/health}"
BACKEND_IMPORT_URL="${ARGUS_BACKEND_IMPORT_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/system-config/import-env}"
ARGUS_RESET_IMPORT_TOKEN=""
PODMAN_PROJECT_LABEL="io.argus.project=argus"
PODMAN_RUNTIME_LABEL="io.argus.runtime=podman"
PODMAN_DB_CONTAINER="argus-db"
PODMAN_REDIS_CONTAINER="argus-redis"
PODMAN_BACKEND_CONTAINER="argus-backend"
PODMAN_FRONTEND_CONTAINER="argus-frontend"
PODMAN_BACKEND_IMAGE="${ARGUS_PODMAN_BACKEND_IMAGE:-argus/backend-local:latest}"
PODMAN_FRONTEND_IMAGE="${ARGUS_PODMAN_FRONTEND_IMAGE:-argus/frontend-local:latest}"
PODMAN_POSTGRES_IMAGE="${ARGUS_PODMAN_POSTGRES_IMAGE:-${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}/postgres:18.3-alpine3.23}"
PODMAN_REDIS_IMAGE="${ARGUS_PODMAN_REDIS_IMAGE:-${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}/redis:8.6.2-alpine3.23}"
PODMAN_TARGETARCH="${ARGUS_PODMAN_TARGETARCH:-amd64}"
PODMAN_AUDIT_SANDBOX_IMAGE="${ARGUS_PODMAN_AUDIT_SANDBOX_IMAGE:-argus/audit-sandbox:latest}"
DEFAULT_JOERN_IMAGE="ghcr.nju.edu.cn/joernio/joern:nightly"
PODMAN_CONTAINER_SOCKET="/run/podman/podman.sock"
PODMAN_SEQUENTIAL_BUILD="${ARGUS_SEQUENTIAL_BUILD:-false}"
PODMAN_BUILD_LOG_DIR="${TMPDIR:-/tmp}"

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
  ./$SCRIPT_NAME [--runtime docker|podman] [--dry-run] [--wait-exit] [--sequential-build] [--help] -- <mode>
  ./$SCRIPT_NAME
  ./$SCRIPT_NAME -- default
  ./$SCRIPT_NAME -- keep-cache
  ./$SCRIPT_NAME -- aggressive
  ./$SCRIPT_NAME --runtime podman --wait-exit -- default

Shell support:
  Compatible with both bash and zsh. Run as ./$SCRIPT_NAME or via
  bash $SCRIPT_NAME / zsh $SCRIPT_NAME.

Environment:
  LLM env template:  llm.env.example
  LLM env file:      .argus-llm.env
  Runtime env file:  .env
  First run creates .argus-llm.env from llm.env.example and creates .env for
  generated SECRET_KEY / advanced overrides, then exits before Docker cleanup.
  Fill only .argus-llm.env for normal use, or run
  scripts/validate-llm-config.sh --env-file ./.argus-llm.env to confirm the LLM
  config, then run ./$SCRIPT_NAME again. Existing legacy LLM values in .env are
  migrated into .argus-llm.env automatically.
  python3 (preferred) or jq is required to parse the multi-row LLM import response.

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
  Default:     docker compose up -d --build db redis backend, poll backend, import LLM env,
               start frontend, then docker compose logs -f
               Ctrl-C/SIGTERM stops the Compose stack before exiting.
  --wait-exit: same gating, then poll http://127.0.0.1:$FRONTEND_PORT, then exit

Ports:
  Argus_FRONTEND_PORT           Frontend host port. Default: 13000
  Argus_BACKEND_PORT            Backend host port. Default: 18000
  ARGUS_PORT_AUTO_FREE          After Compose down, auto-free FRONTEND/BACKEND
                                ports if still busy: stop Docker containers
                                publishing them, then SIGTERM/SIGKILL host
                                processes via lsof/ss/fuser. Default: true.
                                Set to false to disable (script will fail loudly
                                on busy ports instead of clearing them).
  ARGUS_PORT_FREE_GRACE         Seconds to wait between SIGTERM and SIGKILL
                                for processes holding Argus ports. Default: 2.

Test / verification:
  --dry-run                     Preview commands and skip Docker/curl execution.
  ARGUS_STUB_DOCKER=true        Print Docker/curl/env commands instead of running them.
  --runtime docker|podman       Explicit container runtime. Default: podman.
                                podman mode uses local image/container startup;
                                it does not use a Podman Compose path, never removes
                                Podman images or volumes, and makes the default
                                Opengrep dockerfile_container runner use rootless
                                Podman with no host Docker socket.
                                docker mode remains available as a local/dev
                                fallback through Docker Compose.
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

read_env_value_from_file() {
  local file="$1"
  local key="$2"
  [[ -f "$file" ]] || return 0
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
  ' "$file"
}

read_env_value() {
  local key="$1"
  read_env_value_from_file "$ARGUS_ENV_FILE" "$key"
}

read_llm_env_value() {
  local key="$1"
  read_env_value_from_file "$ARGUS_LLM_ENV_FILE" "$key"
}

# _assert_json_tool_available: fail visibly (in the main shell) if neither jq nor python3 works.
# Call this BEFORE any subshell that invokes parse_import_response_json.
_assert_json_tool_available() {
  if printf 'null' | jq -e . >/dev/null 2>&1; then return 0; fi
  if printf 'import sys\n' | python3 - >/dev/null 2>&1; then return 0; fi
  fail "argus-bootstrap requires python3 (preferred) or jq to parse the multi-row LLM import response. Install one of them and re-run."
}

# parse_import_response_json: parse the backend import response (multi-row or legacy single-row).
# Reads JSON from $1 (string). Outputs:
#   WINNING_ROW_ID=<id or empty>      — from winningRowId field (empty if absent)
#   SUCCESS=<true|false>              — from success field (for legacy single-row compat)
#   [LLM N] preflight: id=... reasonCode=... message=...   (one per row, only if rows present)
# Requires python3 (preferred) or jq. Fails hard if neither available.
parse_import_response_json() {
  local json="$1"
  # Probe tools with a trivial invocation to confirm they are functional (not just present in PATH).
  local _jq_ok=false _py_ok=false
  if printf 'null' | jq -e . >/dev/null 2>&1; then _jq_ok=true; fi
  if printf 'import sys\n' | python3 - >/dev/null 2>&1; then _py_ok=true; fi

  if "$_jq_ok"; then
    printf '%s' "$json" | jq -r '
      "WINNING_ROW_ID=" + (.winningRowId // ""),
      "SUCCESS=" + (if .success == false then "false" else "true" end),
      (.rows[]? | "[LLM \(.index+1)] \(.preflight): id=\(.id) reasonCode=\(.reasonCode // "null") message=\(.message // "")")
    '
  elif "$_py_ok"; then
    printf '%s' "$json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
winning = d.get('winningRowId') or ''
print('WINNING_ROW_ID=' + winning)
success = 'false' if d.get('success') is False else 'true'
print('SUCCESS=' + success)
rows = d.get('rows') or []
for r in rows:
    idx = (r.get('index') or 0) + 1
    preflight = r.get('preflight') or 'unknown'
    rid = r.get('id') or ''
    reason = r.get('reasonCode') or 'null'
    msg = r.get('message') or ''
    print('[LLM %d] %s: id=%s reasonCode=%s message=%s' % (idx, preflight, rid, reason, msg))
"
  else
    fail "argus-bootstrap requires python3 (preferred) or jq to parse the multi-row LLM import response. Install one of them and re-run."
  fi
}

# detect_duplicate_legacy_bare_keys: warn if ARGUS_LLM_ENV_FILE has stacked bare LLM_PROVIDER blocks.
detect_duplicate_legacy_bare_keys() {
  local count
  count=$(awk '/^[[:space:]]*#/ {next} /^[[:space:]]*LLM_PROVIDER[[:space:]]*=/ { c++ } END { print c+0 }' "$ARGUS_LLM_ENV_FILE")
  if (( count > 1 )); then
    printf >&2 '[argus-bootstrap] Warning: detected %s stacked bare LLM_PROVIDER blocks in %s. Only the LAST block is active. Convert to LLM_1_*/LLM_2_*/... to use all of them.\n' "$count" "$ARGUS_LLM_ENV_FILE"
  fi
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

run_cmd() {
  if "$DRY_RUN"; then
    printf '[dry-run] %s\n' "$(quote_cmd "$@")"
    return 0
  fi
  if is_truthy "$STUB_DOCKER" && [[ "${1:-}" =~ ^(docker|podman|curl|env)$ ]]; then
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
  ensure_llm_env_file
  detect_duplicate_legacy_bare_keys
  "$LLM_CONFIG_VALIDATOR" --env-file "$ARGUS_LLM_ENV_FILE"
}

ensure_root_env_file() {
  if [[ -f "$ARGUS_ENV_FILE" ]]; then
    ensure_secret_key
    return 0
  fi
  cat > "$ARGUS_ENV_FILE" <<'ENV'
# Argus runtime env.
# Generated automatically. Normal users only need .argus-llm.env.
# Add advanced overrides here only when defaults are not enough.
ENV
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  ensure_secret_key
  log "Created runtime .env for generated SECRET_KEY and advanced overrides: $ARGUS_ENV_FILE"
}

legacy_llm_env_is_configured() {
  local provider api_key model base_url
  provider="$(read_env_value_from_file "$ARGUS_ENV_FILE" LLM_PROVIDER)"
  api_key="$(read_env_value_from_file "$ARGUS_ENV_FILE" LLM_API_KEY)"
  model="$(read_env_value_from_file "$ARGUS_ENV_FILE" LLM_MODEL)"
  base_url="$(read_env_value_from_file "$ARGUS_ENV_FILE" LLM_BASE_URL)"
  [[ -n "$provider" && -n "$api_key" && -n "$model" && -n "$base_url" ]] || return 1
  ! is_placeholder_value "$api_key" && ! is_placeholder_value "$model" && ! is_placeholder_value "$base_url"
}

copy_legacy_llm_env_file() {
  local keys=(
    LLM_PROVIDER
    LLM_API_KEY
    LLM_MODEL
    LLM_BASE_URL
    LLM_TIMEOUT
    LLM_TEMPERATURE
    LLM_MAX_TOKENS
    LLM_FIRST_TOKEN_TIMEOUT
    LLM_STREAM_TIMEOUT
    LLM_CUSTOM_HEADERS
    AGENT_TIMEOUT
  )
  {
    printf '# Argus dedicated LLM env.\n'
    printf '# Migrated from legacy .env; secrets redacted in logs only.\n'
    local key value
    for key in "${keys[@]}"; do
      value="$(read_env_value_from_file "$ARGUS_ENV_FILE" "$key")"
      [[ -n "$value" ]] || continue
      printf '%s=%s\n' "$key" "$value"
    done
  } > "$ARGUS_LLM_ENV_FILE"
  chmod 600 "$ARGUS_LLM_ENV_FILE" 2>/dev/null || true
  log "Created dedicated LLM env from legacy .env: $ARGUS_LLM_ENV_FILE (secrets redacted)."
}

ensure_llm_env_file() {
  if [[ -f "$ARGUS_LLM_ENV_FILE" ]]; then
    return 0
  fi
  if legacy_llm_env_is_configured; then
    copy_legacy_llm_env_file
    return 0
  fi
  [[ -f "$ARGUS_LLM_ENV_EXAMPLE" ]] || fail "LLM env template is missing: $ARGUS_LLM_ENV_EXAMPLE"
  cp "$ARGUS_LLM_ENV_EXAMPLE" "$ARGUS_LLM_ENV_FILE"
  chmod 600 "$ARGUS_LLM_ENV_FILE" 2>/dev/null || true
  log "Created dedicated LLM env from llm.env.example: $ARGUS_LLM_ENV_FILE"
  cat >&2 <<MESSAGE
[argus-bootstrap] 已自动生成 SECRET_KEY；请填写 .argus-llm.env 中的 LLM 配置后再次运行 ./argus-bootstrap.sh。
[argus-bootstrap] 也可以先运行 ./scripts/validate-llm-config.sh --env-file ./.argus-llm.env 确认配置无误后再运行脚本。
MESSAGE
  exit 1
}

generate_secret_key() {
  local secret=""
  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
  elif command -v od >/dev/null 2>&1 && [[ -r /dev/urandom ]]; then
    secret="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  else
    fail "Unable to generate SECRET_KEY: openssl or /dev/urandom+od is required"
  fi
  [[ -n "$secret" ]] || fail "Generated SECRET_KEY is empty"
  printf '%s' "$secret"
}

write_secret_key() {
  local secret="$1"
  local tmp
  tmp="$(mktemp "${ARGUS_ENV_FILE}.tmp.XXXXXX")"
  awk -v secret="$secret" '
    BEGIN { replaced = 0 }
    /^[[:space:]]*SECRET_KEY[[:space:]]*=/ {
      print "SECRET_KEY=" secret
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) {
        print "SECRET_KEY=" secret
      }
    }
  ' "$ARGUS_ENV_FILE" > "$tmp"
  mv "$tmp" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
}

ensure_secret_key() {
  local existing
  existing="$(read_env_value SECRET_KEY)"
  if ! is_placeholder_value "$existing"; then
    return 0
  fi
  write_secret_key "$(generate_secret_key)"
  log "Generated SECRET_KEY in root .env (redacted)."
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
    log "Dry-run/stub mode: skipping ${CONTAINER_RUNTIME} daemon/tool preflight."
    return 0
  fi
  case "$CONTAINER_RUNTIME" in
    docker)
      command -v docker >/dev/null 2>&1 || fail "docker CLI not found"
      docker compose version >/dev/null || fail "docker compose plugin is not available"
      docker info >/dev/null || fail "Docker daemon is not reachable"
      ;;
    podman)
      command -v podman >/dev/null 2>&1 || fail "podman CLI not found"
      command -v python3 >/dev/null 2>&1 || fail "python3 is required to prepare Podman-compatible Dockerfiles"
      # Auto-recovery: if podman socket is unreachable (common on WSL2 where
      # podman.socket systemd unit may be masked at /etc/xdg/systemd/user/),
      # start the API service manually. Permanent fix:
      #   sudo rm /etc/xdg/systemd/user/podman.socket
      #   systemctl --user daemon-reload
      #   systemctl --user enable --now podman.socket
      if ! podman info >/dev/null 2>&1; then
        log "Podman socket not reachable; attempting to start podman system service..."
        local _sock="/run/user/$(id -u)/podman/podman.sock"
        mkdir -p "$(dirname "$_sock")"
        podman system service --time=0 "unix://$_sock" &disown
        local _wait=0
        while [[ $_wait -lt 5 ]] && ! podman info >/dev/null 2>&1; do
          sleep 1; ((_wait++))
        done
        podman info >/dev/null 2>&1 || fail "Podman daemon/runtime is not reachable (auto-start failed)"
        log "Podman system service started successfully."
      fi
      local podman_rootless
      podman_rootless="$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)"
      [[ "$podman_rootless" == "true" ]] || fail "Podman runtime must be rootless for Argus runner mode"
      [[ -S "$ARGUS_PODMAN_SOCKET_PATH" ]] || fail "Rootless Podman socket is not available at $ARGUS_PODMAN_SOCKET_PATH"
      ;;
    *)
      fail "Unsupported container runtime reached preflight: $CONTAINER_RUNTIME"
      ;;
  esac
  command -v curl >/dev/null 2>&1 || fail "curl not found"
}

ensure_env_key_default() {
  local key="$1"
  local default_value="$2"
  local comment="${3:-}"
  local existing
  existing="$(read_env_value "$key")"
  if [[ -n "$existing" ]]; then
    return 0
  fi
  if [[ ! -f "$ARGUS_ENV_FILE" ]]; then
    return 0
  fi
  {
    if [[ -n "$comment" ]]; then
      printf '\n# %s\n' "$comment"
    else
      printf '\n'
    fi
    printf '%s=%s\n' "$key" "$default_value"
  } >> "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  log "Added ${key}=${default_value} to ${ARGUS_ENV_FILE} (legacy .env upgrade)."
}

write_env_key_value() {
  local key="$1"
  local value="$2"
  local tmp
  [[ -f "$ARGUS_ENV_FILE" ]] || return 0
  tmp="$(mktemp "${ARGUS_ENV_FILE}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      print key "=" value
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) {
        print key "=" value
      }
    }
  ' "$ARGUS_ENV_FILE" > "$tmp"
  mv "$tmp" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
}

normalize_legacy_opengrep_image_env() {
  local key="$1"
  local value
  value="$(read_env_value "$key")"
  case "$value" in
    Argus/opengrep-runner-local:latest)
      write_env_key_value "$key" "argus/opengrep-runner-local:latest"
      log "Normalized ${key}=argus/opengrep-runner-local:latest for OCI-compatible A3S Box image refs."
      ;;
    Argus/opengrep-runner:latest)
      write_env_key_value "$key" "argus/opengrep-runner:latest"
      log "Normalized ${key}=argus/opengrep-runner:latest for OCI-compatible A3S Box image refs."
      ;;
  esac
}

normalize_legacy_ghcr_image_env() {
  local key="$1"
  local legacy_registry value normalized
  legacy_registry="ghcr."
  legacy_registry="${legacy_registry}io"
  value="$(read_env_value "$key")"
  case "$value" in
    "$legacy_registry"/*)
      normalized="ghcr.nju.edu.cn/${value#${legacy_registry}/}"
      write_env_key_value "$key" "$normalized"
      log "Normalized ${key}=${normalized}; legacy GHCR image pulls are routed through ghcr.nju.edu.cn."
      ;;
  esac
}

normalize_legacy_vite_api_target_env() {
  local value backend_port target
  value="$(read_env_value VITE_API_TARGET)"
  backend_port="$(read_env_value Argus_BACKEND_PORT)"
  [[ -n "$backend_port" ]] || backend_port="$BACKEND_PORT"
  [[ -n "$backend_port" ]] || backend_port="18000"
  target="http://host.docker.internal:${backend_port}"
  case "$value" in
    http://backend:8000|http://backend:"${backend_port}")
      write_env_key_value "VITE_API_TARGET" "$target"
      log "Normalized VITE_API_TARGET=${target}; backend uses host networking, so Docker service DNS 'backend' is not a valid Vite proxy target."
      ;;
  esac
}

ensure_podman_rootless_socket_env() {
  if [[ "$CONTAINER_RUNTIME" != "podman" ]]; then
    return 0
  fi
  if [[ -z "${CONTAINER_HOST:-}" ]]; then
    export CONTAINER_HOST="unix:///run/user/$(id -u)/podman/podman.sock"
  fi
  if [[ -z "${ARGUS_PODMAN_SOCKET_PATH:-}" ]]; then
    ARGUS_PODMAN_SOCKET_PATH="${CONTAINER_HOST#unix://}"
  fi
  [[ -n "$ARGUS_PODMAN_SOCKET_PATH" ]] || fail "Unable to resolve rootless Podman socket path"
  case "$ARGUS_PODMAN_SOCKET_PATH" in
    *docker.sock*) fail "Podman runtime must not use Docker socket path: $ARGUS_PODMAN_SOCKET_PATH" ;;
  esac
  # Rootless Podman socket is 0700 by default; backend container needs access
  # via bind-mount across user namespaces, so widen permissions.
  if [[ -S "$ARGUS_PODMAN_SOCKET_PATH" ]]; then
    chmod 0777 "$ARGUS_PODMAN_SOCKET_PATH" 2>/dev/null || true
  fi
}

podman_volume_mountpoint() {
  local volume="$1"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    printf '/var/lib/containers/storage/volumes/%s/_data' "$volume"
    return 0
  fi
  podman volume inspect --format '{{.Mountpoint}}' "$volume"
}

ensure_root_env_keys() {
  local backend_port
  backend_port="$(read_env_value Argus_BACKEND_PORT)"
  [[ -n "$backend_port" ]] || backend_port="$BACKEND_PORT"
  [[ -n "$backend_port" ]] || backend_port="18000"
  ensure_env_key_default \
    "VITE_API_TARGET" \
    "http://host.docker.internal:${backend_port}" \
    "Frontend dev proxy target. Backend uses host networking, so use host.docker.internal rather than Docker service DNS."
  normalize_legacy_vite_api_target_env
  ensure_env_key_default \
    "SCANNER_OPENGREP_IMAGE" \
    "argus/opengrep-runner-local:latest" \
    "Local lowercase OCI tag for Docker and A3S Box OpenGrep scans."
  ensure_env_key_default \
    "SCANNER_JOERN_IMAGE" \
    "$DEFAULT_JOERN_IMAGE" \
    "Joern scanner image prepared during bootstrap and used by per-task Joern scan containers."
  normalize_legacy_opengrep_image_env "SCANNER_OPENGREP_IMAGE"
  normalize_legacy_opengrep_image_env "SCANNER_OPENGREP_A3S_BOX_IMAGE"
  normalize_legacy_ghcr_image_env "SCANNER_JOERN_IMAGE"
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

port_is_busy() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -lnt "sport = :${port}" 2>/dev/null | awk 'NR>1 {found=1} END {exit !found}'
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -lnt 2>/dev/null | awk -v p=":${port}\$" '$4 ~ p {found=1} END {exit !found}'
    return $?
  fi
  ( exec 3<>"/dev/tcp/127.0.0.1/${port}" ) 2>/dev/null
}

port_listener_pids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -lntp "sport = :${port}" 2>/dev/null \
      | awk -F'pid=' 'NR>1 && NF>1 {split($2,a,","); if (a[1] ~ /^[0-9]+$/) print a[1]}' \
      | sort -u
    return 0
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' | sort -u
    return 0
  fi
}

free_port_if_busy() {
  local port="$1"
  local label="${2:-port}"
  local disable_hint="${3:-ARGUS_PORT_AUTO_FREE=false}"
  if ! port_is_busy "$port"; then
    return 0
  fi
  log "Port ${port} (${label}) is busy; attempting auto-free (set ${disable_hint} to disable)."

  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    local pcids
    pcids="$(podman ps --filter "publish=${port}" --format '{{.ID}}' 2>/dev/null || true)"
    if [[ -n "$pcids" ]]; then
      log "Stopping podman containers publishing port ${port}: $(printf '%s ' $pcids)"
      # shellcheck disable=SC2086
      podman stop $pcids >/dev/null 2>&1 || true
      # shellcheck disable=SC2086
      podman rm -f $pcids >/dev/null 2>&1 || true
    fi
  fi

  if ! port_is_busy "$port"; then
    log "Port ${port} freed via podman container stop."
    return 0
  fi

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    local cids
    cids="$(docker ps --filter "publish=${port}" --format '{{.ID}}' 2>/dev/null || true)"
    if [[ -n "$cids" ]]; then
      log "Stopping docker containers publishing port ${port}: $(printf '%s ' $cids)"
      # shellcheck disable=SC2086
      docker stop $cids >/dev/null 2>&1 || true
      # shellcheck disable=SC2086
      docker rm -f $cids >/dev/null 2>&1 || true
    fi
  fi

  if ! port_is_busy "$port"; then
    log "Port ${port} freed via docker container stop."
    return 0
  fi

  local pids pid
  pids="$(port_listener_pids "$port" || true)"
  if [[ -n "$pids" ]]; then
    log "Sending SIGTERM to host processes holding port ${port}: $(printf '%s ' $pids)"
    for pid in $pids; do
      kill -TERM "$pid" 2>/dev/null || true
    done
    sleep "$ARGUS_PORT_FREE_GRACE"
    pids="$(port_listener_pids "$port" || true)"
    if [[ -n "$pids" ]]; then
      log "Sending SIGKILL to lingering processes on port ${port}: $(printf '%s ' $pids)"
      for pid in $pids; do
        kill -KILL "$pid" 2>/dev/null || true
      done
      sleep 1
    fi
  fi

  if port_is_busy "$port"; then
    fail "Port ${port} (${label}) still busy after auto-free attempts. Inspect with: ss -lntp 'sport = :${port}' or lsof -iTCP:${port} -sTCP:LISTEN. Override with ${disable_hint} to skip."
  fi
  log "Port ${port} (${label}) freed."
}

ensure_argus_ports_free() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping busy-port auto-free."
    return 0
  fi
  if ! is_truthy "$ARGUS_PORT_AUTO_FREE"; then
    log "ARGUS_PORT_AUTO_FREE=false; skipping host-port auto-free preflight."
    return 0
  fi
  log "Preflight: ensuring Argus host ports are free (frontend=${FRONTEND_PORT}, backend=${BACKEND_PORT})."
  free_port_if_busy "$FRONTEND_PORT" "frontend"
  free_port_if_busy "$BACKEND_PORT" "backend"
}

prune_docker_system() {
  if is_falsey "$DOCKER_SYSTEM_PRUNE"; then
    log "Skipping global Docker prune because ARGUS_DOCKER_SYSTEM_PRUNE=false."
    return 0
  fi
  log "WARNING: running docker system prune -af --volumes; this can delete unused Docker resources and volumes from other projects."
  run_cmd docker system prune -af --volumes
}

podman_container_names() {
  printf '%s\n' "$PODMAN_FRONTEND_CONTAINER" "$PODMAN_BACKEND_CONTAINER" "$PODMAN_REDIS_CONTAINER" "$PODMAN_DB_CONTAINER"
}

podman_rm_container_if_exists() {
  local name="$1"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_cmd podman inspect --format '{{ index .Config.Labels "io.argus.project" }} {{ index .Config.Labels "io.argus.runtime" }}' "$name"
    run_cmd podman rm -f "$name"
    return 0
  fi
  if ! podman container exists "$name"; then
    return 0
  fi
  local project_label runtime_label
  project_label="$(podman inspect --format '{{ index .Config.Labels "io.argus.project" }}' "$name" 2>/dev/null || true)"
  runtime_label="$(podman inspect --format '{{ index .Config.Labels "io.argus.runtime" }}' "$name" 2>/dev/null || true)"
  if [[ "$project_label" != "argus" || "$runtime_label" != "podman" ]]; then
    fail "Refusing to remove existing Podman container ${name}: required labels ${PODMAN_PROJECT_LABEL} and ${PODMAN_RUNTIME_LABEL} are not both present"
  fi
  run_cmd podman rm -f "$name"
}

podman_cleanup_runtime_containers() {
  log "Stopping/removing Argus Podman containers only; preserving Podman images and volumes."
  local name
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    podman_rm_container_if_exists "$name"
  done < <(podman_container_names)
}

podman_external_storage_container_ids() {
  podman ps -a --external --filter 'status=storage' --format '{{.ID}}' 2>/dev/null \
    | sed '/^[[:space:]]*$/d' \
    | sort -u || true
}

podman_dangling_image_ids() {
  {
    podman images --filter 'dangling=true' -q 2>/dev/null || true
    podman images --format '{{.ID}} {{.Repository}} {{.Tag}}' 2>/dev/null \
      | awk '$2 == "<none>" && $3 == "<none>" {print $1}' || true
  } | sed '/^[[:space:]]*$/d' | sort -u
}

podman_remove_external_storage_containers() {
  local external_ids
  external_ids="$(podman_external_storage_container_ids)"
  if [[ -z "$external_ids" ]]; then
    printf '0'
    return 0
  fi
  local count=0 external_id
  while IFS= read -r external_id; do
    [[ -n "$external_id" ]] || continue
    podman rm "$external_id" >/dev/null 2>&1 && count=$((count + 1)) || true
  done <<< "$external_ids"
  printf '%s' "$count"
}

podman_remove_image_ids() {
  local image_ids="$1"
  if [[ -z "$image_ids" ]]; then
    printf '0'
    return 0
  fi
  local count=0 image_id
  # Remove only explicit dangling image IDs. Avoid Podman image/system prune so
  # unrelated local build cache and named images remain untouched.
  while IFS= read -r image_id; do
    [[ -n "$image_id" ]] || continue
    podman rmi "$image_id" >/dev/null 2>&1 && count=$((count + 1)) || true
  done <<< "$image_ids"
  printf '%s' "$count"
}

podman_cleanup_dangling_images() {
  local label="${1:-Podman dangling cleanup}"
  local before_file="${2:-}"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping Podman dangling image cleanup for ${label}."
    return 0
  fi

  local after_file image_ids removed external_removed image_removed
  after_file="$(mktemp "${TMPDIR:-/tmp}/argus-podman-dangling-after.XXXXXX")"
  podman_dangling_image_ids > "$after_file"
  if [[ -n "$before_file" && -f "$before_file" ]]; then
    image_ids="$(comm -13 "$before_file" "$after_file" || true)"
  else
    image_ids="$(cat "$after_file")"
  fi

  rm -f "$after_file"
  [[ -z "$before_file" ]] || rm -f "$before_file"

  external_removed="$(podman_remove_external_storage_containers)"
  image_removed="$(podman_remove_image_ids "$image_ids")"
  removed=$((external_removed + image_removed))
  if (( removed > 0 )); then
    log "Podman cleanup after ${label}: removed ${removed} dangling build resources."
  fi
}

podman_prune_dangling() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping Podman dangling cleanup."
    return 0
  fi
  local removed=0
  local exited_ids
  exited_ids="$(podman ps -a --filter 'status=exited' --filter 'status=created' --format '{{.ID}} {{.Names}}' 2>/dev/null || true)"
  if [[ -n "$exited_ids" ]]; then
    local cid cname
    while IFS=' ' read -r cid cname; do
      [[ -n "$cid" ]] || continue
      case "$cname" in
        argus-db|argus-redis|argus-backend|argus-frontend) continue ;;
      esac
      podman rm -f "$cid" >/dev/null 2>&1 && removed=$((removed + 1)) || true
    done <<< "$exited_ids"
  fi

  local external_removed image_removed image_ids
  external_removed="$(podman_remove_external_storage_containers)"
  image_ids="$(podman_dangling_image_ids)"
  image_removed="$(podman_remove_image_ids "$image_ids")"
  removed=$((removed + external_removed + image_removed))
  if (( removed > 0 )); then
    log "Podman cleanup: removed ${removed} dangling/exited resources."
  fi
}

cleanup_for_run_mode() {
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
    case "$RUN_MODE" in
      default|keep-cache|aggressive)
        log "${RUN_MODE} mode under Podman runtime: preserving Podman images and volumes."
        podman_cleanup_runtime_containers
        podman_prune_dangling
        ;;
      *)
        fail "Unsupported run mode reached Podman cleanup dispatcher: $RUN_MODE"
        ;;
    esac
    return 0
  fi
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
    "ARGUS_LLM_ENV_FILE=$ARGUS_LLM_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build
}

compose_up_backend_detached() {
  log "Starting Argus backend prerequisites detached"
  run_cmd env \
    "ARGUS_ENV_FILE=$ARGUS_ENV_FILE" \
    "ARGUS_LLM_ENV_FILE=$ARGUS_LLM_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build db redis backend
}

compose_up_frontend_detached() {
  log "Starting Argus frontend on port ${FRONTEND_PORT}"
  run_cmd env \
    "ARGUS_ENV_FILE=$ARGUS_ENV_FILE" \
    "ARGUS_LLM_ENV_FILE=$ARGUS_LLM_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build frontend
}

prepare_podman_dockerfile() {
  local source_file="$1"
  local target_file="$2"
  python3 - "$source_file" "$target_file" <<'PYEOF'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
lines = source.read_text().splitlines()
out = []
idx = 0

mount_prefix = re.compile(r'^(?P<indent>\s*)RUN\s+--mount=')
continued_mount = re.compile(r'^\s*--mount=')

while idx < len(lines):
    line = lines[idx]
    match = mount_prefix.match(line)
    if not match:
        out.append(line)
        idx += 1
        continue

    indent = match.group('indent')
    remainder = line.split('\\', 1)[1] if '\\' in line else ''
    idx += 1
    while idx < len(lines) and continued_mount.match(lines[idx]):
        if '\\' not in lines[idx]:
            remainder = ''
            idx += 1
            break
        idx += 1
    if idx < len(lines):
        command = lines[idx].lstrip()
        out.append(f'{indent}RUN {remainder.strip() or command}')
        if remainder.strip():
            out.append(command)
        idx += 1
    else:
        out.append(f'{indent}RUN')

target.write_text('\n'.join(out) + '\n')
PYEOF
}

podman_build_file_arg() {
  local source_file="$1"
  local prepared_file="$2"
  # Podman 4.1+ supports --mount=type=cache natively; skip stripping.
  printf '%s' "$source_file"
}

cleanup_podman_dockerfile() {
  local prepared_file="$1"
  local source_file="$2"
  [[ "$prepared_file" == "$source_file" ]] && return 0
  rm -f "$prepared_file"
}

podman_capture_dangling_before() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    printf ''
    return 0
  fi
  local before_file
  before_file="$(mktemp "${TMPDIR:-/tmp}/argus-podman-dangling-before.XXXXXX")"
  podman_dangling_image_ids > "$before_file"
  printf '%s' "$before_file"
}

podman_cleanup_after_successful_build() {
  local label="$1"
  local before_file="${2:-}"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping Podman dangling cleanup after ${label}."
    return 0
  fi
  podman_cleanup_dangling_images "$label" "$before_file"
}

podman_build_backend_image() {
  log "Building Argus backend Podman image: $PODMAN_BACKEND_IMAGE"
  local podman_backend_dockerfile
  podman_backend_dockerfile="$(podman_build_file_arg "$ROOT_DIR/docker/backend.Dockerfile" "${TMPDIR:-/tmp}/argus-backend-podman.Dockerfile.$$")"
  local build_rc=0 dangling_before
  dangling_before="$(podman_capture_dangling_before)"
  run_cmd podman build \
    --file "$podman_backend_dockerfile" \
    --target runtime-plain \
    --platform "linux/$PODMAN_TARGETARCH" \
    --http-proxy=false \
    --build-arg "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}" \
    --build-arg "BACKEND_APT_MIRROR_PRIMARY=${BACKEND_APT_MIRROR_PRIMARY:-mirrors.aliyun.com}" \
    --build-arg "BACKEND_APT_SECURITY_PRIMARY=${BACKEND_APT_SECURITY_PRIMARY:-mirrors.aliyun.com}" \
    --build-arg "BACKEND_APT_MIRROR_FALLBACK=${BACKEND_APT_MIRROR_FALLBACK:-deb.debian.org}" \
    --build-arg "BACKEND_APT_SECURITY_FALLBACK=${BACKEND_APT_SECURITY_FALLBACK:-security.debian.org}" \
    --tag "$PODMAN_BACKEND_IMAGE" \
    "$ROOT_DIR" || build_rc=$?
  cleanup_podman_dockerfile "$podman_backend_dockerfile" "$ROOT_DIR/docker/backend.Dockerfile"
  if [[ "$build_rc" -eq 0 ]]; then
    podman_cleanup_after_successful_build "$PODMAN_BACKEND_IMAGE" "$dangling_before"
  else
    [[ -z "$dangling_before" ]] || rm -f "$dangling_before"
  fi
  return "$build_rc"
}

podman_build_frontend_image() {
  log "Building Argus frontend Podman image: $PODMAN_FRONTEND_IMAGE"
  local podman_frontend_dockerfile
  podman_frontend_dockerfile="$(podman_build_file_arg "$ROOT_DIR/docker/frontend.Dockerfile" "${TMPDIR:-/tmp}/argus-frontend-podman.Dockerfile.$$")"
  local build_rc=0 dangling_before
  dangling_before="$(podman_capture_dangling_before)"
  run_cmd podman build \
    --file "$podman_frontend_dockerfile" \
    --target dev \
    --http-proxy=false \
    --build-arg "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}" \
    --tag "$PODMAN_FRONTEND_IMAGE" \
    "$ROOT_DIR/frontend" || build_rc=$?
  cleanup_podman_dockerfile "$podman_frontend_dockerfile" "$ROOT_DIR/docker/frontend.Dockerfile"
  if [[ "$build_rc" -eq 0 ]]; then
    podman_cleanup_after_successful_build "$PODMAN_FRONTEND_IMAGE" "$dangling_before"
  else
    [[ -z "$dangling_before" ]] || rm -f "$dangling_before"
  fi
  return "$build_rc"
}

podman_build_opengrep_runner_image() {
  local image
  image="$(opengrep_runner_image_ref)"
  log "Building Argus Opengrep runner Podman image: $image"
  local podman_runner_dockerfile
  podman_runner_dockerfile="$(podman_build_file_arg "$ROOT_DIR/docker/opengrep-runner.Dockerfile" "${TMPDIR:-/tmp}/argus-opengrep-runner-podman.Dockerfile.$$")"
  local build_rc=0 dangling_before
  dangling_before="$(podman_capture_dangling_before)"
  run_cmd podman build \
    --file "$podman_runner_dockerfile" \
    --target opengrep-runner \
    --platform "linux/$PODMAN_TARGETARCH" \
    --http-proxy=false \
    --build-arg "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}" \
    --build-arg "BACKEND_APT_MIRROR_PRIMARY=${BACKEND_APT_MIRROR_PRIMARY:-mirrors.aliyun.com}" \
    --build-arg "BACKEND_APT_SECURITY_PRIMARY=${BACKEND_APT_SECURITY_PRIMARY:-mirrors.aliyun.com}" \
    --build-arg "BACKEND_APT_MIRROR_FALLBACK=${BACKEND_APT_MIRROR_FALLBACK:-deb.debian.org}" \
    --build-arg "BACKEND_APT_SECURITY_FALLBACK=${BACKEND_APT_SECURITY_FALLBACK:-security.debian.org}" \
    --tag "$image" \
    "$ROOT_DIR" || build_rc=$?
  cleanup_podman_dockerfile "$podman_runner_dockerfile" "$ROOT_DIR/docker/opengrep-runner.Dockerfile"
  if [[ "$build_rc" -eq 0 ]]; then
    podman_cleanup_after_successful_build "$image" "$dangling_before"
  else
    [[ -z "$dangling_before" ]] || rm -f "$dangling_before"
  fi
  return "$build_rc"
}

podman_build_codeql_runner_image() {
  local image
  image="$(codeql_runner_image_ref)"
  log "Building Argus CodeQL runner Podman image: $image"

  # Pre-download cache artifacts if missing
  local cache_dir="$ROOT_DIR/docker/cache"
  local codeql_version="${CODEQL_VERSION:-2.16.1}"
  local gradle_version="${GRADLE_VERSION:-8.7}"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping CodeQL cache artifact download."
  elif [[ ! -f "$cache_dir/codeql-bundle-linux64.tar.gz" ]] || [[ ! -f "$cache_dir/gradle-${gradle_version}-bin.zip" ]]; then
    log "Downloading CodeQL build cache artifacts..."
    bash "$ROOT_DIR/docker/codeql-cache-download.sh"
  fi

  local build_rc=0 dangling_before
  dangling_before="$(podman_capture_dangling_before)"
  run_cmd podman build \
    --file "$ROOT_DIR/docker/codeql.Dockerfile" \
    --platform "linux/$PODMAN_TARGETARCH" \
    --network host \
    --http-proxy=false \
    --build-arg "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}" \
    --build-arg "APT_MIRROR=${BACKEND_APT_MIRROR_PRIMARY:-mirrors.aliyun.com}" \
    --build-arg "CODEQL_VERSION=${codeql_version}" \
    --build-arg "GRADLE_VERSION=${gradle_version}" \
    --tag "$image" \
    "$ROOT_DIR" || build_rc=$?
  if [[ "$build_rc" -eq 0 ]]; then
    podman_cleanup_after_successful_build "$image" "$dangling_before"
  else
    [[ -z "$dangling_before" ]] || rm -f "$dangling_before"
  fi
  return "$build_rc"
}

podman_build_audit_sandbox_image() {
  log "Building Argus audit sandbox Podman image: $PODMAN_AUDIT_SANDBOX_IMAGE"
  local build_rc=0 dangling_before
  dangling_before="$(podman_capture_dangling_before)"
  run_cmd podman build \
    --file "$ROOT_DIR/docker/audit-sandbox.Dockerfile" \
    --platform "linux/$PODMAN_TARGETARCH" \
    --http-proxy=false \
    --build-arg "DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}" \
    --build-arg "APT_MIRROR=${BACKEND_APT_MIRROR_PRIMARY:-mirrors.aliyun.com}" \
    --tag "$PODMAN_AUDIT_SANDBOX_IMAGE" \
    "$ROOT_DIR" || build_rc=$?
  if [[ "$build_rc" -eq 0 ]]; then
    podman_cleanup_after_successful_build "$PODMAN_AUDIT_SANDBOX_IMAGE" "$dangling_before"
  else
    [[ -z "$dangling_before" ]] || rm -f "$dangling_before"
  fi
  return "$build_rc"
}

podman_prepull_base_images() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping base/scanner image pre-pull."
    return 0
  fi
  local mirror="${DOCKERHUB_LIBRARY_MIRROR:-m.daocloud.io/docker.io/library}"
  local joern_image
  joern_image="$(joern_runner_image_ref)"
  log "Pre-pulling base/scanner images in parallel (including Joern: $joern_image)..."
  local -a images=(
    "${mirror}/rust:1.90-slim-bookworm"
    "${mirror}/debian:trixie-slim"
    "${mirror}/node:22-alpine"
    "${mirror}/node:22-slim"
    "${mirror}/ubuntu:22.04"
    "$joern_image"
  )
  local -a pull_pids=() pull_images=()
  for img in "${images[@]}"; do
    podman pull "$img" > /dev/null 2>&1 &
    pull_pids+=($!)
    pull_images+=("$img")
  done
  local pull_failures=0
  for i in "${!pull_pids[@]}"; do
    local pid="${pull_pids[$i]}"
    local img="${pull_images[$i]}"
    if wait "$pid"; then
      log "Base/scanner image pre-pulled: $img"
    else
      pull_failures=$((pull_failures + 1))
      log "Warning: failed to pre-pull base/scanner image: $img (builds will pull on demand)."
    fi
  done
  if [[ "$pull_failures" -gt 0 ]]; then
    log "Warning: $pull_failures base/scanner image(s) failed to pre-pull (builds will pull on demand)."
  else
    log "All base/scanner images pre-pulled."
  fi
}

podman_build_local_images() {
  local skip_build="${ARGUS_SKIP_BUILD:-false}"
  if [[ "$skip_build" == "true" ]]; then
    log "ARGUS_SKIP_BUILD=true; skipping image builds."
    return 0
  fi

  # Podman auto-injects host proxy env vars into build context; clear them
  # so container builds can reach registries directly without host proxy.
  # (Primary clearing is at script top; this is a safety net for subshells.)
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY 2>/dev/null || true

  if "$DRY_RUN" || is_truthy "$STUB_DOCKER" || is_truthy "$PODMAN_SEQUENTIAL_BUILD"; then
    log "Building Podman images sequentially (visible logs for dry-run/stub or --sequential-build)."
    podman_build_opengrep_runner_image
    podman_build_codeql_runner_image
    podman_build_audit_sandbox_image
    podman_build_backend_image
    podman_build_frontend_image
    return 0
  fi

  log "Building Podman images in parallel (layer cache handles unchanged content)."
  podman_prepull_base_images

  local dangling_before_all
  dangling_before_all="$(podman_capture_dangling_before)"

  local -a build_pids=() build_names=() build_logs=()
  local build_funcs=("podman_build_opengrep_runner_image" "podman_build_codeql_runner_image" "podman_build_audit_sandbox_image" "podman_build_backend_image" "podman_build_frontend_image")
  local image_names=("opengrep-runner" "codeql-runner" "audit-sandbox" "backend" "frontend")
  local total=${#build_funcs[@]}

  for i in "${!build_funcs[@]}"; do
    local logfile="${PODMAN_BUILD_LOG_DIR}/argus-build-${image_names[$i]}.log"
    build_logs+=("$logfile")
    build_names+=("${image_names[$i]}")
    ( ${build_funcs[$i]} ) > "$logfile" 2>&1 &
    build_pids+=($!)
  done

  local -a failed=() succeeded=()
  for i in "${!build_pids[@]}"; do
    if wait "${build_pids[$i]}"; then
      succeeded+=("${build_names[$i]}")
      printf "  [%d/%d] %s ✓\n" $((${#succeeded[@]} + ${#failed[@]})) "$total" "${build_names[$i]}"
    else
      failed+=("${build_names[$i]}")
      printf "  [%d/%d] %s ✗ (retrying...)\n" $((${#succeeded[@]} + ${#failed[@]})) "$total" "${build_names[$i]}"
    fi
  done

  if [[ ${#failed[@]} -gt 0 ]]; then
    local -a retry_failed=()
    for i in "${!failed[@]}"; do
      local name="${failed[$i]}"
      local func_idx
      for fi in "${!image_names[@]}"; do
        [[ "${image_names[$fi]}" == "$name" ]] && func_idx=$fi && break
      done
      local logfile="${PODMAN_BUILD_LOG_DIR}/argus-build-${name}-retry.log"
      if ( ${build_funcs[$func_idx]} ) > "$logfile" 2>&1; then
        printf "  [retry] %s ✓\n" "$name"
      else
        retry_failed+=("$name")
        printf "  [retry] %s ✗ FAILED\n" "$name"
        log "Build log for failed image $name:"
        cat "$logfile" >&2
      fi
    done
    if [[ ${#retry_failed[@]} -gt 0 ]]; then
      fail "Image build failed after retry: ${retry_failed[*]}"
    fi
  fi

  log "All Podman images built successfully."
  podman_cleanup_dangling_images "parallel-build" "$dangling_before_all"
}

podman_run_db() {
  log "Starting Podman Postgres container: $PODMAN_DB_CONTAINER"
  run_cmd podman run -d \
    --name "$PODMAN_DB_CONTAINER" \
    --label "$PODMAN_PROJECT_LABEL" \
    --label "$PODMAN_RUNTIME_LABEL" \
    --network host \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e "POSTGRES_DB=${POSTGRES_DB:-Argus}" \
    -v argus_postgres_data:/var/lib/postgresql \
    "$PODMAN_POSTGRES_IMAGE"
}

podman_run_redis() {
  log "Starting Podman Redis container: $PODMAN_REDIS_CONTAINER"
  run_cmd podman run -d \
    --name "$PODMAN_REDIS_CONTAINER" \
    --label "$PODMAN_PROJECT_LABEL" \
    --label "$PODMAN_RUNTIME_LABEL" \
    --network host \
    -v argus_redis_data:/data \
    "$PODMAN_REDIS_IMAGE"
}

podman_run_backend() {
  log "Starting Podman backend container: $PODMAN_BACKEND_CONTAINER"
  local scan_workspace_host
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_cmd podman volume create argus_scan_workspace || true
  else
    podman volume create argus_scan_workspace >/dev/null 2>&1 || true
  fi
  scan_workspace_host="${ARGUS_PODMAN_SCAN_WORKSPACE:-$(podman_volume_mountpoint argus_scan_workspace)}"
  run_cmd podman run -d \
    --name "$PODMAN_BACKEND_CONTAINER" \
    --label "$PODMAN_PROJECT_LABEL" \
    --label "$PODMAN_RUNTIME_LABEL" \
    --network host \
    -e HTTP_PROXY= \
    -e HTTPS_PROXY= \
    -e http_proxy= \
    -e https_proxy= \
    -e ALL_PROXY= \
    -e all_proxy= \
    -e NO_PROXY='*' \
    -e no_proxy='*' \
    --env-file "$ARGUS_ENV_FILE" \
    --env-file "$ARGUS_LLM_ENV_FILE" \
    -e "BIND_ADDR=0.0.0.0:${BACKEND_PORT}" \
    -e "DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/${POSTGRES_DB:-Argus}" \
    -e "ASYNCPG_DSN=postgresql://postgres:postgres@127.0.0.1:5432/${POSTGRES_DB:-Argus}" \
    -e REDIS_URL=redis://127.0.0.1:6379/0 \
    -e "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    -e OPENGREP_RUNNER_RUNTIME=podman \
    -e "Argus_PODMAN_BIN=podman" \
    -e "CONTAINER_HOST=unix://${PODMAN_CONTAINER_SOCKET}" \
    -e "SCAN_WORKSPACE_ROOT=$scan_workspace_host" \
    -e "ARGUS_CODEGRAPH_DATA_DIR=$scan_workspace_host/codegraph" \
    -e "RUNNER_PREFLIGHT_STRICT=${RUNNER_PREFLIGHT_STRICT:-false}" \
    -e "CONTAINER_CLI=podman" \
    -e "SCANNER_CODEQL_IMAGE=$(codeql_runner_image_ref)" \
    -e "SCANNER_JOERN_IMAGE=$(joern_runner_image_ref)" \
    -e "AUDIT_SANDBOX_IMAGE=${PODMAN_AUDIT_SANDBOX_IMAGE}" \
    -v argus_backend_uploads:/app/uploads \
    -v argus_backend_runtime_data:/app/data/runtime \
    -v "$ARGUS_ENV_FILE:/app/.env:ro" \
    -v "$scan_workspace_host:$scan_workspace_host" \
    -v "$ARGUS_PODMAN_SOCKET_PATH:$PODMAN_CONTAINER_SOCKET" \
    --entrypoint sh \
    "$PODMAN_BACKEND_IMAGE" \
    -c 'ln -sf /usr/bin/podman /usr/local/bin/docker && exec /usr/local/bin/backend-entrypoint.sh'
}

podman_run_frontend() {
  log "Starting Podman frontend container: $PODMAN_FRONTEND_CONTAINER"
  run_cmd podman run -d \
    --name "$PODMAN_FRONTEND_CONTAINER" \
    --label "$PODMAN_PROJECT_LABEL" \
    --label "$PODMAN_RUNTIME_LABEL" \
    --network host \
    -e HTTP_PROXY= \
    -e HTTPS_PROXY= \
    -e http_proxy= \
    -e https_proxy= \
    -e NO_PROXY='*' \
    -e "COREPACK_NPM_REGISTRY=${NPM_REGISTRY:-https://registry.npmmirror.com}" \
    -e "FRONTEND_NPM_REGISTRY=${NPM_REGISTRY:-https://registry.npmmirror.com}" \
    -e "PNPM_VERSION=${PNPM_VERSION:-10.11.0}" \
    -e FRONTEND_PUBLIC_URL="http://localhost:${FRONTEND_PORT}" \
    -e VITE_API_BASE_URL=/api/v1 \
    -e "VITE_API_TARGET=${VITE_API_TARGET:-http://127.0.0.1:${BACKEND_PORT}}" \
    -e BACKEND_PUBLIC_URL="http://localhost:${BACKEND_PORT}" \
    -e VITE_HMR_HOST=localhost \
    -e "VITE_HMR_PORT=${FRONTEND_PORT}" \
    -e "FRONTEND_DEV_PORT=${FRONTEND_PORT}" \
    -v "$ROOT_DIR/frontend:/app" \
    -v argus_frontend_node_modules:/app/node_modules \
    -v argus_frontend_pnpm_store:/pnpm/store \
    "$PODMAN_FRONTEND_IMAGE"
}

podman_start_backend_stack() {
  podman_run_db
  podman_run_redis
  podman_run_backend
}

podman_start_frontend_stack() {
  podman_run_frontend
}

joern_cli_contract_check() {
  cat <<'EOF'
command -v joern >/dev/null &&
command -v joern-parse >/dev/null &&
joern-parse --help | grep -F -- '--output' >/dev/null
EOF
}

podman_ensure_joern_image_container_starts() {
  local image
  image="$(joern_runner_image_ref)"
  log "Ensuring Joern scanner image container starts (Podman mode): $image"
  local contract_check
  contract_check="$(joern_cli_contract_check)"
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_cmd podman image inspect "$image"
    run_cmd podman pull "$image"
    run_cmd podman run --rm --network none "$image" /bin/sh -lc "$contract_check"
    return 0
  fi

  if podman image inspect "$image" >/dev/null 2>&1; then
    log "Joern scanner image already available: $image"
  else
    run_cmd podman pull "$image"
  fi
  run_cmd podman run --rm --network none "$image" /bin/sh -lc "$contract_check"
}

build_runner_images() {
  log "Building Opengrep runner image without starting runner service containers."
  run_cmd docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" build opengrep-runner
}

ensure_joern_image_container_starts() {
  local image
  image="$(joern_runner_image_ref)"
  log "Ensuring backend Podman can start Joern image: $image"
  local contract_check
  contract_check="$(joern_cli_contract_check)"
  run_cmd docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" \
    exec -T backend sh -lc '
      set -eu
      image="$1"
      contract_check="$2"
      if podman image inspect "$image" >/dev/null 2>&1; then
        echo "Joern scanner image already available: $image"
      else
        podman pull "$image"
      fi
      podman run --rm --network none "$image" /bin/sh -lc "$contract_check"
    ' sh "$image" "$contract_check"
}

normalize_opengrep_image_ref_value() {
  local image="$1"
  case "$image" in
    Argus/opengrep-runner-local:latest) image="argus/opengrep-runner-local:latest" ;;
    Argus/opengrep-runner:latest) image="argus/opengrep-runner:latest" ;;
  esac
  printf '%s' "$image"
}

opengrep_runner_image_ref() {
  local image
  image="${SCANNER_OPENGREP_IMAGE:-}"
  [[ -z "$image" ]] && image="$(read_env_value SCANNER_OPENGREP_IMAGE)"
  [[ -z "$image" ]] && image="argus/opengrep-runner-local:latest"
  normalize_opengrep_image_ref_value "$image"
}

codeql_runner_image_ref() {
  local image
  image="${SCANNER_CODEQL_IMAGE:-}"
  [[ -z "$image" ]] && image="$(read_env_value SCANNER_CODEQL_IMAGE)"
  [[ -z "$image" ]] && image="localhost/argus/codeql-runner:latest"
  printf '%s' "$image"
}

joern_runner_image_ref() {
  local image
  image="${SCANNER_JOERN_IMAGE:-}"
  [[ -z "$image" ]] && image="$(read_env_value SCANNER_JOERN_IMAGE)"
  [[ -z "$image" ]] && image="$DEFAULT_JOERN_IMAGE"
  printf '%s' "$image"
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
    if curl -fsS "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
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
    printf '%s\n' "$response"
  elif "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    run_cmd curl -fsS -X POST -H "X-Argus-Reset-Import-Token: $ARGUS_RESET_IMPORT_TOKEN" "$BACKEND_IMPORT_URL"
    return 0
  elif response="$(curl -fsS -X POST -H "X-Argus-Reset-Import-Token: $ARGUS_RESET_IMPORT_TOKEN" "$BACKEND_IMPORT_URL")"; then
    printf '%s\n' "$response"
  else
    fail "backend LLM env import/test failed. 请重新配置 $ARGUS_LLM_ENV_FILE 后再运行 bootstrap。"
  fi

  # Verify a JSON tool is functional before entering the subshell for parse_import_response_json.
  # This must happen in the main shell so fail() can print the error and exit visibly.
  _assert_json_tool_available

  # Parse response via parse_import_response_json (requires python3 or jq; fails hard if neither).
  # Outputs: WINNING_ROW_ID=<id|empty|null>, then one [LLM N] line per row.
  # For legacy single-row responses (no rows array), also outputs SUCCESS=<true|false>.
  local parsed_output winning_row_id
  parsed_output="$(parse_import_response_json "$response")"
  winning_row_id="$(printf '%s\n' "$parsed_output" | grep '^WINNING_ROW_ID=' | cut -d= -f2)"

  # Log one line per row (skip the metadata lines).
  while IFS= read -r row_line; do
    case "$row_line" in
      WINNING_ROW_ID=*|SUCCESS=*) continue ;;
    esac
    log "$row_line"
  done <<< "$parsed_output"

  # Determine if this is a multi-row response (has rows) or legacy single-row.
  # Use awk for explicit numeric extraction — grep -c can return non-zero exit when
  # count is 0, causing spurious failures even with || true in strict mode.
  local has_rows
  has_rows=$(printf '%s\n' "$parsed_output" | awk '/^\[LLM /{c++} END{print c+0}')

  if [[ "$has_rows" -eq 0 ]]; then
    # Legacy single-row response: use SUCCESS field parsed alongside.
    local success_val
    success_val="$(printf '%s\n' "$parsed_output" | grep '^SUCCESS=' | cut -d= -f2)"
    if [[ "$success_val" == "false" ]]; then
      fail "backend LLM env import/test returned failure. 请重新配置 $ARGUS_LLM_ENV_FILE 后再运行 bootstrap。"
    fi
    log "Backend LLM env import/test succeeded; response was sanitized by backend."
    return 0
  fi

  # Multi-row response: require a winning row.
  if [[ -z "$winning_row_id" || "$winning_row_id" == "null" ]]; then
    fail "backend LLM env import/test failed: no row passed preflight. Per-row failures above. 请重新配置 $ARGUS_LLM_ENV_FILE 后再运行 bootstrap."
  fi

  log "Backend LLM env import succeeded; winning row=$winning_row_id. Response sanitized by backend."
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

follow_podman_logs() {
  log "Following Podman logs in foreground. Ctrl-C/SIGTERM stops Argus Podman containers before exiting."
  local _pids=()
  _argus_podman_stop_on_signal() {
    log "Signal received; stopping log followers and Argus Podman containers before exit."
    for _p in "${_pids[@]}"; do kill "$_p" 2>/dev/null || true; done
    wait "${_pids[@]}" 2>/dev/null || true
    podman_cleanup_runtime_containers
    exit 130
  }
  trap _argus_podman_stop_on_signal INT TERM
  podman logs -f "$PODMAN_BACKEND_CONTAINER" 2>&1 | sed "s/^/[backend] /" &
  _pids+=($!)
  podman logs -f "$PODMAN_FRONTEND_CONTAINER" 2>&1 | sed "s/^/[frontend] /" &
  _pids+=($!)
  wait "${_pids[@]}" 2>/dev/null || true
  trap - INT TERM
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
    if curl -fsS "$url" >/dev/null 2>&1; then
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
  if [[ "$CONTAINER_RUNTIME" == "podman" ]]; then
    podman_start_stack
    return 0
  fi
  build_runner_images
  compose_up_backend_detached
  wait_for_backend
  ensure_joern_image_container_starts
  import_backend_env
  compose_up_frontend_detached
  if "$WAIT_EXIT"; then
    wait_for_frontend
    log "Complete. Frontend: http://127.0.0.1:$FRONTEND_PORT"
  else
    follow_foreground_logs
    log "Compose foreground log-follow exited. Frontend port: $FRONTEND_PORT"
  fi
}

podman_start_stack() {
  log "Starting Argus via Podman image/container mode."
  ensure_podman_rootless_socket_env
  podman_build_local_images
  podman_ensure_joern_image_container_starts
  podman_start_backend_stack
  wait_for_backend
  log "Podman runtime: default Opengrep dockerfile_container runner uses rootless Podman; Docker fallback remains Compose/dev-only."
  import_backend_env
  podman_start_frontend_stack
  if "$WAIT_EXIT"; then
    wait_for_frontend
    log "Complete. Frontend: http://127.0.0.1:$FRONTEND_PORT"
  else
    follow_podman_logs
    log "Podman foreground log-follow exited. Frontend port: $FRONTEND_PORT"
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

supported_container_runtimes() {
  printf '%s' "$SUPPORTED_CONTAINER_RUNTIMES"
}

is_supported_container_runtime() {
  case " $SUPPORTED_CONTAINER_RUNTIMES " in
    *" $1 "*) return 0 ;;
    *) return 1 ;;
  esac
}

set_container_runtime() {
  local runtime="$1"
  if ! is_supported_container_runtime "$runtime"; then
    fail "Unknown container runtime: $runtime. Supported container runtimes: $(supported_container_runtimes)"
  fi
  CONTAINER_RUNTIME="$runtime"
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
      --runtime)
        [[ $# -ge 2 ]] || fail "--runtime requires one of: $(supported_container_runtimes)"
        set_container_runtime "$2"
        shift 2
        ;;
      --runtime=*)
        set_container_runtime "${1#--runtime=}"
        shift
        ;;
      --sequential-build)
        PODMAN_SEQUENTIAL_BUILD=true
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
  ensure_podman_rootless_socket_env
  print_banner
  log "Argus bootstrap beginning. Project: $PROJECT_NAME"
  log "Run mode: $RUN_MODE"
  log "Container runtime: $CONTAINER_RUNTIME"
  validate_llm_config
  ensure_root_env_keys
  require_real_tools
  generate_import_token
  cleanup_for_run_mode
  ensure_argus_ports_free
  start_stack
}

main "$@"
