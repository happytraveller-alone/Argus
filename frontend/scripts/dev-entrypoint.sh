#!/usr/bin/env sh
set -eu

cd /app

corepack enable >/dev/null 2>&1 || true
corepack prepare "pnpm@${PNPM_VERSION:-9.15.4}" --activate >/dev/null 2>&1 || true

pnpm config set registry "${FRONTEND_NPM_REGISTRY:-https://registry.npmmirror.com}" >/dev/null 2>&1 || true
pnpm config set store-dir /pnpm/store >/dev/null 2>&1 || true
pnpm config set network-timeout 300000 >/dev/null 2>&1 || true
pnpm config set fetch-retries 5 >/dev/null 2>&1 || true

LOCK_FILE="/app/pnpm-lock.yaml"
STAMP_FILE="/pnpm/store/.Argus_frontend_lock.sha256"
INSTALL_MODE="${FRONTEND_DEV_INSTALL_MODE:-auto}"
NEED_INSTALL="0"

if [ ! -f /app/node_modules/.modules.yaml ] || [ ! -x /app/node_modules/.bin/vite ] || [ ! -x /app/node_modules/.bin/tsc ]; then
  NEED_INSTALL="1"
fi

if [ "$INSTALL_MODE" = "always" ]; then
  NEED_INSTALL="1"
elif [ "$INSTALL_MODE" = "never" ]; then
  NEED_INSTALL="0"
elif [ -f "$LOCK_FILE" ]; then
  CURRENT_HASH="$(sha256sum "$LOCK_FILE" | awk '{print $1}')"
  PREVIOUS_HASH=""
  if [ -f "$STAMP_FILE" ]; then
    PREVIOUS_HASH="$(cat "$STAMP_FILE" 2>/dev/null || true)"
  fi
  if [ "$CURRENT_HASH" != "$PREVIOUS_HASH" ]; then
    NEED_INSTALL="1"
  fi
fi

if [ "$NEED_INSTALL" = "1" ]; then
  echo "[frontend-dev] installing dependencies..."
  pnpm install --no-frozen-lockfile
  if [ -f "$LOCK_FILE" ]; then
    sha256sum "$LOCK_FILE" | awk '{print $1}' > "$STAMP_FILE"
  fi
else
  echo "[frontend-dev] lockfile unchanged, skip install"
fi

export BROWSER="${BROWSER:-none}"
FRONTEND_PUBLIC_URL="${FRONTEND_PUBLIC_URL:-http://localhost:3000}"
BACKEND_PUBLIC_URL="${BACKEND_PUBLIC_URL:-http://localhost:8000}"
VITE_READY_URL="http://127.0.0.1:${FRONTEND_DEV_PORT:-5173}/"

if [ -z "${CHOKIDAR_USEPOLLING:-}" ]; then
  case "$(uname -s)" in
    Darwin|MINGW*|MSYS*|CYGWIN*)
      export CHOKIDAR_USEPOLLING=true
      ;;
    *)
      export CHOKIDAR_USEPOLLING=false
      ;;
  esac
fi

pnpm dev --host 0.0.0.0 --port "${FRONTEND_DEV_PORT:-5173}" &
vite_pid=$!

cleanup() {
  if kill -0 "$vite_pid" 2>/dev/null; then
    kill "$vite_pid" 2>/dev/null || true
  fi
}

trap cleanup INT TERM

ready_logged=0
while kill -0 "$vite_pid" 2>/dev/null; do
  if curl -fsS "${VITE_READY_URL}" >/dev/null 2>&1; then
    if [ "$ready_logged" -eq 0 ]; then
      echo "[frontend-dev] frontend ready: ${FRONTEND_PUBLIC_URL}"
      echo "[frontend-dev] backend docs: ${BACKEND_PUBLIC_URL}/docs"
      ready_logged=1
    fi
    break
  fi
  sleep 1
done

wait "$vite_pid"
