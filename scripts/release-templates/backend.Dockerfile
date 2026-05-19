ARG DOCKERHUB_LIBRARY_MIRROR=m.daocloud.io/docker.io/library
ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli
ARG BACKEND_CARGO_REGISTRY=sparse+https://rsproxy.cn/index/
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS=30
ARG BACKEND_CARGO_NET_RETRY=10
ARG A3S_BOX_VERSION=v2.0.3
ARG A3S_BOX_DOWNLOAD_BASE_URL=https://v6.gh-proxy.org/https://github.com/AI45Lab/Box/releases/download

FROM ${DOCKERHUB_LIBRARY_MIRROR}/rust:1.90-slim-bookworm AS builder
ARG BACKEND_CARGO_REGISTRY
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS
ARG BACKEND_CARGO_NET_RETRY
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl pkg-config libssl-dev \
  && rm -rf /var/lib/apt/lists/*

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

RUN CARGO_HTTP_TIMEOUT="${BACKEND_CARGO_HTTP_TIMEOUT_SECONDS}" \
  CARGO_NET_RETRY="${BACKEND_CARGO_NET_RETRY}" \
  cargo build --locked --release --bin backend-rust

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS a3s-box-binary-src

ARG A3S_BOX_VERSION
ARG A3S_BOX_DOWNLOAD_BASE_URL
ARG TARGETARCH

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
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

FROM ${DOCKER_CLI_IMAGE} AS docker-cli-src

FROM builder AS backend-assets-archive

COPY backend/assets/scan_rule_assets /tmp/scan_rule_assets

RUN mkdir -p /opt/backend-assets \
  && tar -C /tmp -czf /opt/backend-assets/scan_rule_assets.tar.gz scan_rule_assets \
  && tar -tzf /opt/backend-assets/scan_rule_assets.tar.gz >/dev/null

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS runtime-base

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl git iproute2 openssh-client python3 \
  && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appgroup \
  && useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser \
  && mkdir -p /app/assets /app/docker /app/scripts /app/uploads/zip_files /app/data/runtime/home /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config

WORKDIR /app

COPY --from=builder /app/target/release/backend-rust /usr/local/bin/backend
COPY --from=docker-cli-src /usr/local/bin/docker /usr/local/bin/docker
COPY --from=a3s-box-binary-src /opt/a3s-box/bin/ /usr/local/bin/
COPY --from=a3s-box-binary-src /opt/a3s-box/lib/ /usr/local/lib/
COPY --from=backend-assets-archive /opt/backend-assets/scan_rule_assets.tar.gz /app/assets/scan_rule_assets.tar.gz
COPY --chmod=755 docker/opengrep-scan.sh /app/docker/opengrep-scan.sh

RUN chown -R appuser:appgroup /app

ENV BIND_ADDR=0.0.0.0:8000
ENV ZIP_STORAGE_PATH=/app/uploads/zip_files
ENV HOME=/app/data/runtime/home
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config
ENV LD_LIBRARY_PATH=/usr/local/lib

HEALTHCHECK --interval=5s --timeout=5s --start-period=180s --retries=120 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

USER appuser

EXPOSE 8000

CMD ["/usr/local/bin/backend"]

FROM runtime-base AS runtime-plain
FROM runtime-base AS runtime-release
