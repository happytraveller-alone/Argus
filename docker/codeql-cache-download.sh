#!/bin/bash
# Pre-download CodeQL build artifacts to docker/cache/ for fast image builds.
# Run once; subsequent `podman build` will COPY from cache instead of downloading.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="$SCRIPT_DIR/cache"
CODEQL_VERSION="${CODEQL_VERSION:-2.16.1}"
GRADLE_VERSION="${GRADLE_VERSION:-8.7}"

mkdir -p "$CACHE_DIR"

CODEQL_BUNDLE="$CACHE_DIR/codeql-bundle-linux64.tar.gz"
GRADLE_ZIP="$CACHE_DIR/gradle-${GRADLE_VERSION}-bin.zip"

download_if_missing() {
  local dest="$1" url="$2" label="$3"
  if [[ -f "$dest" ]]; then
    echo "[cache] $label already cached: $dest"
    return 0
  fi
  echo "[cache] Downloading $label..."
  wget -q --show-progress "$url" -O "${dest}.tmp" && mv "${dest}.tmp" "$dest"
  echo "[cache] Done: $dest ($(du -h "$dest" | cut -f1))"
}

download_if_missing "$CODEQL_BUNDLE" \
  "https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_VERSION}/codeql-bundle-linux64.tar.gz" \
  "CodeQL bundle v${CODEQL_VERSION}"

download_if_missing "$GRADLE_ZIP" \
  "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
  "Gradle ${GRADLE_VERSION}"

echo "[cache] All artifacts ready. Build with:"
echo "  podman build -f docker/codeql.Dockerfile --network=host --tag localhost/argus/codeql-runner:latest ."
