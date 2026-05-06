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
ARGUS_PORT_AUTO_FREE="${ARGUS_PORT_AUTO_FREE:-true}"
ARGUS_PORT_FREE_GRACE="${ARGUS_PORT_FREE_GRACE:-2}"
CUBE_PORT_AUTO_FREE="${CUBE_PORT_AUTO_FREE:-true}"
CUBE_DISABLE_WEBUI="${CUBE_DISABLE_WEBUI:-true}"
BACKEND_HEALTH_URL="${ARGUS_BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/health}"
BACKEND_IMPORT_URL="${ARGUS_BACKEND_IMPORT_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/system-config/import-env}"
BACKEND_CUBESANDBOX_TEMPLATES_URL="${ARGUS_BACKEND_CUBESANDBOX_TEMPLATES_URL:-http://127.0.0.1:${BACKEND_PORT}/api/v1/cubesandbox/templates}"
ARGUS_REQUIRE_CUBESANDBOX_TEMPLATES_READY="${ARGUS_REQUIRE_CUBESANDBOX_TEMPLATES_READY:-true}"
ARGUS_RESET_IMPORT_TOKEN=""

# CubeSandbox host-side bootstrap configuration.
# These govern argus-bootstrap.sh's host-side preflight, VM startup, install,
# and CodeQL C/C++ template provisioning. They are independent of
# CUBESANDBOX_AUTO_START / CUBESANDBOX_AUTO_INSTALL in .env, which gate the
# backend's in-container lazy fallback.
CUBE_QUICKSTART="$ROOT_DIR/scripts/cubesandbox-quickstart.sh"
CUBE_SSH_PORT_DEFAULT="${CUBE_SSH_PORT:-10022}"
CUBE_API_PORT_DEFAULT="${CUBE_API_PORT:-23000}"
CUBE_PROXY_HTTP_PORT_DEFAULT="${CUBE_PROXY_HTTP_PORT:-21080}"
CUBE_PROXY_HTTPS_PORT_DEFAULT="${CUBE_PROXY_HTTPS_PORT:-21443}"
CUBE_WEB_UI_PORT_DEFAULT="${CUBE_WEB_UI_PORT:-22088}"
CUBE_BOOTSTRAP_TIMEOUT="${ARGUS_CUBE_BOOTSTRAP_TIMEOUT:-1800}"
CUBE_BOOTSTRAP_POLL_INTERVAL="${ARGUS_CUBE_BOOTSTRAP_POLL_INTERVAL:-5}"
CUBESANDBOX_BOOTSTRAP_AUTO_DEFAULT="true"
CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE_DEFAULT="true"
SKIP_CUBESANDBOX="${ARGUS_SKIP_CUBESANDBOX:-false}"
CUBESANDBOX_ONLY=false
RESET_CUBESANDBOX_TEMPLATE=false
CUBESANDBOX_STATUS=false

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
  Default:     docker compose up -d --build db redis backend, poll backend, import LLM env,
               ensure CubeSandbox CodeQL+OpenGrep templates are ready, start frontend, then docker compose logs -f
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
  CUBE_PORT_AUTO_FREE           Before cubesandbox doctor preflight, auto-free
                                CubeSandbox host ports if busy: SSH (10022),
                                CubeMaster API (23000), proxy HTTP (21080),
                                proxy HTTPS (21443), WebUI (22088). Stops
                                publishing Docker containers, then
                                SIGTERM/SIGKILL host processes via
                                lsof/ss/fuser. Reuses ARGUS_PORT_FREE_GRACE.
                                Default: true. Set to false to keep
                                cubesandbox's own lifecycle in charge of
                                these ports (script will fail loudly on
                                doctor's busy-port report instead).
  CUBE_DISABLE_WEBUI            Skip CubeSandbox WebUI (host port 22088, guest
                                12088). When true (default), quickstart.sh
                                patches dev-env/run_vm.sh after each
                                fetch_upstream to drop the WebUI hostfwd, and
                                doctor / port-auto-free skip 22088 entirely
                                (guest WebUI service still runs in-VM but is
                                not exposed to the host). Set to false to
                                restore the WebUI host port forward.

CubeSandbox host-side bootstrap (WSL2-native):
  By default argus-bootstrap.sh runs scripts/cubesandbox-quickstart.sh
  doctor -> prepare-vm -> run-vm-background -> install ->
  provision-codeql-cpp-template before starting Compose. Each step is
  idempotent and skipped when its readiness check passes (SSH port for the VM,
  CubeMaster API health for the install, non-empty CUBESANDBOX_TEMPLATE_ID
  in .env for the template).

  --skip-cubesandbox             Skip host-side cubesandbox bootstrap entirely.
  --cubesandbox-only             Only run the cubesandbox bootstrap; skip
                                 Compose cleanup/start/follow.
  --cubesandbox-reset            Clear CUBESANDBOX_TEMPLATE_ID in .env before
                                 ensure_cubesandbox so the next run re-provisions
                                 the CodeQL C/C++ template. Does not touch the VM.
  --cubesandbox-status           Print host, .env toggles, VM SSH, CubeMaster API,
                                 and CodeQL template state, then exit. Read-only.
  ARGUS_SKIP_CUBESANDBOX=true    Same effect as --skip-cubesandbox.
  CUBESANDBOX_ENABLED=false      Disable cubesandbox in .env (also skips bootstrap).
  CUBESANDBOX_BOOTSTRAP_AUTO=false
                                 Disable host-side auto-bootstrap in .env.
  CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE=false
                                 Skip pre-provisioning the CodeQL C/C++ template
                                 (backend lazy-provisions on first scan instead).
  ARGUS_REQUIRE_CUBESANDBOX_TEMPLATES_READY=false
                                 Skip backend template reset/provision/readiness gate
                                 before starting frontend.
  ARGUS_CUBE_BOOTSTRAP_TIMEOUT   Per-step wait timeout in seconds. Default: 1800.

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

read_env_value() {
  local key="$1"
  [[ -f "$ARGUS_ENV_FILE" ]] || return 0
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
  ' "$ARGUS_ENV_FILE"
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
    ensure_secret_key
    return 0
  fi
  [[ -f "$ARGUS_ENV_EXAMPLE" ]] || fail "Root env template is missing: $ARGUS_ENV_EXAMPLE"
  cp "$ARGUS_ENV_EXAMPLE" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  ensure_secret_key
  log "Created .env from env.example: $ARGUS_ENV_FILE"
  cat >&2 <<MESSAGE
[argus-bootstrap] 已自动生成 SECRET_KEY；请填写 .env 中的 LLM 配置后再次运行 ./argus-bootstrap.sh。
[argus-bootstrap] 也可以先运行 ./scripts/validate-llm-config.sh --env-file ./.env 确认配置无误后再运行脚本。
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
    log "Dry-run/stub mode: skipping Docker daemon/tool preflight."
    return 0
  fi
  command -v docker >/dev/null 2>&1 || fail "docker CLI not found"
  docker compose version >/dev/null || fail "docker compose plugin is not available"
  docker info >/dev/null || fail "Docker daemon is not reachable"
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
  normalize_legacy_opengrep_image_env "SCANNER_OPENGREP_IMAGE"
  normalize_legacy_opengrep_image_env "SCANNER_OPENGREP_A3S_BOX_IMAGE"
  ensure_env_key_default \
    "CUBESANDBOX_BOOTSTRAP_AUTO" \
    "$CUBESANDBOX_BOOTSTRAP_AUTO_DEFAULT" \
    "Host-side bootstrap auto-build for CubeSandbox VM + install + CodeQL C/C++ template."
  ensure_env_key_default \
    "CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE" \
    "$CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE_DEFAULT" \
    "Pre-provision the CodeQL C/C++ template during bootstrap. Set to false to keep template lazy."
}

cubesandbox_enabled_in_env() {
  local val="${CUBESANDBOX_ENABLED:-}"
  if [[ -z "$val" ]]; then
    val="$(read_env_value CUBESANDBOX_ENABLED)"
  fi
  [[ -z "$val" ]] && val="true"
  is_truthy "$val"
}

cubesandbox_bootstrap_auto_in_env() {
  local val="${CUBESANDBOX_BOOTSTRAP_AUTO:-}"
  if [[ -z "$val" ]]; then
    val="$(read_env_value CUBESANDBOX_BOOTSTRAP_AUTO)"
  fi
  [[ -z "$val" ]] && val="$CUBESANDBOX_BOOTSTRAP_AUTO_DEFAULT"
  is_truthy "$val"
}

cubesandbox_bootstrap_provision_template_in_env() {
  local val="${CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE:-}"
  if [[ -z "$val" ]]; then
    val="$(read_env_value CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE)"
  fi
  [[ -z "$val" ]] && val="$CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE_DEFAULT"
  is_truthy "$val"
}

is_wsl2_host() {
  grep -qi microsoft /proc/version 2>/dev/null
}

cube_tcp_reachable() {
  local port="$1"
  ( exec 3<>"/dev/tcp/127.0.0.1/${port}" ) 2>/dev/null
}

cube_ssh_reachable() {
  # QEMU usernet (`-nic user,hostfwd=...`) accepts TCP on the host as soon as
  # the VM boots, well before guest sshd is listening — a pure TCP probe would
  # return "ready" too early, and the next install/ssh call would fail with
  # "Connection timed out during banner exchange". Connect once and wait for
  # the SSH banner ("SSH-2.0-...") to confirm guest sshd is actually up.
  local banner
  banner="$(
    exec 3<>"/dev/tcp/127.0.0.1/${CUBE_SSH_PORT_DEFAULT}" 2>/dev/null || exit 1
    IFS= read -r -t 4 banner <&3 2>/dev/null || true
    printf '%s' "${banner:-}"
  )"
  [[ "$banner" == SSH-* ]]
}

