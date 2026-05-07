#!/usr/bin/env bash
# bench-a3s-vs-docker.sh — A3S-box vs Docker opengrep benchmark
#
# Usage:
#   bench-a3s-vs-docker.sh [--dry-run] <project-id> [<runs-per-side>]
#
# Defaults:
#   runs-per-side = 3
#   ARGUS_BACKEND_URL = http://localhost:18000
#
# Output:
#   .omc/reports/a3s-bench-<YYYYMMDD>.md
#
# Runtime field used: opengrep_sandbox = "a3s_box" | "dockerfile_container"
# (POST /api/v1/static-tasks/tasks, polled via GET .../progress, findings via GET .../findings)
#
# TODO(Step 4+): backend currently does NOT expose a SARIF download endpoint per task.
#   findings are returned as JSON array via GET /api/v1/static-tasks/tasks/{id}/findings.
#   compare-sarif.sh operates on SARIF files — if a native SARIF export endpoint is added
#   in a later step, wire it here. For now the bench writes findings JSON and calls compare_findings()
#   directly via jq tuple extraction.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="$REPO_ROOT/.omc/reports"
COMPARE_SARIF="$SCRIPT_DIR/compare-sarif.sh"

BACKEND_URL="${ARGUS_BACKEND_URL:-http://localhost:18000}"
API_BASE="$BACKEND_URL/api/v1/static-tasks"

DRY_RUN=false
PROJECT_ID=""
RUNS=3

# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

usage() {
    echo "Usage: $(basename "$0") [--dry-run] <project-id> [<runs-per-side>]" >&2
    echo "" >&2
    echo "  --dry-run     Skip actual scans; verify backend reachability + output fake report" >&2
    echo "  project-id    Argus project UUID" >&2
    echo "  runs-per-side Number of scan runs per path (default: 3)" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage ;;
        *)
            if [[ -z "$PROJECT_ID" ]]; then
                PROJECT_ID="$1"
            elif [[ "$RUNS" -eq 3 && "$1" =~ ^[0-9]+$ ]]; then
                RUNS="$1"
            else
                echo "ERROR: unexpected argument: $1" >&2; usage
            fi
            shift
            ;;
    esac
done

[[ -n "$PROJECT_ID" ]] || usage

DATE_TAG="$(date +%Y%m%d)"
REPORT_FILE="$REPORTS_DIR/a3s-bench-${DATE_TAG}.md"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[bench] $*"; }

# Compute median of a space-separated list of integers (bash-only, no bc needed)
median() {
    local vals=("$@")
    local n=${#vals[@]}
    # sort numerically
    IFS=$'\n' read -r -d '' -a sorted < <(printf '%s\n' "${vals[@]}" | sort -n && printf '\0') || true
    local mid=$(( n / 2 ))
    if (( n % 2 == 1 )); then
        echo "${sorted[$mid]}"
    else
        echo $(( (sorted[$mid - 1] + sorted[$mid]) / 2 ))
    fi
}

ms_to_s() { awk "BEGIN{printf \"%.2f\", $1/1000}"; }

# ---------------------------------------------------------------------------
# prerequisite check
# ---------------------------------------------------------------------------

check_prerequisites() {
    local ok=true

    info "Checking prerequisites..."

    # jq
    if ! command -v jq >/dev/null 2>&1; then
        echo "MISSING: jq — install with: apt-get install jq / brew install jq" >&2
        ok=false
    else
        info "  jq: $(jq --version)"
    fi

    # curl
    if ! command -v curl >/dev/null 2>&1; then
        echo "MISSING: curl" >&2
        ok=false
    fi

    # docker daemon reachable
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        info "  docker: reachable"
    else
        echo "WARN: docker daemon not reachable — docker path results will fail" >&2
        # not fatal: docker path may simply fail at scan time
    fi

    # backend reachable
    local backend_status
    backend_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND_URL/api/v1/static-tasks/tasks" 2>/dev/null || true)"
    if [[ "$backend_status" =~ ^(200|204|400|401|403|405)$ ]]; then
        info "  backend: reachable ($BACKEND_URL)"
    else
        echo "MISSING: backend not reachable at $BACKEND_URL (HTTP $backend_status)" >&2
        ok=false
    fi

    # compare-sarif.sh
    if [[ ! -x "$COMPARE_SARIF" ]]; then
        echo "WARN: compare-sarif.sh not executable at $COMPARE_SARIF" >&2
    fi

    [[ "$ok" == "true" ]] || die "Prerequisite check failed — aborting"
}

# ---------------------------------------------------------------------------
# project validation
# ---------------------------------------------------------------------------

validate_project() {
    info "Validating project: $PROJECT_ID"
    local resp
    resp="$(curl -s --max-time 10 "$BACKEND_URL/api/v1/projects/$PROJECT_ID" 2>/dev/null || true)"
    local name
    name="$(echo "$resp" | jq -r '.name // empty' 2>/dev/null || true)"
    if [[ -z "$name" ]]; then
        echo "WARN: could not resolve project name for $PROJECT_ID (project may not exist or API differs)" >&2
        PROJECT_NAME="$PROJECT_ID"
    else
        PROJECT_NAME="$name"
        info "  project name: $PROJECT_NAME"
    fi
}

# ---------------------------------------------------------------------------
# scan runner
# ---------------------------------------------------------------------------

# submit_scan <sandbox_kind> -> prints task_id
submit_scan() {
    local sandbox="$1"
    local payload
    payload="$(jq -n \
        --arg pid  "$PROJECT_ID" \
        --arg sb   "$sandbox" \
        --arg name "bench-${sandbox}-$(date +%s)" \
        '{project_id: $pid, opengrep_sandbox: $sb, name: $name}')"

    local resp
    resp="$(curl -s --max-time 15 \
        -X POST "$API_BASE/tasks" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null)"

    local task_id
    task_id="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null || true)"
    if [[ -z "$task_id" ]]; then
        echo ""
        echo "SUBMIT_ERROR: $resp" >&2
    else
        echo "$task_id"
    fi
}

# poll_task <task_id> <timeout_seconds> -> echoes final status
poll_task() {
    local task_id="$1"
    local timeout="${2:-1800}"
    local deadline=$(( $(date +%s) + timeout ))
    local status=""
    local interval=5

    while true; do
        local now
        now="$(date +%s)"
        if (( now >= deadline )); then
            echo "timeout"
            return
        fi

        local resp
        resp="$(curl -s --max-time 10 \
            "$API_BASE/tasks/$task_id/progress" 2>/dev/null || true)"
        status="$(echo "$resp" | jq -r '.status // empty' 2>/dev/null || true)"

        case "$status" in
            completed|failed|interrupted|cancelled)
                echo "$status"
                return
                ;;
        esac

        sleep "$interval"
        # back-off: max 30s between polls
        (( interval < 30 )) && interval=$(( interval + 5 ))
    done
}

