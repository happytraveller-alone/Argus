#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$FRONTEND_DIR/.." && pwd)"

if [ ! -f "$FRONTEND_DIR/.env" ] && [ -f "$FRONTEND_DIR/.env.example" ]; then
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env"
  echo "✅ 已从 .env.example 创建 frontend/.env"
fi

NODE_OK="0"
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  NODE_MINOR="$(node -p 'process.versions.node.split(".")[1]' 2>/dev/null || echo 0)"
  if [ "$NODE_MAJOR" -gt 20 ] || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -ge 6 ]; }; then
    NODE_OK="1"
  fi
fi

if [ "$NODE_OK" = "1" ]; then
  if ! command -v pnpm >/dev/null 2>&1 && command -v corepack >/dev/null 2>&1; then
    corepack enable || true
    corepack prepare pnpm@9.15.4 --activate || true
  fi
  if command -v pnpm >/dev/null 2>&1; then
    echo "✅ 使用本机 Node + pnpm 安装前端依赖"
    cd "$FRONTEND_DIR"
    exec pnpm install --no-frozen-lockfile
  fi
fi

echo "ℹ️ 本机前端工具链不可用，切换到 Docker 前端环境完成安装"
cd "$REPO_ROOT"
exec bash "$SCRIPT_DIR/run-in-dev-container.sh" pnpm install --no-frozen-lockfile