cube_api_healthy() {
  curl -fsS --max-time 5 "http://127.0.0.1:${CUBE_API_PORT_DEFAULT}/health" >/dev/null 2>&1
}

cube_template_id_from_env() {
  read_env_value CUBESANDBOX_TEMPLATE_ID
}

cube_run_quickstart() {
  local subcmd="$1"
  shift
  if [[ ! -x "$CUBE_QUICKSTART" ]]; then
    fail "cubesandbox quickstart helper not executable: $CUBE_QUICKSTART"
  fi
  if "$DRY_RUN"; then
    printf '[dry-run] %s %s' "$CUBE_QUICKSTART" "$subcmd"
    if [[ $# -gt 0 ]]; then
      printf ' %s' "$*"
    fi
    printf '\n'
    return 0
  fi
  log "cubesandbox: running $subcmd"
  "$CUBE_QUICKSTART" "$subcmd" "$@"
}

cube_doctor_or_fail() {
  if "$DRY_RUN"; then
    log "[dry-run] would run: $CUBE_QUICKSTART doctor"
    return 0
  fi
  if "$CUBE_QUICKSTART" doctor; then
    return 0
  fi
  fail "cubesandbox host preflight failed; review remediation hints above and re-run, or pass --skip-cubesandbox / set CUBESANDBOX_BOOTSTRAP_AUTO=false in .env to bring the rest of Argus up without cubesandbox."
}

cube_wait_for_predicate() {
  local label="$1"
  local predicate="$2"
  local timeout="$3"
  if "$DRY_RUN"; then
    log "[dry-run] would wait for cubesandbox $label"
    return 0
  fi
  local start now elapsed last_heartbeat=0
  start="$(date +%s)"
  log "cubesandbox: waiting up to ${timeout}s for $label..."
  while true; do
    if "$predicate"; then
      log "cubesandbox: $label reached."
      return 0
    fi
    now="$(date +%s)"
    elapsed=$((now - start))
    if (( elapsed - last_heartbeat >= 60 )); then
      log "cubesandbox: still waiting for $label (${elapsed}s/${timeout}s)..."
      last_heartbeat=$elapsed
    fi
    if (( elapsed >= timeout )); then
      fail "cubesandbox $label not reached within ${timeout}s."
    fi
    sleep "$CUBE_BOOTSTRAP_POLL_INTERVAL"
  done
}

cube_ensure_vm() {
  if cube_ssh_reachable; then
    log "cubesandbox: VM SSH already reachable on 127.0.0.1:${CUBE_SSH_PORT_DEFAULT}; skip prepare-vm/run-vm-background."
    return 0
  fi
  log "cubesandbox: VM not reachable; preparing OpenCloudOS image and starting QEMU in background."
  cube_run_quickstart prepare-vm
  cube_run_quickstart run-vm-background
  cube_wait_for_predicate "VM SSH (127.0.0.1:${CUBE_SSH_PORT_DEFAULT})" cube_ssh_reachable "$CUBE_BOOTSTRAP_TIMEOUT"
}

cube_ensure_install() {
  if cube_api_healthy; then
    log "cubesandbox: CubeMaster API already healthy on 127.0.0.1:${CUBE_API_PORT_DEFAULT}; skip install."
    return 0
  fi
  log "cubesandbox: CubeMaster API not yet healthy; running one-click install in VM (5-15 min on first run)."
  cube_run_quickstart install
  cube_wait_for_predicate "CubeMaster API (127.0.0.1:${CUBE_API_PORT_DEFAULT}/health)" cube_api_healthy "$CUBE_BOOTSTRAP_TIMEOUT"
}

# Source cubesandbox lib (double-source guard is inside the lib itself).
# shellcheck source=scripts/cubesandbox-lib.sh
[[ -z "${CUBESANDBOX_LIB_LOADED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/scripts/cubesandbox-lib.sh"

cube_persist_template_id() {
  local id="$1"
  local tmp
  tmp="$(mktemp "${ARGUS_ENV_FILE}.tmp.XXXXXX")"
  awk -v id="$id" '
    BEGIN { replaced = 0 }
    /^[[:space:]]*CUBESANDBOX_TEMPLATE_ID[[:space:]]*=/ {
      print "CUBESANDBOX_TEMPLATE_ID=" id
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) {
        print "CUBESANDBOX_TEMPLATE_ID=" id
      }
    }
  ' "$ARGUS_ENV_FILE" > "$tmp"
  mv "$tmp" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  log "Persisted CUBESANDBOX_TEMPLATE_ID=${id} in ${ARGUS_ENV_FILE}."
}

cube_persist_opengrep_template_id() {
  local id="$1"
  local tmp
  tmp="$(mktemp "${ARGUS_ENV_FILE}.tmp.XXXXXX")"
  awk -v id="$id" '
    BEGIN { replaced = 0 }
    /^[[:space:]]*CUBESANDBOX_OPENGREP_TEMPLATE_ID[[:space:]]*=/ {
      print "CUBESANDBOX_OPENGREP_TEMPLATE_ID=" id
      replaced = 1
      next
    }
    { print }
    END {
      if (!replaced) {
        print "CUBESANDBOX_OPENGREP_TEMPLATE_ID=" id
      }
    }
  ' "$ARGUS_ENV_FILE" > "$tmp"
  mv "$tmp" "$ARGUS_ENV_FILE"
  chmod 600 "$ARGUS_ENV_FILE" 2>/dev/null || true
  log "Persisted CUBESANDBOX_OPENGREP_TEMPLATE_ID=${id} in ${ARGUS_ENV_FILE}."
}

cube_inventory_templates() {
  local zombie_hours="${ARGUS_CUBE_INVENTORY_ZOMBIE_HOURS:-6}"
  log "cube inventory: scanning templates (zombie_hours=${zombie_hours})..."

  # Read .env-pinned IDs up-front — used for fallback kind-detection and
  # inviolability guard (MAJOR #1 and MAJOR #2).
  local env_pin_codeql env_pin_opengrep
  env_pin_codeql="$(read_env_value CUBESANDBOX_TEMPLATE_ID)"
  env_pin_opengrep="$(read_env_value CUBESANDBOX_OPENGREP_TEMPLATE_ID)"

  local raw_json
  raw_json="$(cubesandbox_template_list --json 2>&1)" || {
    fail "cube inventory: cubemastercli tpl list failed (rc=$?); cannot proceed."
  }

  local winners
  winners="$(python3 - "$zombie_hours" "$env_pin_codeql" "$env_pin_opengrep" <<'PYEOF'
import sys, json, datetime, re

zombie_hours = float(sys.argv[1])
env_pin_codeql  = sys.argv[2] if len(sys.argv) > 2 else ""
env_pin_opengrep = sys.argv[3] if len(sys.argv) > 3 else ""
now = datetime.datetime.utcnow()

raw = sys.stdin.read().strip()
# Attempt JSON parse; if not JSON, treat as tabular (no winner, just warn).
try:
    records = json.loads(raw)
except Exception:
    print("PARSE_FAIL", flush=True)
    sys.exit(0)

buckets = {"codeql_cpp": [], "opengrep": []}

# Build reverse map from env-pin id → kind for fallback detection
pin_to_kind = {}
if env_pin_codeql:
    pin_to_kind[env_pin_codeql] = "codeql_cpp"
if env_pin_opengrep:
    pin_to_kind[env_pin_opengrep] = "opengrep"

kind_method = "substring"  # audit log: which path was taken

for r in records:
    image_ref = r.get("image_ref") or ""
    tid = r.get("template_id") or r.get("id") or ""
    status = (r.get("status") or "").upper()
    created_at_str = r.get("created_at") or ""

    # Determine kind from image_ref substring (AS-1 normal path)
    if "codeql" in image_ref:
        kind = "codeql_cpp"
    elif "opengrep" in image_ref:
        kind = "opengrep"
    else:
        # Fallback: match against .env-pinned IDs (MAJOR #1)
        if tid and tid in pin_to_kind:
            kind = pin_to_kind[tid]
            kind_method = "env-pin-fallback"
            print(f"WARNING:unknown_bucket_fallback tid={tid} image_ref={image_ref!r} kind_via_env_pin={kind}", flush=True)
        else:
            print(f"WARNING:unknown_bucket tid={tid} image_ref={image_ref!r} (no env-pin match; skipping)", flush=True)
            continue

    # Parse created_at
    created_at = None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            created_at = datetime.datetime.strptime(created_at_str[:26].rstrip("Z"), fmt.rstrip("Z"))
            break
        except Exception:
            pass

    age_hours = (now - created_at).total_seconds() / 3600.0 if created_at else 0.0

    # Determine action
    if status in ("FAILED", "INVALIDATED"):
        action = "delete"
    elif status in ("RUNNING", "BUILDING"):
        action = "delete" if age_hours >= zombie_hours else "keep"
    elif status == "READY":
        action = "candidate"  # ranked later
    else:
        action = "keep"  # unknown status: skip

    buckets[kind].append({
        "tid": tid, "status": status, "created_at": created_at,
        "created_at_str": created_at_str, "action": action,
    })

print(f"KIND_METHOD:{kind_method}", flush=True)

winner_codeql = ""
winner_opengrep = ""

for kind, entries in buckets.items():
    pin_id = env_pin_codeql if kind == "codeql_cpp" else env_pin_opengrep
    bad_pinned = False

    # Sort READY candidates newest-first
    ready = sorted(
        [e for e in entries if e["action"] == "candidate"],
        key=lambda e: e["created_at"] or datetime.datetime.min,
        reverse=True,
    )
    # Winner = rank 0 (newest READY)
    if ready:
        winner = ready[0]
        if kind == "codeql_cpp":
            winner_codeql = winner["tid"]
        else:
            winner_opengrep = winner["tid"]
        # surplus READY → delete
        for surplus in ready[1:]:
            print(f"DELETE:{surplus['tid']}", flush=True)

    # Emit deletes for FAILED + INVALIDATED + zombies; flag pin if its target is FAILED/INVALIDATED
    for e in entries:
        if e["action"] == "delete":
            print(f"DELETE:{e['tid']}", flush=True)
            if pin_id and e["tid"] == pin_id and e["status"] in ("FAILED", "INVALIDATED"):
                bad_pinned = True

    if bad_pinned:
        print(f"CLEAR_PIN:{kind}", flush=True)

print(f"WINNER_CODEQL:{winner_codeql}", flush=True)
print(f"WINNER_OPENGREP:{winner_opengrep}", flush=True)
PYEOF
  <<< "$raw_json")" || {
    fail "cube inventory: Python parse step failed (rc=$?)."
  }

  # Check for parse failure (tabular fallback)
  if grep -q '^PARSE_FAIL' <<< "$winners"; then
    log "WARNING: cube inventory: tpl list output was not JSON; skipping inventory (tabular mode not supported for deletion)."
    return 0
  fi

  # Log which kind-detection path was taken (audit trail for MAJOR #1)
  local kind_method
  kind_method="$(grep '^KIND_METHOD:' <<< "$winners" | cut -d: -f2-)"
  log "cube inventory: kind-detection method=${kind_method:-unknown}"

  # Emit warnings for unknown buckets
  while IFS= read -r line; do
    [[ "$line" == WARNING:* ]] && log "WARNING: cube inventory: ${line#WARNING:}"
  done <<< "$winners"

  # Process CLEAR_PIN markers FIRST: when the .env-pinned template is FAILED or
  # INVALIDATED it must be deleted, so clear the pin so the inviolability guard
  # below does not refuse the delete. This handles the common shutdown→bootstrap
  # cycle where prior templates come back as INVALIDATED.
  while IFS= read -r line; do
    if [[ "$line" == CLEAR_PIN:* ]]; then
      case "${line#CLEAR_PIN:}" in
        codeql_cpp)
          if [[ -n "$env_pin_codeql" ]]; then
            log "cube inventory: pinned codeql template ${env_pin_codeql} is FAILED/INVALIDATED; clearing CUBESANDBOX_TEMPLATE_ID before delete."
            cube_persist_template_id ""
            env_pin_codeql=""
          fi
          ;;
        opengrep)
          if [[ -n "$env_pin_opengrep" ]]; then
            log "cube inventory: pinned opengrep template ${env_pin_opengrep} is FAILED/INVALIDATED; clearing CUBESANDBOX_OPENGREP_TEMPLATE_ID before delete."
            cube_persist_opengrep_template_id ""
            env_pin_opengrep=""
          fi
          ;;
      esac
    fi
  done <<< "$winners"

  # Process deletes — with env-pin inviolability guard (MAJOR #2)
  while IFS= read -r line; do
    if [[ "$line" == DELETE:* ]]; then
      local tid="${line#DELETE:}"
      # Inviolability guard: never delete a template that is currently pinned in .env
      if [[ -n "$env_pin_codeql"   && "$tid" == "$env_pin_codeql"   ]]; then
        log "WARNING: cube inventory: refusing to delete .env-pinned template ${tid} (kind=codeql_cpp); use shutdown --hard if you really want this gone."
        continue
      fi
      if [[ -n "$env_pin_opengrep" && "$tid" == "$env_pin_opengrep" ]]; then
        log "WARNING: cube inventory: refusing to delete .env-pinned template ${tid} (kind=opengrep); use shutdown --hard if you really want this gone."
        continue
      fi
      log "cube inventory: deleting template ${tid}..."
      local rc=0
      cubesandbox_template_delete "$tid" || rc=$?
      if [[ $rc -eq 2 ]]; then
        log "WARNING: cube inventory: delete ${tid} rejected (unsafe ID, rc=2); continuing."
      elif [[ $rc -ne 0 ]]; then
        log "WARNING: cube inventory: delete ${tid} returned rc=${rc}; continuing."
      fi
    fi
  done <<< "$winners"

  # Persist winners to .env
  local winner_codeql winner_opengrep
  winner_codeql="$(grep '^WINNER_CODEQL:' <<< "$winners" | cut -d: -f2-)"
  winner_opengrep="$(grep '^WINNER_OPENGREP:' <<< "$winners" | cut -d: -f2-)"

  if [[ -n "$winner_codeql" ]]; then
    log "cube inventory: codeql_cpp winner=${winner_codeql}"
    cube_persist_template_id "$winner_codeql"
  else
    log "cube inventory: no READY codeql_cpp template found; .env unchanged."
  fi

  if [[ -n "$winner_opengrep" ]]; then
    log "cube inventory: opengrep winner=${winner_opengrep}"
    cube_persist_opengrep_template_id "$winner_opengrep"
  else
    log "cube inventory: no READY opengrep template found; .env unchanged."
  fi

  log "cube inventory: done."
}


