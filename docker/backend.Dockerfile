FROM rust:1.90-slim AS builder

WORKDIR /app
COPY backend/Cargo.toml ./Cargo.toml
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/tests ./tests

RUN cargo build --release

FROM debian:bookworm-slim AS runtime-plain

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/target/release/backend-rust /usr/local/bin/backend

ENV BIND_ADDR=0.0.0.0:8000
ENV ZIP_STORAGE_PATH=/app/uploads/zip_files

EXPOSE 8000

CMD ["/usr/local/bin/backend"]
