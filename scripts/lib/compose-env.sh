#!/usr/bin/env bash

compose_env_log_info() {
  if declare -F log_info >/dev/null 2>&1; then
    log_info "$@"
    return
  fi
  echo "[INFO] $*"
}

compose_env_log_warn() {
  if declare -F log_warn >/dev/null 2>&1; then
    log_warn "$@"
    return
  fi
  echo "[WARN] $*" >&2
}

compose_env_log_error() {
  if declare -F log_error >/dev/null 2>&1; then
    log_error "$@"
    return
  fi
  echo "[ERROR] $*" >&2
}

# ─── 自动注入 DOCKER_SOCKET_PATH（仅在运行时探测，不修改文件）────────────────
# 供 compose-up-with-fallback.sh 等脚本调用：若 .env 未设置 DOCKER_SOCKET_PATH
# 且当前 socket 是 Podman socket，则自动 export，使 compose 变量替换生效。
# 已在 .env 中明确设置时直接跳过（优先级最高）。
load_container_socket_env() {
  # 若 .env 或调用方已设置，跳过探测
  if [ -n "${DOCKER_SOCKET_PATH:-}" ]; then
    return 0
  fi

  # 优先检查真 Docker socket
  local docker_candidates=("/var/run/docker.sock" "/run/docker.sock")
  local s
  for s in "${docker_candidates[@]}"; do
    if [ -S "$s" ]; then
      # docker socket 存在且不是 Podman compat 层 → 默认值已经正确，无需设置
      return 0
    fi
  done

  # 找 Podman socket
  local uid
  uid="$(id -u)"
  local podman_candidates=(
    "/run/podman/podman.sock"
    "/var/run/podman/podman.sock"
    "/run/user/${uid}/podman/podman.sock"
  )
  if [ "$(uname -s)" = "Darwin" ]; then
    local xdg_data="${XDG_RUNTIME_DIR:-${HOME}/.local/share}"
    podman_candidates+=(
      "${xdg_data}/containers/podman/machine/qemu/podman.sock"
      "${xdg_data}/containers/podman/machine/podman.sock"
    )
  fi

  for s in "${podman_candidates[@]}"; do
    if [ -S "$s" ]; then
      export DOCKER_SOCKET_PATH="$s"
      compose_env_log_info "auto-detected Podman socket: DOCKER_SOCKET_PATH=${s}"
      return 0
    fi
  done

  # 也尝试 DOCKER_HOST（用户可能已在 shell 中设置）
  if [ -n "${DOCKER_HOST:-}" ]; then
    local sock_from_env="${DOCKER_HOST#unix://}"
    if [ "$sock_from_env" != "$DOCKER_HOST" ] && [ -S "$sock_from_env" ]; then
      export DOCKER_SOCKET_PATH="$sock_from_env"
      compose_env_log_info "using DOCKER_HOST socket: DOCKER_SOCKET_PATH=${sock_from_env}"
    fi
  fi
}

# ─── 自动探测 compose 命令（docker compose / podman compose）──────────────────
# 设置 COMPOSE_BIN 数组。优先级: docker compose > podman compose > docker-compose
detect_compose_cmd_auto() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return 0
  fi
  # podman compose -f 需要 Podman 4.x+；3.x 的 compose 子命令不支持 -f 标志
  local _podman_major=0
  if command -v podman >/dev/null 2>&1; then
    _podman_major="$(podman -v 2>/dev/null | awk '{print $NF}' | cut -d. -f1)"
    _podman_major="${_podman_major:-0}"
  fi
  if [ "$_podman_major" -ge 4 ] 2>/dev/null && podman compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(podman compose)
    compose_env_log_info "using podman compose (Podman ${_podman_major}.x) as COMPOSE_BIN"
    return 0
  fi
  # podman-compose Python 工具：兼容 Podman 3.x/4.x
  if command -v podman-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(podman-compose)
    compose_env_log_info "using podman-compose as COMPOSE_BIN"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return 0
  fi
  compose_env_log_error "no compose tool found (docker compose / podman compose / podman-compose / docker-compose)"
  return 1
}

ensure_backend_docker_env_file() {
  local repo_root="${1:-${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
  local env_dir="${repo_root}/docker/env/backend"
  local env_file="${env_dir}/.env"
  local example_file="${env_dir}/env.example"

  mkdir -p "${env_dir}"

  if [ -f "${env_file}" ]; then
    return 0
  fi

  if [ ! -f "${example_file}" ]; then
    compose_env_log_error "missing ${example_file}; cannot bootstrap docker/env/backend/.env"
    return 1
  fi

  cp "${example_file}" "${env_file}"
  compose_env_log_info "自动生成 backend Docker 环境文件: docker/env/backend/.env"
  compose_env_log_warn "已从 docker/env/backend/env.example 复制默认配置；如需真实模型密钥，请编辑 docker/env/backend/.env。"
}
