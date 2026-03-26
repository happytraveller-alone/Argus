# VulHunter - 面向仓库级代码漏洞挖掘与安全审计的平台

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

VulHunter 聚焦代码仓库级别的安全审计与漏洞挖掘，使用 Multi-Agent 协作、规则扫描、RAG 语义召回和 LLM 推理，把“发现可疑点”到“验证潜在漏洞”的流程串成一条完整链路。

## 使用场景

- 在项目上线、交付或开源发布前，对整个仓库做一次集中安全审计。
- 对存量代码库进行周期性巡检，补齐密钥泄露、依赖风险和高危代码模式排查。
- 对第三方仓库、外包代码或历史遗留项目做快速风险摸底，缩小人工复核范围。
- 作为安全团队或研发团队的辅助平台，用来整理发现、查看证据并导出审计结果。

## 漏洞挖掘方式

VulHunter 默认按“编排 -> 初筛 -> 深挖 -> 验证”的方式工作：

1. **Multi-Agent 编排**：由编排 Agent 拆解任务，协调侦察、分析和验证阶段。
2. **静态扫描初筛**：结合规则扫描、依赖审计和密钥检测，快速定位高风险入口。
3. **RAG 语义召回**：对仓库代码建立向量索引，用语义检索补充上下文和相似模式线索。
4. **LLM 深度分析**：结合代码上下文、数据流线索和安全知识，对可疑点进行进一步推理。
5. **PoC 沙箱验证（可选）**：在 Docker 隔离环境中执行验证脚本，帮助确认漏洞真实性并过滤误报。

这套方式适合仓库级、跨模块、需要同时兼顾“扫描效率”和“分析深度”的代码审计任务。

## 快速部署

### 1. 克隆仓库

```bash
git clone https://github.com/unbengable12/AuditTool.git
cd AuditTool
```

### 2. 配置后端环境变量

```bash
cp backend/env.example backend/.env
```

至少补充你的模型相关配置，例如 `LLM_API_KEY`、`LLM_PROVIDER`、`LLM_MODEL`。不要把真实密钥提交到仓库。

### 3. 启动服务

默认推荐直接使用 Docker Compose：

```bash
docker compose up --build
```

Windows 请使用 Docker Desktop + Linux containers。

如需显式执行全量本地构建，请叠加 `docker-compose.full.yml`：

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

默认 `docker compose up --build` 的 compose 层只拉起常驻服务，compose 不再声明一次性 runner 预热 / 自检服务。
backend 启动时会自行执行 runner preflight，校验 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 指向的镜像和命令是否可用；真正执行扫描时，backend 仍会通过 Docker SDK 按镜像名动态拉起临时 runner 容器。

如需查看可选的 legacy 包装脚本说明，请参考 [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)。

### 4. 访问服务

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`

相关文档：
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/AGENT_AUDIT.md`](docs/AGENT_AUDIT.md) ·
[`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)
