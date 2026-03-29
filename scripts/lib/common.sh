#!/usr/bin/env bash
# scripts/lib/common.sh — 公共日志、端口检查、PID/日志目录、健康检查工具
# 所有其他脚本 source 此文件；不直接执行。

# ─── 颜色 ────────────────────────────────────────────────────────────────────
_CLR_RESET='\033[0m'
_CLR_GREEN='\033[0;32m'
_CLR_YELLOW='\033[1;33m'
_CLR_RED='\033[0;31m'
_CLR_CYAN='\033[0;36m'
_CLR_BOLD='\033[1m'

# ─── 日志 ────────────────────────────────────────────────────────────────────
log_info()    { printf "${_CLR_GREEN}[INFO]${_CLR_RESET}  %s\n" "$*"; }
log_step()    { printf "${_CLR_CYAN}[STEP]${_CLR_RESET}  %s\n" "$*"; }
log_warn()    { printf "${_CLR_YELLOW}[WARN]${_CLR_RESET}  %s\n" "$*" >&2; }
log_error()   { printf "${_CLR_RED}[ERROR]${_CLR_RESET} %s\n" "$*" >&2; }
log_success() { printf "${_CLR_GREEN}${_CLR_BOLD}[OK]${_CLR_RESET}    %s\n" "$*"; }

# ─── 常量 ────────────────────────────────────────────────────────────────────
DEPLOY_DIR="${REPO_ROOT:?REPO_ROOT must be set}/.deploy"
PIDS_DIR="${DEPLOY_DIR}/pids"
LOGS_DIR="${DEPLOY_DIR}/logs"
RUNTIME_DIR="${DEPLOY_DIR}/runtime"

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
NEXUS_PORT="${NEXUS_PORT:-5174}"

FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
BACKEND_URL="http://localhost:${BACKEND_PORT}"
BACKEND_DOCS_URL="http://localhost:${BACKEND_PORT}/docs"
NEXUS_URL="http://localhost:${NEXUS_PORT}"

# ─── 初始化目录 ───────────────────────────────────────────────────────────────
ensure_deploy_dirs() {
  mkdir -p "${PIDS_DIR}" "${LOGS_DIR}" "${RUNTIME_DIR}"
}

# ─── OS 检查 ──────────────────────────────────────────────────────────────────
check_os() {
  if [ ! -f /etc/os-release ]; then
    log_error "无法检测操作系统（/etc/os-release 不存在）"
    exit 1
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ;;
    *)
      log_error "当前系统 '${ID:-unknown}' 不受支持，仅支持 Ubuntu/Debian。"
      exit 1
      ;;
  esac
}

# ─── sudo 检查 ────────────────────────────────────────────────────────────────
check_sudo() {
  if ! command -v sudo >/dev/null 2>&1; then
    log_error "sudo 不可用，请以 root 运行或安装 sudo。"
    exit 1
  fi
  if ! sudo -n true 2>/dev/null; then
    log_info "需要 sudo 权限，请输入密码..."
    sudo -v || { log_error "sudo 认证失败"; exit 1; }
  fi
}

# ─── 命令检查 ─────────────────────────────────────────────────────────────────
require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "命令 '${cmd}' 未找到，请先安装。"
    exit 1
  fi
}

cmd_exists() {
  command -v "$1" >/dev/null 2>&1
}

# ─── 端口占用检查 ─────────────────────────────────────────────────────────────
port_in_use() {
  local port="$1"
  ss -tlnH "sport = :${port}" 2>/dev/null | grep -q . || \
    (cmd_exists lsof && lsof -i ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1)
}

check_port_free() {
  local port="$1"
  local name="${2:-port ${port}}"
  if port_in_use "$port"; then
    log_error "端口 ${port}（${name}）已被占用，请先释放。"
    exit 1
  fi
}

# ─── PID 文件管理 ─────────────────────────────────────────────────────────────
pid_file() {
  echo "${PIDS_DIR}/${1}.pid"
}

write_pid() {
  local name="$1"
  local pid="$2"
  echo "$pid" > "$(pid_file "$name")"
}

read_pid() {
  local name="$1"
  local f
  f="$(pid_file "$name")"
  [ -f "$f" ] && cat "$f" || echo ""
}

is_pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

stop_by_pid() {
  local name="$1"
  local pid
  pid="$(read_pid "$name")"
  if [ -z "$pid" ]; then
    log_warn "${name}: 无 PID 文件，跳过停止。"
    return 0
  fi
  if is_pid_alive "$pid"; then
    log_step "停止 ${name} (pid=${pid})..."
    kill "$pid" 2>/dev/null || true
    local i=0
    while [ $i -lt 15 ] && is_pid_alive "$pid"; do
      sleep 1; i=$((i+1))
    done
    if is_pid_alive "$pid"; then
      log_warn "${name} 未响应 SIGTERM，强制杀死..."
      kill -9 "$pid" 2>/dev/null || true
    fi
    log_success "${name} 已停止"
  else
    log_info "${name} 进程不存在（pid=${pid}），跳过。"
  fi
  rm -f "$(pid_file "$name")"
}

# ─── 健康检查 ─────────────────────────────────────────────────────────────────
wait_for_http() {
  local url="$1"
  local name="${2:-service}"
  local timeout="${3:-60}"
  local i=0
  log_step "等待 ${name} 就绪（最多 ${timeout}s）：${url}"
  while [ $i -lt "$timeout" ]; do
    if curl -fsS --connect-timeout 2 --max-time 5 "$url" >/dev/null 2>&1; then
      log_success "${name} 已就绪"
      return 0
    fi
    sleep 2; i=$((i+2))
  done
  log_error "${name} 在 ${timeout}s 内未就绪：${url}"
  return 1
}

# ─── 打印就绪横幅 ──────────────────────────────────────────────────────────────
print_ready_banner() {
  echo ""
  printf "${_CLR_GREEN}${_CLR_BOLD}==============================${_CLR_RESET}\n"
  printf "${_CLR_GREEN}${_CLR_BOLD}  VulHunter 已启动${_CLR_RESET}\n"
  printf "${_CLR_GREEN}${_CLR_BOLD}==============================${_CLR_RESET}\n"
  printf "  前端:     %s\n" "${FRONTEND_URL}"
  printf "  后端 API: %s\n" "${BACKEND_DOCS_URL}"
  printf "  Nexus:    %s\n" "${NEXUS_URL}"
  echo ""
}