cube_refresh_template_pins_from_inventory() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    return 0
  fi
  if ! cube_api_healthy; then
    return 0
  fi
  cube_inventory_templates
}

cube_reset_template_id() {
  local current
  current="$(cube_template_id_from_env)"
  if [[ -z "$current" ]] || is_placeholder_value "$current"; then
    log "cubesandbox: --cubesandbox-reset noop (CUBESANDBOX_TEMPLATE_ID already empty)."
    return 0
  fi
  if "$DRY_RUN"; then
    log "[dry-run] would clear CUBESANDBOX_TEMPLATE_ID=${current} in ${ARGUS_ENV_FILE} to force re-provision."
    return 0
  fi
  log "cubesandbox: --cubesandbox-reset clearing CUBESANDBOX_TEMPLATE_ID=${current}; next provision will create a new template."
  cube_persist_template_id ""
}

cube_ensure_template() {
  if ! cubesandbox_bootstrap_provision_template_in_env; then
    log "cubesandbox: CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE=false; skipping template pre-provision (backend will lazy-provision on first CodeQL scan)."
    return 0
  fi
  local current
  current="$(cube_template_id_from_env)"
  if [[ -n "$current" ]] && ! is_placeholder_value "$current"; then
    log "cubesandbox: CodeQL C/C++ template already configured (${current}); skip provision."
    return 0
  fi
  log "cubesandbox: provisioning CodeQL C/C++ template (configure-docker-mirror -> start-local-registry -> build-codeql-cpp-image -> create-codeql-cpp-template -> watch). 10-30 min on first run."
  if "$DRY_RUN"; then
    printf '[dry-run] %s provision-codeql-cpp-template\n' "$CUBE_QUICKSTART"
    return 0
  fi
  local provision_log
  provision_log="$(mktemp -t argus-cube-provision.XXXXXX.log)"
  local provision_rc=0
  set +e
  "$CUBE_QUICKSTART" provision-codeql-cpp-template 2>&1 | tee "$provision_log"
  provision_rc=${PIPESTATUS[0]}
  set -e
  if (( provision_rc != 0 )); then
    rm -f "$provision_log"
    fail "cubesandbox provision-codeql-cpp-template exited with rc=${provision_rc}; see streamed output above."
  fi
  local template_id
  template_id="$(grep -E '^PROVISION_RESULT=' "$provision_log" \
    | tail -n 1 \
    | sed -E 's/^PROVISION_RESULT=//' \
    | python3 -c "import json, sys; data=json.load(sys.stdin); tid=data.get('template_id') or ''; sys.stdout.write(tid)" \
    2>/dev/null \
    || true)"
  rm -f "$provision_log"
  if [[ -z "$template_id" ]]; then
    fail "cubesandbox provision exited 0 but no template_id was parsed; inspect the streamed log above."
  fi
  cube_persist_template_id "$template_id"
}

