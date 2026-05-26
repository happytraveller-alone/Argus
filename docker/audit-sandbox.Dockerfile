# Audit sandbox for intelligent agent tool execution + codegraph code intelligence.
# Archive is mounted read-only at /workspace; /tmp is writable for PoC execution.
# /codegraph/{src,index,cache_in} are mount points for codegraph indexing.
ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:20-bookworm-slim AS node-runtime

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:bookworm-slim

ARG APT_MIRROR=mirrors.aliyun.com
ARG NPM_MIRROR=https://registry.npmmirror.com
ARG CODEGRAPH_VERSION=0.9.4

# Switch apt sources for faster builds in China and force image-local package
# managers to ignore host-only proxy settings injected by container engines.
RUN set -eux; \
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "30";'; \
      echo 'Acquire::https::Timeout "30";'; \
      echo 'Acquire::ForceIPv4 "true";'; \
    } > /etc/apt/apt.conf.d/99-argus-no-proxy; \
    sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
    grep \
    findutils \
    coreutils \
    file \
    procps \
    python3 \
    python3-pip \
    gcc \
    g++ \
    make \
    curl \
    git \
    jq \
    ca-certificates \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS from the mirrored Node base image instead of running
# the external NodeSource setup script inside this image.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN set -eux; \
    ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    npm config --global delete proxy || true; \
    npm config --global delete https-proxy || true; \
    npm config --global set registry "${NPM_MIRROR}"; \
    node --version | grep -E '^v20\.'; \
    npm --version

# Install codegraph at pinned version via China npm mirror
RUN set -eux; \
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY; \
    npm install -g "@colbymchenry/codegraph@${CODEGRAPH_VERSION}" && \
    codegraph --version

# Create non-root user for sandbox execution
RUN useradd -m -s /bin/bash auditor

# Workspace mount point (archive mounted here read-only)
RUN mkdir -p /workspace && chown auditor:auditor /workspace

# Writable tmp for PoC compilation/execution
RUN mkdir -p /tmp/poc && chown auditor:auditor /tmp/poc

# Codegraph mount points (per ralplan-codegraph-integration v3.2):
#   /codegraph/src     - bind-mounted host-extracted staging source, writable while indexing
#   /codegraph/index   - bind-mounted host writable index dir (where codegraph writes .codegraph/)
#   /codegraph/cache_in - bind-mounted host cache dir, read-only (pre-built index for cache hits)
RUN mkdir -p /codegraph/src /codegraph/index /codegraph/cache_in && \
    chown -R auditor:auditor /codegraph

USER auditor
WORKDIR /workspace

# Keep container alive for exec commands
CMD ["sleep", "infinity"]