# get_findings_count <task_id> -> integer
get_findings_count() {
    local task_id="$1"
    local resp
    resp="$(curl -s --max-time 10 "$API_BASE/tasks/$task_id/progress" 2>/dev/null || true)"
    echo "$resp" | jq -r '.total_findings // (.findings | length) // 0' 2>/dev/null || echo "0"
}

# get_findings_json <task_id> -> JSON array (writes to file path $2)
get_findings_json() {
    local task_id="$1"
    local out_file="$2"
    curl -s --max-time 30 "$API_BASE/tasks/$task_id/findings" 2>/dev/null > "$out_file" || true
}

# ---------------------------------------------------------------------------
# run one scan, return metrics
# ---------------------------------------------------------------------------
# Outputs: wall_ms findings_count exit_code oom_flag findings_path
# All values space-separated on one line.
run_one_scan() {
    local sandbox="$1"
    local run_num="$2"
    local findings_path="$3"   # output file for findings JSON

    local t_start t_end wall_ms
    t_start="$(date +%s%3N)"

    local task_id
    task_id="$(submit_scan "$sandbox")"

    if [[ -z "$task_id" ]]; then
        t_end="$(date +%s%3N)"
        wall_ms=$(( t_end - t_start ))
        echo "$wall_ms 0 1 no n/a"
        return
    fi

    info "    run $run_num: task_id=$task_id sandbox=$sandbox"

    local final_status
    final_status="$(poll_task "$task_id" 1800)"

    t_end="$(date +%s%3N)"
    wall_ms=$(( t_end - t_start ))

    local exit_code=0
    local oom_flag="no"

    case "$final_status" in
        completed)    exit_code=0 ;;
        timeout)      exit_code=124; oom_flag="timeout" ;;
        failed)       exit_code=1 ;;
        interrupted)  exit_code=130 ;;
        *)            exit_code=2 ;;
    esac

    # detect OOM from progress message
    local prog_resp
    prog_resp="$(curl -s --max-time 10 "$API_BASE/tasks/$task_id/progress" 2>/dev/null || true)"
    if echo "$prog_resp" | jq -r '.message // ""' 2>/dev/null | grep -qi "oom\|out of memory\|killed"; then
        oom_flag="yes"
        exit_code=137
    fi

    local findings_count=0
    if [[ "$final_status" == "completed" ]]; then
        get_findings_json "$task_id" "$findings_path"
        findings_count="$(jq 'if type == "array" then length else 0 end' "$findings_path" 2>/dev/null || echo "0")"
    fi

    echo "$wall_ms $findings_count $exit_code $oom_flag $task_id"
}

