# Argus Sandbox Runner - 按需加载代码执行镜像
# 参考 flow-parser-runner 设计,专注于安全隔离的代码执行能力
# 不包含重量级扫描工具,保持镜像精简

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG SANDBOX_RUNNER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG SANDBOX_RUNNER_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG SANDBOX_RUNNER_APT_MIRROR_FALLBACK=deb.debian.org
ARG SANDBOX_RUNNER_APT_SECURITY_FALLBACK=security.debian.org
ARG SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG SANDBOX_RUNNER_NPM_REGISTRY=https://registry.npmmirror.com

# === Stage 1: Node.js 运行时 ===
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim AS nodebase

# === Stage 2: 构建阶段 - 安装工具和依赖 ===
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS builder

ARG SANDBOX_RUNNER_APT_MIRROR_PRIMARY
ARG SANDBOX_RUNNER_APT_SECURITY_PRIMARY
ARG SANDBOX_RUNNER_APT_MIRROR_FALLBACK
ARG SANDBOX_RUNNER_APT_SECURITY_FALLBACK
ARG SANDBOX_RUNNER_PYPI_INDEX_PRIMARY

# 安装构建依赖
RUN --mount=type=cache,id=Argus-sandbox-runner-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=Argus-sandbox-runner-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::http::Timeout "30";'; \
      echo 'Acquire::https::Timeout "30";'; \
      echo 'Acquire::ForceIPv4 "true";'; \
    } > /etc/apt/apt.conf.d/99-sandbox-runner-network; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_build_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        wget; \
    }; \
    write_sources "${SANDBOX_RUNNER_APT_MIRROR_PRIMARY}" "${SANDBOX_RUNNER_APT_SECURITY_PRIMARY}"; \
    if ! install_build_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${SANDBOX_RUNNER_APT_MIRROR_FALLBACK}" "${SANDBOX_RUNNER_APT_SECURITY_FALLBACK}"; \
      install_build_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# 创建虚拟环境并安装 Python 依赖
ENV VIRTUAL_ENV=/opt/sandbox-runner-venv
ENV PATH=/opt/sandbox-runner-venv/bin:${PATH}

RUN python3 -m venv /opt/sandbox-runner-venv

# 安装运行时 Python 库 (只安装代码执行所需的最小依赖)
RUN --mount=type=cache,id=Argus-sandbox-runner-pip,target=/root/.cache/pip \
    set -eux; \
    pip_install_with_index() { \
      idx="$1"; \
      PIP_DEFAULT_TIMEOUT=60 /opt/sandbox-runner-venv/bin/pip install \
        --disable-pip-version-check \
        -i "${idx}" \
        requests \
        httpx \
        beautifulsoup4 \
        pycryptodome \
        pyjwt; \
    }; \
    pip_install_with_index "${SANDBOX_RUNNER_PYPI_INDEX_PRIMARY}" || \
    pip_install_with_index "https://pypi.org/simple"

# === Stage 3: 运行时阶段 ===
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS sandbox-runner

ARG SANDBOX_RUNNER_APT_MIRROR_PRIMARY
ARG SANDBOX_RUNNER_APT_SECURITY_PRIMARY
ARG SANDBOX_RUNNER_APT_MIRROR_FALLBACK
ARG SANDBOX_RUNNER_APT_SECURITY_FALLBACK
ARG SANDBOX_RUNNER_NPM_REGISTRY

LABEL maintainer="Argus Team"
LABEL description="Lightweight sandbox runner for on-demand code execution"

# 只安装运行时必需的包 (移除构建工具)
RUN --mount=type=cache,id=Argus-sandbox-runner-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,id=Argus-sandbox-runner-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; \
    rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
    { \
      echo 'Acquire::http::Proxy "false";'; \
      echo 'Acquire::https::Proxy "false";'; \
      echo 'Acquire::Retries "3";'; \
      echo 'Acquire::http::Timeout "20";'; \
      echo 'Acquire::https::Timeout "20";'; \
      echo 'Acquire::ForceIPv4 "true";'; \
    } > /etc/apt/apt.conf.d/99-sandbox-runner-network; \
    . /etc/os-release; \
    CODENAME="${VERSION_CODENAME:-bookworm}"; \
    write_sources() { \
      main_host="$1"; \
      security_host="$2"; \
      rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
      printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
      printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    }; \
    install_runtime_packages() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        netcat-openbsd \
        dnsutils \
        iputils-ping \
        git \
        jq \
        php-cli \
        openjdk-21-jre-headless \
        ruby; \
    }; \
    write_sources "${SANDBOX_RUNNER_APT_MIRROR_PRIMARY}" "${SANDBOX_RUNNER_APT_SECURITY_PRIMARY}"; \
    if ! install_runtime_packages; then \
      rm -rf /var/lib/apt/lists/*; \
      write_sources "${SANDBOX_RUNNER_APT_MIRROR_FALLBACK}" "${SANDBOX_RUNNER_APT_SECURITY_FALLBACK}"; \
      install_runtime_packages; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# 复制 Node.js 运行时
COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN set -eux; \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
    ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    npm config set registry "${SANDBOX_RUNNER_NPM_REGISTRY}"; \
    node --version; \
    npm --version

# 复制虚拟环境
COPY --from=builder /opt/sandbox-runner-venv /opt/sandbox-runner-venv

# 设置环境变量
ENV VIRTUAL_ENV=/opt/sandbox-runner-venv
ENV PATH=/opt/sandbox-runner-venv/bin:${PATH}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONNOUSERSITE=1
ENV HOME=/home/sandbox

# 创建非 root 用户
RUN groupadd -g 1000 sandbox && \
    useradd -u 1000 -g sandbox -m -s /bin/bash sandbox

# 创建工作目录并设置权限
RUN mkdir -p /workspace /scan && \
    chown -R sandbox:sandbox /workspace /scan

# 限制 Python 导入路径
ENV PYTHONPATH=/workspace

# 切换到非 root 用户
USER sandbox

WORKDIR /workspace

# 验证安装
RUN set -eux; \
    python3 --version; \
    node --version; \
    npm --version; \
    php --version; \
    java --version; \
    ruby --version; \
    python3 -c "import requests; import httpx; import jwt; print('Python deps OK')"

# 默认命令
CMD ["/bin/bash"]
