ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli
ARG BACKEND_CARGO_REGISTRY=sparse+https://rsproxy.cn/index/
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS=30
ARG BACKEND_CARGO_NET_RETRY=10

FROM ${DOCKERHUB_LIBRARY_MIRROR}/rust:1.90-slim-bookworm AS builder
ARG BACKEND_CARGO_REGISTRY
ARG BACKEND_CARGO_HTTP_TIMEOUT_SECONDS
ARG BACKEND_CARGO_NET_RETRY
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends pkg-config libssl-dev \
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

FROM ${DOCKER_CLI_IMAGE} AS docker-cli-src

FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:trixie-slim AS runtime-base

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appgroup \
  && useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser \
  && mkdir -p /app/uploads/zip_files /app/data/runtime/xdg-data /app/data/runtime/xdg-cache /app/data/runtime/xdg-config

WORKDIR /app

COPY --from=builder /app/target/release/backend-rust /usr/local/bin/backend
COPY --from=docker-cli-src /usr/local/bin/docker /usr/local/bin/docker

RUN chown -R appuser:appgroup /app

ENV BIND_ADDR=0.0.0.0:8000
ENV ZIP_STORAGE_PATH=/app/uploads/zip_files
ENV XDG_DATA_HOME=/app/data/runtime/xdg-data
ENV XDG_CACHE_HOME=/app/data/runtime/xdg-cache
ENV XDG_CONFIG_HOME=/app/data/runtime/xdg-config

HEALTHCHECK --interval=5s --timeout=5s --start-period=180s --retries=120 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

USER appuser

EXPOSE 8000

CMD ["/usr/local/bin/backend"]

FROM runtime-base AS runtime-plain
FROM runtime-base AS runtime-release
