ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library

# ─── deps 阶段：安装 pnpm 依赖 ────────────────────────────────────────────────
# build context 为 nexus-web/，nexus-web 源码由 git submodule 提供（nexus-web/src/）
# 不再在构建时克隆外部仓库，离线/内网环境友好，版本由 submodule commit 锁定
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:20-alpine AS deps

WORKDIR /app

ARG NEXUS_WEB_NPM_REGISTRY=https://registry.npmmirror.com
ARG NEXUS_WEB_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG NEXUS_WEB_PNPM_VERSION=10.32.1

ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 只复制 lockfile 相关文件，充分利用 Docker 层缓存；
# 源码来自 submodule（nexus-web/src/），build context 根即为 nexus-web/
COPY src/package.json src/pnpm-lock.yaml ./

# 修补 packageManager 字段（若上游 package.json 缺少该字段，corepack 需要它）
RUN NEXUS_WEB_PNPM_VERSION="${NEXUS_WEB_PNPM_VERSION}" node -e '\
  const fs = require("fs");\
  const path = "/app/package.json";\
  const pkg = JSON.parse(fs.readFileSync(path, "utf8"));\
  if (pkg.packageManager) process.exit(0);\
  pkg.packageManager = `pnpm@${process.env.NEXUS_WEB_PNPM_VERSION}`;\
  fs.writeFileSync(path, `${JSON.stringify(pkg, null, 2)}\n`);\
  '

RUN --mount=type=cache,id=nexus-web-npm,target=/root/.npm \
  --mount=type=cache,id=nexus-web-corepack,target=/root/.cache/node/corepack \
  --mount=type=cache,id=nexus-web-pnpm,target=/pnpm/store \
  set -eux; \
  FALLBACK_REGISTRY="${NEXUS_WEB_NPM_REGISTRY_FALLBACK}"; \
  step_timeout=300; \
  corepack enable; \
  prepare_pnpm() { \
  reg="$1"; \
  attempt=1; \
  npm config set registry "${reg}"; \
  export COREPACK_NPM_REGISTRY="${reg}"; \
  while [ "${attempt}" -le 2 ]; do \
  if corepack prepare "pnpm@${NEXUS_WEB_PNPM_VERSION}" --activate; then \
  return 0; \
  else \
  prepare_status="$?"; \
  echo "pnpm bootstrap failed via ${reg} (attempt ${attempt}/2, exit ${prepare_status})." >&2; \
  fi; \
  sleep $((attempt + 1)); \
  attempt=$((attempt + 1)); \
  done; \
  return 1; \
  }; \
  run_nexus_install() { \
  timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline --network-concurrency 1; \
  }; \
  install_nexus_deps() { \
  reg="$1"; \
  attempt=1; \
  if ! wget -q -T 5 -O /dev/null "${reg}/-/ping"; then \
  echo "pnpm registry probe failed for ${reg}, continue with direct fetch attempt." >&2; \
  fi; \
  pnpm config set registry "${reg}"; \
  while [ "${attempt}" -le 2 ]; do \
  echo "pnpm fetch via ${reg} (attempt ${attempt}/2, timeout ${step_timeout}s)"; \
  if timeout "${step_timeout}" pnpm fetch --frozen-lockfile; then \
  if run_nexus_install; then \
  return 0; \
  else \
  install_status="$?"; \
  if [ "${install_status}" -eq 124 ]; then \
  echo "pnpm install timed out via ${reg} after ${step_timeout}s (attempt ${attempt}/2)." >&2; \
  else \
  echo "pnpm install failed via ${reg} (attempt ${attempt}/2, exit ${install_status})." >&2; \
  fi; \
  fi; \
  else \
  fetch_status="$?"; \
  if [ "${fetch_status}" -eq 124 ]; then \
  echo "pnpm fetch timed out via ${reg} after ${step_timeout}s (attempt ${attempt}/2)." >&2; \
  else \
  echo "pnpm fetch failed via ${reg} (attempt ${attempt}/2, exit ${fetch_status})." >&2; \
  fi; \
  fi; \
  sleep $((attempt + 1)); \
  attempt=$((attempt + 1)); \
  done; \
  return 1; \
  }; \
  prepare_pnpm "${NEXUS_WEB_NPM_REGISTRY}" || prepare_pnpm "${FALLBACK_REGISTRY}"; \
  npm config set registry "${NEXUS_WEB_NPM_REGISTRY}"; \
  pnpm config set store-dir /pnpm/store; \
  pnpm config set network-timeout 120000; \
  pnpm config set fetch-retries 1; \
  install_nexus_deps "${NEXUS_WEB_NPM_REGISTRY}" || install_nexus_deps "${FALLBACK_REGISTRY}"

# ─── build 阶段：复制完整源码并构建 ──────────────────────────────────────────
FROM deps AS build

WORKDIR /app

# 将 submodule 中的完整源码复制进来（覆盖 deps 阶段只有 lockfile 的目录）
COPY src/. ./

RUN pnpm build

# ─── runtime 阶段：nginx 静态服务 ─────────────────────────────────────────────
FROM ${DOCKERHUB_LIBRARY_MIRROR}/nginx:1.27-alpine AS runtime

RUN set -eux; \
  rm -rf /usr/share/nginx/html/*; \
  rm -f /etc/nginx/conf.d/default.conf; \
  mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp; \
  chown -R nginx:nginx /usr/share/nginx/html /tmp /var/cache/nginx

# nginx.conf 由主仓库的 nexus-web/nginx.conf 提供（随 build context 传入）
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /app/dist/ /usr/share/nginx/html/

USER nginx

EXPOSE 5174