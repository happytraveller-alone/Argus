# ============================================
# 多阶段构建 - 构建阶段
# ============================================
ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
ARG BACKEND_PYPI_INDEX_FALLBACK=https://pypi.org/simple
ARG BACKEND_PYPI_INDEX_CANDIDATES=https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.mirrors.ustc.edu.cn/simple/,https://mirrors.cloud.tencent.com/pypi/simple/,https://mirrors.huaweicloud.com/repository/pypi/simple/,https://mirrors.bfsu.edu.cn/pypi/web/simple/,https://pypi.org/simple
ARG BACKEND_INSTALL_CJK_FONTS=1
ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli
# CONTAINER_CLI_PROVIDER: 容器 CLI 提供方
#   docker (默认) — 仅使用 Docker CLI；配合 DOCKER_HOST 可透明路由到 Podman socket
#   podman — 额外安装 podman-remote，使 runner_preflight 可调用 podman build
ARG CONTAINER_CLI_PROVIDER=docker
FROM ${UV_IMAGE} AS uvbin
FROM ${DOCKER_CLI_IMAGE} AS docker-cli-src
FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim AS python-base
FROM python-base AS builder

WORKDIR /app
ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BACKEND_VENV_PATH=/opt/backend-venv

# 彻底清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"

RUN --mount=type=cache,id=vulhunter-backend-builder-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=vulhunter-backend-builder-apt-cache,target=/var/cache/apt,sharing=locked \
  set -eux; \
  rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
  { \
  echo 'Acquire::http::Proxy "false";'; \
  echo 'Acquire::https::Proxy "false";'; \
  echo 'Acquire::Retries "5";'; \
  echo 'Acquire::http::Timeout "60";'; \
  } > /etc/apt/apt.conf.d/99-no-proxy; \
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
  install_builder_packages() { \
  apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ccache \
  gcc \
  libc6-dev \
  libpq-dev \
  libffi-dev; \
  }; \
  write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
  if ! install_builder_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
  install_builder_packages; \
  fi; \
  rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=uvbin /uv /usr/local/bin/uv

# 配置 uv/pip 镜像（主源 + 回退）
ENV UV_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}

# 镜像源测速脚本（最先复制，几乎不会变化）
COPY backend_old/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

COPY backend_old/pyproject.toml backend_old/uv.lock backend_old/README.md ./

RUN --mount=type=cache,id=vulhunter-backend-uv-cache,target=/root/.cache/uv \
  set -eux; \
  uv_step_timeout=240; \
  uv_http_timeout=45; \
  pypi_index_candidates="${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.mirrors.ustc.edu.cn/simple/,https://mirrors.cloud.tencent.com/pypi/simple/,https://mirrors.huaweicloud.com/repository/pypi/simple/,https://pypi.org/simple}"; \
  best_index="${BACKEND_PYPI_INDEX_PRIMARY:-https://mirrors.aliyun.com/pypi/simple/}"; \
  ordered="$(python3 /usr/local/bin/package_source_selector.py \
  --candidates "${pypi_index_candidates}" --kind pypi --timeout-seconds 2 2>/dev/null || true)"; \
  if [ -n "${ordered}" ]; then \
  first="$(printf '%s\n' "${ordered}" | head -1)"; \
  [ -z "${first}" ] || best_index="${first}"; \
  fi; \
  echo "Selected PyPI index: ${best_index}"; \
  uv venv "${BACKEND_VENV_PATH}"; \
  sync_with_index() { \
  idx="$1"; attempt=1; \
  while [ "${attempt}" -le 2 ]; do \
  echo "uv sync via ${idx} (attempt ${attempt}/2, timeout ${uv_step_timeout}s)"; \
  if timeout "${uv_step_timeout}" env \
  VIRTUAL_ENV="${BACKEND_VENV_PATH}" PATH="${BACKEND_VENV_PATH}/bin:${PATH}" \
  UV_HTTP_TIMEOUT="${uv_http_timeout}" UV_INDEX_URL="${idx}" PIP_INDEX_URL="${idx}" \
  UV_CONCURRENT_DOWNLOADS=50 UV_CONCURRENT_INSTALLS=8 \
  uv sync --active --frozen --no-dev; then \
  return 0; \
  else \
  status="$?"; \
  fi; \
  if [ "${status}" -eq 124 ]; then \
  echo "uv sync timed out via ${idx} after ${uv_step_timeout}s (attempt ${attempt}/2)." >&2; \
  else \
  echo "uv sync failed via ${idx} (attempt ${attempt}/2, exit ${status})." >&2; \
  fi; \
  sleep $((attempt + 1)); attempt=$((attempt + 1)); \
  done; return 1; \
  }; \
  echo "uv sync using index: ${best_index}"; \
  if sync_with_index "${best_index}"; then \
  exit 0; \
  fi; \
  OLD_IFS="${IFS}"; IFS=','; set -- ${pypi_index_candidates}; IFS="${OLD_IFS}"; \
  for idx in "$@"; do \
  stripped="$(printf '%s' "${idx}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"; \
  [ -n "${stripped}" ] && [ "${stripped}" != "${best_index}" ] || continue; \
  if sync_with_index "${stripped}"; then \
  exit 0; \
  fi; \
  done; \
  echo "ERROR: uv sync failed on all mirrors" >&2; exit 1

