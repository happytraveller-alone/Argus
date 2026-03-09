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
STAMP_FILE="/pnpm/store/.deepaudit_frontend_lock.sha256"
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

exec pnpm dev --host 0.0.0.0 --port "${FRONTEND_DEV_PORT:-5173}"
