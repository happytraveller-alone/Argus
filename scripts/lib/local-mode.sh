#!/usr/bin/env bash
# scripts/lib/local-mode.sh — Local 模式主链路
# 依赖 common.sh 已被 source。
# nexus 相关操作由 nexus.sh 提供。

# ─── apt 依赖安装 ──────────────────────────────────────────────────────────────
_apt_install_if_missing() {
  local pkg="$1"
  if dpkg -s "$pkg" >/dev/null 2>&1; then
    return 0
  fi
  log_step "安装 ${pkg}..."
  sudo apt-get install -y "$pkg"
}

local_install_system_deps() {
  log_step "更新 apt 包列表..."
  sudo apt-get update -qq

  local pkgs=(
    git curl ca-certificates build-essential
    python3 python3-venv python3-pip
    postgresql redis-server
  )
  for pkg in "${pkgs[@]}"; do
    _apt_install_if_missing "$pkg"
  done

  # Docker Engine（本地模式仍需 Docker 跑 runner）
  if ! command -v docker >/dev/null 2>&1; then
    log_step "安装 Docker Engine..."
    sudo apt-get install -y docker.io
    sudo systemctl enable --now docker || true
    # 将当前用户加入 docker 组（需重新登录后生效）
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    log_warn "已将 ${USER} 加入 docker 组，若后续 docker 命令权限不足，请重新登录或执行: newgrp docker"
  fi

  # uv
  if ! command -v uv >/dev/null 2>&1; then
    log_step "安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 把 uv 加入当前 session PATH
    export PATH="${HOME}/.local/bin:${PATH}"
    if ! command -v uv >/dev/null 2>&1; then
      log_error "uv 安装后仍不可用，请手动将 ~/.local/bin 加入 PATH"
      exit 1
    fi
  fi

  # Node.js ≥ 20
  local node_major=0
  if command -v node >/dev/null 2>&1; then
    node_major="$(node -e 'process.stdout.write(process.version.replace(/^v(\d+).*$/,"$1"))' 2>/dev/null || echo 0)"
  fi
  if [ "$node_major" -lt 20 ]; then
    log_step "安装 Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi

  # pnpm via corepack
  if ! command -v pnpm >/dev/null 2>&1; then
    log_step "启用 corepack / 安装 pnpm..."
    sudo corepack enable
    corepack prepare pnpm@latest --activate 2>/dev/null || \
      npm install -g pnpm@latest 2>/dev/null || true
  fi
}

# ─── PostgreSQL ───────────────────────────────────────────────────────────────
local_start_postgres() {
  if ! sudo systemctl is-active --quiet postgresql; then
    log_step "启动 PostgreSQL..."
    sudo systemctl start postgresql
  fi
  log_success "PostgreSQL 已运行"
}

local_init_database() {
  local db="vulhunter"
  local pg_user="postgres"
  # 检查数据库是否存在
  if sudo -u postgres psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$db"; then
    log_info "数据库 '${db}' 已存在，跳过创建。"
  else
    log_step "创建数据库 '${db}'..."
    sudo -u postgres createdb "$db" || {
      log_error "创建数据库失败"
      exit 1
    }
    log_success "数据库 '${db}' 创建完成"
  fi
}

# ─── Redis ────────────────────────────────────────────────────────────────────
local_start_redis() {
  if ! sudo systemctl is-active --quiet redis-server; then
    log_step "启动 Redis..."
    sudo systemctl start redis-server
  fi
  log_success "Redis 已运行"
}

# ─── .env.local 生成 ──────────────────────────────────────────────────────────
local_generate_backend_env() {
  local env_src="${REPO_ROOT}/backend/.env"
  local env_dst="${REPO_ROOT}/backend/.env.local"
  local example="${REPO_ROOT}/docker/env/backend/env.example"

  # 以现有 .env 或 example 为基础
  if [ -f "$env_src" ]; then
    cp "$env_src" "$env_dst"
  elif [ -f "$example" ]; then
    cp "$example" "$env_dst"
  else
    log_error "未找到 backend/.env 或 env.example，无法生成 .env.local"
    exit 1
  fi

  # 覆盖本地化项
  _set_env_var() {
    local file="$1" key="$2" val="$3"
    if grep -q "^${key}=" "$file"; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    else
      echo "${key}=${val}" >> "$file"
    fi
  }

  local be_dir="${REPO_ROOT}/backend"
  _set_env_var "$env_dst" POSTGRES_SERVER "localhost"
  _set_env_var "$env_dst" REDIS_URL "redis://localhost:6379/0"
  _set_env_var "$env_dst" DATABASE_URL "postgresql+asyncpg://postgres:postgres@localhost/vulhunter"
  _set_env_var "$env_dst" ASYNCPG_DSN "postgresql://postgres:postgres@localhost/vulhunter"
  _set_env_var "$env_dst" RUNNER_PREFLIGHT_BUILD_CONTEXT "${be_dir}"
  _set_env_var "$env_dst" XDG_CONFIG_HOME "${REPO_ROOT}/.deploy/runtime/xdg-config"
  _set_env_var "$env_dst" SANDBOX_ENABLED "true"
  _set_env_var "$env_dst" FLOW_PARSER_RUNNER_ENABLED "true"
  _set_env_var "$env_dst" RUNNER_PREFLIGHT_ENABLED "true"

  log_success "已生成 backend/.env.local"
}

