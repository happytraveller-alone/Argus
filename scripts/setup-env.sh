#!/usr/bin/env bash
# scripts/setup-env.sh — 自动探测容器运行时并生成根目录 .env
#
# 解决的核心问题:
#   docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
#   podman compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
#   ——以上两条命令应当完全等效，无需额外 -f 参数。
#
# 原理:
#   docker compose / podman compose 均会自动加载项目根目录的 .env（无论是否指定 -f）
#   本脚本将 DOCKER_SOCKET_PATH 写入根 .env，compose 文件中的
#   ${DOCKER_SOCKET_PATH:-/var/run/docker.sock} 变量替换即可自动适配运行时。
#
# 用法:
#   bash scripts/setup-env.sh           # 探测并写入 .env
#   bash scripts/setup-env.sh --force   # 强制覆盖已有 DOCKER_SOCKET_PATH
#   bash scripts/setup-env.sh --dry-run # 仅打印，不写文件
#
# 幂等性:
#   多次执行安全。已有配置不会被覆盖（除非传入 --force）。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_ENV_FILE="${REPO_ROOT}/.env"

FORCE=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --force)   FORCE=1 ;;
    --dry-run) DRY_RUN=1 ;;
  esac
done

log_info()  { echo "[setup-env] $*"; }
log_warn()  { echo "[setup-env] WARN: $*" >&2; }
log_error() { echo "[setup-env] ERROR: $*" >&2; }

# ─── 探测 Docker socket ────────────────────────────────────────────────────────
detect_docker_socket() {
  # Docker 默认 socket
  local candidates=(
    "/var/run/docker.sock"
    "/run/docker.sock"
  )
  local s
  for s in "${candidates[@]}"; do
    if [ -S "$s" ]; then
      printf '%s' "$s"
      return 0
    fi
  done
  return 1
}

# ─── 探测 Podman socket ────────────────────────────────────────────────────────
detect_podman_socket() {
  # 1. 优先使用 podman info 的输出（最准确）
  if command -v podman > /dev/null 2>&1; then
    local podman_sock
    podman_sock="$(podman info --format '{{.Host.RemoteSocket.Path}}' 2>/dev/null || true)"
    if [ -n "$podman_sock" ] && [ -S "$podman_sock" ]; then
      printf '%s' "$podman_sock"
      return 0
    fi
  fi

  # 2. 尝试 DOCKER_HOST 环境变量（若已设置）
  if [ -n "${DOCKER_HOST:-}" ]; then
    local sock_from_env="${DOCKER_HOST#unix://}"
    if [ "$sock_from_env" != "$DOCKER_HOST" ] && [ -S "$sock_from_env" ]; then
      printf '%s' "$sock_from_env"
      return 0
    fi
  fi

  # 3. 常见固定路径 — rootful / rootless / macOS
  local uid
  uid="$(id -u)"
  local candidates=(
    "/run/podman/podman.sock"              # rootful Linux
    "/var/run/podman/podman.sock"          # 部分发行版
    "/run/user/${uid}/podman/podman.sock"  # rootless Linux
  )
  # macOS: ~/.local/share/containers/podman/machine/...
  if [ "$(uname -s)" = "Darwin" ]; then
    local xdg_data="${XDG_RUNTIME_DIR:-${HOME}/.local/share}"
    candidates+=(
      "${xdg_data}/containers/podman/machine/qemu/podman.sock"
      "${xdg_data}/containers/podman/machine/podman.sock"
    )
  fi

  local s
  for s in "${candidates[@]}"; do
    if [ -S "$s" ]; then
      printf '%s' "$s"
      return 0
    fi
  done
  return 1
}

# ─── 判断是否为 Docker daemon（而不是 Podman 的 docker compat 层）────────────
is_real_docker() {
  local docker_cmd="${1:-docker}"
  local server_info
  server_info="$("$docker_cmd" info --format '{{.Server.ServerVersion}}' 2>/dev/null || true)"
  local engine_type
  engine_type="$("$docker_cmd" info --format '{{.OperatingSystem}}' 2>/dev/null || true)"

  # Podman 的 docker compat API 会在 OperatingSystem 中带有 "podman"
  if printf '%s' "$engine_type" | grep -qi 'podman'; then
    return 1
  fi
  return 0
}

# ─── 写入或更新 .env 中的某个 KEY=VALUE ───────────────────────────────────────
upsert_env_key() {
  local key="$1"
  local value="$2"

  if [ "$DRY_RUN" -eq 1 ]; then
    log_info "[dry-run] would write: ${key}=${value}"
    return
  fi

  # 若 .env 不存在则创建
  if [ ! -f "$ROOT_ENV_FILE" ]; then
    touch "$ROOT_ENV_FILE"
    log_info "created ${ROOT_ENV_FILE}"
  fi

  # 检查 key 是否已存在（忽略注释行）
  if grep -qE "^${key}=" "$ROOT_ENV_FILE" 2>/dev/null; then
    if [ "$FORCE" -eq 1 ]; then
      # sed 原地替换
      sed -i "s|^${key}=.*|${key}=${value}|" "$ROOT_ENV_FILE"
      log_info "updated  ${key}=${value}  (${ROOT_ENV_FILE})"
    else
      local existing_val
      existing_val="$(grep -E "^${key}=" "$ROOT_ENV_FILE" | head -1 | cut -d= -f2-)"
      log_info "skip: ${key} already set to '${existing_val}' (use --force to override)"
    fi
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ROOT_ENV_FILE"
    log_info "wrote    ${key}=${value}  (${ROOT_ENV_FILE})"
  fi
}

