#!/usr/bin/env bash
# scripts/compose-up-with-fallback.sh — 带镜像源探测与故障转移的 docker compose 包装脚本
#
# 用法:
#   ./scripts/compose-up-with-fallback.sh              # 等效于 docker compose up -d --build
#   ./scripts/compose-up-with-fallback.sh up           # 前台 attached 模式（服务 ready 后打印横幅）
#   ./scripts/compose-up-with-fallback.sh up -d --build
#   ./scripts/compose-up-with-fallback.sh down
#   ./scripts/compose-up-with-fallback.sh logs -f backend
#
# 核心功能:
#   1. 并行探测多个 DockerHub / GHCR / PyPI / NPM / APT 镜像源延迟，按响应速度排序
#   2. 按排序结果依次尝试（多 phase 故障转移），每个 phase 内部支持 PHASE_RETRY_COUNT 次重试
#   3. 前台 up 模式下，后台监测前端/后端 ready，就绪后打印访问地址
#   4. 可选通过 VULHUNTER_OPEN_BROWSER=1 在就绪后自动打开浏览器
#
# 关键环境变量（均可通过 export 覆盖，跳过自动探测）:
#   DOCKERHUB_LIBRARY_MIRROR        — 指定 DockerHub 镜像源（跳过探测）
#   GHCR_REGISTRY                   — 指定 GHCR 镜像源（跳过探测）
#   FRONTEND_NPM_REGISTRY           — 前端 NPM 镜像源
#   BACKEND_PYPI_INDEX_PRIMARY      — Backend PyPI 主索引
#   SANDBOX_PYPI_INDEX_PRIMARY      — Sandbox PyPI 主索引
#   PHASE_RETRY_COUNT               — 每个 phase 的最大重试次数（默认 3）
#   PROBE_ATTEMPTS                  — 每个候选镜像的探测次数（默认 3，取中位数）
#   VULHUNTER_READY_TIMEOUT_SECONDS — 等待服务就绪超时秒数（默认 900）
#   VULHUNTER_OPEN_BROWSER          — 设为 1 时服务就绪后自动打开浏览器

set -euo pipefail

# ─── 日志工具 ─────────────────────────────────────────────────────────────────
log_info() {
  echo "[INFO] $*"
}

# 输出到 stderr，用于后台探测子进程中不污染 stdout 的日志
log_info_err() {
  echo "[INFO] $*" >&2
}

log_warn() {
  echo "[WARN] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

# ─── Compose 命令检测 ─────────────────────────────────────────────────────────
# 优先使用 `docker compose`（插件形式），回退到独立的 docker-compose 二进制
detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return
  fi
  log_error "docker compose (or docker-compose) not found"
  exit 127
}

# ─── Compose 参数分析 ─────────────────────────────────────────────────────────
# 判断 compose 参数是否为"前台 up"（有 up 且没有 -d/--detach）
# 返回 0 表示是前台 up，返回 1 表示不是
compose_args_target_attached_up() {
  local -a args=("$@")
  local seen_up=0
  local idx=0
  local arg=""

  while [ "$idx" -lt "${#args[@]}" ]; do
    arg="${args[$idx]}"
    if [ "$seen_up" -eq 0 ]; do
      case "$arg" in
        up)
          seen_up=1
          ;;
        # 跳过带参数的选项（消耗下一个 token）
        -f|--file|--env-file|-p|--project-name|--project-directory|--profile|--ansi|--parallel)
          idx=$((idx + 1))
          ;;
        -*)
          ;;
        # 遇到非选项非 up 的位置参数，说明不是 up 子命令
        *)
          return 1
          ;;
      esac
    else
      case "$arg" in
        -d|--detach)
          return 1
          ;;
      esac
    fi
    idx=$((idx + 1))
  done

  [ "$seen_up" -eq 1 ]
}

# 判断 compose 参数是否为"后台 up"（有 up 且有 -d/--detach）
# 返回 0 表示是后台 up，返回 1 表示不是
compose_args_target_detached_up() {
  local -a args=("$@")
  local seen_up=0
  local idx=0
  local arg=""

  while [ "$idx" -lt "${#args[@]}" ]; do
    arg="${args[$idx]}"
    if [ "$seen_up" -eq 0 ]; then
      case "$arg" in
        up)
          seen_up=1
          ;;
        -f|--file|--env-file|-p|--project-name|--project-directory|--profile|--ansi|--parallel)
          idx=$((idx + 1))
          ;;
        -*)
          ;;
        *)
          return 1
          ;;
      esac
    else
      case "$arg" in
        -d|--detach)
          return 0
          ;;
      esac
    fi
    idx=$((idx + 1))
  done

  return 1
}

# 校验参数必须是正整数，否则打印错误并退出
require_positive_int() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1 ]; then
    log_error "${name} must be a positive integer, got: ${value}"
    exit 2
  fi
}