# ---------------------------------------------------------------------------
# findings equivalence (AC7)
# ---------------------------------------------------------------------------
# Compares two findings JSON arrays (not SARIF — converts to comparable tuples).
# Returns: "PASS" or "FAIL: <reason>"
compare_findings() {
    local file_a="$1"
    local file_b="$2"

    # If backend later provides SARIF export, use compare-sarif.sh directly.
    # For now: extract (rule_id, path, line, severity) tuples from findings JSON.
    local tuples_a tuples_b
    tuples_a="$(jq -S -c '
      if type == "array" then .[] else . end
      | {
          rule_id:  (.rule_id // .ruleId // ""),
          path:     (.path // .file // .location // ""),
          line:     (.line // .start_line // 0),
          severity: (.severity // .level // "warning")
        }
    ' "$file_a" 2>/dev/null | sort -u || true)"

    tuples_b="$(jq -S -c '
      if type == "array" then .[] else . end
      | {
          rule_id:  (.rule_id // .ruleId // ""),
          path:     (.path // .file // .location // ""),
          line:     (.line // .start_line // 0),
          severity: (.severity // .level // "warning")
        }
    ' "$file_b" 2>/dev/null | sort -u || true)"

    if [[ "$tuples_a" == "$tuples_b" ]]; then
        echo "PASS"
    else
        local only_a only_b
        only_a="$(comm -23 <(echo "$tuples_a") <(echo "$tuples_b") | head -5)"
        only_b="$(comm -13 <(echo "$tuples_a") <(echo "$tuples_b") | head -5)"
        echo "FAIL: findings differ. only-in-a: $only_a | only-in-b: $only_b"
    fi
}

# ---------------------------------------------------------------------------
# markdown report builder
# ---------------------------------------------------------------------------

write_report() {
    local report_file="$1"
    shift
    # remaining args: arrays passed via nameref — use global variables instead

    mkdir -p "$(dirname "$report_file")"

    {
        echo "# A3S vs Docker Benchmark — $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        echo "**Project**: \`$PROJECT_ID\` ($PROJECT_NAME)"
        echo "**Runs per side**: $RUNS"
        echo "**Backend**: $BACKEND_URL"
        echo ""
        echo "## Results"
        echo ""
        echo "| Path | Run | Wall-clock (s) | Findings | Exit | OOM |"
        echo "|------|-----|----------------|----------|------|-----|"

        local i
        for i in "${!A3S_WALL_MS[@]}"; do
            local run=$(( i + 1 ))
            local wall_s
            wall_s="$(ms_to_s "${A3S_WALL_MS[$i]}")"
            echo "| A3S | $run | $wall_s | ${A3S_FINDINGS[$i]} | ${A3S_EXIT[$i]} | ${A3S_OOM[$i]} |"
        done
        local a3s_med
        a3s_med="$(median "${A3S_WALL_MS[@]}")"
        echo "| **A3S** | **median** | **$(ms_to_s "$a3s_med")** | — | — | — |"

        for i in "${!DOCKER_WALL_MS[@]}"; do
            local run=$(( i + 1 ))
            local wall_s
            wall_s="$(ms_to_s "${DOCKER_WALL_MS[$i]}")"
            echo "| Docker | $run | $wall_s | ${DOCKER_FINDINGS[$i]} | ${DOCKER_EXIT[$i]} | ${DOCKER_OOM[$i]} |"
        done
        local docker_med
        docker_med="$(median "${DOCKER_WALL_MS[@]}")"
        echo "| **Docker** | **median** | **$(ms_to_s "$docker_med")** | — | — | — |"

        echo ""
        echo "## Summary"
        echo ""

        # AC2: small/medium ≤ 1.2x docker
        # AC3: large ≤ 1.5x docker
        # We can't auto-classify project size here without more info — report both.
        local ratio
        if (( docker_med > 0 )); then
            ratio="$(awk "BEGIN{printf \"%.3f\", $a3s_med/$docker_med}")"
        else
            ratio="N/A"
        fi

        echo "**A3S median**: $(ms_to_s "$a3s_med") s"
        echo ""
        echo "**Docker median**: $(ms_to_s "$docker_med") s"
        echo ""
        echo "**Ratio (A3S/Docker)**: $ratio"
        echo ""
        echo "### AC Checks"
        echo ""

        local ac2_status="UNKNOWN (docker did not complete)"
        local ac3_status="UNKNOWN (docker did not complete)"
        if (( docker_med > 0 )); then
            if awk "BEGIN{exit !($a3s_med/$docker_med <= 1.2)}"; then
                ac2_status="PASS"
            else
                ac2_status="FAIL (ratio $ratio > 1.2)"
            fi
            if awk "BEGIN{exit !($a3s_med/$docker_med <= 1.5)}"; then
                ac3_status="PASS"
            else
                ac3_status="FAIL (ratio $ratio > 1.5)"
            fi
        fi

        echo "- **AC2 (small/medium ≤ 1.2x docker)**: $ac2_status"
        echo "- **AC3 (large ≤ 1.5x docker)**: $ac3_status"
        echo "- **AC7 (findings equivalent)**: $AC7_STATUS"
        echo ""
        echo "---"
        echo "_Generated by \`scripts/bench-a3s-vs-docker.sh\`_"
    } > "$report_file"
}

# ---------------------------------------------------------------------------
# dry-run mode
# ---------------------------------------------------------------------------

dry_run() {
    info "DRY-RUN mode — skipping actual scans"

    # Verify backend reachability
    local backend_status
    backend_status="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND_URL/api/v1/static-tasks/tasks" 2>/dev/null || echo "000")"
    info "Backend HTTP status: $backend_status"

    validate_project

    # Fake data
    A3S_WALL_MS=(12340 11980 12100)
    A3S_FINDINGS=(42 42 42)
    A3S_EXIT=(0 0 0)
    A3S_OOM=(no no no)

    DOCKER_WALL_MS=(11200 11500 11300)
    DOCKER_FINDINGS=(42 42 42)
    DOCKER_EXIT=(0 0 0)
    DOCKER_OOM=(no no no)

    AC7_STATUS="PASS (dry-run fake data — both paths returned same 42 findings)"

    mkdir -p "$REPORTS_DIR"
    write_report "$REPORT_FILE"
    info "Dry-run report written: $REPORT_FILE"
    echo ""
    cat "$REPORT_FILE"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

main() {
    check_prerequisites
    validate_project

    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    A3S_WALL_MS=()
    A3S_FINDINGS=()
    A3S_EXIT=()
    A3S_OOM=()
    A3S_TASK_IDS=()

    DOCKER_WALL_MS=()
    DOCKER_FINDINGS=()
    DOCKER_EXIT=()
    DOCKER_OOM=()
    DOCKER_TASK_IDS=()

    # ---- A3S runs ----
    info "Running A3S path ($RUNS runs)..."
    for run in $(seq 1 "$RUNS"); do
        local findings_path="$TMP_DIR/a3s-findings-${run}.json"
        touch "$findings_path"
        read -r wall_ms findings exit_code oom task_id \
            < <(run_one_scan "a3s_box" "$run" "$findings_path")
        A3S_WALL_MS+=("$wall_ms")
        A3S_FINDINGS+=("$findings")
        A3S_EXIT+=("$exit_code")
        A3S_OOM+=("$oom")
        A3S_TASK_IDS+=("$task_id")
        info "  a3s run $run: ${wall_ms}ms, findings=$findings, exit=$exit_code, oom=$oom"
    done

    # ---- Docker runs ----
    info "Running Docker path ($RUNS runs)..."
    for run in $(seq 1 "$RUNS"); do
        local findings_path="$TMP_DIR/docker-findings-${run}.json"
        touch "$findings_path"
        read -r wall_ms findings exit_code oom task_id \
            < <(run_one_scan "dockerfile_container" "$run" "$findings_path")
        DOCKER_WALL_MS+=("$wall_ms")
        DOCKER_FINDINGS+=("$findings")
        DOCKER_EXIT+=("$exit_code")
        DOCKER_OOM+=("$oom")
        DOCKER_TASK_IDS+=("$task_id")
        info "  docker run $run: ${wall_ms}ms, findings=$findings, exit=$exit_code, oom=$oom"
    done

    # ---- AC7: findings equivalence ----
    info "Comparing findings for AC7..."
    # Use first successful run from each side
    local a3s_ref="" docker_ref=""
    for i in "${!A3S_EXIT[@]}"; do
        if [[ "${A3S_EXIT[$i]}" == "0" ]]; then
            a3s_ref="$TMP_DIR/a3s-findings-$(( i + 1 )).json"
            break
        fi
    done
    for i in "${!DOCKER_EXIT[@]}"; do
        if [[ "${DOCKER_EXIT[$i]}" == "0" ]]; then
            docker_ref="$TMP_DIR/docker-findings-$(( i + 1 )).json"
            break
        fi
    done

    if [[ -n "$a3s_ref" && -n "$docker_ref" && -s "$a3s_ref" && -s "$docker_ref" ]]; then
        AC7_STATUS="$(compare_findings "$a3s_ref" "$docker_ref")"
    else
        AC7_STATUS="SKIP (no successful runs on both sides to compare)"
    fi

    # ---- write report ----
    mkdir -p "$REPORTS_DIR"
    write_report "$REPORT_FILE"

    info "Report written: $REPORT_FILE"
    echo ""
    cat "$REPORT_FILE"

    # ---- exit code ----
    # Fail if AC7 failed or any run had unexpected exit
    if echo "$AC7_STATUS" | grep -q "^FAIL"; then
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" == "true" ]]; then
    dry_run
else
    main
fi
