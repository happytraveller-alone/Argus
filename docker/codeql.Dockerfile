# =============================================
# CodeQL Scanner Image
# Base image for CodeQL static analysis scans.
# Used as base for both exploration and scan modes.
# =============================================
FROM ubuntu:22.04

LABEL org.argus.scanner=codeql

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    unzip \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── C/C++ toolchain ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    cmake \
    autoconf \
    automake \
    libtool \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ── Java (OpenJDK 17 + Maven) ─────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless \
    maven \
    && rm -rf /var/lib/apt/lists/*

# ── Gradle (direct download) ──────────────────────────────────────────────────
ARG GRADLE_VERSION=8.7
RUN wget -q "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
        -O /tmp/gradle.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle \
    && rm /tmp/gradle.zip

# ── Node.js 20 LTS (NodeSource) ───────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python 3 ──────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# ── CodeQL CLI bundle ─────────────────────────────────────────────────────────
ARG CODEQL_VERSION=2.16.1
RUN wget -q \
        "https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_VERSION}/codeql-bundle-linux64.tar.gz" \
        -O /tmp/codeql-bundle.tar.gz \
    && tar -xzf /tmp/codeql-bundle.tar.gz -C /opt \
    && rm /tmp/codeql-bundle.tar.gz

ENV PATH="/opt/codeql:${PATH}"