# ============================================
# 多阶段构建 - 运行时基础阶段
# ============================================
FROM python-base AS runtime-base

WORKDIR /app
ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_PYPI_INDEX_FALLBACK
ARG BACKEND_PYPI_INDEX_CANDIDATES
ARG CONTAINER_CLI_PROVIDER=docker

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BACKEND_VENV_PATH=/opt/backend-venv

# 彻底清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV all_proxy=""
ENV ALL_PROXY=""
ENV no_proxy="*"
ENV NO_PROXY="*"
ENV UV_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PIP_INDEX_URL=${BACKEND_PYPI_INDEX_PRIMARY}
ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}


# 只安装运行时依赖（不需要 gcc）；CJK 字体可通过 BACKEND_INSTALL_CJK_FONTS 控制
ARG BACKEND_INSTALL_CJK_FONTS
RUN --mount=type=cache,id=vulhunter-backend-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=vulhunter-backend-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
  set -eux; \
  rm -f /etc/apt/apt.conf.d/proxy.conf 2>/dev/null || true; \
  { \
  echo 'Acquire::http::Proxy "false";'; \
  echo 'Acquire::https::Proxy "false";'; \
  echo 'Acquire::Retries "5";'; \
  echo 'Acquire::http::Timeout "60";'; \
  } > /etc/apt/apt.conf.d/99-no-proxy; \
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
  RUNTIME_PACKAGES=" \
  libpq5 \
  git \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libpangocairo-1.0-0 \
  libcairo2 \
  libgdk-pixbuf-2.0-0 \
  libglib2.0-0 \
  shared-mime-info"; \
  if [ "${BACKEND_INSTALL_CJK_FONTS}" = "1" ]; then \
  RUNTIME_PACKAGES="${RUNTIME_PACKAGES} fonts-noto-cjk"; \
  fi; \
  install_runtime_packages() { \
  apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${RUNTIME_PACKAGES}; \
  }; \
  write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
  if ! install_runtime_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
  install_runtime_packages; \
  fi; \
  if [ "${BACKEND_INSTALL_CJK_FONTS}" = "1" ]; then \
  fc-cache -fv; \
  fi; \
  rm -rf /var/lib/apt/lists/*

COPY backend_old/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py

# 复制 docker CLI 及 buildx 插件，供 runner_preflight 以 subprocess 方式执行 docker build
# buildx 是 Docker 23+ 执行 BuildKit 构建的必要插件（--mount=type=cache 等特性依赖它）
COPY --from=docker-cli-src /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli-src /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx

# Podman 支持：当 CONTAINER_CLI_PROVIDER=podman 时安装 podman-remote 并建立软链接
# podman-remote 是无守护进程的 podman 客户端，连接宿主机 Podman socket 执行 podman build
# 若使用默认的 docker（CONTAINER_CLI_PROVIDER=docker），此步骤跳过，不增加镜像体积
RUN --mount=type=cache,id=vulhunter-backend-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=vulhunter-backend-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
  if [ "${CONTAINER_CLI_PROVIDER}" = "podman" ]; then \
  set -eux; \
  apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends podman-remote && \
  ln -sf /usr/bin/podman-remote /usr/local/bin/podman; \
  fi


# ============================================
# 多阶段构建 - 运行阶段
# ============================================
FROM runtime-base AS dev-runtime

COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

RUN set -eux; \
  for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
  find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
  done; \
  rm -rf /root/.cache/pip; \
  rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1

RUN mkdir -p /app /opt/backend-venv /root/.cache/uv /app/uploads/zip_files /app/data/runtime

EXPOSE 8000

CMD ["python3", "-m", "app.runtime.container_startup", "dev"]

# ============================================================
# Cython 编译阶段：将 Python 源码编译为 .so 扩展（代码混淆）
# 基于 builder 阶段（已含 gcc、Python 头文件、完整 venv）
# ============================================================
FROM builder AS cython-compiler

# 安装 Cython 和 setuptools（builder 使用 uv 管理 venv，无 pip，用 uv pip install）
ARG BACKEND_PYPI_INDEX_PRIMARY
ARG BACKEND_CYTHON_JOBS=4
RUN --mount=type=cache,id=vulhunter-cython-uv,target=/root/.cache/uv \
  VIRTUAL_ENV=/opt/backend-venv \
  UV_INDEX_URL="${BACKEND_PYPI_INDEX_PRIMARY:-https://mirrors.aliyun.com/pypi/simple/}" \
  uv pip install "Cython>=3.0.0,<4.0.0" "setuptools>=68"

# 复制源码和编译脚本
COPY backend_old/app /build/app
COPY backend_old/cython_build /build/cython_build

# 执行编译，产物写入 /build/compiled/
# --parallel $(nproc): 并行 gcc 编译所有 .c 文件（4vCPU→ ~6 分钟，原串行 ~22 分钟）
# CC=ccache gcc: 跨构建缓存编译产物（源码不变时 hit 率 ~100%，近乎瞬间完成）
RUN --mount=type=cache,id=vulhunter-cython-ccache,target=/root/.ccache,sharing=shared \
  set -eux; \
  export CC="ccache gcc" CXX="ccache g++"; \
  export CCACHE_DIR=/root/.ccache; \
  export CCACHE_MAXSIZE=2G; \
  NPROC="${BACKEND_CYTHON_JOBS}"; \
  echo "[Cython] 并行编译（jobs=${NPROC}），ccache dir=${CCACHE_DIR}"; \
  cd /build; \
  /opt/backend-venv/bin/python cython_build/setup.py build_ext \
  --build-lib /build/compiled \
  --build-temp /build/tmp \
  --parallel "${NPROC}"; \
  SO_COUNT=$(find /build/compiled -name "*.so" | wc -l); \
  echo "[Cython] 编译完成，.so 文件数: ${SO_COUNT}"; \
  ccache --show-stats; \
  test "${SO_COUNT}" -gt 50

# ============================================================
# 组装最终 app/ 目录：.so 编译产物 + 必须保留 .py 的文件
# ============================================================
FROM cython-compiler AS runtime-app-assembler

RUN set -eux; \
  mkdir -p /final/app; \
  # 1. 复制所有 .so 编译产物（按包路径排列）
  cp -r /build/compiled/app/. /final/app/; \
  # 2. 复制所有 __init__.py（Cython 不编译它们，保持包结构）
  find /build/app -name "__init__.py" | while IFS= read -r f; do \
  rel="${f#/build/app/}"; \
  mkdir -p "/final/app/$(dirname "${rel}")"; \
  cp "${f}" "/final/app/${rel}"; \
  done; \
  # 3. 复制入口文件（CMD 直接引用，必须保留 .py）
  cp /build/app/main.py /final/app/main.py; \
  mkdir -p /final/app/runtime; \
  cp /build/app/runtime/container_startup.py /final/app/runtime/container_startup.py; \
  # 4. 复制 launchers 目录（COPY --chmod=755 可执行脚本）
  cp -r /build/app/runtime/launchers /final/app/runtime/launchers; \
  # 5. 复制 schema_snapshots 目录（Alembic baseline）
  mkdir -p /final/app/db; \
  cp -r /build/app/db/schema_snapshots /final/app/db/schema_snapshots; \
  # 6. 复制 patches 目录（若存在）
  if [ -d /build/app/db/patches ]; then \
  cp -r /build/app/db/patches /final/app/db/patches; \
  fi; \
  # 7. 兜底：将所有无对应 .so 的 .py 文件（即 Cython 排除的模块）复制到 /final/app
  #    确保未来新增排除文件时无需再修改此 Dockerfile
  find /build/app -name "*.py" | while IFS= read -r f; do \
  rel="${f#/build/app/}"; \
  dir="$(dirname "${rel}")"; \
  base="$(basename "${rel%.py}")"; \
  if [ -z "$(find /final/app/"${dir}" -name "${base}.cpython-*.so" 2>/dev/null | head -1)" ] && \
  [ ! -f "/final/app/${rel}" ]; then \
  mkdir -p "/final/app/${dir}"; \
  cp "${f}" "/final/app/${rel}"; \
  echo "[Assembler] 保留 .py(无对应.so): ${rel}"; \
  fi; \
  done; \
  # 验证：核心 .so 文件存在
  echo "[Assembler] 验证关键 .so 文件:"; \
  ls /final/app/core/*.so 2>/dev/null | head -5; \
  ls /final/app/services/agent/*.so 2>/dev/null | head -5; \
  echo "[Assembler] 组装完成"

# ── Layer 1 增强：.so 符号剥离 ──────────────────────────────
RUN set -eux; \
  SO_COUNT=$(find /final/app -name "*.so" | wc -l); \
  echo "[Strip] 开始剥离 ${SO_COUNT} 个 .so 文件符号"; \
  find /final/app -name "*.so" \
  -exec strip --strip-all --remove-section=.comment {} \; ; \
  echo "[Strip] 符号剥离完成"; \
  find /final/app -name "*.so" | head -5 | while read -r so; do \
  file "$so" | grep -q "ELF.*shared object" || \
  { echo "INVALID ELF: $so" >&2; exit 1; }; \
  done; \
  echo "[Strip] ELF 完整性验证通过"

# ── Layer 2：白名单 .py → legacy .pyc 编译 + 删除源码 ───────
# 删除源码后，Python 需要相邻的 legacy .pyc；仅保留 __pycache__ 不足以导入。
# 只保护运行时入口与少量残余源码，避免误删 Alembic/patch/build-context 依赖文件。
RUN set -eux; \
  BYTECODE_TARGETS="\
  /final/app/main.py \
  /final/app/runtime/container_startup.py \
  /final/app/runtime/launchers/yasa_uast4py_launcher.py \
  /final/app/runtime/launchers/opengrep_launcher.py \
  /final/app/runtime/launchers/phpstan_launcher.py \
  /final/app/runtime/launchers/yasa_engine_launcher.py \
  /final/app/runtime/launchers/yasa_launcher.py \
  /final/app/api/v1/endpoints/agent_tasks_reporting.py"; \
  TARGET_COUNT=0; \
  for src in ${BYTECODE_TARGETS}; do \
  test -f "${src}"; \
  /opt/backend-venv/bin/python -m compileall -q -b "${src}"; \
  test -f "${src}c"; \
  rm -f "${src}"; \
  TARGET_COUNT=$((TARGET_COUNT + 1)); \
  echo "[Bytecode] protected: ${src#/final/}"; \
  done; \
  PY_REMAINING=$(find /final/app -name "*.py" ! -name "__init__.py" | wc -l); \
  echo "[Bytecode] 受保护文件数: ${TARGET_COUNT}"; \
  echo "[Bytecode] 剩余源码文件数（白名单外保留）: ${PY_REMAINING}"; \
  test -f /final/app/main.pyc || \
  { echo "ERROR: main.pyc 未生成" >&2; exit 1; }; \
  test -f /final/app/runtime/container_startup.pyc || \
  { echo "ERROR: container_startup.pyc 未生成" >&2; exit 1; }; \
  echo "[Bytecode] 关键 legacy .pyc 验证通过"

# ============================================================
# runtime-cython: 全量 Cython + strip + pyc（最强混淆，资源占用高）
# 仅在确实需要 .so 级保护时显式使用 --target runtime-cython
# ============================================================
FROM runtime-base AS runtime-cython

# 提前复制 builder 产物，避免 runtime 与 builder 并行下载导致网络争抢
COPY --from=builder /opt/backend-venv /opt/backend-venv

RUN set -eux; \
  for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
  find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
  done; \
  rm -rf /root/.cache/pip; \
  rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1

# Runtime 持久化目录
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
RUN mkdir -p /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config



# 仅复制运行时所需代码与脚本，避免把测试/文档打进运行镜像
# 使用 Cython 编译产物（.so）替代 Python 源码，实现代码混淆
COPY --from=runtime-app-assembler /final/app /app/app
# 删除残留的 .c 中间文件（若有）
RUN find /app/app -name "*.c" -delete 2>/dev/null || true
COPY backend_old/alembic /app/alembic
COPY backend_old/alembic.ini /app/alembic.ini
COPY backend_old/scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py

# 创建运行时持久化目录
RUN mkdir -p \
  /app/uploads/zip_files \
  /app/data/runtime \
  /app/data/runtime/xdg-config

# ── 非 root 用户：降权运行，减小容器逃逸风险 ───────────────
RUN groupadd --gid 1001 appgroup && \
  useradd --uid 1001 --gid appgroup \
  --no-create-home --shell /usr/sbin/nologin appuser && \
  chown -R appuser:appgroup \
  /app \
  /opt/backend-venv

USER appuser

# 暴露端口
EXPOSE 8000

# 验证核心模块可从 .so / .pyc 正确导入（确保运行时入口与 Cython 产物完整）
RUN /opt/backend-venv/bin/python - <<'PYEOF'
import importlib.util
cython_mods = ['app.core.config', 'app.services.agent.config', 'app.db.session']
for mod_name in cython_mods:
    spec = importlib.util.find_spec(mod_name)
    assert spec is not None, 'Module ' + mod_name + ' not found'
    assert spec.origin.endswith('.so'), 'Expected .so for ' + mod_name + ', got ' + spec.origin
    print('[Cython] ' + mod_name + ': OK (' + spec.origin.split('/')[-1] + ')')
pyc_mods = [
    'app.main',
    'app.runtime.container_startup',
    'app.api.v1.endpoints.agent_tasks_reporting',
]
for mod_name in pyc_mods:
    spec = importlib.util.find_spec(mod_name)
    assert spec is not None, 'Module ' + mod_name + ' not found'
    assert spec.origin.endswith('.pyc'), 'Expected .pyc for ' + mod_name + ', got ' + spec.origin
    print('[Bytecode] ' + mod_name + ': OK (' + spec.origin.split('/')[-1] + ')')
print('[Cython] All core module verifications PASSED')
PYEOF

CMD ["python3", "-m", "app.runtime.container_startup", "prod"]

# ============================================================
# runtime: 平衡型生产 target
# 跳过全量 Cython，保留轻量混淆（legacy .pyc）+ 非 root 运行
# 默认推荐此 target，避免全量 Cython 在构建阶段占满 CPU / 内存
# ============================================================
FROM runtime-base AS runtime

COPY --from=builder /opt/backend-venv /opt/backend-venv

RUN set -eux; \
  for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
  find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
  done; \
  rm -rf /root/.cache/pip; \
  rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1

ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
RUN mkdir -p /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config

COPY backend_old/app /app/app
RUN find /app/app -name "*.c" -delete 2>/dev/null || true
COPY backend_old/alembic /app/alembic
COPY backend_old/alembic.ini /app/alembic.ini
COPY backend_old/scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py

RUN mkdir -p \
  /app/uploads/zip_files \
  /app/data/runtime \
  /app/data/runtime/xdg-config

# 默认 target 只对少量高价值入口做轻量混淆，避免再触发全量 Cython/GCC 编译。
RUN set -eux; \
  BYTECODE_TARGETS="\
  /app/app/main.py \
  /app/app/runtime/container_startup.py \
  /app/app/runtime/launchers/yasa_uast4py_launcher.py \
  /app/app/runtime/launchers/opengrep_launcher.py \
  /app/app/runtime/launchers/phpstan_launcher.py \
  /app/app/runtime/launchers/yasa_engine_launcher.py \
  /app/app/runtime/launchers/yasa_launcher.py \
  /app/app/api/v1/endpoints/agent_tasks_reporting.py"; \
  TARGET_COUNT=0; \
  for src in ${BYTECODE_TARGETS}; do \
  test -f "${src}"; \
  /opt/backend-venv/bin/python -m compileall -q -b "${src}"; \
  test -f "${src}c"; \
  rm -f "${src}"; \
  TARGET_COUNT=$((TARGET_COUNT + 1)); \
  echo "[Bytecode] protected: ${src#/app/}"; \
  done; \
  PY_REMAINING=$(find /app/app -name "*.py" ! -name "__init__.py" | wc -l); \
  echo "[Bytecode] 受保护文件数: ${TARGET_COUNT}"; \
  echo "[Bytecode] 剩余源码文件数（白名单外保留）: ${PY_REMAINING}"; \
  test -f /app/app/main.pyc || \
  { echo "ERROR: main.pyc 未生成" >&2; exit 1; }; \
  test -f /app/app/runtime/container_startup.pyc || \
  { echo "ERROR: container_startup.pyc 未生成" >&2; exit 1; }; \
  echo "[Bytecode] 关键 legacy .pyc 验证通过"

RUN groupadd --gid 1001 appgroup && \
  useradd --uid 1001 --gid appgroup \
  --no-create-home --shell /usr/sbin/nologin appuser && \
  chown -R appuser:appgroup \
  /app \
  /opt/backend-venv

USER appuser

EXPOSE 8000

RUN /opt/backend-venv/bin/python - <<'PYEOF'
import importlib.util
pyc_mods = [
    'app.main',
    'app.runtime.container_startup',
    'app.api.v1.endpoints.agent_tasks_reporting',
]
for mod_name in pyc_mods:
    spec = importlib.util.find_spec(mod_name)
    assert spec is not None, 'Module ' + mod_name + ' not found'
    assert spec.origin.endswith('.pyc'), 'Expected .pyc for ' + mod_name + ', got ' + spec.origin
    print('[Bytecode] ' + mod_name + ': OK (' + spec.origin.split('/')[-1] + ')')
source_mods = ['app.core.config', 'app.db.session']
for mod_name in source_mods:
    spec = importlib.util.find_spec(mod_name)
    assert spec is not None, 'Module ' + mod_name + ' not found'
    assert spec.origin.endswith('.py'), 'Expected .py for ' + mod_name + ', got ' + spec.origin
    print('[Source] ' + mod_name + ': OK (' + spec.origin.split('/')[-1] + ')')
print('[Runtime] Balanced obfuscation verifications PASSED')
PYEOF

CMD ["python3", "-m", "app.runtime.container_startup", "prod"]

# ============================================================
# runtime-plain: 跳过 Cython 编译，直接使用 Python 源码
# 用于本地开发构建（hybrid / full compose），节省 ~20 分钟构建时间
# ============================================================
FROM runtime-base AS runtime-plain

COPY --from=builder /opt/backend-venv /opt/backend-venv

RUN set -eux; \
  for site_packages_dir in $(python3 -c 'import site; [print(path) for path in site.getsitepackages() if "site-packages" in path]'); do \
  find "${site_packages_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +; \
  done; \
  rm -rf /root/.cache/pip; \
  rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11

ENV VIRTUAL_ENV=/opt/backend-venv
ENV PATH=/opt/backend-venv/bin:${PATH}
ENV PYTHONNOUSERSITE=1

# Runtime 持久化目录
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
RUN mkdir -p /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config

# 直接复制 Python 源码（跳过 Cython 编译加固）
COPY backend_old/app /app/app
COPY backend_old/alembic /app/alembic
COPY backend_old/alembic.ini /app/alembic.ini
COPY backend_old/scripts/reset_static_scan_tables.py /app/scripts/reset_static_scan_tables.py

RUN mkdir -p \
  /app/uploads/zip_files \
  /app/data/runtime \
  /app/data/runtime/xdg-config

EXPOSE 8000

CMD ["python3", "-m", "app.runtime.container_startup", "prod"]
