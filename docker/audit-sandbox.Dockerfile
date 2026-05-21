# Audit sandbox for intelligent agent tool execution.
# Archive is mounted read-only at /workspace; /tmp is writable for PoC execution.
ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:bookworm-slim

ARG APT_MIRROR=mirrors.aliyun.com

# Switch apt sources for faster builds in China
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    grep \
    findutils \
    coreutils \
    file \
    python3 \
    python3-pip \
    gcc \
    g++ \
    make \
    curl \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for sandbox execution
RUN useradd -m -s /bin/bash auditor

# Workspace mount point (archive mounted here read-only)
RUN mkdir -p /workspace && chown auditor:auditor /workspace

# Writable tmp for PoC compilation/execution
RUN mkdir -p /tmp/poc && chown auditor:auditor /tmp/poc

USER auditor
WORKDIR /workspace

# Keep container alive for exec commands
CMD ["sleep", "infinity"]
