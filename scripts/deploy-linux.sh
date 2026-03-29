#!/usr/bin/env bash
# scripts/deploy-linux.sh — VulHunter Linux 统一部署入口
#
# 用法:
#   ./scripts/deploy-linux.sh           # 交互式菜单
#   ./scripts/deploy-linux.sh docker    # Docker 模式启动
#   ./scripts/deploy-linux.sh local     # 本地模式启动
#   ./scripts/deploy-linux.sh status    # 查看运行状态
#   ./scripts/deploy-linux.sh stop      # 停止所有服务
#
# 支持系统: Ubuntu / Debian

set -euo pipefail

# ─── 定位脚本根目录 ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REPO_ROOT
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ─── source 公共库 ────────────────────────────────────────────────────────────
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=scripts/lib/docker-mode.sh
source "${SCRIPT_DIR}/lib/docker-mode.sh"
# shellcheck source=scripts/lib/local-mode.sh
source "${SCRIPT_DIR}/lib/local-mode.sh"
# shellcheck source=scripts/lib/nexus.sh
source "${SCRIPT_DIR}/lib/nexus.sh"

# ─── 参数解析 ─────────────────────────────────────────────────────────────────
MODE="${1:-}"

# ─── 交互菜单 ─────────────────────────────────────────────────────────────────
_interactive_menu() {
  echo ""
  printf "${_CLR_BOLD}VulHunter — Linux 部署向导${_CLR_RESET}\n"
  echo "─────────────────────────────────────"
  echo "  1) Docker 模式  （推荐，全功能，需要 Docker）"
  echo "  2) Local 模式   （主服务跑宿主机，扫描 runner 仍用 Docker）"
  echo "  3) 查看状态"
  echo "  4) 停止所有服务"
  echo "  q) 退出"
  echo ""
  local choice
  read -r -p "请选择 [1/2/3/4/q]: " choice
  case "$choice" in
    1) MODE="docker" ;;
    2) MODE="local"  ;;
    3) MODE="status" ;;
    4) MODE="stop"   ;;
    q|Q) exit 0      ;;
    *)
      log_error "无效选项: ${choice}"
      exit 1
      ;;
  esac
}

# ─── status 汇总（覆盖 docker + local） ──────────────────────────────────────
_status_all() {
  echo ""
  printf "${_CLR_BOLD}=== Docker 服务状态 ===${_CLR_RESET}\n"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    local _compose_ok=0
    if docker compose version >/dev/null 2>&1; then
      cd "${REPO_ROOT}"
      docker compose ps 2>/dev/null && _compose_ok=1
    fi
    [ "$_compose_ok" -eq 0 ] && echo "  （无 Compose 服务或 Compose 未初始化）"
  else
    echo "  （Docker 不可用）"
  fi

  echo ""
  printf "${_CLR_BOLD}=== Local 服务状态 ===${_CLR_RESET}\n"
  ensure_deploy_dirs
  local_status
}

# ─── stop 汇总（覆盖 docker + local） ────────────────────────────────────────
_stop_all() {
  log_step "停止所有服务（Docker + Local）..."

  # Docker
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      cd "${REPO_ROOT}"
      docker compose down 2>/dev/null && log_success "Docker Compose 已停止" || true
    fi
  fi

  # Local
  ensure_deploy_dirs
  local_stop
  nexus_stop
}

# ─── Local 完整启动（含 nexus） ───────────────────────────────────────────────
_local_full_start() {
  local_start   # 不含 nexus，见 local-mode.sh 末尾注释
  nexus_start   # nexus 由 nexus.sh 单独处理
}

# ─── 主分发 ───────────────────────────────────────────────────────────────────
if [ -z "$MODE" ]; then
  _interactive_menu
fi

case "$MODE" in
  docker)
    docker_start
    ;;
  local)
    _local_full_start
    ;;
  status)
    _status_all
    ;;
  stop)
    _stop_all
    ;;
  *)
    log_error "未知参数: '${MODE}'"
    echo ""
    echo "用法:"
    echo "  $0              # 交互式菜单"
    echo "  $0 docker       # Docker 模式"
    echo "  $0 local        # Local 模式"
    echo "  $0 status       # 查看状态"
    echo "  $0 stop         # 停止服务"
    exit 2
    ;;
esac
