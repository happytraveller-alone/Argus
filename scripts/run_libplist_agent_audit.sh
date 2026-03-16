#!/usr/bin/env bash
set -euo pipefail

EXIT_DEPENDENCY_MISSING=2
EXIT_SERVICE_UNREADY=3
EXIT_API_OPERATION_FAILED=4
EXIT_TASK_FAILED=5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPO_URL="https://github.com/libimobiledevice/libplist.git"
BRANCH="master"
PROJECT_NAME="libplist"
API_BASE="http://localhost:8000/api/v1"
TASK_TIMEOUT=7200
POLL_INTERVAL=5
OUTPUT_DIR="${ROOT_DIR}/artifacts/libplist-audit/${TIMESTAMP}"
REBUILD_SANDBOX=false
AUTH_TOKEN="${VulHunter_AUTH_TOKEN:-${AUTH_TOKEN:-}}"

COMPOSE_BIN=()

log() {
  local level="$1"
  shift
  printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${level}" "$*" >&2
}

log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }

die() {
  local code="$1"
  shift
  log_error "$*"
  exit "${code}"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_libplist_agent_audit.sh [options]

Options:
  --repo-url <url>         Target repository URL
                           (default: https://github.com/libimobiledevice/libplist.git)
  --branch <name>          Target branch (default: master)
  --project-name <name>    Project name when creating project (default: libplist)
  --api-base <url>         API base URL (default: http://localhost:8000/api/v1)
  --task-timeout <sec>     Task timeout seconds (default: 7200)
  --poll-interval <sec>    Poll interval seconds (default: 5)
  --output-dir <path>      Output directory
                           (default: artifacts/libplist-audit/<timestamp>)
  --rebuild-sandbox        Force rebuild sandbox image
  --auth-token <token>     Optional bearer token
                           (or env: VulHunter_AUTH_TOKEN / AUTH_TOKEN)
  -h, --help               Show this help
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo-url)
        [[ $# -ge 2 ]] || die 1 "Missing value for --repo-url"
        REPO_URL="$2"
        shift 2
        ;;
      --branch)
        [[ $# -ge 2 ]] || die 1 "Missing value for --branch"
        BRANCH="$2"
        shift 2
        ;;
      --project-name)
        [[ $# -ge 2 ]] || die 1 "Missing value for --project-name"
        PROJECT_NAME="$2"
        shift 2
        ;;
      --api-base)
        [[ $# -ge 2 ]] || die 1 "Missing value for --api-base"
        API_BASE="$2"
        shift 2
        ;;
      --task-timeout)
        [[ $# -ge 2 ]] || die 1 "Missing value for --task-timeout"
        TASK_TIMEOUT="$2"
        shift 2
        ;;
      --poll-interval)
        [[ $# -ge 2 ]] || die 1 "Missing value for --poll-interval"
        POLL_INTERVAL="$2"
        shift 2
        ;;
      --output-dir)
        [[ $# -ge 2 ]] || die 1 "Missing value for --output-dir"
        OUTPUT_DIR="$2"
        shift 2
        ;;
      --rebuild-sandbox)
        REBUILD_SANDBOX=true
        shift
        ;;
      --auth-token)
        [[ $# -ge 2 ]] || die 1 "Missing value for --auth-token"
        AUTH_TOKEN="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die 1 "Unknown option: $1"
        ;;
    esac
  done
}

ensure_number() {
  local value="$1"
  local flag_name="$2"
  [[ "${value}" =~ ^[0-9]+$ ]] || die 1 "${flag_name} must be a positive integer"
}

normalize_repo_url() {
  local url="$1"
  url="$(printf '%s' "${url}" | tr '[:upper:]' '[:lower:]')"
  url="${url%/}"
  url="${url%.git}"
  printf '%s' "${url}"
}

detect_compose() {
  if ! command -v docker >/dev/null 2>&1; then
    die "${EXIT_DEPENDENCY_MISSING}" "Missing dependency: docker"
  fi
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return
  fi
  die "${EXIT_DEPENDENCY_MISSING}" "Missing dependency: docker compose (or docker-compose)"
}

check_dependencies() {
  detect_compose
  command -v curl >/dev/null 2>&1 || die "${EXIT_DEPENDENCY_MISSING}" "Missing dependency: curl"
  command -v jq >/dev/null 2>&1 || die "${EXIT_DEPENDENCY_MISSING}" "Missing dependency: jq"
}

compose_cmd() {
  "${COMPOSE_BIN[@]}" "$@"
}

api_call_json() {
  local method="$1"
  local endpoint="$2"
  local payload="${3:-}"
  local url="${API_BASE%/}${endpoint}"
  local body_file
  body_file="$(mktemp)"
  local http_code
  local -a headers=("-H" "Accept: application/json")
  if [[ -n "${AUTH_TOKEN}" ]]; then
    headers+=("-H" "Authorization: Bearer ${AUTH_TOKEN}")
  fi
  if [[ -n "${payload}" ]]; then
    headers+=("-H" "Content-Type: application/json")
    http_code="$(curl -sS -o "${body_file}" -w '%{http_code}' -X "${method}" "${url}" "${headers[@]}" --data "${payload}" || true)"
  else
    http_code="$(curl -sS -o "${body_file}" -w '%{http_code}' -X "${method}" "${url}" "${headers[@]}" || true)"
  fi
  if [[ ! "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
    log_error "API failed: ${method} ${url} (HTTP ${http_code})"
    if [[ -s "${body_file}" ]]; then
      log_error "Response: $(cat "${body_file}")"
    fi
    rm -f "${body_file}"
    return 1
  fi
  cat "${body_file}"
  rm -f "${body_file}"
}

api_download() {
  local endpoint="$1"
  local output_file="$2"
  local accept_header="$3"
  local url="${API_BASE%/}${endpoint}"
  local -a headers=("-H" "Accept: ${accept_header}")
  if [[ -n "${AUTH_TOKEN}" ]]; then
    headers+=("-H" "Authorization: Bearer ${AUTH_TOKEN}")
  fi
  local http_code
  http_code="$(curl -sS -L -o "${output_file}" -w '%{http_code}' "${url}" "${headers[@]}" || true)"
  if [[ ! "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
    log_error "Download failed: ${url} (HTTP ${http_code})"
    return 1
  fi
}

backend_health_url() {
  local base="${API_BASE%/}"
  if [[ "${base}" == */api/v1 ]]; then
    base="${base%/api/v1}"
  fi
  printf '%s/health' "${base}"
}

wait_for_http_ok() {
  local url="$1"
  local timeout_sec="$2"
  local label="$3"
  local start_epoch
  start_epoch="$(date +%s)"
  while true; do
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' "${url}" || true)"
    if [[ "${code}" == "200" ]]; then
      log_info "${label} is ready (${url})"
      return 0
    fi
    local now_epoch elapsed
    now_epoch="$(date +%s)"
    elapsed=$((now_epoch - start_epoch))
    if (( elapsed >= timeout_sec )); then
      return 1
    fi
    sleep 3
  done
}

start_services() {
  if [[ "${REBUILD_SANDBOX}" == "true" ]] || ! docker image inspect VulHunter/sandbox:latest >/dev/null 2>&1; then
    log_info "Building sandbox image (VulHunter/sandbox:latest)..."
    compose_cmd --profile build build sandbox || die "${EXIT_SERVICE_UNREADY}" "Failed to build sandbox image"
  else
    log_info "Sandbox image exists, skip rebuild"
  fi

  log_info "Starting core services..."
  compose_cmd up -d db redis backend || die "${EXIT_SERVICE_UNREADY}" "Failed to start required services"

  local backend_health
  backend_health="$(backend_health_url)"
  log_info "Waiting backend health: ${backend_health}"
  wait_for_http_ok "${backend_health}" 300 "Backend" || {
    log_error "Backend health timeout (300s)"
    log_error "Try inspect logs: ${COMPOSE_BIN[*]} logs --tail=200 backend"
    exit "${EXIT_SERVICE_UNREADY}"
  }

}

resolve_or_create_project() {
  local target_norm
  target_norm="$(normalize_repo_url "${REPO_URL}")"

  local projects_json
  projects_json="$(api_call_json GET "/projects/?limit=200")" || return 1

  local project_id
  project_id="$(jq -r --arg target "${target_norm}" '
    def norm_url: ascii_downcase | sub("/+$";"") | sub("\\.git$";"");
    (map(select((.repository_url // "") != ""))
      | map(select((.repository_url | norm_url) == $target))
      | first
      | .id) // empty
  ' <<<"${projects_json}")"

  if [[ -n "${project_id}" ]]; then
    log_info "Reusing existing project: ${project_id}"
    printf '%s' "${project_id}"
    return 0
  fi

  log_info "No reusable project found, creating new project..."
  local create_payload create_resp
  create_payload="$(jq -n \
    --arg name "${PROJECT_NAME}" \
    --arg repo "${REPO_URL}" \
    --arg branch "${BRANCH}" \
    '{
      name: $name,
      source_type: "repository",
      repository_url: $repo,
      repository_type: "github",
      default_branch: $branch
    }'
  )"
  create_resp="$(api_call_json POST "/projects/" "${create_payload}")" || return 1
  project_id="$(jq -r '.id // empty' <<<"${create_resp}")"
  if [[ -z "${project_id}" ]]; then
    log_error "Project creation response missing project id"
    return 1
  fi
  log_info "Project created: ${project_id}"
  printf '%s' "${project_id}"
}

create_agent_task() {
  local project_id="$1"
  local task_name="libplist-agent-audit-${TIMESTAMP}"
  local task_description="Automated intelligent audit for libplist (${REPO_URL}@${BRANCH})"
  local payload response task_id

  payload="$(jq -n \
    --arg project_id "${project_id}" \
    --arg name "${task_name}" \
    --arg description "${task_description}" \
    --arg branch_name "${BRANCH}" \
    --arg verification_level "analysis_with_poc_plan" \
    --argjson timeout_seconds "${TASK_TIMEOUT}" \
    '{
      project_id: $project_id,
      name: $name,
      description: $description,
      branch_name: $branch_name,
      verification_level: $verification_level,
      authorization_confirmed: true,
      timeout_seconds: $timeout_seconds
    }'
  )"

  response="$(api_call_json POST "/agent-tasks/" "${payload}")" || return 1
  task_id="$(jq -r '.id // empty' <<<"${response}")"
  if [[ -z "${task_id}" ]]; then
    log_error "Task creation response missing task id"
    return 1
  fi
  printf '%s' "${task_id}"
}

write_json_file() {
  local json_content="$1"
  local path="$2"
  if jq . >/dev/null 2>&1 <<<"${json_content}"; then
    jq . <<<"${json_content}" >"${path}"
  else
    printf '%s\n' "${json_content}" >"${path}"
  fi
}

poll_task_until_done() {
  local task_id="$1"
  local start_epoch
  start_epoch="$(date +%s)"
  local last_task_json=""

  while true; do
    local task_json
    task_json="$(api_call_json GET "/agent-tasks/${task_id}")" || return 1
    last_task_json="${task_json}"

    local status phase progress findings tokens
    status="$(jq -r '.status // "unknown"' <<<"${task_json}")"
    phase="$(jq -r '.current_phase // "-"' <<<"${task_json}")"
    progress="$(jq -r '.progress_percentage // 0' <<<"${task_json}")"
    findings="$(jq -r '.findings_count // 0' <<<"${task_json}")"
    tokens="$(jq -r '.tokens_used // 0' <<<"${task_json}")"

    log_info "Task ${task_id:0:8} status=${status} phase=${phase} progress=${progress}% findings=${findings} tokens=${tokens}"

    if [[ "${status}" == "completed" ]]; then
      printf '%s' "${last_task_json}"
      return 0
    fi

    if [[ "${status}" == "failed" || "${status}" == "cancelled" ]]; then
      mkdir -p "${OUTPUT_DIR}"
      write_json_file "${task_json}" "${OUTPUT_DIR}/task.json"
      local events_json='[]'
      if events_json="$(api_call_json GET "/agent-tasks/${task_id}/events/list?after_sequence=0&limit=100")"; then
        write_json_file "${events_json}" "${OUTPUT_DIR}/events_recent.json"
      fi
      log_error "Task ended with status=${status}, details saved: ${OUTPUT_DIR}"
      return 2
    fi

    local now_epoch elapsed
    now_epoch="$(date +%s)"
    elapsed=$((now_epoch - start_epoch))
    if (( elapsed >= TASK_TIMEOUT )); then
      mkdir -p "${OUTPUT_DIR}"
      log_warn "Task timeout reached (${TASK_TIMEOUT}s), sending cancel request..."
      api_call_json POST "/agent-tasks/${task_id}/cancel" >/dev/null || true
      write_json_file "${task_json}" "${OUTPUT_DIR}/task.json"
      local events_json='[]'
      if events_json="$(api_call_json GET "/agent-tasks/${task_id}/events/list?after_sequence=0&limit=100")"; then
        write_json_file "${events_json}" "${OUTPUT_DIR}/events_recent.json"
      fi
      log_error "Task timed out and was cancelled, details saved: ${OUTPUT_DIR}"
      return 3
    fi

    sleep "${POLL_INTERVAL}"
  done
}

export_outputs() {
  local task_id="$1"
  local final_task_json="$2"

  mkdir -p "${OUTPUT_DIR}"
  write_json_file "${final_task_json}" "${OUTPUT_DIR}/task.json"

  local findings_json
  findings_json="$(api_call_json GET "/agent-tasks/${task_id}/findings?limit=200")" || return 1
  write_json_file "${findings_json}" "${OUTPUT_DIR}/findings.json"

  api_download "/agent-tasks/${task_id}/report?format=markdown" "${OUTPUT_DIR}/report.md" "text/markdown" || return 1
  api_download "/agent-tasks/${task_id}/report?format=json" "${OUTPUT_DIR}/report.json" "application/json" || return 1
  return 0
}

print_summary() {
  local task_id="$1"
  local total critical high medium low

  if [[ -f "${OUTPUT_DIR}/report.json" ]] && jq . >/dev/null 2>&1 <"${OUTPUT_DIR}/report.json"; then
    total="$(jq -r '.summary.total_findings // (.findings | length) // 0' "${OUTPUT_DIR}/report.json")"
    critical="$(jq -r '.summary.severity_distribution.critical // 0' "${OUTPUT_DIR}/report.json")"
    high="$(jq -r '.summary.severity_distribution.high // 0' "${OUTPUT_DIR}/report.json")"
    medium="$(jq -r '.summary.severity_distribution.medium // 0' "${OUTPUT_DIR}/report.json")"
    low="$(jq -r '.summary.severity_distribution.low // 0' "${OUTPUT_DIR}/report.json")"
  else
    total="$(jq -r 'length // 0' "${OUTPUT_DIR}/findings.json" 2>/dev/null || printf '0')"
    critical="N/A"
    high="N/A"
    medium="N/A"
    low="N/A"
  fi

  printf '\n'
  printf '========== Audit Summary ==========\n'
  printf 'Task ID: %s\n' "${task_id}"
  printf 'Total findings: %s\n' "${total}"
  printf 'Severity distribution: critical=%s high=%s medium=%s low=%s\n' "${critical}" "${high}" "${medium}" "${low}"
  printf 'Output directory: %s\n' "${OUTPUT_DIR}"
  printf '===================================\n'
}

main() {
  parse_args "$@"
  ensure_number "${TASK_TIMEOUT}" "--task-timeout"
  ensure_number "${POLL_INTERVAL}" "--poll-interval"
  [[ "${TASK_TIMEOUT}" -gt 0 ]] || die 1 "--task-timeout must be > 0"
  [[ "${POLL_INTERVAL}" -gt 0 ]] || die 1 "--poll-interval must be > 0"

  API_BASE="${API_BASE%/}"
  if [[ "${OUTPUT_DIR}" != /* ]]; then
    OUTPUT_DIR="${ROOT_DIR}/${OUTPUT_DIR}"
  fi

  check_dependencies
  start_services

  log_info "Resolving project for repository: ${REPO_URL}"
  local project_id
  project_id="$(resolve_or_create_project)" || die "${EXIT_API_OPERATION_FAILED}" "Failed to resolve/create project"

  log_info "Creating agent task for project: ${project_id}"
  local task_id
  task_id="$(create_agent_task "${project_id}")" || die "${EXIT_API_OPERATION_FAILED}" "Failed to create agent task"
  log_info "Task created: ${task_id}"

  log_info "Polling task until completion (timeout=${TASK_TIMEOUT}s, interval=${POLL_INTERVAL}s)..."
  local final_task_json
  if ! final_task_json="$(poll_task_until_done "${task_id}")"; then
    die "${EXIT_TASK_FAILED}" "Task did not complete successfully"
  fi

  log_info "Task completed successfully, exporting report artifacts..."
  export_outputs "${task_id}" "${final_task_json}" || die "${EXIT_TASK_FAILED}" "Failed to export outputs"
  print_summary "${task_id}"
  log_info "Done"
}

main "$@"
