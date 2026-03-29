#!/usr/bin/env bash
# Sandbox Runner 测试脚本
# 验证镜像构建、功能和安全配置

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-vulhunter/sandbox-runner:latest}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Sandbox Runner 测试套件"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查镜像是否存在
echo "1️⃣  检查镜像..."
if docker images "${IMAGE_NAME}" --format "{{.Repository}}:{{.Tag}}" | grep -q "${IMAGE_NAME}"; then
    echo -e "${GREEN}✅ 镜像存在: ${IMAGE_NAME}${NC}"
    docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
else
    echo -e "${YELLOW}⚠️  镜像不存在,请先构建: ./build-runner.sh${NC}"
    exit 1
fi

echo ""
echo "2️⃣  测试运行时环境..."

# 测试 Python
echo -n "  Python 3.11: "
if docker run --rm "${IMAGE_NAME}" python3 --version > /dev/null 2>&1; then
    VERSION=$(docker run --rm "${IMAGE_NAME}" python3 --version)
    echo -e "${GREEN}✅ ${VERSION}${NC}"
else
    echo -e "${RED}❌ FAILED${NC}"
    exit 1
fi

# 测试 Node.js
echo -n "  Node.js: "
if docker run --rm "${IMAGE_NAME}" node --version > /dev/null 2>&1; then
    VERSION=$(docker run --rm "${IMAGE_NAME}" node --version)
    echo -e "${GREEN}✅ ${VERSION}${NC}"
else
    echo -e "${RED}❌ FAILED${NC}"
    exit 1
fi

# 测试 PHP
echo -n "  PHP: "
if docker run --rm "${IMAGE_NAME}" php --version | head -1 > /dev/null 2>&1; then
    VERSION=$(docker run --rm "${IMAGE_NAME}" php --version | head -1)
    echo -e "${GREEN}✅ ${VERSION}${NC}"
else
    echo -e "${RED}❌ FAILED${NC}"
    exit 1
fi

# 测试 Java
echo -n "  Java: "
if docker run --rm "${IMAGE_NAME}" java --version | head -1 > /dev/null 2>&1; then
    VERSION=$(docker run --rm "${IMAGE_NAME}" java --version | head -1)
    echo -e "${GREEN}✅ ${VERSION}${NC}"
else
    echo -e "${RED}❌ FAILED${NC}"
    exit 1
fi

# 测试 Ruby
echo -n "  Ruby: "
if docker run --rm "${IMAGE_NAME}" ruby --version > /dev/null 2>&1; then
    VERSION=$(docker run --rm "${IMAGE_NAME}" ruby --version)
    echo -e "${GREEN}✅ ${VERSION}${NC}"
else
    echo -e "${RED}❌ FAILED${NC}"
    exit 1
fi

echo ""
echo "3️⃣  测试 Python 依赖..."

# 测试 Python 包
DEPS=("requests" "httpx" "jwt" "Crypto")
for dep in "${DEPS[@]}"; do
    echo -n "  ${dep}: "
    if docker run --rm "${IMAGE_NAME}" python3 -c "import ${dep}" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        exit 1
    fi
done

echo ""
echo "4️⃣  测试安全配置..."

# 测试非 root 用户
echo -n "  非 root 用户: "
USER_ID=$(docker run --rm "${IMAGE_NAME}" id -u)
if [ "${USER_ID}" = "1000" ]; then
    echo -e "${GREEN}✅ uid=${USER_ID} (sandbox)${NC}"
else
    echo -e "${RED}❌ uid=${USER_ID} (应该是 1000)${NC}"
    exit 1
fi

# 测试网络隔离
echo -n "  网络隔离: "
if docker run --rm --network none "${IMAGE_NAME}" ping -c 1 8.8.8.8 > /dev/null 2>&1; then
    echo -e "${RED}❌ 网络未隔离${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 网络已隔离${NC}"
fi

# 测试只读 + tmpfs
echo -n "  只读文件系统 + tmpfs: "
if docker run --rm \
    --read-only \
    --tmpfs /tmp:rw,exec,size=512m \
    "${IMAGE_NAME}" \
    python3 -c "import tempfile; f=tempfile.NamedTemporaryFile(); f.close()" > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌${NC}"
    exit 1
fi

echo ""
echo "5️⃣  测试代码执行..."

# Python 代码执行
echo -n "  Python 执行: "
OUTPUT=$(docker run --rm "${IMAGE_NAME}" python3 -c "print('hello')")
if [ "${OUTPUT}" = "hello" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ (输出: ${OUTPUT})${NC}"
    exit 1
fi

# Node.js 代码执行
echo -n "  Node.js 执行: "
OUTPUT=$(docker run --rm "${IMAGE_NAME}" node -e "console.log('world')")
if [ "${OUTPUT}" = "world" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ (输出: ${OUTPUT})${NC}"
    exit 1
fi

# PHP 代码执行
echo -n "  PHP 执行: "
OUTPUT=$(docker run --rm "${IMAGE_NAME}" php -r "echo 'test';")
if [ "${OUTPUT}" = "test" ]; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌ (输出: ${OUTPUT})${NC}"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}🎉 所有测试通过!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 镜像信息:"
docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"
