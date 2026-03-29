#!/usr/bin/env bash
# Build sandbox runner image
# 按需加载的轻量级代码执行镜像

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_NAME="${IMAGE_NAME:-vulhunter/sandbox-runner}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64,linux/arm64}"

echo "🚀 Building Sandbox Runner image..."
echo "  Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  Platform: ${PLATFORM}"

cd "${PROJECT_ROOT}"

# 使用 docker buildx 支持多平台
docker buildx build \
  --platform "${PLATFORM}" \
  --file docker/sandbox-runner.Dockerfile \
  --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
  --load \
  .

echo "✅ Build complete: ${IMAGE_NAME}:${IMAGE_TAG}"

# 验证镜像
echo ""
echo "📊 Image info:"
docker images "${IMAGE_NAME}:${IMAGE_TAG}"

echo ""
echo "🧪 Quick test:"
docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" python3 -c "import requests; print('✅ Sandbox runner OK')"
