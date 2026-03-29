ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library

FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:20-alpine AS source

WORKDIR /src

ARG NEXUS_WEB_REPO_URL=https://github.com/happytraveller-alone/nexus-web.git
ARG NEXUS_WEB_GIT_MIRROR_PREFIX=https://v6.gh-proxy.org/
ARG NEXUS_WEB_GIT_REF=
ARG NEXUS_WEB_PNPM_VERSION=10.32.1

RUN apk add --no-cache git

RUN set -eux; \
    git clone --depth=1 "${NEXUS_WEB_GIT_MIRROR_PREFIX}${NEXUS_WEB_REPO_URL}" .; \
    if [ -n "${NEXUS_WEB_GIT_REF}" ]; then \
      git fetch --depth=1 origin "${NEXUS_WEB_GIT_REF}"; \
      git checkout --detach FETCH_HEAD; \
    fi

RUN NEXUS_WEB_PNPM_VERSION="${NEXUS_WEB_PNPM_VERSION}" node -e '\
const fs = require("fs");\
const path = "/src/package.json";\
const pkg = JSON.parse(fs.readFileSync(path, "utf8"));\
if (pkg.packageManager) process.exit(0);\
pkg.packageManager = `pnpm@${process.env.NEXUS_WEB_PNPM_VERSION}`;\
fs.writeFileSync(path, `${JSON.stringify(pkg, null, 2)}\n`);\
'

FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:20-alpine AS deps

WORKDIR /app

ARG NEXUS_WEB_NPM_REGISTRY=https://registry.npmmirror.com
ARG NEXUS_WEB_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG NEXUS_WEB_PNPM_VERSION=10.32.1

ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

COPY --from=source /src/package.json /src/pnpm-lock.yaml ./

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

FROM deps AS build

WORKDIR /app

# RUN apk add --no-cache git

COPY --from=source /src/. ./
# COPY patches/nexus-web-build.patch /tmp/nexus-web-build.patch

# RUN set -eux; \
#     git apply --check /tmp/nexus-web-build.patch; \
#     git apply /tmp/nexus-web-build.patch; \
#     pnpm build
RUN pnpm build
FROM ${DOCKERHUB_LIBRARY_MIRROR}/nginx:1.27-alpine AS runtime

RUN set -eux; \
    rm -rf /usr/share/nginx/html/*; \
    rm -f /etc/nginx/conf.d/default.conf; \
    mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp; \
    chown -R nginx:nginx /usr/share/nginx/html /tmp /var/cache/nginx

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=nginx:nginx /app/dist/ /usr/share/nginx/html/

USER nginx

EXPOSE 5174

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:5174/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
