# VulHunter Agent Sandbox
# 安全沙箱环境用于漏洞验证和 PoC 执行
# 集成各类安全扫描工具 (Opengrep, Bandit, Gitleaks, etc.)

ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG SANDBOX_BASE_IMAGE=docker.m.daocloud.io/python:3.11-slim
FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim AS nodebase
FROM ${SANDBOX_BASE_IMAGE}

ARG SANDBOX_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG SANDBOX_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG SANDBOX_APT_MIRROR_FALLBACK=deb.debian.org
ARG SANDBOX_APT_SECURITY_FALLBACK=security.debian.org
ARG SANDBOX_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG SANDBOX_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG SANDBOX_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com
ARG SANDBOX_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org
ARG SANDBOX_PNPM_VERSION=9.15.4
ARG SANDBOX_PNPM_CMD_TIMEOUT_SECONDS=420
ARG GO_VERSION=1.21.6
ARG OPENGREP_VERSION=v1.15.1
ARG GITLEAKS_VERSION=8.18.2
ARG OSV_SCANNER_VERSION=1.6.2
ARG PMD_VERSION=7.22.0

LABEL maintainer="XCodeReviewer Team"
LABEL description="Secure sandbox environment for vulnerability verification and security scanning"

COPY --chmod=755 runtime/opengrep_launcher.py /usr/local/bin/opengrep

