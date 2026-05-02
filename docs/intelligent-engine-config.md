# 智能引擎多模型配置指南

> 适用状态：2026-05-02 的 Rust backend / React frontend 主线。本文记录智能引擎配置页、后端 `/system-config` LLM 配置契约，以及 claw-code 智能审计迁移的基础 LLM 配置适配层。

## 快速结论

智能引擎配置已从旧版单一 `llmConfig` 对象替换为 schema v2 多行配置表。系统设置页展示多 provider 表格；智能审计创建弹窗不增加 provider/model 选择器，仍只通过 agent preflight 判断是否允许创建。

## 启动与导入

1. 保留根目录 `env.example`。首次运行 bootstrap 时，如果根目录 `.env` 不存在，脚本会复制模板、自动生成 `SECRET_KEY` 并退出：

   ```bash
   ./argus-bootstrap.sh --wait-exit -- default
   ```

2. 填写根目录 `.env`，至少包括：
   - `LLM_PROVIDER`：canonical provider，例如 `openai_compatible` 或 `anthropic_compatible`
   - `LLM_API_KEY`
   - `LLM_MODEL`
   - `LLM_BASE_URL`

3. 可先校验 LLM 配置：

   ```bash
   ./scripts/validate-llm-config.sh --env-file ./.env
   ```

4. 校验通过后再次启动：

   ```bash
   ./argus-bootstrap.sh --wait-exit -- default
   ```

`argus-bootstrap.sh` 会先确保根目录 `.env` 存在且 `SECRET_KEY` 已自动生成，再调用 `scripts/validate-llm-config.sh --env-file ./.env` 校验 env/LLM 配置；缺文件、缺 `LLM_MODEL` / `LLM_BASE_URL` 等必填项、LLM 占位值、unsupported provider 或 backend import/test 失败都会中止启动并提示重新配置。Compose 会通过 `ARGUS_ENV_FILE` 指定的 env file（默认 `./.env`）注入 backend。UI/API 不写回这个文件；启动导入只负责把环境里的初始 LLM 配置导入 system-config。

## API 契约

### GET/PUT `/api/v1/system-config`

`llmConfig` 是 breaking schema v2 envelope：

```json
{
  "schemaVersion": 2,
  "rows": [
    {
      "id": "llmcfg_stable_id",
      "priority": 1,
      "enabled": true,
      "provider": "openai_compatible",
      "baseUrl": "https://api.openai.com/v1",
      "model": "gpt-5",
      "hasApiKey": true,
      "advanced": {
        "llmTimeout": 120000,
        "llmTemperature": 0.2,
        "llmMaxTokens": 8192,
        "llmFirstTokenTimeout": 30,
        "llmStreamTimeout": 120,
        "agentTimeout": 1800,
        "subAgentTimeout": 900,
        "toolTimeout": 300,
        "llmCustomHeaders": "{}"
      },
      "modelStatus": {
        "available": null,
        "lastCheckedAt": null,
        "reasonCode": null
      },
      "preflight": {
        "status": "untested",
        "reasonCode": null,
        "message": null,
        "checkedAt": null,
        "fingerprint": null
      }
    }
  ],
  "latestPreflightRun": {
    "runId": null,
    "checkedAt": null,
    "attemptedRowIds": [],
    "winningRowId": null,
    "winningFingerprint": null
  },
  "migration": {
    "status": "not_needed",
    "message": null,
    "sourceSchemaVersion": null
  }
}
```

后端 helper `backend/src/routes/llm_config_set.rs` 负责旧单配置迁移、行优先级归一、row-id 密钥保留、公开脱敏、fallback 分类和 row 到 runtime config 的转换。`selected_enabled_runtime` 在所有已启用行均加载失败时会返回包含最后一条失败原因的详细错误消息（例如 "已启用 2 行均无法加载：LLM 配置缺失：`apiKey` 必填。"），而非泛化提示。路由层不要绕过 helper 直接拼写或修改 LLM row JSON。

claw-code 迁移的基础适配层位于 `backend/src/runtime/intelligent/config.rs`。它消费同一套 saved `system-config` row，输出不序列化明文 API key 的 `IntelligentLlmConfig`：provider、model、base URL、fingerprint、超时/温度/token 参数和自定义 header 名称。Anthropic-compatible 配置会映射为 claw-code Anthropic API key 认证，OpenAI-compatible 配置会映射为 OpenAI-compatible bearer 认证；该适配层不是任务创建 API，也不会自行发起智能审计。

### POST `/api/v1/system-config/test-llm`

系统设置页连接测试接口。请求可以带 `rowId`，表示测试指定配置行；测试成功或失败会更新该行 `preflight` 元数据和 `latestPreflightRun`。

