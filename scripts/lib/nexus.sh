#!/usr/bin/env bash
# scripts/lib/nexus.sh — nexus-web 外部拉取与本地启动
# 依赖 common.sh 已被 source。

NEXUS_SRC_DIR="${REPO_ROOT}/nexus-web/src"
NEXUS_REPO_URL="${NEXUS_WEB_REPO_URL:-https://github.com/happytraveller-alone/nexus-web.git}"
NEXUS_GIT_MIRROR_PREFIX="${NEXUS_WEB_GIT_MIRROR_PREFIX:-https://v6.gh-proxy.org/}"
NEXUS_GIT_REF="${NEXUS_WEB_GIT_REF:-}"
NEXUS_PNPM_VERSION="${NEXUS_WEB_PNPM_VERSION:-10.32.1}"

# ─── 拉取源码 ──────────────────────────────────────────────────────────────────
nexus_fetch_source() {
  if [ -d "${NEXUS_SRC_DIR}/.git" ]; then
    log_step "nexus-web 源码已存在，执行 git fetch 更新..."
    cd "${NEXUS_SRC_DIR}"
    git fetch --depth=1 origin 2>/dev/null || log_warn "nexus-web git fetch 失败，使用已有代码继续。"
    if [ -n "${NEXUS_GIT_REF}" ]; then
      git fetch --depth=1 origin "${NEXUS_GIT_REF}" 2>/dev/null || true
      git checkout --detach FETCH_HEAD 2>/dev/null || true
    fi
    cd "${REPO_ROOT}"
    return 0
  fi

  mkdir -p "${REPO_ROOT}/nexus-web"
  log_step "拉取 nexus-web 源码（通过 mirror）..."

  local clone_url="${NEXUS_GIT_MIRROR_PREFIX}${NEXUS_REPO_URL}"
  if git clone --depth=1 "${clone_url}" "${NEXUS_SRC_DIR}" 2>/dev/null; then
    log_success "nexus-web 源码拉取成功（mirror）"
  else
    log_warn "mirror 拉取失败，回退到直连..."
    if git clone --depth=1 "${NEXUS_REPO_URL}" "${NEXUS_SRC_DIR}"; then
      log_success "nexus-web 源码拉取成功（直连）"
    else
      log_error "nexus-web 源码拉取失败，请检查网络或手动克隆到 ${NEXUS_SRC_DIR}"
      exit 1
    fi
  fi

  if [ -n "${NEXUS_GIT_REF}" ]; then
    cd "${NEXUS_SRC_DIR}"
    git fetch --depth=1 origin "${NEXUS_GIT_REF}" || true
    git checkout --detach FETCH_HEAD || true
    cd "${REPO_ROOT}"
  fi
}

# ─── 补全 packageManager 字段 ─────────────────────────────────────────────────
nexus_patch_package_json() {
  local pkg_file="${NEXUS_SRC_DIR}/package.json"
  if [ ! -f "$pkg_file" ]; then
    log_error "nexus-web package.json 不存在：${pkg_file}"
    exit 1
  fi
  # 若 packageManager 字段缺失，则用 node 补写
  node -e "
const fs = require('fs');
const path = '${pkg_file}';
const pkg = JSON.parse(fs.readFileSync(path, 'utf8'));
if (pkg.packageManager) { process.exit(0); }
pkg.packageManager = 'pnpm@${NEXUS_PNPM_VERSION}';
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
console.log('已补全 packageManager: pnpm@${NEXUS_PNPM_VERSION}');
" 2>/dev/null || true
}

# ─── 安装依赖 & 构建 ──────────────────────────────────────────────────────────
nexus_build() {
  log_step "安装 nexus-web 依赖..."
  cd "${NEXUS_SRC_DIR}"

  corepack enable 2>/dev/null || true
  corepack prepare "pnpm@${NEXUS_PNPM_VERSION}" --activate 2>/dev/null || true

  pnpm install --no-frozen-lockfile -s

  log_step "构建 nexus-web..."
  pnpm build

  cd "${REPO_ROOT}"
}

# ─── 静态服务兜底：用 npx serve ───────────────────────────────────────────────
_nexus_serve_fallback() {
  local dist_dir="$1"
  log_warn "nexus-web 缺少 preview/serve 脚本，使用 npx serve 作为静态服务..."
  if ! command -v serve >/dev/null 2>&1; then
    npm install -g serve --quiet 2>/dev/null || true
  fi
  nohup serve -s "$dist_dir" -l "${NEXUS_PORT}" \
    > "${LOGS_DIR}/nexus.log" 2>&1 &
  echo $!
}

# ─── 启动 nexus-web ───────────────────────────────────────────────────────────
nexus_start() {
  nexus_fetch_source
  nexus_patch_package_json
  nexus_build

  check_port_free "$NEXUS_PORT" "nexus"
  ensure_deploy_dirs

  local log_file="${LOGS_DIR}/nexus.log"
  local pid

  cd "${NEXUS_SRC_DIR}"

  # 优先使用上游 preview 脚本
  if node -e "
const pkg = require('./package.json');
process.exit(pkg.scripts && pkg.scripts.preview ? 0 : 1);
" 2>/dev/null; then
    log_step "启动 nexus-web（pnpm preview，端口 ${NEXUS_PORT}，日志：${log_file}）..."
    # 部分上游的 preview 端口固定，先尝试 --port 透传
    nohup pnpm preview --host 0.0.0.0 --port "${NEXUS_PORT}" \
      > "$log_file" 2>&1 &
    pid=$!
  else
    # 找 dist 目录兜底
    local dist_dir="dist"
    [ -d "dist" ] || dist_dir="build"
    if [ -d "$dist_dir" ]; then
      pid="$(_nexus_serve_fallback "${NEXUS_SRC_DIR}/${dist_dir}")"
    else
      log_error "nexus-web 既无 preview 脚本，也无 dist/build 目录，无法启动静态服务。"
      cd "${REPO_ROOT}"
      return 1
    fi
  fi

  cd "${REPO_ROOT}"
  write_pid "nexus" "$pid"
  log_info "nexus PID=${pid}"
  wait_for_http "http://localhost:${NEXUS_PORT}/" "nexus" 60 || true
}

# ─── 停止 nexus ───────────────────────────────────────────────────────────────
nexus_stop() {
  stop_by_pid "nexus"
}
