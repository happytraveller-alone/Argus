# Execution Contracts 实施规格

## 阅读定位

- **文档类型**：Reference（实施规格）。
- **目标读者**：准备把 workspace、finding persistence、phase 输入输出和 phase result 收口成正式执行契约的开发者。
- **阅读目标**：固定 `WorkspaceRef`、`SnapshotRef`、`ArtifactRef`、`WorkspaceResolver`、`FindingStorePort`、`PhaseRunnerInput`、`PhaseRunnerResult`、`PhaseResultPort` 的最小结构和 Phase 1 映射规则。
- **建议前置**：先读 [./control-plane-execution-plane-boundary.md](./control-plane-execution-plane-boundary.md) 和 [./redis-db-workspace-worker-sequence.md](./redis-db-workspace-worker-sequence.md) 理解这些接口为什么存在。
- **本文不覆盖**：对象存储、manifest 服务、远程 artifact store、真正的多 worker 共享文件系统。

## 1. 规范状态

- **当前已存在**
  - `SCAN_WORKSPACE_ROOT`
  - `ensure_scan_workspace(...)`
  - `ensure_scan_project_dir(...)`
  - `ensure_scan_output_dir(...)`
  - `ensure_scan_logs_dir(...)`
  - `ensure_scan_meta_dir(...)`
  - scanner runner 挂载整个 workspace 到 `/scan`
  - `SaveVerificationResultTool` / `UpdateVulnerabilityFindingTool` 的私有 callback 注入
  - `ParallelPhaseExecutor._build_worker_input(...)` 的 ad hoc dict 输入
- **Phase 1 新引入**
  - `WorkspaceRef`
  - `SnapshotRef`
  - `ArtifactRef`
  - `WorkspaceResolver`
  - `FindingStorePort`
  - `PhaseRunnerInput`
  - `PhaseRunnerResult`
  - `PhaseResultPort`
- **明确延后**
  - 远端 workspace service
  - artifact manifest API
  - 远程 phase result HTTP 接口

## 2. 当前代码锚点

| 当前代码锚点 | 当前事实 | Phase 1 映射目标 |
| --- | --- | --- |
| `backend/app/core/config.py` | `SCAN_WORKSPACE_ROOT` 默认 `/tmp/Argus/scans` | `WorkspaceResolver` 的本地根目录来源 |
| `backend/app/api/v1/endpoints/static_tasks_shared.py` | 当前工作区路径规则为 `<SCAN_WORKSPACE_ROOT>/<scan_type>/<task_id>/{project,output,logs,meta}` | `WorkspaceRef` / `SnapshotRef` / `ArtifactRef` 的本地解析规则 |
| `backend/app/services/scanner_runner.py` | scanner 把整个 workspace 挂载到 `/scan` | `WorkspaceResolver` 必须保证 ref 能解析到可挂载目录 |
| `backend/app/services/agent/tools/verification_result_tools.py` | verification/report 通过私有 `_save_callback` / `_update_callback` 持久化 | `FindingStorePort` |
| `backend/app/services/agent/workflow/parallel_executor.py` | worker 输入由 ad hoc dict 组装，包含 `project_root` / `risk_point` / `finding` / `handoff` / `config` | `PhaseRunnerInput` |

## 3. `WorkspaceRef`

`WorkspaceRef` 是 Phase 1 的 **逻辑工作区引用**。它不代表远端服务，只代表“当前 task 的本地工作区身份”。

### 3.1 固定结构

```python
{
    "id": "ws:{scan_type}:{task_id}",
    "scan_type": str,
    "task_id": str,
    "layout_version": "local-v1",
}
```

### 3.2 生成方

- 由 control plane 在任务进入执行阶段时生成。
- 同一 `task_id + scan_type` 在整个任务生命周期内只生成一个 `WorkspaceRef`。

### 3.3 生命周期

- task 执行期间保持稳定不变。
- 同一 task 的 retry 必须复用同一个 `WorkspaceRef`。
- cleanup 只能由 control plane 在终态收敛后触发。

## 4. `SnapshotRef`

`SnapshotRef` 表示当前 task 在工作区中的只读代码快照。Phase 1 只定义本地 `project/` 目录这一个快照。

### 4.1 固定结构

```python
{
    "id": "snap:{scan_type}:{task_id}:project",
    "workspace_id": "ws:{scan_type}:{task_id}",
    "relative_path": "project",
    "immutable": True,
}
```

### 4.2 生成方

- 由 `WorkspaceResolver` 在准备完项目树并固定到 `project/` 后生成。

### 4.3 约束

- `project/` 一旦形成快照，就视为只读输入。
- phase worker 不得向 `project/` 写产物。

## 5. `ArtifactRef`

`ArtifactRef` 表示当前 task 工作区中的执行产物引用。

### 5.1 固定结构

```python
{
    "id": "artifact:{scan_type}:{task_id}:{category}:{relative_path}",
    "workspace_id": "ws:{scan_type}:{task_id}",
    "category": "output" | "logs" | "meta",
    "relative_path": str,
}
```

### 5.2 本地目录映射规则

Phase 1 本地映射规则固定为：

- workspace 根目录：`<SCAN_WORKSPACE_ROOT>/<scan_type>/<task_id>`
- snapshot 目录：`<workspace>/project`
- output 目录：`<workspace>/output`
- logs 目录：`<workspace>/logs`
- meta 目录：`<workspace>/meta`

### 5.3 写入规则

为避免并发覆盖，Phase 1 写入规则固定为：

- `output/<phase>/<attempt>/...`
- `logs/<phase>/<attempt>/...`
- `meta/<phase>/<attempt>/...`

