#!/usr/bin/env bash
# scripts/build-frontend.sh — 构建 frontend Docker 镜像
#
# 用法:
#   ./scripts/build-frontend.sh
#
# 说明:
#   自动检测当前 CPU 架构（arm64 / amd64），设置 BUILD_ARCH 环境变量后
#   调用 docker compose build frontend。
#   如果 BuildKit 可用则启用 DOCKER_BUILDKIT=1，否则降级继续构建。
#
# 环境变量（可覆盖）:
#   BUILD_ARCH            — 目标架构，默认自动检测（arm64 / amd64）
#   FRONTEND_DOCKERFILE   — 使用的 Dockerfile 路径，默认 Dockerfile

set -euo pipefail

# 定位仓库根目录，保证从任何位置调用都能正确工作
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ─── 架构检测 ─────────────────────────────────────────────────────────────────
# 优先使用 BUILD_ARCH 环境变量；若未设置则自动检测宿主机架构
ARCH_RAW="${BUILD_ARCH:-$(uname -m)}"
case "$ARCH_RAW" in
  arm64|aarch64)
    BUILD_ARCH="arm64"
    ;;
  x86_64|amd64)
    BUILD_ARCH="amd64"
    ;;
  *)
    # 其他架构直接透传，由 Dockerfile 自行处理
    BUILD_ARCH="$ARCH_RAW"
    ;;
esac
export BUILD_ARCH

# ─── BuildKit 检测 ────────────────────────────────────────────────────────────
# BuildKit 提供更快的并行构建与缓存能力；不可用时回退到普通构建
if docker buildx version >/dev/null 2>&1; then
  export DOCKER_BUILDKIT=1
  export FRONTEND_DOCKERFILE="${FRONTEND_DOCKERFILE:-Dockerfile}"
  echo "[INFO] BuildKit detected, using ${FRONTEND_DOCKERFILE}"
else
  export DOCKER_BUILDKIT=0
  export FRONTEND_DOCKERFILE="${FRONTEND_DOCKERFILE:-Dockerfile}"
  echo "[WARN] BuildKit unavailable, continuing with ${FRONTEND_DOCKERFILE}"
fi

# ─── 构建 ─────────────────────────────────────────────────────────────────────
echo "[INFO] building frontend image (arch=${BUILD_ARCH})..."
docker compose build frontend