ENV UV_INDEX_URL=${SANDBOX_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${SANDBOX_PYPI_INDEX_PRIMARY}
ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:${PATH}

# 安装基础运行时与构建工具（主镜像源失败后回退）
RUN set -eux; \
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; \
  rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
  { \
  echo 'Acquire::http::Proxy "false";'; \
  echo 'Acquire::https::Proxy "false";'; \
  echo 'Acquire::Retries "5";'; \
  echo 'Acquire::http::Timeout "30";'; \
  echo 'Acquire::https::Timeout "30";'; \
  echo 'Acquire::ForceIPv4 "true";'; \
  } > /etc/apt/apt.conf.d/99-VulHunter-network; \
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
  install_core_packages() { \
  apt-get update && apt-get install -y --no-install-recommends --fix-missing \
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
  openjdk-21-jdk-headless \
  ruby-full \
  build-essential \
  cmake \
  clang \
  llvm \
  xz-utils; \
  }; \
  write_sources "${SANDBOX_APT_MIRROR_PRIMARY}" "${SANDBOX_APT_SECURITY_PRIMARY}"; \
  if ! install_core_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  write_sources "${SANDBOX_APT_MIRROR_FALLBACK}" "${SANDBOX_APT_SECURITY_FALLBACK}"; \
  install_core_packages; \
  fi; \
  rm -rf /var/lib/apt/lists/*

# 引入 Node.js 22 运行时并用 corepack 安装 pnpm（主源失败后回退）
COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=cache,id=VulHunter-sandbox-npm,target=/root/.npm \
  set -eux; \
  ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
  ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
  ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
  ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack; \
  corepack enable; \
  prepare_pnpm() { \
  reg="$1"; \
  attempt=1; \
  npm config set registry "${reg}"; \
  export COREPACK_NPM_REGISTRY="${reg}"; \
  while [ "${attempt}" -le 2 ]; do \
  if corepack prepare "pnpm@${SANDBOX_PNPM_VERSION}" --activate; then \
  return 0; \
  fi; \
  sleep $((attempt + 1)); \
  attempt=$((attempt + 1)); \
  done; \
  return 1; \
  }; \
  prepare_pnpm "${SANDBOX_NPM_REGISTRY_PRIMARY}" || prepare_pnpm "${SANDBOX_NPM_REGISTRY_FALLBACK}"; \
  pnpm config set registry "${SANDBOX_NPM_REGISTRY_PRIMARY}"; \
  node --version; npm --version; pnpm --version

# 安装 MCP 与 qmd CLI（供沙盒域运行时调用）
RUN --mount=type=cache,id=VulHunter-sandbox-pnpm-store,target=/pnpm/store \
  set -eux; \
  mkdir -p /pnpm /pnpm/global /pnpm/store; \
  cmd_timeout="${SANDBOX_PNPM_CMD_TIMEOUT_SECONDS:-420}"; \
  case "${cmd_timeout}" in ''|*[!0-9]*) cmd_timeout=420 ;; esac; \
  pnpm_step_timeout=120; \
  if [ "${cmd_timeout}" -lt "${pnpm_step_timeout}" ]; then pnpm_step_timeout="${cmd_timeout}"; fi; \
  pnpm config set store-dir /pnpm/store; \
  pnpm config set global-bin-dir /pnpm; \
  pnpm config set global-dir /pnpm/global; \
  pnpm config set fetch-retries 1; \
  pnpm config set fetch-retry-factor 2; \
  pnpm config set fetch-retry-mintimeout 2000; \
  pnpm config set fetch-retry-maxtimeout 8000; \
  pnpm config set network-concurrency 4; \
  install_mcp_packages() { \
  reg="$1"; \
  attempt=1; \
  if ! curl -fsS --max-time 5 "${reg}/-/ping" >/dev/null 2>&1; then \
  echo "pnpm registry probe failed for ${reg}, continue with direct add attempt." >&2; \
  fi; \
  pnpm config set registry "${reg}"; \
  while [ "${attempt}" -le 2 ]; do \
  if timeout "${pnpm_step_timeout}" pnpm add -g \
  @modelcontextprotocol/server-memory \
  @modelcontextprotocol/server-sequential-thinking \
  @tobilu/qmd; then \
  return 0; \
  fi; \
  status="$?"; \
  if [ "${status}" -eq 124 ]; then \
  echo "pnpm add timed out via ${reg} after ${pnpm_step_timeout}s (attempt ${attempt}/2)." >&2; \
  else \
  echo "pnpm add failed via ${reg} (attempt ${attempt}/2, exit ${status})." >&2; \
  fi; \
  sleep $((attempt + 1)); \
  attempt=$((attempt + 1)); \
  done; \
  return 1; \
  }; \
  install_mcp_packages "${SANDBOX_NPM_REGISTRY_PRIMARY}" || install_mcp_packages "${SANDBOX_NPM_REGISTRY_FALLBACK}"; \
  command -v qmd

# 安装 Python 安全工具（主源失败后回退）
RUN --mount=type=cache,id=VulHunter-sandbox-pip,target=/root/.cache/pip \
  set -eux; \
  pip_install_with_index() { \
  idx="$1"; \
  PIP_INDEX_URL="${idx}" pip install --no-cache-dir \
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
  safety \
  code2flow; \
  }; \
  pip_install_with_index "${SANDBOX_PYPI_INDEX_PRIMARY}" || pip_install_with_index "${SANDBOX_PYPI_INDEX_FALLBACK}"

# 安装 Go/Rust 与安全扫描工具（统一下载函数 + 架构对齐）
ENV PATH=$PATH:/usr/local/go/bin
ENV GOPROXY=https://goproxy.cn,direct
ENV RUSTUP_HOME=/usr/local/rustup \
  CARGO_HOME=/usr/local/cargo \
  PATH=/usr/local/cargo/bin:$PATH \
  RUSTUP_DIST_SERVER=https://rsproxy.cn \
  RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup
RUN set -eux; \
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; \
  ARCH_RAW="$(dpkg --print-architecture)"; \
  case "${ARCH_RAW}" in \
  amd64) GO_ARCH="amd64"; GITLEAKS_ARCH="x64"; OSV_ARCH="amd64"; OG_DIST="opengrep_manylinux_x86" ;; \
  arm64) GO_ARCH="arm64"; GITLEAKS_ARCH="arm64"; OSV_ARCH="arm64"; OG_DIST="opengrep_manylinux_aarch64" ;; \
  *) echo "unsupported arch: ${ARCH_RAW}" >&2; exit 1 ;; \
  esac; \
  download_with_fallback() { \
  output="$1"; \
  shift; \
  for url in "$@"; do \
  attempt=1; \
  while [ "${attempt}" -le 2 ]; do \
  if curl -fL --connect-timeout 8 --max-time 120 "${url}" -o "${output}.tmp"; then \
  mv "${output}.tmp" "${output}"; \
  return 0; \
  fi; \
  rm -f "${output}.tmp"; \
  sleep $((attempt + 1)); \
  attempt=$((attempt + 1)); \
  done; \
  done; \
  return 1; \
  }; \
  GO_TARBALL="go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"; \
  download_with_fallback \
  /tmp/go.tar.gz \
  "https://mirrors.aliyun.com/golang/${GO_TARBALL}" \
  "https://go.dev/dl/${GO_TARBALL}"; \
  tar -C /usr/local -xzf /tmp/go.tar.gz; \
  rm -f /tmp/go.tar.gz; \
  curl --proto '=https' --tlsv1.2 -sSf https://rsproxy.cn/rustup-init.sh | sh -s -- -y --default-toolchain stable --profile minimal; \
  chmod -R a+w /usr/local/cargo; \
  download_with_fallback \
  /usr/local/bin/opengrep.real \
  "https://gh-proxy.com/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
  "https://v6.gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
  "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}"; \
  chmod +x /usr/local/bin/opengrep.real; \
  GITLEAKS_TARBALL="gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz"; \
  download_with_fallback \
  /tmp/gitleaks.tar.gz \
  "https://gh-proxy.com/https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${GITLEAKS_TARBALL}" \
  "https://v6.gh-proxy.org/https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${GITLEAKS_TARBALL}" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${GITLEAKS_TARBALL}"; \
  tar -xzf /tmp/gitleaks.tar.gz -C /tmp; \
  mv /tmp/gitleaks /usr/local/bin/gitleaks; \
  rm -f /tmp/gitleaks.tar.gz; \
  download_with_fallback \
  /usr/local/bin/osv-scanner \
  "https://gh-proxy.com/https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_${OSV_SCANNER_VERSION}_linux_${OSV_ARCH}" \
  "https://v6.gh-proxy.org/https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_${OSV_SCANNER_VERSION}_linux_${OSV_ARCH}" \
  "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_${OSV_SCANNER_VERSION}_linux_${OSV_ARCH}"; \
  chmod +x /usr/local/bin/osv-scanner; \
  download_with_fallback \
  /tmp/pmd.zip \
  "https://gh-proxy.com/https://github.com/pmd/pmd/releases/download/pmd_releases%2F${PMD_VERSION}/pmd-dist-${PMD_VERSION}-bin.zip" \
  "https://v6.gh-proxy.org/https://github.com/pmd/pmd/releases/download/pmd_releases%2F${PMD_VERSION}/pmd-dist-${PMD_VERSION}-bin.zip" \
  "https://github.com/pmd/pmd/releases/download/pmd_releases%2F${PMD_VERSION}/pmd-dist-${PMD_VERSION}-bin.zip"; \
  unzip -q /tmp/pmd.zip -d /opt; \
  ln -sf "/opt/pmd-bin-${PMD_VERSION}/bin/pmd" /usr/local/bin/pmd; \
  rm -f /tmp/pmd.zip; \
  curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin; \
  download_with_fallback \
  /usr/local/bin/phpstan \
  "https://gh-proxy.com/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar" \
  "https://v6.gh-proxy.org/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar" \
  "https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar"; \
  chmod +x /usr/local/bin/phpstan; \
  opengrep --version; \
  gitleaks version; \
  osv-scanner --version; \
  pmd --version || true

# 创建非 root 用户
RUN groupadd -g 1000 sandbox && \
  useradd -u 1000 -g sandbox -m -s /bin/bash sandbox

# 创建工作目录
RUN mkdir -p /workspace /tmp/sandbox \
  /workspace/.VulHunter/mcp/xdg-data \
  /workspace/.VulHunter/mcp/xdg-cache \
  /workspace/.VulHunter/mcp/xdg-config \
  /workspace/.VulHunter/qmd && \
  chown -R sandbox:sandbox /workspace /tmp/sandbox

# 设置环境变量
ENV HOME=/home/sandbox
ENV PATH=/home/sandbox/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV XDG_DATA_HOME=/workspace/.VulHunter/mcp/xdg-data
ENV XDG_CACHE_HOME=/workspace/.VulHunter/mcp/xdg-cache
ENV XDG_CONFIG_HOME=/workspace/.VulHunter/mcp/xdg-config
RUN mkdir -p /workspace/.VulHunter/mcp/xdg-data /workspace/.VulHunter/mcp/xdg-cache /workspace/.VulHunter/mcp/xdg-config
ENV QMD_DATA_DIR=/workspace/.VulHunter/qmd

# 限制 Python 导入路径
ENV PYTHONPATH=/workspace

# 切换到非 root 用户
USER sandbox

WORKDIR /workspace

# 默认命令
CMD ["/bin/bash"]
