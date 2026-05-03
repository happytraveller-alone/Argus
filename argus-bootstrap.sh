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

# CubeSandbox host-side bootstrap configuration.
# These govern argus-bootstrap.sh's host-side preflight, VM startup, install,
# and CodeQL C/C++ template provisioning. They are independent of
# CUBESANDBOX_AUTO_START / CUBESANDBOX_AUTO_INSTALL in .env, which gate the
# backend's in-container lazy fallback.
CUBE_QUICKSTART="$ROOT_DIR/scripts/cubesandbox-quickstart.sh"
CUBE_SSH_PORT_DEFAULT="${CUBE_SSH_PORT:-10022}"
CUBE_API_PORT_DEFAULT="${CUBE_API_PORT:-23000}"
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
  Default:     docker compose up -d --build, poll backend, import LLM env, then docker compose logs -f
               Ctrl-C/SIGTERM stops the Compose stack before exiting.
  --wait-exit: docker compose up -d --build, poll backend, import LLM env, poll http://127.0.0.1:$FRONTEND_PORT, then exit

Ports:
  Argus_FRONTEND_PORT           Frontend host port. Default: 13000

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

ensure_root_env_keys() {
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
  cube_tcp_reachable "${CUBE_SSH_PORT_DEFAULT}"
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
  if ! is_wsl2_host; then
    log "cubesandbox host-side auto-bootstrap is only supported on WSL2 + KVM hosts. Detected non-WSL2 environment; skipping. Set CUBESANDBOX_BOOTSTRAP_AUTO=false in .env to silence this notice."
    return 0
  fi
  if [[ ! -x "$CUBE_QUICKSTART" ]]; then
    fail "cubesandbox quickstart helper not executable: $CUBE_QUICKSTART"
  fi
  log "cubesandbox host-side bootstrap: doctor -> VM -> install -> template (idempotent)."
  cube_doctor_or_fail
  cube_ensure_vm
  cube_ensure_install
  if "$RESET_CUBESANDBOX_TEMPLATE"; then
    cube_reset_template_id
  fi
  cube_ensure_template
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

build_runner_images() {
  log "Building Opengrep runner image without starting runner service containers."
  run_cmd docker compose --project-directory "$ROOT_DIR" --file "$COMPOSE_FILE" --project-name "$PROJECT_NAME" build opengrep-runner
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
  build_runner_images
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
  ensure_cubesandbox
  start_stack
}

main "$@"