# ─── 服务就绪检测 ─────────────────────────────────────────────────────────────
# 轮询前端和后端 HTTP 健康端点，两者均返回 200 才算就绪
# 超时后返回 1
wait_for_services_ready() {
  if ! command -v curl >/dev/null 2>&1; then
    log_warn "curl not found; skipping readiness banner"
    return 2
  fi

  local deadline now
  local frontend_ready=0
  local backend_ready=0
  deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))

  while :; do
    if [ "$frontend_ready" -eq 0 ]; then
      if curl -fsS \
        --connect-timeout "$PROBE_CONNECT_TIMEOUT_SECONDS" \
        --max-time "$PROBE_TIMEOUT_SECONDS" \
        "$FRONTEND_READY_URL" >/dev/null 2>&1; then
        frontend_ready=1
      fi
    fi

    if [ "$backend_ready" -eq 0 ]; then
      if curl -fsS \
        --connect-timeout "$PROBE_CONNECT_TIMEOUT_SECONDS" \
        --max-time "$PROBE_TIMEOUT_SECONDS" \
        "$BACKEND_READY_URL" >/dev/null 2>&1; then
        backend_ready=1
      fi
    fi

    if [ "$frontend_ready" -eq 1 ] && [ "$backend_ready" -eq 1 ]; then
      return 0
    fi

    now="$(date +%s)"
    if [ "$now" -ge "$deadline" ]; then
      return 1
    fi

    sleep 2
  done
}

# ─── 浏览器打开 ───────────────────────────────────────────────────────────────
# 依次尝试 wslview / powershell.exe / xdg-open / open，取第一个可用的
open_browser_url() {
  local url="$1"
  local -a openers=(wslview powershell.exe xdg-open open)
  local command_name

  for command_name in "${openers[@]}"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      continue
    fi

    if [ "$command_name" = "powershell.exe" ]; then
      if powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1; then
        log_info "opened browser: ${url}"
        return 0
      fi
    elif "$command_name" "$url" >/dev/null 2>&1; then
      log_info "opened browser: ${url}"
      return 0
    fi
    log_warn "failed to open browser with ${command_name}"
  done

  log_warn "unable to find a working browser opener for ${url}"
  return 1
}

print_ready_banner() {
  local attached_mode="${1:-0}"
  log_info "services ready"
  log_info "frontend: ${FRONTEND_PUBLIC_URL}"
  log_info "backend docs: ${BACKEND_DOCS_URL}"
  if [ "$attached_mode" -eq 1 ]; then
    log_info "press Ctrl+C to stop containers"
  fi
}

notify_when_ready() {
  local attached_mode="${1:-0}"

  if wait_for_services_ready; then
    print_ready_banner "$attached_mode"
    if [ "${VULHUNTER_OPEN_BROWSER:-0}" = "1" ]; then
      open_browser_url "${FRONTEND_PUBLIC_URL}" || true
    fi
    return 0
  fi

  log_warn "timed out waiting for frontend/backend readiness after ${READY_TIMEOUT_SECONDS}s"
  return 1
}

# ─── CSV 工具函数 ─────────────────────────────────────────────────────────────
# 以下函数用于处理逗号分隔的镜像候选列表

# 去除字符串首尾空白
trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

first_csv_item() {
  local csv="$1"
  local item
  IFS=',' read -r item _ <<<"$csv"
  trim "$item"
}

second_csv_item() {
  local csv="$1"
  local _ item
  IFS=',' read -r _ item _ <<<"$csv"
  trim "$item"
}

csv_item_or_last() {
  local csv="$1"
  local index="$2"
  local -a items=()
  local raw
  IFS=',' read -r -a raw <<<"$csv"
  local it
  if [ "${#raw[@]}" -gt 0 ]; then
    for it in "${raw[@]}"; do
      it="$(trim "$it")"
      [ -n "$it" ] && items+=("$it")
    done
  fi
  if [ "${#items[@]}" -eq 0 ]; then
    return 1
  fi
  if [ "$index" -lt "${#items[@]}" ]; then
    printf '%s' "${items[$index]}"
  else
    printf '%s' "${items[$((${#items[@]} - 1))]}"
  fi
}

count_csv_items() {
  local csv="$1"
  local -a raw=()
  IFS=',' read -r -a raw <<<"$csv"
  local count=0
  local it
  if [ "${#raw[@]}" -gt 0 ]; then
    for it in "${raw[@]}"; do
      it="$(trim "$it")"
      [ -n "$it" ] && count=$((count + 1))
    done
  fi
  printf '%s' "$count"
}

dedupe_csv() {
  local csv="$1"
  local -a raw=()
  local -a dedup=()
  IFS=',' read -r -a raw <<<"$csv"
  local item
  if [ "${#raw[@]}" -gt 0 ]; then
    for item in "${raw[@]}"; do
      item="$(trim "$item")"
      [ -z "$item" ] && continue
      local seen=0
      local existing
      if [ "${#dedup[@]}" -gt 0 ]; then
        for existing in "${dedup[@]}"; do
          if [ "$existing" = "$item" ]; then
            seen=1
            break
          fi
        done
      fi
      [ "$seen" -eq 0 ] && dedup+=("$item")
    done
  fi
  local out=""
  local i
  for i in "${!dedup[@]}"; do
    if [ "$i" -gt 0 ]; then
      out+=","
    fi
    out+="${dedup[$i]}"
  done
  printf '%s' "$out"
}

