# =============================================
# CodeQL Scanner Image (optimized build)
# Pre-download artifacts to docker/cache/ via:
#   docker/codeql-cache-download.sh
# Then build with:
#   podman build -f docker/codeql.Dockerfile --network=host \
#     --tag localhost/argus/codeql-runner:latest .
# =============================================
ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
ARG APT_MIRROR=mirrors.aliyun.com
ARG CODEQL_VERSION=2.16.1
ARG GRADLE_VERSION=8.7

# ── Single stage: runtime (artifacts pre-cached) ────────────────────────────
FROM ${DOCKERHUB_LIBRARY_MIRROR}/ubuntu:22.04 AS runtime

LABEL org.argus.scanner=codeql

ENV DEBIAN_FRONTEND=noninteractive

ARG APT_MIRROR=mirrors.aliyun.com
ARG GRADLE_VERSION=8.7
ARG CODEQL_VERSION=2.16.1

RUN sed -i "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g; \
    s|http://security.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates unzip \
    gcc g++ make cmake autoconf automake libtool pkg-config \
    openjdk-17-jdk-headless maven \
    python3 python3-pip python3-venv python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# COPY pre-downloaded artifacts from build context cache
COPY docker/cache/codeql-bundle-linux64.tar.gz /tmp/codeql-bundle.tar.gz
RUN mkdir -p /opt/codeql && tar -xzf /tmp/codeql-bundle.tar.gz -C /opt \
    && rm /tmp/codeql-bundle.tar.gz

COPY docker/cache/gradle-${GRADLE_VERSION}-bin.zip /tmp/gradle.zip
RUN unzip -q /tmp/gradle.zip -d /opt && rm /tmp/gradle.zip
RUN ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle

ENV PATH="/opt/codeql:${PATH}"
