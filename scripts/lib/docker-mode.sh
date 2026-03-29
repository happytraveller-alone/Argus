#!/usr/bin/env bash
# scripts/lib/docker-mode.sh — Docker 模式：检查、启动、状态、停止
# 依赖 common.sh 已被 source。

# ─── Docker/Compose 检测 ──────────────────────────────────────────────────────
_detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return 0
  fi
  log_error "未找到 docker compose 或 docker-compose，请先安装 Docker Compose plugin。"
  exit 1
}

_check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker 未安装，请参考 https://docs.docker.com/engine/install/ 安装。"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    log_error "Docker daemon 未运行，请执行: sudo systemctl start docker"
    exit 1
  fi
}

# ─── .env 准备 ────────────────────────────────────────────────────────────────
_prepare_docker_env() {
  local env_file="${REPO_ROOT}/backend/.env"
  local example_file="${REPO_ROOT}/docker/env/backend/env.example"
  if [ ! -f "$env_file" ]; then
    if [ -f "$example_file" ]; then
      log_warn "backend/.env 不存在，从 env.example 自动生成..."
      cp "$example_file" "$env_file"
      log_warn "请编辑 ${env_file} 填入 LLM_API_KEY 等必要配置后重新运行。"
    else
      log_error "未找到 backend/.env 也未找到 env.example，请手动创建配置文件。"
      exit 1
    fi
  fi
}

# ─── 端口预检 ─────────────────────────────────────────────────────────────────
_check_docker_ports() {
  check_port_free "$FRONTEND_PORT" "frontend"
  check_port_free "$BACKEND_PORT" "backend"
}

# ─── 启动 ─────────────────────────────────────────────────────────────────────
docker_start() {
  log_step "Docker 模式：启动 VulHunter..."
  _check_docker
  _detect_compose
  _prepare_docker_env
  _check_docker_ports

  cd "${REPO_ROOT}"
  log_step "运行: ${COMPOSE_BIN[*]} up --build -d"
  "${COMPOSE_BIN[@]}" up --build -d

  # 等待就绪
  wait_for_http "${BACKEND_URL}/health" "backend" 180 || true
  wait_for_http "${FRONTEND_URL}/" "frontend" 60 || true
  print_ready_banner
}

# ─── 状态 ─────────────────────────────────────────────────────────────────────
docker_status() {
  _check_docker
  _detect_compose
  cd "${REPO_ROOT}"
  log_step "Docker Compose 服务状态："
  "${COMPOSE_BIN[@]}" ps
}

# ─── 停止 ─────────────────────────────────────────────────────────────────────
docker_stop() {
  _check_docker
  _detect_compose
  cd "${REPO_ROOT}"
  log_step "停止 Docker Compose 服务..."
  "${COMPOSE_BIN[@]}" down
  log_success "所有容器已停止"
}