# ─── 镜像探测 ─────────────────────────────────────────────────────────────────
# 根据镜像类型（dockerhub/ghcr/npm/pypi/apt）构造探测 URL
build_probe_url() {
  local kind="$1"
  local candidate="$2"
  local apt_codename="$3"
  case "$kind" in
    dockerhub)
      local host="${candidate%%/*}"
      if [ "$host" = "docker.io" ] || [ "$host" = "index.docker.io" ]; then
        host="docker.m.daocloud.io"
      fi
      printf 'https://%s/v2/' "$host"
      ;;
    ghcr)
      printf 'https://%s/v2/' "$candidate"
      ;;
    npm)
      printf '%s/-/ping' "${candidate%/}"
      ;;
    pypi)
      if [[ "$candidate" == */simple || "$candidate" == */simple/ ]]; then
        printf '%s' "$candidate"
      else
        printf '%s/simple/' "${candidate%/}"
      fi
      ;;
    apt)
      printf 'https://%s/debian/dists/%s/Release' "$candidate" "$apt_codename"
      ;;
    apt-security)
      printf 'https://%s/debian-security/dists/%s-security/Release' "$candidate" "$apt_codename"
      ;;
    *)
      return 1
      ;;
  esac
}

# 对单个 URL 做 PROBE_ATTEMPTS 次 curl 请求，返回响应时间中位数（秒）
# 所有请求均失败时返回 1
probe_median_seconds() {
  local url="$1"
  local -a samples=()
  local i output code total

  for ((i = 1; i <= PROBE_ATTEMPTS; i++)); do
    output="$(curl -L -o /dev/null -sS \
      --connect-timeout "$PROBE_CONNECT_TIMEOUT_SECONDS" \
      --max-time "$PROBE_TIMEOUT_SECONDS" \
      -w '%{http_code} %{time_total}' "$url" || true)"
    code="${output%% *}"
    total="${output##* }"

    if [[ "$code" =~ ^[0-9]{3}$ ]] && [ "$code" != "000" ] && [[ "$total" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
      samples+=("$total")
    fi
  done

  if [ "${#samples[@]}" -eq 0 ]; then
    return 1
  fi

  printf '%s\n' "${samples[@]}" | sort -g | awk '
    { a[NR]=$1 }
    END {
      if (NR == 0) exit 1;
      if (NR % 2 == 1) {
        printf "%.6f", a[(NR+1)/2];
      } else {
        printf "%.6f", (a[NR/2] + a[NR/2+1]) / 2;
      }
    }
  '
}

# 串行探测候选列表，按中位延迟排序后返回 CSV（最快优先）
# 探测失败的候选以延迟 9999 排在末尾（保留为兜底）
rank_candidates() {
  local kind="$1"
  local label="$2"
  local candidates_csv="$3"
  local apt_codename="$4"

  candidates_csv="$(dedupe_csv "$candidates_csv")"
  if [ -z "$candidates_csv" ]; then
    return 1
  fi

  local tmp
  tmp="$(mktemp)"
  local raw
  IFS=',' read -r -a raw <<<"$candidates_csv"

  local candidate url median
  if [ "${#raw[@]}" -gt 0 ]; then
    for candidate in "${raw[@]}"; do
      candidate="$(trim "$candidate")"
      [ -z "$candidate" ] && continue

      if ! url="$(build_probe_url "$kind" "$candidate" "$apt_codename")"; then
        continue
      fi

      if median="$(probe_median_seconds "$url")"; then
      log_info_err "probe ${label}: ${candidate} median=${median}s url=${url}"
      printf '%s|%s\n' "$median" "$candidate" >>"$tmp"
      else
        log_warn "probe ${label}: ${candidate} failed url=${url}"
        printf '9999|%s\n' "$candidate" >>"$tmp"
      fi
    done
  fi

  if [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    return 1
  fi

  local ranked
  ranked="$(sort -t'|' -g -k1,1 "$tmp" | cut -d'|' -f2 | paste -sd, -)"
  rm -f "$tmp"

  [ -n "$ranked" ] || return 1
  printf '%s' "$ranked"
}

# 并行探测候选列表（每个候选开一个后台子进程），结果写入临时文件后汇总排序
# 相比串行版本大幅减少总探测时间，适合候选列表较多的场景
rank_candidates_parallel() {
  local kind="$1"
  local label="$2"
  local candidates_csv="$3"
  local apt_codename="$4"

  candidates_csv="$(dedupe_csv "$candidates_csv")"
  if [ -z "$candidates_csv" ]; then
    return 1
  fi

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local ranking_file
  ranking_file="$(mktemp)"
  local raw
  IFS=',' read -r -a raw <<<"$candidates_csv"

  local -a pids=()
  local -a result_files=()
  local candidate
  local index=0
  if [ "${#raw[@]}" -gt 0 ]; then
    for candidate in "${raw[@]}"; do
      candidate="$(trim "$candidate")"
      [ -z "$candidate" ] && continue

      local result_file="${tmp_dir}/probe-${index}.result"
      result_files+=("$result_file")
      (
        local url median
        if ! url="$(build_probe_url "$kind" "$candidate" "$apt_codename")"; then
          printf 'skip|||%s\n' "$candidate"
          exit 0
        fi

        if median="$(probe_median_seconds "$url")"; then
          printf 'ok|%s|%s|%s\n' "$median" "$candidate" "$url"
        else
          printf 'fail|9999|%s|%s\n' "$candidate" "$url"
        fi
      ) >"$result_file" &
      pids+=("$!")
      index=$((index + 1))
    done
  fi

  if [ "${#pids[@]}" -eq 0 ]; then
    rm -f "$ranking_file"
    rm -rf "$tmp_dir"
    return 1
  fi

  local pid
  if [ "${#pids[@]}" -gt 0 ]; then
    for pid in "${pids[@]}"; do
      if ! wait "$pid"; then
        log_warn "probe ${label}: worker exited unexpectedly pid=${pid}"
      fi
    done
  fi

  local result_line status median url
  if [ "${#result_files[@]}" -gt 0 ]; then
    for result_file in "${result_files[@]}"; do
      [ -f "$result_file" ] || continue
      result_line="$(cat "$result_file")"
      IFS='|' read -r status median candidate url <<<"$result_line"
      case "$status" in
        ok)
          log_info_err "probe ${label}: ${candidate} median=${median}s url=${url}"
          printf '%s|%s\n' "$median" "$candidate" >>"$ranking_file"
          ;;
        fail)
          log_warn "probe ${label}: ${candidate} failed url=${url}"
          printf '9999|%s\n' "$candidate" >>"$ranking_file"
          ;;
        *)
          ;;
      esac
    done
  fi

  rm -rf "$tmp_dir"

  if [ ! -s "$ranking_file" ]; then
    rm -f "$ranking_file"
    return 1
  fi

  local ranked
  ranked="$(sort -t'|' -g -k1,1 "$ranking_file" | cut -d'|' -f2 | paste -sd, -)"
  rm -f "$ranking_file"

  [ -n "$ranked" ] || return 1
  printf '%s' "$ranked"
}