cube_ensure_opengrep_template() {
  if ! cubesandbox_bootstrap_provision_template_in_env; then
    log "cubesandbox: CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE=false; skipping Opengrep template pre-provision (backend will lazy-provision on first Opengrep scan)."
    return 0
  fi
  local current
  current="$(read_env_value CUBESANDBOX_OPENGREP_TEMPLATE_ID)"
  if [[ -n "$current" ]] && ! is_placeholder_value "$current"; then
    log "cubesandbox: Opengrep template already configured (${current}); skip provision."
    return 0
  fi
  log "cubesandbox: provisioning Opengrep template (configure-docker-mirror -> start-local-registry -> build-opengrep-image -> create-opengrep-template -> watch). 5-15 min on first run."
  if "$DRY_RUN"; then
    printf '[dry-run] %s provision-opengrep-template\n' "$CUBE_QUICKSTART"
    return 0
  fi
  local provision_log
  provision_log="$(mktemp -t argus-cube-opengrep-provision.XXXXXX.log)"
  local provision_rc=0
  set +e
  "$CUBE_QUICKSTART" provision-opengrep-template 2>&1 | tee "$provision_log"
  provision_rc=${PIPESTATUS[0]}
  set -e
  if (( provision_rc != 0 )); then
    rm -f "$provision_log"
    fail "cubesandbox provision-opengrep-template exited with rc=${provision_rc}; see streamed output above."
  fi
  local template_id
  template_id="$(grep -E '^PROVISION_RESULT=' "$provision_log" \
    | tail -n 1 \
    | sed -E 's/^PROVISION_RESULT=//' \
    | python3 -c "import json, sys; data=json.load(sys.stdin); tid=data.get('template_id') or ''; sys.stdout.write(tid)" \
    2>/dev/null \
    || true)"
  rm -f "$provision_log"
  if [[ -z "$template_id" ]]; then
    fail "cubesandbox opengrep provision exited 0 but no template_id was parsed; inspect the streamed log above."
  fi
  cube_persist_opengrep_template_id "$template_id"
}

