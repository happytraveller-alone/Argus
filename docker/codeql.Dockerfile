# =============================================
# CodeQL Scanner Image (multi-stage build)
# Base image for CodeQL static analysis scans.
# Used as base for both exploration and scan modes.
# =============================================
ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
ARG APT_MIRROR=mirrors.aliyun.com
ARG CODEQL_VERSION=2.16.1
ARG GRADLE_VERSION=8.7

# ── Stage 1: Download artifacts ──────────────────────────────────────────────
FROM ${DOCKERHUB_LIBRARY_MIRROR}/ubuntu:22.04 AS downloader

ARG APT_MIRROR=mirrors.aliyun.com
ARG CODEQL_VERSION=2.16.1
ARG GRADLE_VERSION=8.7

ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g; \
    s|http://security.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates wget unzip \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q \
    "https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_VERSION}/codeql-bundle-linux64.tar.gz" \
    -O /tmp/codeql-bundle.tar.gz \
    && mkdir -p /opt/codeql-extracted \
    && tar -xzf /tmp/codeql-bundle.tar.gz -C /opt/codeql-extracted \
    && rm /tmp/codeql-bundle.tar.gz

RUN wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
    -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && rm /tmp/gradle.zip

# ── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM ${DOCKERHUB_LIBRARY_MIRROR}/ubuntu:22.04 AS runtime

LABEL org.argus.scanner=codeql

ENV DEBIAN_FRONTEND=noninteractive

ARG APT_MIRROR=mirrors.aliyun.com
ARG GRADLE_VERSION=8.7

RUN sed -i "s|http://archive.ubuntu.com|http://${APT_MIRROR}|g; \
    s|http://security.ubuntu.com|http://${APT_MIRROR}|g" /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates \
    gcc g++ make cmake autoconf automake libtool pkg-config \
    openjdk-17-jdk-headless maven \
    python3 python3-pip python3-venv python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=downloader /opt/codeql-extracted/codeql /opt/codeql
COPY --from=downloader /opt/gradle-${GRADLE_VERSION} /opt/gradle-${GRADLE_VERSION}
RUN ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle

ENV PATH="/opt/codeql:${PATH}"
