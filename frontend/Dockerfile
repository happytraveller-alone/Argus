# syntax=docker/dockerfile:1.7
# =============================================
# DeepAudit Frontend Docker 构建（BuildKit 缓存优化）
# =============================================

FROM node:20-slim AS builder

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
ARG PNPM_VERSION=9.15.4
ARG BUILD_WEAK_NETWORK=false
ARG BUILD_ARCH=

ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 使用 corepack 管理 pnpm，避免全局 npm install 带来的层抖动
RUN corepack enable && \
    corepack prepare pnpm@${PNPM_VERSION} --activate && \
    npm config set registry ${FRONTEND_NPM_REGISTRY} && \
    pnpm config set registry ${FRONTEND_NPM_REGISTRY} && \
    pnpm config set store-dir /pnpm/store

# 复制依赖文件
COPY package.json pnpm-lock.yaml ./

# 利用 BuildKit 缓存 mount 复用 pnpm store，减少重复下载
RUN --mount=type=cache,id=deepaudit-frontend-pnpm,target=/pnpm/store \
    set -eux; \
    pnpm config set network-timeout 300000; \
    pnpm config set fetch-retries 5; \
    pnpm fetch --frozen-lockfile; \
    if [ "${BUILD_WEAK_NETWORK}" = "true" ] || [ "${BUILD_ARCH}" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; then \
      pnpm install --frozen-lockfile --offline --prefer-offline --network-concurrency 1; \
    else \
      pnpm install --frozen-lockfile --offline --prefer-offline; \
    fi

# 复制源代码
COPY . .

# 构建时使用占位符，运行时由 entrypoint 注入 API 地址
ENV VITE_API_BASE_URL=__API_BASE_URL__

# 构建生产版本
RUN pnpm build

# =============================================
# 生产镜像 - 使用 Nginx (支持 SSE 反向代理)
# =============================================
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 Nginx 配置 (包含 SSE 反向代理配置)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制启动脚本
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