`relative_path` 必须以这组 phase-scoped 子目录为准，不得直接把所有文件堆在根级目录。

## 6. `WorkspaceResolver`

`WorkspaceResolver` 负责把 ref 映射到当前本地路径。Phase 1 只做本地 resolver，不做远端 resolver。

### 6.1 最小方法集

```python
class WorkspaceResolver:
    def build_workspace_ref(self, *, scan_type: str, task_id: str) -> dict[str, object]: ...
    def build_snapshot_ref(self, workspace_ref: dict[str, object]) -> dict[str, object]: ...
    def build_artifact_ref(
        self,
        workspace_ref: dict[str, object],
        *,
        category: str,
        relative_path: str,
    ) -> dict[str, object]: ...
    def resolve_workspace(self, workspace_ref: dict[str, object]) -> str: ...
    def resolve_snapshot(self, snapshot_ref: dict[str, object]) -> str: ...
    def resolve_artifact(self, artifact_ref: dict[str, object]) -> str: ...
    def cleanup_workspace(self, workspace_ref: dict[str, object]) -> None: ...
```

### 6.2 Phase 1 不做的能力

- 不做 workspace manifest
- 不做 artifact checksum catalog
- 不做远端下载 / 上传
- 不做多实例共享文件锁

## 7. `FindingStorePort`

`FindingStorePort` 取代工具私有 `_save_callback` / `_update_callback`，成为 execution side 与全局 finding 真相之间的正式边界。

### 7.1 最小方法集

```python
class FindingStorePort:
    async def save_verified_findings(
        self,
        task_id: str,
        findings: list[dict[str, object]],
    ) -> int: ...

    async def update_finding(
        self,
        task_id: str,
        *,
        finding_identity: str,
        fields_to_update: dict[str, object],
        update_reason: str,
    ) -> dict[str, object]: ...

    async def attach_artifact(
        self,
        task_id: str,
        *,
        finding_identity: str,
        artifact_ref: dict[str, object],
        role: str,
    ) -> None: ...
```

### 7.2 责任边界

- verification 阶段通过 `save_verified_findings(...)` 提交已验证 finding
- report 阶段通过 `update_finding(...)` 修正已存在 finding
- phase 产物与报告证据通过 `attach_artifact(...)` 关联到 finding

### 7.3 明确不做

- worker 直接写 DB session
- 工具对象自行管理真正的持久化回调
- report worker 自行裁决全局 finding 的最终真相

## 8. `PhaseRunnerInput`

`PhaseRunnerInput` 是 execution side 的固定输入契约。Phase 1 起，不再允许 worker 主要依赖 ad hoc dict。

### 8.1 固定字段

```python
{
    "task_id": str,
    "phase": str,
    "workspace_ref": dict[str, object],
    "snapshot_ref": dict[str, object],
    "subject_type": "risk_point" | "finding" | "report_item",
    "subject_payload": dict[str, object],
    "handoff": dict[str, object] | None,
    "config": dict[str, object],
    "attempt": int,
}
```

### 8.2 字段规则

- `phase` 使用 workflow 阶段名。
- `subject_type` 只允许上面 3 个值。
- `subject_payload` 是当前 phase 的业务主体；它取代现在散落的 `risk_point` / `finding` / `queue_finding`。
- `attempt` 从 `1` 开始计数。

## 9. `PhaseRunnerResult`

`PhaseRunnerResult` 是 execution side 的固定输出契约。

### 9.1 固定字段

```python
{
    "status": "succeeded" | "failed" | "retryable" | "cancelled",
    "subject_updates": list[dict[str, object]],
    "artifacts": list[dict[str, object]],
    "events": list[dict[str, object]],
    "metrics": dict[str, object],
    "error": str | None,
}
```

### 9.2 字段规则

- `subject_updates` 表示对当前 phase 主体产出的结构化结果；不得直接把全局 finding 真相塞在这里冒充最终裁决。
- `artifacts` 中的每一项必须是 `ArtifactRef`。
- `events` 只包含当前 phase 希望 control plane 发出的结构化事件。
- `metrics` 必须只包含可序列化值。

## 10. `PhaseResultPort`

`PhaseResultPort` 是 execution 到 control plane 的内部提交边界。

### 10.1 最小方法集

```python
class PhaseResultPort:
    async def submit_phase_result(
        self,
        *,
        task_id: str,
        phase: str,
        result: dict[str, object],
    ) -> None: ...
```

### 10.2 责任边界

- worker 负责提交 `PhaseRunnerResult`
- control plane 负责解释该结果并推进：
  - 事件发射
  - finding 收口
  - 状态推进
  - 是否进入下一阶段

这条边界必须保持，不允许 execution side 反过来直接裁决全局生命周期。

## 11. 与当前代码的替换关系

| 当前旧边界 | Phase 1 新边界 |
| --- | --- |
| `project_root` 作为唯一上下文定位方式 | `workspace_ref + snapshot_ref` |
| 工具私有 `_save_callback` | `FindingStorePort.save_verified_findings(...)` |
| 工具私有 `_update_callback` | `FindingStorePort.update_finding(...)` |
| `ParallelPhaseExecutor._build_worker_input(...)` 的 ad hoc dict | `PhaseRunnerInput` |
| worker 结果直接合并到 orchestrator 私有字段 | `PhaseResultPort.submit_phase_result(...)` 后由 control plane 收口 |

## 12. 明确延后的能力

- 远端 artifact 下载 URL
- 对象存储 backfill
- workspace manifest / index
- phase result 的 HTTP / RPC 网络协议

## 13. 关联文档

- [Phase 1 实施总规格](./phase1-implementation-spec.md)
- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Queue Port 实施规格](./queue-port-spec.md)
