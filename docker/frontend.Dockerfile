# =============================================
# VulHunter Frontend Docker 构建（BuildKit 缓存优化）
# =============================================

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim AS pnpm-base

WORKDIR /app

# 彻底清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"

ARG FRONTEND_NPM_REGISTRY=https://registry.npmmirror.com
ARG FRONTEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG PNPM_VERSION=9.15.4
ARG BUILD_WEAK_NETWORK=false
ARG BUILD_ARCH=

ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 使用 corepack 管理 pnpm，镜像优先且支持官方回退
RUN --mount=type=cache,id=vulhunter-frontend-npm,target=/root/.npm \
    --mount=type=cache,id=vulhunter-frontend-corepack,target=/root/.cache/node/corepack \
    set -eux; \
    corepack enable; \
    prepare_pnpm() { \
      reg="$1"; \
      attempt=1; \
      npm config set registry "${reg}"; \
      export COREPACK_NPM_REGISTRY="${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        if corepack prepare "pnpm@${PNPM_VERSION}" --activate; then \
          return 0; \
        fi; \
        sleep $((attempt + 1)); \
        attempt=$((attempt + 1)); \
      done; \
      return 1; \
    }; \
    prepare_pnpm "${FRONTEND_NPM_REGISTRY}" || prepare_pnpm "${FRONTEND_NPM_REGISTRY_FALLBACK}"; \
    npm config set registry "${FRONTEND_NPM_REGISTRY}" && \
    pnpm config set registry "${FRONTEND_NPM_REGISTRY}" && \
    pnpm config set store-dir /pnpm/store

FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-alpine AS dev

WORKDIR /app

ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"
ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

COPY scripts/dev-launcher.mjs /usr/local/bin/frontend-dev-launcher.mjs

RUN corepack enable

EXPOSE 5173

ENTRYPOINT ["node"]
CMD ["/usr/local/bin/frontend-dev-launcher.mjs"]

FROM pnpm-base AS builder

# 复制依赖文件
COPY package.json pnpm-lock.yaml ./

# 利用 BuildKit 缓存 mount 复用 pnpm store，减少重复下载
RUN --mount=type=cache,id=vulhunter-frontend-pnpm,target=/pnpm/store \
    --mount=type=cache,id=vulhunter-frontend-npm,target=/root/.npm \
    set -eux; \
    FALLBACK_REGISTRY="${FRONTEND_NPM_REGISTRY_FALLBACK}"; \
    step_timeout=300; \
    pnpm config set network-timeout 120000; \
    pnpm config set fetch-retries 1; \
    run_frontend_install() { \
      if [ "${BUILD_WEAK_NETWORK}" = "true" ] || [ "${BUILD_ARCH}" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; then \
        timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline --network-concurrency 1; \
      else \
        timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline; \
      fi; \
    }; \
    install_frontend_deps() { \
      reg="$1"; \
      attempt=1; \
      if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
        echo "pnpm registry probe failed for ${reg}, continue with direct fetch attempt." >&2; \
      fi; \
      pnpm config set registry "${reg}"; \
      while [ "${attempt}" -le 2 ]; do \
        echo "pnpm fetch via ${reg} (attempt ${attempt}/2, timeout ${step_timeout}s)"; \
        if timeout "${step_timeout}" pnpm fetch --frozen-lockfile; then \
          if run_frontend_install; then \
            return 0; \
          fi; \
          install_status="$?"; \
          if [ "${install_status}" -eq 124 ]; then \
            echo "pnpm install timed out via ${reg} after ${step_timeout}s (attempt ${attempt}/2)." >&2; \
          else \
            echo "pnpm install failed via ${reg} (attempt ${attempt}/2, exit ${install_status})." >&2; \
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
    install_frontend_deps "${FRONTEND_NPM_REGISTRY}" || install_frontend_deps "${FALLBACK_REGISTRY}"

# 复制源代码
COPY . .

ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# 构建生产版本
# - VITE_CACHE_DIR 指向 BuildKit cache mount，跨构建复用 vite 转换缓存
# - NODE_OPTIONS 防止大型 bundle 触发 OOM
RUN --mount=type=cache,id=vulhunter-frontend-vite-build,target=/tmp/vite-build-cache \
    VITE_CACHE_DIR=/tmp/vite-build-cache \
    NODE_OPTIONS="--max-old-space-size=3072" \
    pnpm build

FROM ${DOCKERHUB_LIBRARY_MIRROR}/nginx:alpine-slim

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置 (包含 SSE 反向代理配置)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