# 从排序后的 CSV 中选出 primary 和 fallback 镜像
# explicit_primary/fallback 非空时直接使用，否则取排序列表的第 1/2 项
choose_primary_fallback() {
  local ranked_csv="$1"
  local explicit_primary="$2"
  local explicit_fallback="$3"

  local primary fallback
  if [ -n "$explicit_primary" ]; then
    primary="$explicit_primary"
  else
    primary="$(first_csv_item "$ranked_csv")"
  fi

  if [ -n "$explicit_fallback" ]; then
    fallback="$explicit_fallback"
  else
    fallback="$(second_csv_item "$ranked_csv")"
    if [ -z "$fallback" ] || [ "$fallback" = "$primary" ]; then
      fallback="$(first_csv_item "$ranked_csv")"
    fi
  fi

  printf '%s|%s' "$primary" "$fallback"
}

# ─── 带重试的 compose 执行 ────────────────────────────────────────────────────
# 每次调用代表一个"phase"（使用特定的 dockerhub_mirror + ghcr_registry 组合）
# 单个 phase 内部最多重试 retry_count 次，失败后返回非零退出码
# 前台 up 模式下，会在后台启动 ready watcher，compose 退出后清理它
run_with_retries() {
  local phase="$1"
  local retry_count="$2"
  local dockerhub_mirror="$3"
  local ghcr_registry="$4"
  local uv_image="$5"
  local sandbox_base_image="$6"
  local sandbox_image="$7"

  local attempt=1
  local rc=1
  local ready_watcher_pid=""
  while [ "$attempt" -le "$retry_count" ]; do
    log_info "Phase=${phase} attempt ${attempt}/${retry_count}"
    log_info "DOCKERHUB_LIBRARY_MIRROR=${dockerhub_mirror}"
    log_info "GHCR_REGISTRY=${ghcr_registry}"
    log_info "UV_IMAGE=${uv_image}"
    log_info "SANDBOX_BASE_IMAGE=${sandbox_base_image}"
    log_info "SANDBOX_IMAGE=${sandbox_image}"
    log_info "FRONTEND_NPM_REGISTRY=${FRONTEND_NPM_REGISTRY_SELECTED}"
    log_info "FRONTEND_NPM_REGISTRY_FALLBACK=${FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED}"

    ready_watcher_pid=""
    if [ "$IS_ATTACHED_UP" -eq 1 ]; then
      notify_when_ready 1 &
      ready_watcher_pid="$!"
    fi

    set +e
    DOCKERHUB_LIBRARY_MIRROR="${dockerhub_mirror}" \
      GHCR_REGISTRY="${ghcr_registry}" \
      UV_IMAGE="${uv_image}" \
      SANDBOX_BASE_IMAGE="${sandbox_base_image}" \
      SANDBOX_IMAGE="${sandbox_image}" \
      FRONTEND_NPM_REGISTRY="${FRONTEND_NPM_REGISTRY_SELECTED}" \
      FRONTEND_NPM_REGISTRY_FALLBACK="${FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED}" \
      BACKEND_PYPI_INDEX_PRIMARY="${BACKEND_PYPI_INDEX_PRIMARY_SELECTED}" \
      BACKEND_PYPI_INDEX_FALLBACK="${BACKEND_PYPI_INDEX_FALLBACK_SELECTED}" \
      SANDBOX_PYPI_INDEX_PRIMARY="${SANDBOX_PYPI_INDEX_PRIMARY_SELECTED}" \
      SANDBOX_PYPI_INDEX_FALLBACK="${SANDBOX_PYPI_INDEX_FALLBACK_SELECTED}" \
      BACKEND_APT_MIRROR_PRIMARY="${BACKEND_APT_MIRROR_PRIMARY_SELECTED}" \
      BACKEND_APT_SECURITY_PRIMARY="${BACKEND_APT_SECURITY_PRIMARY_SELECTED}" \
      BACKEND_APT_MIRROR_FALLBACK="${BACKEND_APT_MIRROR_FALLBACK_SELECTED}" \
      BACKEND_APT_SECURITY_FALLBACK="${BACKEND_APT_SECURITY_FALLBACK_SELECTED}" \
      SANDBOX_APT_MIRROR_PRIMARY="${SANDBOX_APT_MIRROR_PRIMARY_SELECTED}" \
      SANDBOX_APT_SECURITY_PRIMARY="${SANDBOX_APT_SECURITY_PRIMARY_SELECTED}" \
      SANDBOX_APT_MIRROR_FALLBACK="${SANDBOX_APT_MIRROR_FALLBACK_SELECTED}" \
      SANDBOX_APT_SECURITY_FALLBACK="${SANDBOX_APT_SECURITY_FALLBACK_SELECTED}" \
      SANDBOX_NPM_REGISTRY_PRIMARY="${SANDBOX_NPM_REGISTRY_PRIMARY_SELECTED}" \
      SANDBOX_NPM_REGISTRY_FALLBACK="${SANDBOX_NPM_REGISTRY_FALLBACK_SELECTED}" \
      "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}"
    rc=$?
    set -e

    if [ -n "$ready_watcher_pid" ]; then
      kill "$ready_watcher_pid" >/dev/null 2>&1 || true
      wait "$ready_watcher_pid" >/dev/null 2>&1 || true
    fi

    if [ "$rc" -eq 0 ]; then
      if [ "$IS_DETACHED_UP" -eq 1 ]; then
        notify_when_ready 0 || true
      fi
      log_info "Phase=${phase} succeeded on attempt ${attempt}"
      return 0
    fi

    log_warn "Phase=${phase} failed on attempt ${attempt}, exit_code=${rc}"
    if [ "$attempt" -lt "$retry_count" ]; then
      log_info "Retrying in ${RETRY_INTERVAL_SECONDS}s..."
      sleep "${RETRY_INTERVAL_SECONDS}"
    fi
    attempt=$((attempt + 1))
  done

  return "$rc"
}

