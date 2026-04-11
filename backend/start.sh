#!/bin/sh

set -eu

export BIND_ADDR="${BIND_ADDR:-0.0.0.0:8000}"
export ZIP_STORAGE_PATH="${ZIP_STORAGE_PATH:-$(pwd)/tmp/zip-storage}"

mkdir -p "${ZIP_STORAGE_PATH}"

cargo build --bin backend-rust
exec cargo run --bin backend-rust
