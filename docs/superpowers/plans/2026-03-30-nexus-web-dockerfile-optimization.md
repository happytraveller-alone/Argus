# nexus-web Dockerfile 构建优化实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 nexus-web Docker 镜像构建时 pnpm 安装阶段的"Importing packages to virtual store"瓶颈，大幅缩短构建时间。

**Architecture:** 通过在 Dockerfile 中将 pnpm 的 `node-linker` 切换为 `hoisted` 模式，绕过虚拟存储（`.pnpm/`）的构建过程，改用传统 `node_modules/` 扁平布局；同时修剪构建时不需要的 devDependency。

**Tech Stack:** Docker multi-stage build, pnpm 10.x, Node.js 20-alpine, nginx 1.27-alpine

---

## 问题诊断

```
Progress: resolved 644, reused 643, downloaded 0, added 99
Progress: resolved 644, reused 643, downloaded 0, added 477
Progress: resolved 644, reused 643, downloaded 0, added 643
```

| 字段 | 含义 | 状态 |
|------|------|------|
| resolved 644 | lockfile 中共 644 个包 | 正常 |
| reused 643 | 643 个包已在 pnpm 全局 store 缓存 | 正常，下载不是瓶颈 |
| downloaded 0 | 无需下载 | 正常 |
| added 0→477→643 | **向虚拟存储导入包** | ⚠️ **这是瓶颈** |

**根本原因**：pnpm 默认的 `node-linker=isolated` 模式会为每个包创建 `.pnpm/[pkg@ver]/node_modules/[pkg]/` 目录结构（虚拟存储），644 个包意味着需要创建数千个目录和硬链接，这是 IO 密集操作，即使包已缓存也很慢。

**解决方案**：切换为 `node-linker=hoisted`，pnpm 使用传统 `node_modules/` 扁平布局，直接从全局 store 硬链接到 `node_modules/`，跳过虚拟存储构建。

---

## 受影响文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `docker/nexus-web.Dockerfile` | 修改 | 核心变更：设置 node-linker=hoisted、精简安装逻辑 |

---

## Task 1: 设置 pnpm node-linker=hoisted

**Files:**
- Modify: `docker/nexus-web.Dockerfile`

### 变更说明

`run_nexus_install` 函数当前的命令：
```bash
timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline --network-concurrency 1
```

需要在 `pnpm config set store-dir` 那一行之后立即加入：
```bash
pnpm config set node-linker hoisted
```

这样 pnpm 就不会创建 `.pnpm/` 虚拟存储，而是直接把包解压到 `node_modules/`，速度提升显著。

同时可以放宽网络并发限制，将 `--network-concurrency 1` 改为默认（删除该参数），因为当包已缓存时，并发限制没有意义，而且不限制时对于 fetch 阶段更快。

- [ ] **Step 1: 读取当前 Dockerfile 确认修改位置**

```bash
# 定位需要修改的行
grep -n "node-linker\|store-dir\|network-concurrency\|node-linker" docker/nexus-web.Dockerfile
```

预期：看到 `pnpm config set store-dir` 在第 93 行附近，`--network-concurrency 1` 在第 56 行附近。

- [ ] **Step 2: 修改 Dockerfile — 添加 node-linker=hoisted 配置**

在 `docker/nexus-web.Dockerfile` 中，找到以下代码块（大约第 93 行）：

```bash
    pnpm config set store-dir /pnpm/store; \
    pnpm config set network-timeout 120000; \
    pnpm config set fetch-retries 1; \
```

修改为：

```bash
    pnpm config set store-dir /pnpm/store; \
    pnpm config set network-timeout 120000; \
    pnpm config set fetch-retries 1; \
    pnpm config set node-linker hoisted; \
```

- [ ] **Step 3: 移除 --network-concurrency 1 限制**

找到 `run_nexus_install` 函数中的 install 命令（大约第 56 行）：

```bash
      timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline --network-concurrency 1; \
```

修改为：

```bash
      timeout "${step_timeout}" pnpm install --frozen-lockfile --offline --prefer-offline; \
```

> 原因：`--network-concurrency 1` 仅在网络下载时有意义；由于 `--offline` 保证不走网络，该参数实际无效但引入混淆。

- [ ] **Step 4: 验证修改正确性**

```bash
# 检查修改后的关键行
grep -n "node-linker\|network-concurrency\|pnpm config" docker/nexus-web.Dockerfile
```