detect_compose_cmd

if [ "$#" -eq 0 ]; then
  COMPOSE_ARGS=(up -d --build)
else
  COMPOSE_ARGS=("$@")
fi

if compose_args_target_attached_up "${COMPOSE_ARGS[@]}" && [ -z "${COMPOSE_MENU+x}" ]; then
  export COMPOSE_MENU=false
  log_info "Detected attached 'docker compose up'; defaulting COMPOSE_MENU=false to avoid Compose menu/watch crashes on affected versions."
fi

IS_ATTACHED_UP=0
IS_DETACHED_UP=0
if compose_args_target_attached_up "${COMPOSE_ARGS[@]}"; then
  IS_ATTACHED_UP=1
fi
if compose_args_target_detached_up "${COMPOSE_ARGS[@]}"; then
  IS_DETACHED_UP=1
fi

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

PHASE_RETRY_COUNT="${PHASE_RETRY_COUNT:-${CN_RETRY_COUNT:-3}}"
RETRY_INTERVAL_SECONDS="${RETRY_INTERVAL_SECONDS:-5}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-3}"
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-10}"
PROBE_CONNECT_TIMEOUT_SECONDS="${PROBE_CONNECT_TIMEOUT_SECONDS:-3}"
APT_PROBE_CODENAME="${APT_PROBE_CODENAME:-trixie}"
READY_TIMEOUT_SECONDS="${VULHUNTER_READY_TIMEOUT_SECONDS:-900}"
FRONTEND_PUBLIC_PORT="${VULHUNTER_FRONTEND_PORT:-3000}"
BACKEND_PUBLIC_PORT="${VULHUNTER_BACKEND_PORT:-8000}"
FRONTEND_READY_URL="http://127.0.0.1:${FRONTEND_PUBLIC_PORT}/"
BACKEND_READY_URL="http://127.0.0.1:${BACKEND_PUBLIC_PORT}/health"
FRONTEND_PUBLIC_URL="http://localhost:${FRONTEND_PUBLIC_PORT}"
BACKEND_DOCS_URL="http://localhost:${BACKEND_PUBLIC_PORT}/docs"

require_positive_int "PHASE_RETRY_COUNT" "${PHASE_RETRY_COUNT}"
require_positive_int "RETRY_INTERVAL_SECONDS" "${RETRY_INTERVAL_SECONDS}"
require_positive_int "PROBE_ATTEMPTS" "${PROBE_ATTEMPTS}"
require_positive_int "PROBE_TIMEOUT_SECONDS" "${PROBE_TIMEOUT_SECONDS}"
require_positive_int "PROBE_CONNECT_TIMEOUT_SECONDS" "${PROBE_CONNECT_TIMEOUT_SECONDS}"
require_positive_int "VULHUNTER_READY_TIMEOUT_SECONDS" "${READY_TIMEOUT_SECONDS}"

