# DeepAudit Agent Sandbox
# 安全沙箱环境用于漏洞验证和 PoC 执行
# 集成各类安全扫描工具 (Opengrep, Bandit, Gitleaks, etc.)

ARG SANDBOX_BASE_IMAGE=docker.m.daocloud.io/python:3.11-bullseye
FROM ${SANDBOX_BASE_IMAGE}

LABEL maintainer="XCodeReviewer Team"
LABEL description="Secure sandbox environment for vulnerability verification and security scanning"

# 安装基本工具
# 安装基本工具
# 使用阿里云镜像加速 apt
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    netcat-openbsd \
    dnsutils \
    iputils-ping \
    ca-certificates \
    git \
    unzip \
    jq \
    php-cli \
    openjdk-11-jdk-headless \
    ruby-full \
    build-essential \
    cmake \
    clang \
    llvm \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# 统一 Python 包镜像源（uv/pip）
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 安装 Node.js 22+ 与 pnpm（用于 JavaScript/TypeScript 代码执行、npm audit、qmd）
# 使用 npmmirror 节点二进制下载，避免额外 apt 源
RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "$ARCH" in \
      amd64) NODE_ARCH="x64" ;; \
      arm64) NODE_ARCH="arm64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    NODE_BASE_URL_PRIMARY="https://npmmirror.com/mirrors/node/latest-v22.x"; \
    NODE_BASE_URL_FALLBACK="https://nodejs.org/dist/latest-v22.x"; \
    NODE_BASE_URL="${NODE_BASE_URL_PRIMARY}"; \
    NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" 2>/dev/null | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
    if [ -z "${NODE_TARBALL}" ]; then \
      NODE_BASE_URL="${NODE_BASE_URL_FALLBACK}"; \
      NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
    fi; \
    test -n "${NODE_TARBALL}"; \
    if ! curl -fL "${NODE_BASE_URL}/${NODE_TARBALL}" -o /tmp/node.tar.xz; then \
      NODE_BASE_URL="${NODE_BASE_URL_FALLBACK}"; \
      NODE_TARBALL="$(curl -fsSL "${NODE_BASE_URL}/SHASUMS256.txt" | tr -d '\r' | awk '$2 ~ /linux-'"${NODE_ARCH}"'[.]tar[.]xz$/ {print $2; exit}')"; \
      test -n "${NODE_TARBALL}"; \
      curl -fL "${NODE_BASE_URL}/${NODE_TARBALL}" -o /tmp/node.tar.xz; \
    fi; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner; \
    rm -f /tmp/node.tar.xz; \
    export COREPACK_NPM_REGISTRY="https://registry.npmmirror.com"; \
    corepack enable; \
    corepack prepare pnpm@9.15.4 --activate; \
    pnpm config set registry https://registry.npmmirror.com; \
    node --version; npm --version; pnpm --version

# bullseye 自带 cmake 版本过低（arm64 下 qmd 依赖 node-llama-cpp 需要 >=3.19）
RUN python3 -m pip install --no-cache-dir "cmake>=3.27,<4" && \
    cmake --version

# 安装 MCP 与 qmd CLI（供沙盒域运行时调用）
RUN mkdir -p /pnpm /pnpm/global && \
    pnpm config set global-bin-dir /pnpm && \
    pnpm config set global-dir /pnpm/global && \
    pnpm add -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-sequential-thinking \
    @tobilu/qmd

# 安装 Go (使用阿里云镜像)
ENV PATH=$PATH:/usr/local/go/bin
ENV GOPROXY=https://goproxy.cn,direct
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://mirrors.aliyun.com/golang/go1.21.6.linux-amd64.tar.gz -o go.tar.gz && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz

# 安装 Rust (使用 rsproxy 镜像)
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH \
    RUSTUP_DIST_SERVER=https://rsproxy.cn \
    RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl --proto '=https' --tlsv1.2 -sSf https://rsproxy.cn/rustup-init.sh | sh -s -- -y --default-toolchain stable --profile minimal && \
    chmod -R a+w /usr/local/cargo