### POST `/api/v1/system-config/test-llm/batch`

系统设置页顶部"保存并验证"的批量验证接口。该接口是 saved-config-only：请求体必须为空或 `{}`，后端只读取已保存的 `system-config`，不接受调用方传入的临时 LLM 配置。

批量验证行为：

- 按 `priority` 遍历所有 rows。
- 禁用行返回 `skipped_disabled`，不覆盖该行已有 `preflight`。
- 启用但缺少必填字段的行持久化 `missing_fields`、原因和时间戳。
- 启用且字段完整的行执行真实 LLM 测试；单行失败不会阻断后续行。
- 至少一行实际测试且所有启用行都通过时返回 `reasonCode: "all_rows_passed"`；没有可实时测试行时返回 `reasonCode: "no_eligible_rows"`。
- 响应包含 `rows`、`attemptedRowIds`、`skippedRowIds`、`missingFieldRowIds`、`failedRowIds`、`passedRowIds`，但不得包含明文 API key、自定义 header secret 或 raw runtime config。

### POST `/api/v1/system-config/fetch-llm-models`

模型列表发现接口。请求可以带 `rowId`，后端会以该行保存的 provider/base URL/key 为基础，并允许请求里的 draft provider/base URL/key 覆盖用于本次发现；响应不得回显明文密钥。

### POST `/api/v1/system-config/agent-preflight`

智能审计创建门禁。后端按 `priority` 尝试已启用 rows，停止在第一个通过的 row，并记录 attempted row ids、winning row id 和 winning fingerprint。

Fallback 只允许这些原因继续尝试下一行：

- `connectivity`
- `auth`
- `model_unavailable`

这些原因不 fallback：

- `quota_rate_limit`
- `invalid_config`
- `invalid_response`
- `unknown_error`
- 任务启动后的运行期 LLM 调用失败

## 密钥安全规则

- 公开 GET、test、preflight、fetch-models 和错误响应不得包含明文 `apiKey`。
- 前端表格只展示 `hasApiKey` 或等价存在状态。
- 编辑已有行时，空 API key 表示按稳定 `id` 保留已保存密钥；显式输入新 key 才替换。
- 删除 row 后，后续 GET/test/preflight 不能泄露该 row 的旧 key。

## 前端行为

系统设置页入口：`frontend/src/components/system/SystemConfig.tsx`。

表格使用共享 `Table` primitives 配合 `table-fixed` 显式列宽（序号、模型供应商、地址、模型、状态、操作），确保表格总宽度撑满容器。列间有竖向分割线（`border-r border-border/30`），"操作"列表头居中。列顺序固定为：序号、模型供应商、地址、模型、状态、操作。操作区包含验证、编辑、禁用/启用、删除、上移、下移；删除动作只显示文字，不渲染 trash/delete 图标。单行"验证"自动保存当前行配置并执行 `/system-config/test-llm` 诊断；顶部"保存并验证"先保存，再调用 `/system-config/test-llm/batch` 批量验证所有启用且字段完整的已保存行，随后重新加载后端配置作为状态列来源。新增和编辑使用同一配置弹窗，弹窗采用 flex 列布局（固定头部 + 可滚动内容区 + 固定底栏），分为"基本配置"和"高级配置"两个区域，API key 输入默认不可见。

智能引擎独立配置页 `frontend/src/pages/ScanConfigIntelligentEngine.tsx` 嵌入 `SystemConfig`（仅 LLM 区），表格上方显示可用/异常计数、"保存并验证"和"新增配置"按钮；该页不渲染底部"保存并测试"、"保存"和"重置"按钮。其他复用 `SystemConfig` 的页面可继续通过 `showInlineSaveButtons` 控制底部按钮。

扫描引擎配置页 `frontend/src/pages/ScanConfigEngines.tsx` 嵌入 `OpengrepRules`，其 `DataTable` 使用 `enableColumnResizing` + `fillContainerWidth` 确保表格撑满容器宽度。

智能审计创建弹窗入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`。该弹窗不得新增 provider/model 选择控件；它只消费 agent preflight 的结果。

## 运维冒烟

修改智能引擎配置相关代码后至少运行：

```bash
pnpm --dir frontend test:node
pnpm --dir frontend type-check
pnpm --dir frontend lint
pnpm --dir frontend build
cargo test --manifest-path backend/Cargo.toml system_config
cargo test --manifest-path backend/Cargo.toml runtime::intelligent::config
cargo test --manifest-path backend/Cargo.toml agent_preflight
cargo test --manifest-path backend/Cargo.toml
bash scripts/test-argus-bootstrap.sh
git diff --check
```

视觉证据或等价浏览器可见证据放在 `.omx/evidence/intelligent-engine-config-table-refactor/`。