DOCKERHUB_CN_CANDIDATES_DEFAULT="${CN_DOCKERHUB_LIBRARY_MIRRORS:-${CN_DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library,docker.1ms.run/library}}"
GHCR_CN_CANDIDATES_DEFAULT="${CN_GHCR_REGISTRIES:-${CN_GHCR_REGISTRY:-ghcr.nju.edu.cn,ghcr.m.daocloud.io}}"
DOCKERHUB_CANDIDATES_DEFAULT="${DOCKERHUB_LIBRARY_MIRROR_CANDIDATES:-${DOCKERHUB_CN_CANDIDATES_DEFAULT},${OFFICIAL_DOCKERHUB_LIBRARY_MIRROR:-docker.io/library}}"
GHCR_CANDIDATES_DEFAULT="${GHCR_REGISTRY_CANDIDATES:-${GHCR_CN_CANDIDATES_DEFAULT},${OFFICIAL_GHCR_REGISTRY:-ghcr.io}}"
FRONTEND_NPM_CANDIDATES_DEFAULT="${FRONTEND_NPM_REGISTRY_CANDIDATES:-https://registry.npmmirror.com,https://registry.npmjs.org}"
SANDBOX_NPM_CANDIDATES_DEFAULT="${SANDBOX_NPM_REGISTRY_CANDIDATES:-https://registry.npmmirror.com,https://registry.npmjs.org}"
BACKEND_PYPI_CANDIDATES_DEFAULT="${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"
SANDBOX_PYPI_CANDIDATES_DEFAULT="${SANDBOX_PYPI_INDEX_CANDIDATES:-${BACKEND_PYPI_CANDIDATES_DEFAULT}}"
BACKEND_APT_MIRROR_CANDIDATES_DEFAULT="${BACKEND_APT_MIRROR_CANDIDATES:-mirrors.aliyun.com,deb.debian.org}"
BACKEND_APT_SECURITY_CANDIDATES_DEFAULT="${BACKEND_APT_SECURITY_CANDIDATES:-mirrors.aliyun.com,security.debian.org}"
SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT="${SANDBOX_APT_MIRROR_CANDIDATES:-mirrors.aliyun.com,deb.debian.org}"
SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT="${SANDBOX_APT_SECURITY_CANDIDATES:-mirrors.aliyun.com,security.debian.org}"

if [ -n "${DOCKERHUB_LIBRARY_MIRROR:-}" ]; then
  DOCKERHUB_RANKED="$(dedupe_csv "${DOCKERHUB_LIBRARY_MIRROR},${DOCKERHUB_CANDIDATES_DEFAULT}")"
  log_info "skip probe dockerhub: explicit DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR}"