预期输出（大约）：
```
94:    pnpm config set node-linker hoisted; \
```
且不再有 `--network-concurrency 1`。

- [ ] **Step 5: 清理 Docker 构建缓存（可选，用于基准测试）**

```bash
# 只清理 nexus-web 相关缓存层，进行干净测试
docker builder prune --filter label=nexus-web --force 2>/dev/null || true
```

- [ ] **Step 6: 执行构建测试并计时**

```bash
# 只构建 nexus-web 服务，观察时间
time docker compose build nexus-web 2>&1 | tee /tmp/nexus-web-build.log

# 查看关键步骤耗时
grep -E "Progress:|DONE|ERROR|=>.*#" /tmp/nexus-web-build.log | tail -40
```

预期：`added X` 进度条推进速度明显加快，总构建时间缩短。

- [ ] **Step 7: 验证镜像正常运行**

```bash
# 启动服务，检查健康状态
docker compose up -d nexus-web
sleep 15
docker compose ps nexus-web
docker compose logs nexus-web --tail 20
```

预期：`nexus-web` 状态为 `healthy`，nginx 正常启动，无 WASM 文件缺失错误。

- [ ] **Step 8: 提交**

```bash
git add docker/nexus-web.Dockerfile
git commit -m "perf: 使用 pnpm node-linker=hoisted 加速 nexus-web Docker 构建

将 pnpm node-linker 切换为 hoisted 模式，跳过虚拟存储(.pnpm/)构建，
消除 644 个包的硬链接结构创建瓶颈。缓存命中时可将 deps 阶段从
数分钟缩短至秒级。"
```

---

## Task 2（可选）: 进一步优化 — 添加 .npmrc 显式声明

如果 Task 1 不够稳定（某些 pnpm 版本 `--offline` 与 `hoisted` 的交互有 bug），可以通过显式创建 `.npmrc` 来确保设置生效。

**Files:**
- Modify: `docker/nexus-web.Dockerfile`

- [ ] **Step 1: 在 COPY 之后立即创建 .npmrc**

在 `docker/nexus-web.Dockerfile` 的 `deps` 阶段，找到 `COPY src/package.json ...` 之后、`RUN` 块之前，添加：

```dockerfile
# 强制使用 hoisted linker（传统 node_modules 布局），跳过虚拟存储构建
RUN echo "node-linker=hoisted" > /app/.npmrc && \
    echo "shamefully-hoist=true" >> /app/.npmrc
```

> `shamefully-hoist=true` 是 `node-linker=hoisted` 的补充，确保所有包都提升到顶层 `node_modules/`，兼容 vite 的模块解析。

- [ ] **Step 2: 重新构建测试**

同 Task 1 Step 6。

---

## Task 3（可选）: 移除构建时不需要的 devDependencies

`@vercel/node` (`^5.5.16`) 是 Vercel 服务端运行时，对 Docker 中的 `vite build` 完全无用，但它会拉入额外的依赖。

**Files:**
- Modify: `docker/nexus-web.Dockerfile`

- [ ] **Step 1: 在 deps 阶段修补 package.json，移除 @vercel/node**

在 Dockerfile 的 `packageManager` 修补块之后添加：

```bash
RUN node -e '\
const fs = require("fs");\
const path = "/app/package.json";\
const pkg = JSON.parse(fs.readFileSync(path, "utf8"));\
if (pkg.devDependencies) {\
  delete pkg.devDependencies["@vercel/node"];\
}\
fs.writeFileSync(path, `${JSON.stringify(pkg, null, 2)}\n`);\
'
```

> 注意：移除 package.json 中的包后，需要同时更新 pnpm-lock.yaml，或使用 `pnpm install --no-frozen-lockfile` 跳过 lockfile 校验。因此此步骤有一定风险，建议仅在 Task 1 验证通过后再考虑。

---

## 预期效果

| 阶段 | 优化前 | 优化后（Task 1）|
|------|--------|----------------|
| pnpm fetch（首次） | ~2-5 min | ~2-5 min（无变化，受网络影响）|
| pnpm fetch（有缓存）| ~10s | ~10s（无变化）|
| pnpm install（有缓存）| **数分钟**（虚拟存储构建）| **<30s**（直接 node_modules 硬链接）|
| vite build | ~1-2 min | ~1-2 min（无变化）|

---

## 回滚方案

如果 `hoisted` 模式导致 vite build 失败（模块解析问题），直接删除 `pnpm config set node-linker hoisted` 这一行即可回滚到默认 `isolated` 模式。