# ─── 主逻辑 ───────────────────────────────────────────────────────────────────
log_info "detecting container runtime..."

RUNTIME=""        # docker | podman | unknown
SOCKET_PATH=""    # 要写入 .env 的 socket 路径

# 优先判断本机是否真正运行了 Docker daemon
docker_sock="$(detect_docker_socket || true)"
if [ -n "$docker_sock" ]; then
  if command -v docker > /dev/null 2>&1 && is_real_docker docker; then
    RUNTIME="docker"
    SOCKET_PATH="$docker_sock"
    log_info "detected: Docker daemon, socket=${SOCKET_PATH}"
  fi
fi

# 如果没找到真 Docker，尝试 Podman
if [ -z "$RUNTIME" ]; then
  podman_sock="$(detect_podman_socket || true)"
  if [ -n "$podman_sock" ]; then
    RUNTIME="podman"
    SOCKET_PATH="$podman_sock"
    log_info "detected: Podman, socket=${SOCKET_PATH}"
  fi
fi

# 兜底：没有激活的 socket，但 docker 命令存在（Docker Desktop 等情况）
if [ -z "$RUNTIME" ]; then
  if command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1; then
    RUNTIME="docker"
    SOCKET_PATH="/var/run/docker.sock"
    log_info "detected: Docker (via docker info), assuming socket=${SOCKET_PATH}"
  elif command -v podman > /dev/null 2>&1; then
    RUNTIME="podman"
    # 尝试启动 podman socket 获取路径
    log_warn "Podman socket not found. Run: systemctl --user enable --now podman.socket"
    # 仍然写入预期路径供用户参考
    if [ "$(id -u)" = "0" ]; then
      SOCKET_PATH="/run/podman/podman.sock"
    else
      SOCKET_PATH="/run/user/$(id -u)/podman/podman.sock"
    fi
    log_warn "using expected socket path: ${SOCKET_PATH} (may not exist yet)"
  fi
fi

if [ -z "$RUNTIME" ]; then
  log_error "neither Docker nor Podman detected. Install one of them first."
  exit 1
fi

# ─── 写入 .env ────────────────────────────────────────────────────────────────
# DOCKER_SOCKET_PATH — compose 文件中的 socket 挂载路径
#   Docker: /var/run/docker.sock（默认值，实际上可以不写）
#   Podman: /run/podman/podman.sock  或  /run/user/<uid>/podman/podman.sock
if [ "$RUNTIME" = "podman" ]; then
  upsert_env_key "DOCKER_SOCKET_PATH" "$SOCKET_PATH"
else
  # Docker 环境：默认值即为正确值，仅在已有配置时打印确认
  if grep -qE "^DOCKER_SOCKET_PATH=" "$ROOT_ENV_FILE" 2>/dev/null; then
    log_info "Docker runtime: DOCKER_SOCKET_PATH already set, keeping as-is"
  else
    log_info "Docker runtime: DOCKER_SOCKET_PATH not needed (default /var/run/docker.sock works)"
  fi
fi

# ─── 打印运行时摘要 ────────────────────────────────────────────────────────────
# 检测 Podman 主版本号，用于判断 podman compose -f 是否可用（需 4.x+）
_podman_major=0
if command -v podman >/dev/null 2>&1; then
  _podman_major="$(podman -v 2>/dev/null | awk '{print $NF}' | cut -d. -f1)"
  _podman_major="${_podman_major:-0}"
fi

echo ""
echo "─────────────────────────────────────────────────────────────"
echo " Runtime : ${RUNTIME}"
echo " Socket  : ${SOCKET_PATH}"
echo " Env file: ${ROOT_ENV_FILE}"
echo "─────────────────────────────────────────────────────────────"
echo ""
echo " 现在可以直接使用以下任一命令（效果相同）："
echo ""
echo "   docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build"
if [ "$_podman_major" -ge 4 ] 2>/dev/null; then
  echo "   podman compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build"
elif command -v podman-compose >/dev/null 2>&1; then
  echo "   podman-compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build"
elif [ "$_podman_major" -ge 1 ] 2>/dev/null; then
  echo ""
  echo " 注意: 检测到 Podman ${_podman_major}.x。podman compose -f 需要 Podman 4.x+"
  echo "   请升级 Podman 到 4.x+，或安装 podman-compose: pip install podman-compose"
fi
echo ""
echo " 或使用更省事的方式："
echo ""
echo "   bash scripts/compose-up-with-fallback.sh -f docker-compose.yml \\"
echo "     -f docker-compose.hybrid.yml up --build"
echo ""
echo "─────────────────────────────────────────────────────────────"