cube_status() {
  local enabled_state auto_state provision_state vm_state api_state template_state host_state template_id
  if is_wsl2_host; then host_state="WSL2"; else host_state="non-WSL2"; fi
  if cubesandbox_enabled_in_env; then enabled_state="enabled"; else enabled_state="disabled"; fi
  if cubesandbox_bootstrap_auto_in_env; then auto_state="auto-on"; else auto_state="auto-off"; fi
  if cubesandbox_bootstrap_provision_template_in_env; then provision_state="enabled"; else provision_state="disabled"; fi
  if cube_ssh_reachable; then vm_state="reachable (127.0.0.1:${CUBE_SSH_PORT_DEFAULT})"; else vm_state="not reachable (127.0.0.1:${CUBE_SSH_PORT_DEFAULT})"; fi
  if cube_api_healthy; then api_state="healthy (127.0.0.1:${CUBE_API_PORT_DEFAULT}/health)"; else api_state="not healthy (127.0.0.1:${CUBE_API_PORT_DEFAULT}/health)"; fi
  template_id="$(cube_template_id_from_env)"
  if [[ -n "$template_id" ]] && ! is_placeholder_value "$template_id"; then
    template_state="configured (${template_id})"
  else
    template_state="not configured"
  fi
  cat <<STATUS
[cubesandbox status]
  host:                   ${host_state}
  CUBESANDBOX_ENABLED:    ${enabled_state}
  bootstrap auto:         ${auto_state}
  template provision:     ${provision_state}
  VM SSH:                 ${vm_state}
  CubeMaster API:         ${api_state}
  CodeQL C/C++ template:  ${template_state}
STATUS
}