local_generate_frontend_env() {
  local env_dst="${REPO_ROOT}/frontend/.env.local"
  # 前端本地模式只需确保 API URL 指向本机
  cat > "$env_dst" <<EOF
VITE_API_BASE_URL=http://localhost:${BACKEND_PORT}
EOF
  log_success "已生成 frontend/.env.local"
}

# ─── Alembic 数据库迁移 ───────────────────────────────────────────────────────
local_run_migrations() {
  log_step "执行数据库迁移..."
  cd "${REPO_ROOT}/backend"
  uv sync --group dev -q
  DOTENV_PATH=".env.local" uv run alembic upgrade head || \
    uv run alembic upgrade head  # 部分版本不支持 DOTENV_PATH，直接尝试
  log_success "数据库迁移完成"
  cd "${REPO_ROOT}"
}

# ─── 启动 backend ─────────────────────────────────────────────────────────────
local_start_backend() {
  check_port_free "$BACKEND_PORT" "backend"
  ensure_deploy_dirs

  local log_file="${LOGS_DIR}/backend.log"
  log_step "启动 backend（日志：${log_file}）..."

  cd "${REPO_ROOT}/backend"
  # 设置 DOTENV_FILE 让 uvicorn 加载 .env.local（通过 app.core.config 的 env_file 机制）
  env DOTENV_PATH=".env.local" \
    nohup uv run uvicorn app.main:app \
      --host 0.0.0.0 --port "${BACKEND_PORT}" --no-access-log \
      > "$log_file" 2>&1 &
  local pid=$!
  write_pid "backend" "$pid"
  log_info "backend PID=${pid}"
  cd "${REPO_ROOT}"

  wait_for_http "http://localhost:${BACKEND_PORT}/health" "backend" 90
}

# ─── 启动 frontend ────────────────────────────────────────────────────────────
local_start_frontend() {
  check_port_free "$FRONTEND_PORT" "frontend"
  ensure_deploy_dirs

  local log_file="${LOGS_DIR}/frontend.log"
  log_step "构建 frontend..."
  cd "${REPO_ROOT}/frontend"
  pnpm install --no-frozen-lockfile -s
  pnpm build

  log_step "启动 frontend 预览服务（端口 ${FRONTEND_PORT}，日志：${log_file}）..."
  nohup pnpm exec vite preview --host 0.0.0.0 --port "${FRONTEND_PORT}" \
    > "$log_file" 2>&1 &
  local pid=$!
  write_pid "frontend" "$pid"
  log_info "frontend PID=${pid}"
  cd "${REPO_ROOT}"

  wait_for_http "http://localhost:${FRONTEND_PORT}/" "frontend" 60
}

# ─── 状态查看 ─────────────────────────────────────────────────────────────────
local_status() {
  echo ""
  printf "%-12s %-8s %-8s %s\n" "服务" "PID" "端口" "状态"
  printf "%-12s %-8s %-8s %s\n" "----" "---" "----" "----"

  _service_status() {
    local name="$1" port="$2"
    local pid
    pid="$(read_pid "$name")"
    local pid_str="${pid:-(无)}"
    local alive_str="停止"
    if [ -n "$pid" ] && is_pid_alive "$pid"; then
      alive_str="运行中"
    fi
    local port_str="N/A"
    if port_in_use "$port"; then
      port_str="监听"
    fi
    printf "%-12s %-8s %-8s %s\n" "$name" "$pid_str" "$port_str" "$alive_str"
  }

  _service_status "backend"  "$BACKEND_PORT"
  _service_status "frontend" "$FRONTEND_PORT"
  _service_status "nexus"    "$NEXUS_PORT"

  echo ""
  # 数据库/Redis 探活
  if sudo systemctl is-active --quiet postgresql 2>/dev/null; then
    printf "%-12s %s\n" "postgresql" "运行中"
  else
    printf "%-12s %s\n" "postgresql" "停止"
  fi
  if sudo systemctl is-active --quiet redis-server 2>/dev/null; then
    printf "%-12s %s\n" "redis" "运行中"
  else
    printf "%-12s %s\n" "redis" "停止"
  fi
  echo ""
}

# ─── 停止 ─────────────────────────────────────────────────────────────────────
local_stop() {
  log_step "停止本地服务..."
  stop_by_pid "backend"
  stop_by_pid "frontend"
  stop_by_pid "nexus"
  log_success "所有本地服务已停止"
}

# ─── 完整 local 启动流程 ──────────────────────────────────────────────────────
local_start() {
  log_step "Local 模式：启动 VulHunter（宿主机模式）..."
  check_os
  check_sudo
  local_install_system_deps
  local_start_postgres
  local_init_database
  local_start_redis
  local_generate_backend_env
  local_generate_frontend_env
  local_run_migrations
  local_start_backend
  # nexus 由 nexus.sh 的 nexus_start 函数处理，在 deploy-linux.sh 中调用
  local_start_frontend
  print_ready_banner
}