else
  DOCKERHUB_RANKED="$(rank_candidates_parallel dockerhub dockerhub "${DOCKERHUB_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$DOCKERHUB_RANKED" ] || DOCKERHUB_RANKED="$(dedupe_csv "${DOCKERHUB_CANDIDATES_DEFAULT}")"
fi

if [ -n "${GHCR_REGISTRY:-}" ]; then
  GHCR_RANKED="$(dedupe_csv "${GHCR_REGISTRY},${GHCR_CANDIDATES_DEFAULT}")"
  log_info "skip probe ghcr: explicit GHCR_REGISTRY=${GHCR_REGISTRY}"
else
  GHCR_RANKED="$(rank_candidates_parallel ghcr ghcr "${GHCR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$GHCR_RANKED" ] || GHCR_RANKED="$(dedupe_csv "${GHCR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${FRONTEND_NPM_REGISTRY:-}" ] || [ -n "${FRONTEND_NPM_REGISTRY_FALLBACK:-}" ]; then
  FRONTEND_NPM_RANKED="$(dedupe_csv "${FRONTEND_NPM_REGISTRY:-},${FRONTEND_NPM_REGISTRY_FALLBACK:-},${FRONTEND_NPM_CANDIDATES_DEFAULT}")"
else
  FRONTEND_NPM_RANKED="$(rank_candidates npm frontend-npm "${FRONTEND_NPM_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$FRONTEND_NPM_RANKED" ] || FRONTEND_NPM_RANKED="$(dedupe_csv "${FRONTEND_NPM_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_NPM_REGISTRY_PRIMARY:-}" ] || [ -n "${SANDBOX_NPM_REGISTRY_FALLBACK:-}" ]; then
  SANDBOX_NPM_RANKED="$(dedupe_csv "${SANDBOX_NPM_REGISTRY_PRIMARY:-},${SANDBOX_NPM_REGISTRY_FALLBACK:-},${SANDBOX_NPM_CANDIDATES_DEFAULT}")"
else
  SANDBOX_NPM_RANKED="$(rank_candidates npm sandbox-npm "${SANDBOX_NPM_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_NPM_RANKED" ] || SANDBOX_NPM_RANKED="$(dedupe_csv "${SANDBOX_NPM_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_PYPI_INDEX_PRIMARY:-}" ] || [ -n "${BACKEND_PYPI_INDEX_FALLBACK:-}" ]; then
  BACKEND_PYPI_RANKED="$(dedupe_csv "${BACKEND_PYPI_INDEX_PRIMARY:-},${BACKEND_PYPI_INDEX_FALLBACK:-},${BACKEND_PYPI_CANDIDATES_DEFAULT}")"
else
  BACKEND_PYPI_RANKED="$(rank_candidates pypi backend-pypi "${BACKEND_PYPI_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_PYPI_RANKED" ] || BACKEND_PYPI_RANKED="$(dedupe_csv "${BACKEND_PYPI_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_PYPI_INDEX_PRIMARY:-}" ] || [ -n "${SANDBOX_PYPI_INDEX_FALLBACK:-}" ]; then
  SANDBOX_PYPI_RANKED="$(dedupe_csv "${SANDBOX_PYPI_INDEX_PRIMARY:-},${SANDBOX_PYPI_INDEX_FALLBACK:-},${SANDBOX_PYPI_CANDIDATES_DEFAULT}")"
else
  SANDBOX_PYPI_RANKED="$(rank_candidates pypi sandbox-pypi "${SANDBOX_PYPI_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_PYPI_RANKED" ] || SANDBOX_PYPI_RANKED="$(dedupe_csv "${SANDBOX_PYPI_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_APT_MIRROR_PRIMARY:-}" ] || [ -n "${BACKEND_APT_MIRROR_FALLBACK:-}" ]; then
  BACKEND_APT_MIRROR_RANKED="$(dedupe_csv "${BACKEND_APT_MIRROR_PRIMARY:-},${BACKEND_APT_MIRROR_FALLBACK:-},${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}")"
else
  BACKEND_APT_MIRROR_RANKED="$(rank_candidates apt backend-apt-main "${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_APT_MIRROR_RANKED" ] || BACKEND_APT_MIRROR_RANKED="$(dedupe_csv "${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_APT_SECURITY_PRIMARY:-}" ] || [ -n "${BACKEND_APT_SECURITY_FALLBACK:-}" ]; then
  BACKEND_APT_SECURITY_RANKED="$(dedupe_csv "${BACKEND_APT_SECURITY_PRIMARY:-},${BACKEND_APT_SECURITY_FALLBACK:-},${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}")"
else
  BACKEND_APT_SECURITY_RANKED="$(rank_candidates apt-security backend-apt-security "${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_APT_SECURITY_RANKED" ] || BACKEND_APT_SECURITY_RANKED="$(dedupe_csv "${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_APT_MIRROR_PRIMARY:-}" ] || [ -n "${SANDBOX_APT_MIRROR_FALLBACK:-}" ]; then
  SANDBOX_APT_MIRROR_RANKED="$(dedupe_csv "${SANDBOX_APT_MIRROR_PRIMARY:-},${SANDBOX_APT_MIRROR_FALLBACK:-},${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}")"
else
  SANDBOX_APT_MIRROR_RANKED="$(rank_candidates apt sandbox-apt-main "${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_APT_MIRROR_RANKED" ] || SANDBOX_APT_MIRROR_RANKED="$(dedupe_csv "${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_APT_SECURITY_PRIMARY:-}" ] || [ -n "${SANDBOX_APT_SECURITY_FALLBACK:-}" ]; then
  SANDBOX_APT_SECURITY_RANKED="$(dedupe_csv "${SANDBOX_APT_SECURITY_PRIMARY:-},${SANDBOX_APT_SECURITY_FALLBACK:-},${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}")"
else
  SANDBOX_APT_SECURITY_RANKED="$(rank_candidates apt-security sandbox-apt-security "${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_APT_SECURITY_RANKED" ] || SANDBOX_APT_SECURITY_RANKED="$(dedupe_csv "${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}")"
fi

IFS='|' read -r FRONTEND_NPM_REGISTRY_SELECTED FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${FRONTEND_NPM_RANKED}" "${FRONTEND_NPM_REGISTRY:-}" "${FRONTEND_NPM_REGISTRY_FALLBACK:-}")"
IFS='|' read -r SANDBOX_NPM_REGISTRY_PRIMARY_SELECTED SANDBOX_NPM_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_NPM_RANKED}" "${SANDBOX_NPM_REGISTRY_PRIMARY:-}" "${SANDBOX_NPM_REGISTRY_FALLBACK:-}")"
IFS='|' read -r BACKEND_PYPI_INDEX_PRIMARY_SELECTED BACKEND_PYPI_INDEX_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_PYPI_RANKED}" "${BACKEND_PYPI_INDEX_PRIMARY:-}" "${BACKEND_PYPI_INDEX_FALLBACK:-}")"
IFS='|' read -r SANDBOX_PYPI_INDEX_PRIMARY_SELECTED SANDBOX_PYPI_INDEX_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_PYPI_RANKED}" "${SANDBOX_PYPI_INDEX_PRIMARY:-}" "${SANDBOX_PYPI_INDEX_FALLBACK:-}")"
IFS='|' read -r BACKEND_APT_MIRROR_PRIMARY_SELECTED BACKEND_APT_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_APT_MIRROR_RANKED}" "${BACKEND_APT_MIRROR_PRIMARY:-}" "${BACKEND_APT_MIRROR_FALLBACK:-}")"
IFS='|' read -r BACKEND_APT_SECURITY_PRIMARY_SELECTED BACKEND_APT_SECURITY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_APT_SECURITY_RANKED}" "${BACKEND_APT_SECURITY_PRIMARY:-}" "${BACKEND_APT_SECURITY_FALLBACK:-}")"
IFS='|' read -r SANDBOX_APT_MIRROR_PRIMARY_SELECTED SANDBOX_APT_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_APT_MIRROR_RANKED}" "${SANDBOX_APT_MIRROR_PRIMARY:-}" "${SANDBOX_APT_MIRROR_FALLBACK:-}")"
IFS='|' read -r SANDBOX_APT_SECURITY_PRIMARY_SELECTED SANDBOX_APT_SECURITY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_APT_SECURITY_RANKED}" "${SANDBOX_APT_SECURITY_PRIMARY:-}" "${SANDBOX_APT_SECURITY_FALLBACK:-}")"
IFS='|' read -r DOCKERHUB_LIBRARY_MIRROR_PRIMARY_SELECTED DOCKERHUB_LIBRARY_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${DOCKERHUB_RANKED}" "${DOCKERHUB_LIBRARY_MIRROR:-}" "")"
IFS='|' read -r GHCR_REGISTRY_PRIMARY_SELECTED GHCR_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${GHCR_RANKED}" "${GHCR_REGISTRY:-}" "")"

DOCKERHUB_PHASES_COUNT="$(count_csv_items "${DOCKERHUB_RANKED}")"
GHCR_PHASES_COUNT="$(count_csv_items "${GHCR_RANKED}")"
PHASE_COUNT="$DOCKERHUB_PHASES_COUNT"
if [ "$GHCR_PHASES_COUNT" -gt "$PHASE_COUNT" ]; then
  PHASE_COUNT="$GHCR_PHASES_COUNT"
fi
[ "$PHASE_COUNT" -ge 1 ] || PHASE_COUNT=1

VULHUNTER_IMAGE_TAG="${VULHUNTER_IMAGE_TAG:-latest}"

log_info "Compose command: ${COMPOSE_BIN[*]}"
log_info "Compose args: ${COMPOSE_ARGS[*]}"
log_info "DOCKER_BUILDKIT=${DOCKER_BUILDKIT} COMPOSE_DOCKER_CLI_BUILD=${COMPOSE_DOCKER_CLI_BUILD}"
log_info "rank dockerhub=${DOCKERHUB_RANKED}"
log_info "selected dockerhub primary=${DOCKERHUB_LIBRARY_MIRROR_PRIMARY_SELECTED} fallback=${DOCKERHUB_LIBRARY_MIRROR_FALLBACK_SELECTED}"
log_info "rank ghcr=${GHCR_RANKED}"
log_info "selected ghcr primary=${GHCR_REGISTRY_PRIMARY_SELECTED} fallback=${GHCR_REGISTRY_FALLBACK_SELECTED}"
log_info "rank frontend npm=${FRONTEND_NPM_RANKED}"
log_info "rank sandbox npm=${SANDBOX_NPM_RANKED}"
log_info "rank backend pypi=${BACKEND_PYPI_RANKED}"
log_info "rank sandbox pypi=${SANDBOX_PYPI_RANKED}"
log_info "rank backend apt main=${BACKEND_APT_MIRROR_RANKED}"
log_info "rank backend apt security=${BACKEND_APT_SECURITY_RANKED}"
log_info "rank sandbox apt main=${SANDBOX_APT_MIRROR_RANKED}"
log_info "rank sandbox apt security=${SANDBOX_APT_SECURITY_RANKED}"

for ((phase_index = 0; phase_index < PHASE_COUNT; phase_index++)); do
  dockerhub_mirror="$(csv_item_or_last "${DOCKERHUB_RANKED}" "${phase_index}")"
  ghcr_registry="$(csv_item_or_last "${GHCR_RANKED}" "${phase_index}")"

  if [ -n "${UV_IMAGE:-}" ]; then
    uv_image="${UV_IMAGE}"
  else
    uv_image="${ghcr_registry}/astral-sh/uv:latest"
  fi

  if [ -n "${SANDBOX_BASE_IMAGE:-}" ]; then
    sandbox_base_image="${SANDBOX_BASE_IMAGE}"
  else
    sandbox_base_image="${dockerhub_mirror}/python:3.11-slim"
  fi

  if [ -n "${SANDBOX_IMAGE:-}" ]; then
    sandbox_image="${SANDBOX_IMAGE}"
  else
    sandbox_image="${ghcr_registry}/lintsinghua/vulhunter-sandbox:${VULHUNTER_IMAGE_TAG}"
  fi

  phase_name="rank-$((phase_index + 1))"
  log_info "Phase=${phase_name} mirror selection dockerhub=${dockerhub_mirror} ghcr=${ghcr_registry}"
  if run_with_retries \
    "${phase_name}" \
    "${PHASE_RETRY_COUNT}" \
    "${dockerhub_mirror}" \
    "${ghcr_registry}" \
    "${uv_image}" \
    "${sandbox_base_image}" \
    "${sandbox_image}"; then
    exit 0
  fi

done

log_error "All ranked phases exhausted. Exiting with failure."
exit 1