ensure_cubesandbox() {
  if "$SKIP_CUBESANDBOX"; then
    log "Skipping cubesandbox host-side bootstrap (--skip-cubesandbox or ARGUS_SKIP_CUBESANDBOX=true)."
    return 0
  fi
  if ! cubesandbox_enabled_in_env; then
    log "cubesandbox disabled in ${ARGUS_ENV_FILE} (CUBESANDBOX_ENABLED=false); skipping bootstrap."
    return 0
  fi
  if ! cubesandbox_bootstrap_auto_in_env; then
    log "cubesandbox host-side auto-bootstrap disabled (CUBESANDBOX_BOOTSTRAP_AUTO=false); run scripts/cubesandbox-quickstart.sh manually when ready."
    return 0
  fi
  if is_truthy "$STUB_DOCKER"; then
    log "Stub mode: skipping cubesandbox host-side bootstrap."
    return 0
  fi
  if "$DRY_RUN"; then
    log "Dry-run: skipping cubesandbox host-side bootstrap."
    return 0
  fi
  if ! is_wsl2_host; then
    log "cubesandbox host-side auto-bootstrap is only supported on WSL2 + KVM hosts. Detected non-WSL2 environment; skipping. Set CUBESANDBOX_BOOTSTRAP_AUTO=false in .env to silence this notice."
    return 0
  fi
  if [[ ! -x "$CUBE_QUICKSTART" ]]; then
    fail "cubesandbox quickstart helper not executable: $CUBE_QUICKSTART"
  fi
  log "cubesandbox host-side bootstrap: doctor -> VM -> install -> template (idempotent)."
  # Fast path: if a CubeSandbox VM is already healthy on this host (SSH banner
  # exchange + CubeMaster API health), the busy ports belong to OUR own VM —
  # don't let ensure_cube_ports_free SIGTERM it, don't let doctor fail on
  # those ports, and don't redo prepare-vm/install. Just run the idempotent
  # template provisioning (which itself skips when CUBESANDBOX_TEMPLATE_ID is
  # set and reachable).
  if cube_ssh_reachable && cube_api_healthy; then
    log "cubesandbox: VM already healthy (SSH banner OK, CubeMaster API OK); skipping doctor/VM/install, running template provisioning only."
    if "$RESET_CUBESANDBOX_TEMPLATE"; then
      cube_reset_template_id
    fi
    cube_inventory_templates
    cube_ensure_template
    cube_ensure_opengrep_template
    log "cubesandbox host-side bootstrap complete (fast path)."
    return 0
  fi
  ensure_cube_ports_free
  cube_doctor_or_fail
  cube_ensure_vm
  cube_ensure_install
  if "$RESET_CUBESANDBOX_TEMPLATE"; then
    cube_reset_template_id
  fi
  cube_inventory_templates
  cube_ensure_template
  cube_ensure_opengrep_template
  log "cubesandbox host-side bootstrap complete."
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

ensure_cube_ports_free() {
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Dry-run/stub: skipping cubesandbox busy-port auto-free."
    return 0
  fi
  if ! is_truthy "$CUBE_PORT_AUTO_FREE"; then
    log "CUBE_PORT_AUTO_FREE=false; leaving cubesandbox host ports to its own lifecycle (doctor will fail loudly if any are busy)."
    return 0
  fi
  local webui_msg
  if is_truthy "$CUBE_DISABLE_WEBUI"; then
    webui_msg="webui=skipped(CUBE_DISABLE_WEBUI=true)"
  else
    webui_msg="webui=${CUBE_WEB_UI_PORT_DEFAULT}"
  fi
  log "Preflight: ensuring CubeSandbox host ports are free (ssh=${CUBE_SSH_PORT_DEFAULT}, api=${CUBE_API_PORT_DEFAULT}, proxy-http=${CUBE_PROXY_HTTP_PORT_DEFAULT}, proxy-https=${CUBE_PROXY_HTTPS_PORT_DEFAULT}, ${webui_msg})."
  local hint="CUBE_PORT_AUTO_FREE=false"
  free_port_if_busy "$CUBE_SSH_PORT_DEFAULT"        "cubesandbox ssh"         "$hint"
  free_port_if_busy "$CUBE_API_PORT_DEFAULT"        "cubesandbox api"         "$hint"
  free_port_if_busy "$CUBE_PROXY_HTTP_PORT_DEFAULT" "cubesandbox proxy-http"  "$hint"
  free_port_if_busy "$CUBE_PROXY_HTTPS_PORT_DEFAULT" "cubesandbox proxy-https" "$hint"
  if ! is_truthy "$CUBE_DISABLE_WEBUI"; then
    free_port_if_busy "$CUBE_WEB_UI_PORT_DEFAULT"   "cubesandbox webui"       "$hint"
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

compose_up_backend_detached() {
  log "Starting Argus backend prerequisites detached (frontend is gated until CubeSandbox templates are ready)"
  run_cmd env \
    "ARGUS_ENV_FILE=$ARGUS_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build db redis backend
}

compose_up_frontend_detached() {
  log "Starting Argus frontend on port ${FRONTEND_PORT}"
  run_cmd env \
    "ARGUS_ENV_FILE=$ARGUS_ENV_FILE" \
    "ARGUS_RESET_IMPORT_TOKEN=$ARGUS_RESET_IMPORT_TOKEN" \
    docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" up -d --build frontend
}

build_runner_images() {
  log "Building Opengrep runner image without starting runner service containers."
  run_cmd docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" build opengrep-runner
}

a3s_box_opengrep_image_ref() {
  local image
  image="${SCANNER_OPENGREP_A3S_BOX_IMAGE:-}"
  [[ -z "$image" ]] && image="$(read_env_value SCANNER_OPENGREP_A3S_BOX_IMAGE)"
  [[ -z "$image" ]] && image="${SCANNER_OPENGREP_IMAGE:-}"
  [[ -z "$image" ]] && image="$(read_env_value SCANNER_OPENGREP_IMAGE)"
  [[ -z "$image" ]] && image="argus/opengrep-runner-local:latest"
  case "$image" in
    Argus/opengrep-runner-local:latest) image="argus/opengrep-runner-local:latest" ;;
    Argus/opengrep-runner:latest) image="argus/opengrep-runner:latest" ;;
  esac
  printf '%s' "$image"
}

