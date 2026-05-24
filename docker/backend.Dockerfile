ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG BACKEND_CARGO_REGISTRY=sparse+https://rsproxy.cn/index/
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS=30
ARG BACKEND_CARGO_NET_RETRY=10
ARG A3S_BOX_VERSION=v2.0.3
ARG A3S_BOX_DOWNLOAD_BASE_URL=https://v6.gh-proxy.org/https://github.com/AI45Lab/Box/releases/download

FROM ${DOCKERHUB_LIBRARY_MIRROR}/rust:1.90-slim-bookworm AS builder

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG BACKEND_CARGO_REGISTRY
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS
ARG BACKEND_CARGO_NET_RETRY

WORKDIR /app

RUN --mount=type=cache,id=argus-backend-builder-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=argus-backend-builder-apt-cache,target=/var/cache/apt,sharing=locked \
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
  } > /etc/apt/apt.conf.d/99-backend-builder-network; \
  . /etc/os-release; \
  CODENAME="${VERSION_CODENAME:-bookworm}"; \
  write_sources() { \
  main_host="$1"; \
  security_host="$2"; \
  rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
  printf 'deb http://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
  printf 'deb http://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  printf 'deb http://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  }; \
  write_secure_sources() { \
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
  binutils \
  ca-certificates \
  curl \
  pkg-config \
  libssl-dev; \
  }; \
  main_host="${BACKEND_APT_MIRROR_PRIMARY}"; \
  security_host="${BACKEND_APT_SECURITY_PRIMARY}"; \
  write_sources "${main_host}" "${security_host}"; \
  if ! install_build_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  main_host="${BACKEND_APT_MIRROR_FALLBACK}"; \
  security_host="${BACKEND_APT_SECURITY_FALLBACK}"; \
  write_sources "${main_host}" "${security_host}"; \
  install_build_packages; \
  fi; \
  write_secure_sources "${main_host}" "${security_host}"; \
  rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  mkdir -p /usr/local/cargo; \
  if [ -n "${BACKEND_CARGO_REGISTRY}" ]; then \
  { \
  echo '[source.crates-io]'; \
  echo 'replace-with = "argus-cargo-mirror"'; \
  echo; \
  echo '[source.argus-cargo-mirror]'; \
  printf 'registry = "%s"\n' "${BACKEND_CARGO_REGISTRY}"; \
  echo; \
  echo '[net]'; \
  echo 'git-fetch-with-cli = true'; \
  } > /usr/local/cargo/config.toml; \
  fi

COPY backend/Cargo.toml backend/Cargo.lock ./
COPY backend/src ./src
COPY backend/tests ./tests

RUN --mount=type=cache,id=argus-backend-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
  --mount=type=cache,id=argus-backend-cargo-git,target=/usr/local/cargo/git,sharing=locked \
  --mount=type=cache,id=argus-backend-cargo-target,target=/app/target,sharing=locked \
  CARGO_HTTP_TIMEOUT="${BACKEND_CARGO_HTTP_TIMEOUT_SECONDS}" \
  CARGO_NET_RETRY="${BACKEND_CARGO_NET_RETRY}" \
  cargo build --locked --release --bin backend-rust \
  && cp /app/target/release/backend-rust /usr/local/bin/backend-rust \
  && strip /usr/local/bin/backend-rust

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS a3s-box-binary-src

ARG A3S_BOX_VERSION
ARG A3S_BOX_DOWNLOAD_BASE_URL
ARG TARGETARCH
ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK

RUN --mount=type=cache,id=argus-a3s-box-binary-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=argus-a3s-box-binary-apt-cache,target=/var/cache/apt,sharing=locked \
  set -eux; \
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY; \
  . /etc/os-release; \
  CODENAME="${VERSION_CODENAME:-trixie}"; \
  write_sources() { \
    main_host="$1"; \
    security_host="$2"; \
    rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    printf 'deb http://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
    printf 'deb http://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
    printf 'deb http://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  }; \
  write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
  apt-get update; \
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl || { \
    rm -rf /var/lib/apt/lists/*; \
    write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl; \
  }; \
  rm -rf /var/lib/apt/lists/*; \
  case "${TARGETARCH:-amd64}" in \
    amd64) package_arch="linux-x86_64" ;; \
    arm64) package_arch="linux-arm64" ;; \
    *) echo "unsupported A3S Box TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  package="a3s-box-${A3S_BOX_VERSION}-${package_arch}"; \
  curl -fsSL --retry 5 "${A3S_BOX_DOWNLOAD_BASE_URL}/${A3S_BOX_VERSION}/${package}.tar.gz" -o /tmp/a3s-box.tar.gz; \
  mkdir -p /tmp/a3s-box /opt/a3s-box/bin /opt/a3s-box/lib; \
  tar --no-same-owner --no-same-permissions -xzf /tmp/a3s-box.tar.gz -C /tmp/a3s-box --strip-components=1; \
  install -m 0755 /tmp/a3s-box/a3s-box /opt/a3s-box/bin/a3s-box; \
  install -m 0755 /tmp/a3s-box/a3s-box-shim /opt/a3s-box/bin/a3s-box-shim; \
  install -m 0755 /tmp/a3s-box/a3s-box-guest-init /opt/a3s-box/bin/a3s-box-guest-init; \
  cp -a /tmp/a3s-box/lib/. /opt/a3s-box/lib/; \
  LD_LIBRARY_PATH=/opt/a3s-box/lib /opt/a3s-box/bin/a3s-box --version | grep -F "a3s-box ${A3S_BOX_VERSION#v}"; \
  rm -rf /tmp/a3s-box /tmp/a3s-box.tar.gz

FROM builder AS backend-assets-archive

COPY backend/assets/scan_rule_assets /tmp/scan_rule_assets

RUN mkdir -p /opt/backend-assets \
  && tar -C /tmp -czf /opt/backend-assets/scan_rule_assets.tar.gz scan_rule_assets \
  && tar -tzf /opt/backend-assets/scan_rule_assets.tar.gz >/dev/null

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS runtime-base

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK

RUN --mount=type=cache,id=argus-backend-runtime-apt-lists,target=/var/lib/apt/lists,sharing=locked \
  --mount=type=cache,id=argus-backend-runtime-apt-cache,target=/var/cache/apt,sharing=locked \
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
  } > /etc/apt/apt.conf.d/99-backend-runtime-network; \
  . /etc/os-release; \
  CODENAME="${VERSION_CODENAME:-trixie}"; \
  write_sources() { \
  main_host="$1"; \
  security_host="$2"; \
  rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
  printf 'deb http://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
  printf 'deb http://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  printf 'deb http://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  }; \
  write_secure_sources() { \
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
  git \
  iproute2 \
  openssh-client \
  podman \
  python3; \
  }; \
  main_host="${BACKEND_APT_MIRROR_PRIMARY}"; \
  security_host="${BACKEND_APT_SECURITY_PRIMARY}"; \
  write_sources "${main_host}" "${security_host}"; \
  if ! install_runtime_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  main_host="${BACKEND_APT_MIRROR_FALLBACK}"; \
  security_host="${BACKEND_APT_SECURITY_FALLBACK}"; \
  write_sources "${main_host}" "${security_host}"; \
  install_runtime_packages; \
  fi; \
  write_secure_sources "${main_host}" "${security_host}"; \
  rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appgroup \
  && useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser \
  && mkdir -p /app/assets /app/scripts /app/uploads/zip_files /app/data/runtime/home /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config \
  && chown -R appuser:appgroup /app/uploads /app/data

WORKDIR /app

COPY --chmod=755 docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
COPY --from=builder /usr/local/bin/backend-rust /usr/local/bin/backend
COPY --from=a3s-box-binary-src /opt/a3s-box/bin/ /usr/local/bin/
COPY --from=a3s-box-binary-src /opt/a3s-box/lib/ /usr/local/lib/
COPY --from=backend-assets-archive /opt/backend-assets/scan_rule_assets.tar.gz /app/assets/scan_rule_assets.tar.gz

ENV BIND_ADDR=0.0.0.0:8000
ENV ZIP_STORAGE_PATH=/app/uploads/zip_files
ENV HOME=/app/data/runtime/home
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
ENV LD_LIBRARY_PATH=/usr/local/lib

EXPOSE 8000

CMD ["/usr/local/bin/backend-entrypoint.sh"]

FROM runtime-base AS runtime-plain
FROM runtime-base AS runtime-release
