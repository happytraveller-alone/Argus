#!/bin/sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RUST_BACKEND_DIR="${SCRIPT_DIR}/../backend"

echo "backend_old/start.sh 已废弃，改为转发到 Rust backend 启动脚本..."
cd "${RUST_BACKEND_DIR}"
exec ./start.sh
