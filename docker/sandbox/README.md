# Sandbox 镜像构建指南

## 镜像说明

### 1. 完整 Sandbox (`vulhunter/sandbox:latest`)

**用途**: 综合扫描环境,包含所有安全工具

**特点**:
- ✅ 包含扫描工具: Opengrep, Bandit, Gitleaks, PMD, TruffleHog, PHPStan, OSV-Scanner
- ✅ 包含编译工具: gcc, cmake, clang, Go, Rust
- ✅ 完整运行时: Python, Node, PHP, Java, Ruby
- 📦 镜像大小: ~2GB
- 🎯 使用场景: 完整功能的常驻扫描容器

**构建**:
```bash
# 使用现有脚本
./build.sh

# 或使用 docker build
docker build -f Dockerfile -t vulhunter/sandbox:latest .
```

### 2. Sandbox Runner (`vulhunter/sandbox-runner:latest`)

**用途**: 轻量级按需代码执行镜像

**特点**:
- ❌ 不包含扫描工具
- ❌ 不包含编译工具
- ✅ 只包含运行时: Python, Node, PHP, Java, Ruby
- ✅ 精简的 Python 库: requests, httpx, jwt, beautifulsoup4
- 📦 镜像大小: ~600MB (减少 69%)
- ⚡ 启动速度: 快 3 倍
- 🎯 使用场景: 按需启动的临时代码执行容器

**构建**:
```bash
# 使用构建脚本 (推荐)
./build-runner.sh

# 或使用 docker build
cd ../..
docker build -f docker/sandbox-runner.Dockerfile \
  -t vulhunter/sandbox-runner:latest .
```

## 快速开始

### 构建完整 Sandbox

```bash
./build.sh
```

### 构建 Sandbox Runner

```bash
./build-runner.sh
```

### 测试 Sandbox Runner

```bash
./test-runner.sh
```

## 镜像选择建议

### 使用完整 Sandbox 的场景

- 需要使用扫描工具 (Opengrep, Bandit 等)
- 需要编译代码 (Go, Rust, C++)
- 作为常驻容器使用
- 需要完整的开发环境

### 使用 Sandbox Runner 的场景

- 只需要代码执行能力
- 按需启动的临时容器
- 关注启动速度和资源占用
- 生产环境的代码验证

## Preflight 集成

Sandbox Runner 已集成到 runner preflight 机制:

```bash
# 使用完整构建配置
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
```

Backend 启动时会:
1. 检查 `vulhunter/sandbox-runner:latest` 镜像
2. 如果不存在 → 自动从 `docker/sandbox-runner.Dockerfile` 构建
3. 运行自检命令验证功能
4. 验证通过 → Backend 完成启动

详见: [SANDBOX_RUNNER_PREFLIGHT.md](../SANDBOX_RUNNER_PREFLIGHT.md)

## 参考

- [完整 Sandbox Dockerfile](Dockerfile)
- [Sandbox Runner Dockerfile](../sandbox-runner.Dockerfile)
- [Sandbox Runner 文档](../SANDBOX_RUNNER.md)
- [构建指南](../BUILD_SANDBOX_RUNNER.md)
- [Preflight 集成](../SANDBOX_RUNNER_PREFLIGHT.md)