load_a3s_box_opengrep_image() {
  local image legacy_source
  image="$(a3s_box_opengrep_image_ref)"
  legacy_source=""
  case "$image" in
    argus/*) legacy_source="Argus/${image#argus/}" ;;
  esac
  log "Ensuring backend A3S Box cache has OpenGrep image: ${image}"
  run_cmd docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" \
    exec -T backend sh -lc '
      set -eu
      runtime_home="${ARGUS_BACKEND_HOME:-/app/data/runtime/home}"
      mkdir -p "$runtime_home"
      chown appuser:appgroup "$runtime_home"
      chmod 0700 "$runtime_home"
      export HOME="$runtime_home"
      exec su -m -s /bin/sh appuser -c '"'"'
        set -eu
        image="$1"
        legacy_source="$2"
        inspect_file="/tmp/argus-a3s-opengrep-runner-inspect.$$"
        docker_tmp="/tmp/argus-a3s-opengrep-runner-docker.tar"
        oci_tmp="/tmp/argus-a3s-opengrep-runner-oci.tar"
        source_image="$image"
        source_image_id=""
        marker_dir="${HOME:-/app/data/runtime/home}/.a3s/argus/source-images"
        marker_name="$(printf "%s" "$image" | sed "s/[^A-Za-z0-9._-]/_/g")"
        marker_file="$marker_dir/${marker_name}.id"
        rootfs_marker_file="$marker_dir/${marker_name}.rootfs.id"
        trap "rm -f \"\$inspect_file\" \"\$docker_tmp\" \"\$oci_tmp\"" EXIT
        remove_a3s_rootfs_cache_for_image() {
          python3 - "$1" "${HOME:-/app/data/runtime/home}/.a3s/cache/rootfs" <<PYEOF
import json
import shutil
import sys
from pathlib import Path

image = sys.argv[1]
cache = Path(sys.argv[2])
if not cache.is_dir():
    raise SystemExit(0)

removed = 0
for meta_path in sorted(cache.glob("*.meta.json")):
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        continue
    if meta.get("description") != image:
        continue
    key = meta.get("key") or meta_path.name.removesuffix(".meta.json")
    rootfs_path = cache / key
    shutil.rmtree(rootfs_path, ignore_errors=True)
    meta_path.unlink(missing_ok=True)
    removed += 1

if removed:
    suffix = "y" if removed == 1 else "ies"
    print(f"Removed {removed} stale A3S Box rootfs cache entr{suffix} for {image}.")
PYEOF
        }
        sync_rootfs_marker() {
          if [ -n "$source_image_id" ]; then
            mkdir -p "$marker_dir"
            printf "%s\n" "$source_image_id" > "$rootfs_marker_file"
          fi
        }
        if source_image_id="$(docker image inspect --format "{{.Id}}" "$source_image" 2>/dev/null)"; then
          :
        elif [ -n "$legacy_source" ] && source_image_id="$(docker image inspect --format "{{.Id}}" "$legacy_source" 2>/dev/null)"; then
          source_image="$legacy_source"
        else
          source_image_id=""
        fi
        if [ -n "$source_image_id" ]; then
          rootfs_source_id=""
          if [ -f "$rootfs_marker_file" ]; then
            rootfs_source_id="$(cat "$rootfs_marker_file" 2>/dev/null || true)"
          fi
          if [ "$rootfs_source_id" != "$source_image_id" ]; then
            echo "A3S Box rootfs cache source changed or is untracked; clearing rootfs cache: $image"
            remove_a3s_rootfs_cache_for_image "$image"
            sync_rootfs_marker
          fi
        fi
        if a3s-box image-inspect "$image" >"$inspect_file" 2>/dev/null; then
          digest="$(sed -n "s/.*\"Digest\"[[:space:]]*:[[:space:]]*\"sha256:\([0-9a-fA-F]\{64\}\)\".*/\1/p" "$inspect_file" | head -n 1)"
          cache_dir="${HOME:-/app/data/runtime/home}/.a3s/images/sha256/${digest}"
          if [ -n "$source_image_id" ]; then
            cached_source_id=""
            if [ -f "$marker_file" ]; then
              cached_source_id="$(cat "$marker_file" 2>/dev/null || true)"
            fi
            if [ "$cached_source_id" != "$source_image_id" ]; then
              echo "A3S Box image cache source changed or is untracked; reloading: $image"
              remove_a3s_rootfs_cache_for_image "$image"
              a3s-box rmi "$image" >/dev/null 2>&1 || true
              rm -f "$inspect_file"
            fi
          fi
        fi
        if [ -s "$inspect_file" ] && a3s-box image-inspect "$image" >"$inspect_file" 2>/dev/null; then
          digest="$(sed -n "s/.*\"Digest\"[[:space:]]*:[[:space:]]*\"sha256:\([0-9a-fA-F]\{64\}\)\".*/\1/p" "$inspect_file" | head -n 1)"
          cache_dir="${HOME:-/app/data/runtime/home}/.a3s/images/sha256/${digest}"
          if [ -z "$digest" ] || [ ! -d "$cache_dir" ]; then
            echo "A3S Box image already cached: $image"
            exit 0
          fi
          if [ ! -f "$cache_dir/manifest.json" ] &&
             [ ! -f "$cache_dir/repositories" ] &&
             ! grep -R -E "\"mediaType\"[[:space:]]*:[[:space:]]*\"application/vnd\\.(oci|docker)\\.image\\.(layer\\.v1|rootfs\\.diff)\\.tar\"" "$cache_dir/blobs/sha256" >/dev/null 2>&1; then
            echo "A3S Box image already cached: $image"
            exit 0
          fi
          echo "A3S Box image cache uses Docker/uncompressed layers; reloading as A3S-compatible OCI: $image"
          remove_a3s_rootfs_cache_for_image "$image"
          a3s-box rmi "$image" >/dev/null 2>&1 || true
        fi
        rm -f "$inspect_file"
        if a3s-box image-inspect "$image" >/dev/null 2>&1; then
          echo "A3S Box image already cached: $image"
          exit 0
        fi
        source_image="$image"
        if ! docker image inspect "$source_image" >/dev/null 2>&1; then
          if [ -n "$legacy_source" ] && docker image inspect "$legacy_source" >/dev/null 2>&1; then
            source_image="$legacy_source"
            if [ -z "$source_image_id" ]; then
              source_image_id="$(docker image inspect --format "{{.Id}}" "$legacy_source" 2>/dev/null || true)"
            fi
          else
            echo "Docker image not available for A3S Box cache: $image" >&2
            exit 1
          fi
        fi
        rm -f "$docker_tmp" "$oci_tmp"
        docker save "$source_image" -o "$docker_tmp"
        echo "Converting Docker image archive to A3S-compatible OCI archive for A3S Box."
        python3 - "$docker_tmp" "$oci_tmp" <<PYEOF
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
work = Path(tempfile.mkdtemp(prefix="argus-a3s-oci-"))

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def digest_hex(value: str) -> str:
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise RuntimeError(f"unsupported digest: {value}")
    digest = value[len(prefix):]
    if len(digest) != 64:
        raise RuntimeError(f"unsupported digest: {value}")
    return digest

def add_tree(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    archive.add(path, arcname=arcname, recursive=False)
    if path.is_dir():
        for child in sorted(path.iterdir()):
            add_tree(archive, child, f"{arcname}/{child.name}")

try:
    with tarfile.open(source, "r") as archive:
        archive.extractall(work)

    blobs = work / "blobs" / "sha256"
    index_path = work / "index.json"
    index = json.loads(index_path.read_text())
    for manifest_entry in index.get("manifests", []):
        manifest_path = blobs / digest_hex(manifest_entry["digest"])
        manifest = json.loads(manifest_path.read_text())
        changed = False
        for layer in manifest.get("layers", []):
            if layer.get("mediaType") not in {
                "application/vnd.oci.image.layer.v1.tar",
                "application/vnd.docker.image.rootfs.diff.tar",
            }:
                continue
            layer_path = blobs / digest_hex(layer["digest"])
            raw = layer_path.read_bytes()
            buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as gz:
                gz.write(raw)
            compressed = buffer.getvalue()
            compressed_digest = sha256_hex(compressed)
            compressed_path = blobs / compressed_digest
            compressed_path.write_bytes(compressed)
            if compressed_path != layer_path:
                layer_path.unlink(missing_ok=True)
            layer["mediaType"] = "application/vnd.oci.image.layer.v1.tar+gzip"
            layer["digest"] = f"sha256:{compressed_digest}"
            layer["size"] = len(compressed)
            changed = True
        if changed:
            payload = json.dumps(manifest, separators=(",", ":")).encode()
            manifest_digest = sha256_hex(payload)
            updated_manifest_path = blobs / manifest_digest
            updated_manifest_path.write_bytes(payload)
            if updated_manifest_path != manifest_path:
                manifest_path.unlink(missing_ok=True)
            manifest_entry["digest"] = f"sha256:{manifest_digest}"
            manifest_entry["size"] = len(payload)

    index_path.write_text(json.dumps(index, separators=(",", ":")))
    for extra in ("manifest.json", "repositories"):
        (work / extra).unlink(missing_ok=True)

    target.unlink(missing_ok=True)
    with tarfile.open(target, "w") as archive:
        for name in ("oci-layout", "index.json", "blobs"):
            add_tree(archive, work / name, name)
finally:
    shutil.rmtree(work, ignore_errors=True)
PYEOF
        a3s-box load -i "$oci_tmp" -t "$image"
        rm -f "$docker_tmp" "$oci_tmp"
        a3s-box image-inspect "$image" >/dev/null
        if [ -n "$source_image_id" ]; then
          mkdir -p "$marker_dir"
          printf "%s\n" "$source_image_id" > "$marker_file"
          printf "%s\n" "$source_image_id" > "$rootfs_marker_file"
        fi
        echo "A3S Box image cached: $image"
      '"'"' sh "$1" "$2"
    ' sh "$image" "$legacy_source"
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

cubesandbox_template_status() {
  local api_kind="$1"
  curl -fsS --max-time 10 "${BACKEND_CUBESANDBOX_TEMPLATES_URL}/${api_kind}" \
    | python3 -c "import json,sys; print((json.loads(sys.stdin.read(), strict=False).get('status') or '').lower())"
}

backend_cubesandbox_template_cache_key() {
  local api_kind="$1"
  case "$api_kind" in
    codeql-cpp) printf 'CUBESANDBOX_TEMPLATE_ID' ;;
    opengrep) printf 'CUBESANDBOX_OPENGREP_TEMPLATE_ID' ;;
    *) fail "unknown backend CubeSandbox template kind: $api_kind" ;;
  esac
}