# 安装 Python 安全工具
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    pip install --no-cache-dir \
    requests \
    httpx \
    aiohttp \
    beautifulsoup4 \
    lxml \
    pycryptodome \
    paramiko \
    pyjwt \
    python-jose \
    sqlparse \
    bandit \
    safety

# code-index-mcp 是 Python 包（非 npm 包）
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    pip install --no-cache-dir code-index-mcp

# 安装 Opengrep CLI（仅使用官方安装脚本）
ARG OPENGREP_VERSION=v1.15.1

RUN set -eux; \
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64|amd64) OG_DIST="opengrep_manylinux_x86" ;; \
      aarch64|arm64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: $ARCH" >&2; exit 1 ;; \
    esac; \
    curl -fL "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
      -o /usr/local/bin/opengrep.real; \
    chmod +x /usr/local/bin/opengrep.real; \
    printf '#!/bin/sh\nunset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy\nexport NO_PROXY="*"\nexport no_proxy="*"\nexec /usr/local/bin/opengrep.real "$@"\n' \
      > /usr/local/bin/opengrep; \
    chmod +x /usr/local/bin/opengrep; \
    opengrep --version


# 安装 Gitleaks
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://github.com/gitleaks/gitleaks/releases/download/v8.18.2/gitleaks_8.18.2_linux_x64.tar.gz -o gitleaks.tar.gz && \
    tar -xzf gitleaks.tar.gz && \
    mv gitleaks /usr/local/bin/ && \
    rm gitleaks.tar.gz

# 安装 TruffleHog
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin

# 安装 OSV-Scanner
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://github.com/google/osv-scanner/releases/download/v1.6.2/osv-scanner_1.6.2_linux_amd64 -o /usr/local/bin/osv-scanner && \
    chmod +x /usr/local/bin/osv-scanner

# 安装 PMD
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://github.com/pmd/pmd/releases/download/pmd_releases%2F7.0.0/pmd-dist-7.0.0-bin.zip -o /tmp/pmd.zip && \
    unzip -q /tmp/pmd.zip -d /opt && \
    ln -s /opt/pmd-bin-7.0.0/bin/pmd /usr/local/bin/pmd && \
    rm /tmp/pmd.zip

# 安装 PHPStan (PHP 静态分析工具) - 使用官方 PHAR 直装版（最稳定）
RUN unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY && \
    curl -L https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar -o /usr/local/bin/phpstan && \
    chmod +x /usr/local/bin/phpstan

# 创建非 root 用户
RUN groupadd -g 1000 sandbox && \
    useradd -u 1000 -g sandbox -m -s /bin/bash sandbox

# 创建工作目录
RUN mkdir -p /workspace /tmp/sandbox \
    /workspace/.deepaudit/mcp/code-index \
    /workspace/.deepaudit/mcp/xdg-data \
    /workspace/.deepaudit/mcp/xdg-cache \
    /workspace/.deepaudit/mcp/xdg-config \
    /workspace/.deepaudit/qmd && \
    chown -R sandbox:sandbox /workspace /tmp/sandbox

# 设置环境变量
ENV HOME=/home/sandbox
ENV PATH=/home/sandbox/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV XDG_DATA_HOME=/workspace/.deepaudit/mcp/xdg-data
ENV XDG_CACHE_HOME=/workspace/.deepaudit/mcp/xdg-cache
ENV XDG_CONFIG_HOME=/workspace/.deepaudit/mcp/xdg-config
ENV QMD_DATA_DIR=/workspace/.deepaudit/qmd
ENV CODE_INDEX_INDEXER_PATH=/workspace/.deepaudit/mcp/code-index

# 限制 Python 导入路径
ENV PYTHONPATH=/workspace

# 切换到非 root 用户
USER sandbox

WORKDIR /workspace

# 默认命令
CMD ["/bin/bash"]