backend_cubesandbox_template_cache_hit() {
  local label="$1"
  local api_kind="$2"
  local env_key cached_id
  env_key="$(backend_cubesandbox_template_cache_key "$api_kind")"
  cached_id="$(read_env_value "$env_key")"
  if [[ -z "$cached_id" ]] || is_placeholder_value "$cached_id"; then
    return 1
  fi
  log "cubesandbox: backend ${label} cache hit candidate ${env_key}=${cached_id}; requesting provision endpoint to adopt it if DB state is absent."
  provision_backend_cubesandbox_template "$api_kind"
  return 0
}

reset_backend_cubesandbox_template() {
  local api_kind="$1"
  log "cubesandbox: backend reset requested for ${api_kind} template."
  curl -fsS --max-time 30 -X POST "${BACKEND_CUBESANDBOX_TEMPLATES_URL}/${api_kind}/reset" >/dev/null
}

provision_backend_cubesandbox_template() {
  local api_kind="$1"
  log "cubesandbox: backend provision requested for ${api_kind} template."
  curl -fsS --max-time 30 -X POST "${BACKEND_CUBESANDBOX_TEMPLATES_URL}/${api_kind}/provision" >/dev/null
}

wait_for_backend_cubesandbox_template_ready() {
  local label="$1"
  local api_kind="$2"
  local start now elapsed status
  start="$(date +%s)"
  log "cubesandbox: waiting up to ${CUBE_BOOTSTRAP_TIMEOUT}s for backend ${label} template ready..."
  while true; do
    status="$(cubesandbox_template_status "$api_kind" 2>/dev/null || true)"
    if [[ "$status" == "ready" ]]; then
      log "cubesandbox: backend ${label} template ready."
      return 0
    fi
    if [[ "$status" == "failed" || "$status" == "invalidated" ]]; then
      log "cubesandbox: backend ${label} template is ${status}; resetting."
      reset_backend_cubesandbox_template "$api_kind"
    elif [[ "$status" == "absent" || -z "$status" ]]; then
      log "cubesandbox: backend ${label} template is ${status:-unreachable/unknown}; checking CubeSandbox cache before rebuilding."
      cube_refresh_template_pins_from_inventory
      if ! backend_cubesandbox_template_cache_hit "$label" "$api_kind"; then
        log "cubesandbox: backend ${label} template has no cache hit; provisioning."
        provision_backend_cubesandbox_template "$api_kind"
      fi
    fi
    now="$(date +%s)"
    elapsed=$((now - start))
    if (( elapsed >= CUBE_BOOTSTRAP_TIMEOUT )); then
      fail "backend ${label} CubeSandbox template did not become ready within ${CUBE_BOOTSTRAP_TIMEOUT}s (last status=${status:-unknown})."
    fi
    sleep "$CUBE_BOOTSTRAP_POLL_INTERVAL"
  done
}

ensure_backend_cubesandbox_templates_ready() {
  if ! is_truthy "$ARGUS_REQUIRE_CUBESANDBOX_TEMPLATES_READY"; then
    log "Skipping backend CubeSandbox template readiness gate (ARGUS_REQUIRE_CUBESANDBOX_TEMPLATES_READY=false)."
    return 0
  fi
  if "$SKIP_CUBESANDBOX" || ! cubesandbox_enabled_in_env; then
    log "Skipping backend CubeSandbox template readiness gate because CubeSandbox bootstrap is disabled/skipped."
    return 0
  fi
  if ! cubesandbox_bootstrap_provision_template_in_env; then
    log "Skipping backend CubeSandbox template readiness gate because CUBESANDBOX_BOOTSTRAP_PROVISION_TEMPLATE=false."
    return 0
  fi
  if "$DRY_RUN" || is_truthy "$STUB_DOCKER"; then
    log "Stub/dry-run: would reset failed/invalidated backend CodeQL and OpenGrep templates, then wait for ready before frontend start."
    return 0
  fi
  wait_for_backend_cubesandbox_template_ready "CodeQL C/C++" "codeql-cpp"
  wait_for_backend_cubesandbox_template_ready "OpenGrep" "opengrep"
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
  build_runner_images
  compose_up_backend_detached
  wait_for_backend
  load_a3s_box_opengrep_image
  import_backend_env
  ensure_backend_cubesandbox_templates_ready
  compose_up_frontend_detached
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
      --skip-cubesandbox)
        SKIP_CUBESANDBOX=true
        shift
        ;;
      --cubesandbox-only)
        CUBESANDBOX_ONLY=true
        shift
        ;;
      --cubesandbox-reset)
        RESET_CUBESANDBOX_TEMPLATE=true
        shift
        ;;
      --cubesandbox-status)
        CUBESANDBOX_STATUS=true
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
  if "$CUBESANDBOX_STATUS"; then
    print_banner
    cube_status
    return 0
  fi
  print_banner
  log "Argus bootstrap beginning. Project: $PROJECT_NAME"
  log "Run mode: $RUN_MODE"
  if "$CUBESANDBOX_ONLY"; then
    log "--cubesandbox-only: bootstrapping CubeSandbox runtime only; skipping LLM validation and Compose lifecycle."
    ensure_root_env_file
    ensure_root_env_keys
    ensure_cubesandbox
    log "cubesandbox-only bootstrap complete."
    return 0
  fi
  validate_llm_config
  ensure_root_env_keys
  require_real_tools
  generate_import_token
  cleanup_for_run_mode
  ensure_argus_ports_free
  ensure_cubesandbox
  start_stack
}

main "$@"
