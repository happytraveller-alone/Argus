# Unified Skill Runtime API 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 scan-core 和 prompt-effective skill 统一为 API 驱动协议，扩展 `/skills/catalog` 和 `/skills/{id}` 端点，引入 runtime session 状态模型与工具门禁守卫，并保证现有扫描任务工具调用完全不受影响。

**Architecture:** 分层递进实现：先补全配置与数据结构（无行为变化），再扩展 API 端点（向后兼容追加字段），然后引入 runtime session（默认关闭门禁），最后扩展 ReAct parser（纯追加字段不改旧逻辑）。守卫默认关闭，确保现有扫描任务不受影响。

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, pytest, React/TypeScript, Vite

---

## 关键约束（agent 必读）

> ⚠️ **与原始规格的有意差异**：原始规格代码示例中写的是 `SKILL_LOAD_GUARD_ENABLED: bool = True`，本计划**有意将默认值改为 `False`**。理由：Phase 1 中模型还未学会 `skill_selection` 协议，若默认开启门禁会立即阻断所有现有扫描任务的工具调用。门禁须在 skill_selection 协议全面接入后（Phase 2）再切为 `True`。

1. **不破坏扫描任务工具调用**：`SkillEnforcementGuard` 默认 `SKILL_LOAD_GUARD_ENABLED=False`，Phase 1 全程不开启硬门禁。
2. **纯追加原则**：对 `ParsedReactResponse`、`SkillDetailResponse`、`SkillCatalogItem` 只追加字段，不修改现有字段类型或删除字段。
3. **向后兼容 API**：`/skills/catalog` 和 `/skills/{id}` 的现有字段保持不变，新字段作为可选追加。
4. **每个 task 必须先写测试，再写实现，再跑测试验证。**
5. **每个 task 完成后立即 commit。**

---

## 文件清单

### 新建文件

| 文件路径 | 职责 |
|---------|------|
| `backend/app/services/agent/runtime/__init__.py` | 包入口 |
| `backend/app/services/agent/runtime/state.py` | `TaskHostSkillCache` 数据类 |
| `backend/app/services/agent/runtime/session.py` | `AgentOrWorkerSkillSession` 数据类 |
| `backend/app/services/agent/runtime/message_builder.py` | **Phase 2 存根**：`build_runtime_messages()` 接口占位，Phase 1 只建文件定义函数签名，不接入 agent |
| `backend/app/services/agent/skills/catalog.py` | `build_unified_catalog()` 统一 catalog 构建器 |
| `backend/app/services/agent/skills/loader.py` | `load_unified_skill_detail()` detail 加载器 |
| `backend/app/services/agent/skills/enforcement.py` | `SkillEnforcementGuard` + `GuardDecision` |
| `backend/tests/unit/test_skill_runtime_state.py` | state/session 单元测试 |
| `backend/tests/unit/test_skill_catalog_unified.py` | catalog 构建器单元测试 |
| `backend/tests/unit/test_skill_enforcement.py` | guard 单元测试 |
| `backend/tests/unit/test_react_parser_skill_selection.py` | parser 扩展单元测试 |

### 修改文件

| 文件路径 | 改动内容 |
|---------|---------|
| `backend/app/core/config.py` | 追加 `SKILL_*` 配置字段（有默认值，不影响现有行为） |
| `backend/app/services/agent/agents/react_parser.py` | 追加 `selected_skill_id`、`protocol_error_code` 字段到 `ParsedReactResponse`（不改旧字段） |
| `backend/app/api/v1/endpoints/skills.py` | 扩展 `SkillCatalogItem`/`SkillDetailResponse`，更新 catalog/detail endpoint 调用 unified 服务 |

---

## Task 1：追加配置字段

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/unit/test_skill_config.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_skill_config.py
from app.core.config import Settings

def test_skill_config_defaults():
    s = Settings()
    assert s.SKILL_REGISTRY_ENABLED is False
    assert s.SKILL_REGISTRY_ROOT == "/app/data/runtime/skill-registry"
    assert s.SKILL_REGISTRY_MODE == "prebuilt_only"
    assert s.SKILL_REGISTRY_REQUIRED is False
    assert s.CODEX_HOME == "/app/data/runtime/codex-home"
    assert s.SKILL_LOAD_GUARD_ENABLED is False  # 默认关闭，不影响现有扫描任务
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_config.py -v 2>&1 | tail -20
```
Expected: `FAILED` — AttributeError: Settings 无这些字段

- [ ] **Step 3: 在 config.py 追加字段**

在 `backend/app/core/config.py` 的 `Settings` 类末尾（在现有最后一个字段后），追加：

```python
    # Skill Registry 配置
    SKILL_REGISTRY_ENABLED: bool = False
    SKILL_REGISTRY_ROOT: str = "/app/data/runtime/skill-registry"
    SKILL_REGISTRY_MODE: str = "prebuilt_only"
    SKILL_REGISTRY_REQUIRED: bool = False
    CODEX_HOME: str = "/app/data/runtime/codex-home"

    # Skill Runtime 配置（门禁默认关闭，Phase 1 不开启，保护现有扫描任务）
    SKILL_LOAD_GUARD_ENABLED: bool = False
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_config.py -v 2>&1 | tail -10
```
Expected: `PASSED`

- [ ] **Step 5: 确认现有 import 无破坏**

```bash
cd backend && uv run python -c "from app.core.config import settings; print('ok')"
```
Expected: `ok`

- [ ] **Step 6: commit**

```bash
cd backend
git add app/core/config.py tests/unit/test_skill_config.py
git commit -m "feat: add SKILL_* config fields with safe defaults (guard disabled)"
```

---

## Task 2：实现 Runtime State 数据类

**Files:**
- Create: `backend/app/services/agent/runtime/__init__.py`
- Create: `backend/app/services/agent/runtime/state.py`
- Create: `backend/app/services/agent/runtime/session.py`
- Test: `backend/tests/unit/test_skill_runtime_state.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_skill_runtime_state.py
import pytest
from app.services.agent.runtime.state import TaskHostSkillCache
from app.services.agent.runtime.session import AgentOrWorkerSkillSession

class TestTaskHostSkillCache:
    def test_get_missing_entry_returns_none(self):
        cache = TaskHostSkillCache()
        assert cache.get_catalog_entry("nonexistent") is None

    def test_cache_and_get_detail(self):
        cache = TaskHostSkillCache()
        cache.cache_detail("search_code", {"skill_id": "search_code", "name": "search_code"})
        result = cache.get_cached_detail("search_code")
        assert result is not None
        assert result["skill_id"] == "search_code"

    def test_cached_detail_is_immutable_copy(self):
        cache = TaskHostSkillCache()
        original = {"skill_id": "search_code"}
        cache.cache_detail("search_code", original)
        original["tampered"] = True
        result = cache.get_cached_detail("search_code")
        assert "tampered" not in result

    def test_snapshot_for_worker(self):
        cache = TaskHostSkillCache()
        cache.catalog_digest = "abc123"
        cache.catalog_entries_by_id["search_code"] = {"skill_id": "search_code"}
        snap = cache.snapshot_for_worker()
        assert snap["catalog_digest"] == "abc123"
        assert "search_code" in snap["catalog_entries"]

class TestAgentOrWorkerSkillSession:
    def test_skill_not_loaded_initially(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-1")
        assert session.is_skill_loaded("search_code") is False

    def test_mark_skill_loaded(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-2")
        session.mark_skill_loaded("search_code", {"skill_id": "search_code"})
        assert session.is_skill_loaded("search_code") is True

    def test_active_workflow_skill_initially_none(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-3")
        assert session.get_active_workflow_skill_id() is None

    def test_set_and_get_active_workflow_skill(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-4")
        session.set_active_workflow_skill("using-superpowers@agents")
        assert session.get_active_workflow_skill_id() == "using-superpowers@agents"

    def test_set_workflow_skill_to_none(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-5")
        session.set_active_workflow_skill("some-skill")
        session.set_active_workflow_skill(None)
        assert session.get_active_workflow_skill_id() is None

    def test_active_prompt_skill_initially_none(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-6")
        assert session.get_active_prompt_skill("recon") is None

    def test_set_and_get_active_prompt_skill(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-7")
        detail = {"agent_key": "recon", "effective_content": "..."}
        session.set_active_prompt_skill("recon", detail)
        assert session.get_active_prompt_skill("recon") == detail

    def test_clear_prompt_skill_with_none(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-8")
        session.set_active_prompt_skill("recon", {"agent_key": "recon"})
        session.set_active_prompt_skill("recon", None)
        assert session.get_active_prompt_skill("recon") is None

    def test_record_protocol_error(self):
        session = AgentOrWorkerSkillSession(session_id="test-session-9")
        session.record_protocol_error("skill_not_loaded", "search_code not loaded")
        assert session.last_protocol_error is not None
        assert "skill_not_loaded" in session.last_protocol_error

    def test_sessions_are_isolated(self):
        s1 = AgentOrWorkerSkillSession(session_id="s1")
        s2 = AgentOrWorkerSkillSession(session_id="s2")
        s1.mark_skill_loaded("search_code", {})
        assert s2.is_skill_loaded("search_code") is False
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_runtime_state.py -v 2>&1 | tail -20
```
Expected: `ImportError` — 模块不存在

- [ ] **Step 3: 创建 runtime 包**

创建 `backend/app/services/agent/runtime/__init__.py`（空文件）。

创建 `backend/app/services/agent/runtime/state.py`：

```python
"""TaskHostSkillCache — 任务级只读技能缓存。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TaskHostSkillCache:
    """任务级只读缓存，供 orchestrator 和 worker 共享。worker 只能读取快照，不能回写。"""

    catalog_digest: str = ""
    catalog_entries_by_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    detail_cache_by_skill_id: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_catalog_entry(self, skill_id: str) -> Optional[Dict[str, Any]]:
        return self.catalog_entries_by_id.get(skill_id)

    def get_cached_detail(self, skill_id: str) -> Optional[Dict[str, Any]]:
        cached = self.detail_cache_by_skill_id.get(skill_id)
        return dict(cached) if cached is not None else None

    def cache_detail(self, skill_id: str, detail: Dict[str, Any]) -> None:
        self.detail_cache_by_skill_id[skill_id] = dict(detail)

    def snapshot_for_worker(self) -> Dict[str, Any]:
        return {
            "catalog_digest": self.catalog_digest,
            "catalog_entries": dict(self.catalog_entries_by_id),
            "detail_cache": {k: dict(v) for k, v in self.detail_cache_by_skill_id.items()},
        }
```

创建 `backend/app/services/agent/runtime/session.py`：

```python
"""AgentOrWorkerSkillSession — agent/worker 级 runtime skill state。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class AgentOrWorkerSkillSession:
    """Agent/Worker 级 runtime state。不与其他 worker 共享 loaded_skill_ids。"""

    session_id: str
    loaded_skill_ids: Set[str] = field(default_factory=set)
    active_workflow_skill_id: Optional[str] = None
    active_prompt_skill_by_agent_key: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_protocol_error: Optional[str] = None

    def is_skill_loaded(self, skill_id: str) -> bool:
        return skill_id in self.loaded_skill_ids

    def mark_skill_loaded(self, skill_id: str, detail: Dict[str, Any]) -> None:
        self.loaded_skill_ids.add(skill_id)

    def get_active_workflow_skill_id(self) -> Optional[str]:
        return self.active_workflow_skill_id

    def set_active_workflow_skill(self, skill_id: Optional[str]) -> None:
        self.active_workflow_skill_id = skill_id

    def get_active_prompt_skill(self, agent_key: str) -> Optional[Dict[str, Any]]:
        return self.active_prompt_skill_by_agent_key.get(agent_key)

    def set_active_prompt_skill(self, agent_key: str, detail: Optional[Dict[str, Any]]) -> None:
        if detail is None:
            self.active_prompt_skill_by_agent_key.pop(agent_key, None)
        else:
            self.active_prompt_skill_by_agent_key[agent_key] = detail

    def record_protocol_error(self, error_code: str, detail: str) -> None:
        self.last_protocol_error = f"{error_code}: {detail}"
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_runtime_state.py -v 2>&1 | tail -20
```
Expected: 全部 `PASSED`

- [ ] **Step 5: commit**

```bash
cd backend
git add app/services/agent/runtime/ tests/unit/test_skill_runtime_state.py
git commit -m "feat: add TaskHostSkillCache and AgentOrWorkerSkillSession runtime state"
```

---

## Task 3：实现 SkillEnforcementGuard（默认关闭）

**Files:**
- Create: `backend/app/services/agent/skills/enforcement.py`
- Test: `backend/tests/unit/test_skill_enforcement.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_skill_enforcement.py
import pytest
from app.services.agent.skills.enforcement import SkillEnforcementGuard, GuardDecision
from app.services.agent.runtime.session import AgentOrWorkerSkillSession


def _session(session_id: str = "test") -> AgentOrWorkerSkillSession:
    return AgentOrWorkerSkillSession(session_id=session_id)


class TestGuardDecision:
    def test_allowed_decision_has_no_error(self):
        d = GuardDecision(allowed=True, caller="recon")
        assert d.allowed is True
        assert d.error_code is None


class TestSkillEnforcementGuard:
    def test_non_scan_core_tool_always_allowed(self):
        session = _session()
        decision = SkillEnforcementGuard.check_tool_access(
            resolved_tool_name="some_internal_tool",
            caller="recon",
            session=session,
        )
        assert decision.allowed is True

    def test_scan_core_tool_allowed_when_loaded(self):
        session = _session()
        session.mark_skill_loaded("search_code", {"skill_id": "search_code"})
        decision = SkillEnforcementGuard.check_tool_access(
            resolved_tool_name="search_code",
            caller="recon",
            session=session,
        )
        assert decision.allowed is True

    def test_scan_core_tool_denied_when_not_loaded(self):
        session = _session()
        decision = SkillEnforcementGuard.check_tool_access(
            resolved_tool_name="search_code",
            caller="recon",
            session=session,
        )
        assert decision.allowed is False
        assert decision.error_code == "skill_not_loaded"
        assert decision.required_skill_id == "search_code"
        assert decision.caller == "recon"

    def test_host_internal_caller_bypasses_guard(self):
        """caller=internal_host 的调用（如复合工具内部）应豁免门禁。"""
        session = _session()
        decision = SkillEnforcementGuard.check_tool_access(
            resolved_tool_name="search_code",
            caller="internal_host",
            session=session,
        )
        assert decision.allowed is True

    def test_all_scan_core_ids_are_gated(self):
        from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS
        session = _session()
        for skill_id in SCAN_CORE_SKILL_IDS:
            decision = SkillEnforcementGuard.check_tool_access(
                resolved_tool_name=skill_id,
                caller="analysis",
                session=session,
            )
            assert decision.allowed is False, f"{skill_id} should be gated but was allowed"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_enforcement.py -v 2>&1 | tail -20
```
Expected: `ImportError`

- [ ] **Step 3: 实现 enforcement.py**

```python
# backend/app/services/agent/skills/enforcement.py
"""SkillEnforcementGuard — scan-core 工具门禁。Phase 1 默认关闭，通过 SKILL_LOAD_GUARD_ENABLED 控制。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS

if TYPE_CHECKING:
    from app.services.agent.runtime.session import AgentOrWorkerSkillSession

_HOST_INTERNAL_CALLER = "internal_host"


@dataclass
class GuardDecision:
    allowed: bool
    error_code: Optional[str] = None
    required_skill_id: Optional[str] = None
    caller: str = ""
    message: str = ""


class SkillEnforcementGuard:
    """统一技能门禁。

    caller="internal_host" 的调用（复合工具内部二次调度）自动豁免。
    所有其他 scan-core 工具在 session 未加载时被拒绝。
    """

    @staticmethod
    def check_tool_access(
        resolved_tool_name: str,
        caller: str,
        session: "AgentOrWorkerSkillSession",
    ) -> GuardDecision:
        # 内部宿主调用豁免
        if caller == _HOST_INTERNAL_CALLER:
            return GuardDecision(allowed=True, caller=caller, message="host-internal bypass")

        # 非 scan-core 工具放行
        if resolved_tool_name not in SCAN_CORE_SKILL_IDS:
            return GuardDecision(
                allowed=True,
                caller=caller,
                message=f"non-scan-core tool '{resolved_tool_name}' is not gated",
            )

        # scan-core 工具：检查 session 是否已加载
        if session.is_skill_loaded(resolved_tool_name):
            return GuardDecision(
                allowed=True,
                caller=caller,
                message=f"skill '{resolved_tool_name}' is loaded",
            )

        return GuardDecision(
            allowed=False,
            error_code="skill_not_loaded",
            required_skill_id=resolved_tool_name,
            caller=caller,
            message=(
                f"Skill '{resolved_tool_name}' must be selected and loaded before use. "
                "Output <skill_selection>{\"skill_id\":\"" + resolved_tool_name + "\"}</skill_selection> first."
            ),
        )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_enforcement.py -v 2>&1 | tail -15
```
Expected: 全部 `PASSED`

- [ ] **Step 5: commit**

```bash
cd backend
git add app/services/agent/skills/enforcement.py tests/unit/test_skill_enforcement.py
git commit -m "feat: add SkillEnforcementGuard with host-internal bypass and guard-disabled default"
```

---

## Task 4：扩展 ParsedReactResponse 支持 skill_selection

**Files:**
- Modify: `backend/app/services/agent/agents/react_parser.py`
- Test: `backend/tests/unit/test_react_parser_skill_selection.py`（新建）

**关键约束：** 只追加新字段，不修改现有字段逻辑。现有 `action`/`final_answer`/`thought` 等字段必须不变。

- [ ] **Step 1: 先运行现有 parser 测试，确认基线通过**

```bash
cd backend && uv run python -m pytest tests/ -k "react_parser" -v 2>&1 | tail -20
```
记录当前通过的测试数量，后续必须保持。

- [ ] **Step 2: 写新 skill_selection 失败测试**

```python
# backend/tests/unit/test_react_parser_skill_selection.py
"""Tests for skill_selection extension of ParsedReactResponse."""
import pytest
from app.services.agent.agents.react_parser import parse_react_response, ParsedReactResponse


class TestSkillSelectionParsing:
    def test_parse_skill_selection_only(self):
        text = 'Thought: I need search_code\n<skill_selection>{"skill_id":"search_code"}</skill_selection>'
        result = parse_react_response(text)
        assert result.selected_skill_id == "search_code"
        assert result.action is None
        assert result.is_final is False
        assert result.protocol_error_code is None

    def test_skill_selection_with_whitespace(self):
        text = '<skill_selection>\n  {"skill_id": "dataflow_analysis"}\n</skill_selection>'
        result = parse_react_response(text)
        assert result.selected_skill_id == "dataflow_analysis"
        assert result.protocol_error_code is None

    def test_skill_selection_plus_action_is_protocol_error(self):
        text = (
            "Thought: need skill\n"
            '<skill_selection>{"skill_id":"search_code"}</skill_selection>\n'
            "Action: search_code\nAction Input: {}"
        )
        result = parse_react_response(text)
        assert result.protocol_error_code == "mixed_skill_selection_with_action"

    def test_skill_selection_plus_final_answer_is_protocol_error(self):
        text = (
            '<skill_selection>{"skill_id":"search_code"}</skill_selection>\n'
            "Final Answer: done"
        )
        result = parse_react_response(text)
        assert result.protocol_error_code == "mixed_skill_selection_with_final_answer"

    def test_invalid_json_in_skill_selection_is_protocol_error(self):
        text = '<skill_selection>not-valid-json</skill_selection>'
        result = parse_react_response(text)
        assert result.protocol_error_code == "invalid_skill_selection_json"
        assert result.selected_skill_id is None

    def test_no_skill_selection_leaves_fields_none(self):
        text = "Thought: thinking\nAction: search_code\nAction Input: {}"
        result = parse_react_response(text)
        assert result.selected_skill_id is None
        assert result.protocol_error_code is None

    def test_existing_action_parsing_unchanged(self):
        """现有 action 解析路径不受影响 — 无 skill_selection 时行为与原来完全一致。"""
        text = "Thought: need to search\nAction: search_code\nAction Input: {\"query\": \"test\"}"
        result = parse_react_response(text)
        assert result.action == "search_code"
        assert result.action_input == {"query": "test"}
        assert result.selected_skill_id is None

    def test_existing_final_answer_parsing_unchanged(self):
        text = 'Thought: done\nFinal Answer: {"findings": []}'
        result = parse_react_response(text)
        assert result.is_final is True
        assert result.final_answer == {"findings": []}
        assert result.selected_skill_id is None
```

- [ ] **Step 3: 运行新测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_react_parser_skill_selection.py -v 2>&1 | tail -20
```
Expected: `AttributeError` — `ParsedReactResponse` 无 `selected_skill_id`

- [ ] **Step 4: 扩展 react_parser.py**

在 `react_parser.py` 中，对 `ParsedReactResponse` 追加三个字段（在 `final_answer` 字段后）：

```python
# 在 ParsedReactResponse dataclass 中追加（不改现有字段）：
selected_skill_id: Optional[str] = None
protocol_error_code: Optional[str] = None
protocol_error_detail: Optional[str] = None
```

在 `parse_react_response` 函数末尾（在 `return parsed` 前），追加 skill_selection 解析逻辑：

```python
    # 解析 <skill_selection> 标签（追加，不影响现有路径）
    import json as _json
    _skill_pattern = r'<skill_selection>\s*(\{[^}]+\})\s*</skill_selection>'
    _skill_match = re.search(_skill_pattern, response, re.DOTALL)
    if _skill_match:
        try:
            _skill_data = _json.loads(_skill_match.group(1))
            parsed.selected_skill_id = _skill_data.get("skill_id")
            # 协议冲突检测
            if parsed.action:
                parsed.protocol_error_code = "mixed_skill_selection_with_action"
                parsed.protocol_error_detail = "skill_selection cannot appear with Action"
            elif parsed.is_final:
                parsed.protocol_error_code = "mixed_skill_selection_with_final_answer"
                parsed.protocol_error_detail = "skill_selection cannot appear with Final Answer"
        except _json.JSONDecodeError as exc:
            parsed.protocol_error_code = "invalid_skill_selection_json"
            parsed.protocol_error_detail = str(exc)
```

注意：将这段代码插入到 `parse_react_response` 中最后一个 `return parsed` 语句的**正前方**。

- [ ] **Step 5: 运行新测试和原有 parser 测试**

```bash
cd backend && uv run python -m pytest tests/unit/test_react_parser_skill_selection.py tests/ -k "react_parser" -v 2>&1 | tail -30
```
Expected: 全部 `PASSED`，且原有 parser 测试数量不减少

- [ ] **Step 6: commit**

```bash
cd backend
git add app/services/agent/agents/react_parser.py tests/unit/test_react_parser_skill_selection.py
git commit -m "feat: extend ParsedReactResponse with skill_selection fields (backward compat)"
```

---

## Task 5：实现 Unified Catalog 构建器

**Files:**
- Create: `backend/app/services/agent/skills/catalog.py`
- Test: `backend/tests/unit/test_skill_catalog_unified.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/test_skill_catalog_unified.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.agent.skills.catalog import build_unified_catalog


class TestBuildUnifiedCatalog:
    @pytest.mark.asyncio
    async def test_scan_core_only_without_db(self):
        result = await build_unified_catalog(db=None, user_id=None)
        assert result["enabled"] is True
        assert result["error"] is None
        assert result["total"] > 0
        # 所有 items 应为 tool kind
        for item in result["items"]:
            assert item["kind"] == "tool"
            assert item["namespace"] == "scan-core"
            assert item["source"] == "scan_core"
            assert item["runtime_ready"] is True
            assert item["reason"] == "ready"

    @pytest.mark.asyncio
    async def test_catalog_has_required_fields(self):
        result = await build_unified_catalog(db=None, user_id=None)
        required_fields = {
            "skill_id", "name", "display_name", "kind", "namespace",
            "source", "summary", "selection_label", "entrypoint",
            "runtime_ready", "reason", "load_mode",
        }
        for item in result["items"]:
            for field in required_fields:
                assert field in item, f"Missing field '{field}' in catalog item {item.get('skill_id')}"

    @pytest.mark.asyncio
    async def test_namespace_filter_scan_core(self):
        result = await build_unified_catalog(db=None, user_id=None, namespace="scan-core")
        assert all(item["namespace"] == "scan-core" for item in result["items"])
        assert result["total"] == len(result["items"])

    @pytest.mark.asyncio
    async def test_namespace_filter_unknown_returns_empty(self):
        result = await build_unified_catalog(db=None, user_id=None, namespace="unknown-ns")
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_q_filter_reduces_results(self):
        full = await build_unified_catalog(db=None, user_id=None)
        filtered = await build_unified_catalog(db=None, user_id=None, q="search")
        assert filtered["total"] <= full["total"]
        for item in filtered["items"]:
            text = (item["name"] + item["summary"]).lower()
            assert "search" in text

    @pytest.mark.asyncio
    async def test_load_mode_is_summary_only(self):
        result = await build_unified_catalog(db=None, user_id=None)
        for item in result["items"]:
            assert item["load_mode"] == "summary_only"

    @pytest.mark.asyncio
    async def test_all_scan_core_skills_present(self):
        from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS
        result = await build_unified_catalog(db=None, user_id=None)
        returned_ids = {item["skill_id"] for item in result["items"]}
        for skill_id in SCAN_CORE_SKILL_IDS:
            assert skill_id in returned_ids, f"scan-core skill '{skill_id}' missing from catalog"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_catalog_unified.py -v 2>&1 | tail -15
```
Expected: `ImportError`

- [ ] **Step 3: 实现 catalog.py**

```python
# backend/app/services/agent/skills/catalog.py
"""build_unified_catalog — Phase 1 实现 scan-core + prompt-effective。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.agent.skills.scan_core import _SCAN_CORE_SKILLS, SCAN_CORE_SKILL_IDS
from app.services.agent.skills.prompt_skills import PROMPT_SKILL_AGENT_KEYS


async def build_unified_catalog(
    *,
    db: Any,
    user_id: Optional[int],
    namespace: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """构建统一 skill catalog（Phase 1: scan-core + prompt-effective）。

    db/user_id 为 None 时跳过 prompt-effective，仅返回 scan-core。
    """
    items: List[Dict[str, Any]] = []

    # ── 1. Scan-Core ──────────────────────────────────────────────────
    if namespace is None or namespace == "scan-core":
        for skill in _SCAN_CORE_SKILLS:
            if q:
                text = (skill["name"] + " " + skill["summary"]).lower()
                if q.lower() not in text:
                    continue
            items.append({
                "skill_id": skill["skill_id"],
                "name": skill["name"],
                "display_name": skill.get("display_name", skill["name"]),
                "kind": "tool",
                "namespace": "scan-core",
                "source": "scan_core",
                "summary": skill["summary"],
                "selection_label": f"[scan-core] {skill['name']}",
                "entrypoint": skill["skill_id"],
                "runtime_ready": True,
                "reason": "ready",
                "load_mode": "summary_only",
                "deferred_tools": [],
                "aliases": [],
                "has_scripts": False,
                "has_bin": False,
                "has_assets": False,
            })

    # ── 2. Prompt-Effective（需要 DB）────────────────────────────────
    if (namespace is None or namespace == "prompt") and db is not None and user_id is not None:
        for agent_key in PROMPT_SKILL_AGENT_KEYS:
            skill_id = f"prompt-{agent_key}@effective"
            if q and q.lower() not in (skill_id + agent_key).lower():
                continue
            items.append({
                "skill_id": skill_id,
                "name": skill_id,
                "display_name": f"Prompt: {agent_key.replace('_', ' ').title()}",
                "kind": "prompt",
                "namespace": "prompt",
                "source": "prompt_effective",
                "summary": f"Effective prompt skill for {agent_key} agent",
                "selection_label": f"[prompt] {agent_key}",
                "entrypoint": skill_id,
                "runtime_ready": False,  # 需要调用 loader 实时计算
                "reason": "no_active_prompt_sources",
                "load_mode": "summary_only",
                "deferred_tools": [],
                "aliases": [],
                "has_scripts": False,
                "has_bin": False,
                "has_assets": False,
            })

    # ── 3. Workflow（Phase 2）────────────────────────────────────────
    # TODO: Phase 2 实现 workflow registry source

    total = len(items)
    paginated = items[offset: offset + limit]

    return {
        "enabled": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": paginated,
        "error": None,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_catalog_unified.py -v 2>&1 | tail -15
```
Expected: 全部 `PASSED`

- [ ] **Step 5: commit**

```bash
cd backend
git add app/services/agent/skills/catalog.py tests/unit/test_skill_catalog_unified.py
git commit -m "feat: add build_unified_catalog for scan-core and prompt-effective (Phase 1)"
```

---

## Task 6：实现 Unified Detail Loader

**Files:**
- Create: `backend/app/services/agent/skills/loader.py`
- Test: `backend/tests/unit/test_skill_loader_unified.py`（新建）

- [ ] **Step 1: 读取现有 `get_scan_core_skill_detail` 实现**

```bash
cd backend && uv run python -c "
from app.services.agent.skills.scan_core import get_scan_core_skill_detail
import json
print(json.dumps(get_scan_core_skill_detail('search_code'), ensure_ascii=False, indent=2))
"
```
记录返回的字段结构，loader 必须包含这些字段。

- [ ] **Step 2: 写失败测试**

```python
# backend/tests/unit/test_skill_loader_unified.py
import pytest
from app.services.agent.skills.loader import load_unified_skill_detail


class TestLoadUnifiedSkillDetail:
    @pytest.mark.asyncio
    async def test_load_scan_core_skill(self):
        detail = await load_unified_skill_detail(
            db=None, user_id=None, skill_id="search_code"
        )
        assert detail["skill_id"] == "search_code"
        assert detail["kind"] == "tool"
        assert detail["namespace"] == "scan-core"
        assert detail["source"] == "scan_core"
        assert detail["runtime_ready"] is True

    @pytest.mark.asyncio
    async def test_scan_core_detail_has_backward_compat_fields(self):
        """旧字段兼容矩阵：现有前端仍依赖这些字段。"""
        detail = await load_unified_skill_detail(
            db=None, user_id=None, skill_id="search_code"
        )
        compat_fields = [
            "enabled", "mirror_dir", "source_root", "source_dir",
            "source_skill_md", "aliases", "has_scripts", "has_bin",
            "has_assets", "files_count", "workflow_content",
            "workflow_truncated", "workflow_error",
            "test_supported", "test_mode", "test_reason",
            "default_test_project_name",
        ]
        for f in compat_fields:
            assert f in detail, f"Missing backward compat field: '{f}'"

    @pytest.mark.asyncio
    async def test_load_nonexistent_skill_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await load_unified_skill_detail(
                db=None, user_id=None, skill_id="nonexistent_skill_xyz"
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_load_scan_core_detail_has_display_fields(self):
        detail = await load_unified_skill_detail(
            db=None, user_id=None, skill_id="search_code"
        )
        display_fields = ["display_type", "category", "goal", "task_list",
                          "input_checklist", "phase_bindings"]
        for f in display_fields:
            assert f in detail, f"Missing scan-core display field: '{f}'"

    @pytest.mark.asyncio
    async def test_load_all_scan_core_skills_succeed(self):
        from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS
        for skill_id in SCAN_CORE_SKILL_IDS:
            detail = await load_unified_skill_detail(
                db=None, user_id=None, skill_id=skill_id
            )
            assert detail["skill_id"] == skill_id
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_loader_unified.py -v 2>&1 | tail -15
```
Expected: `ImportError`

- [ ] **Step 4: 实现 loader.py**

先读取 scan_core.py 了解 `get_scan_core_skill_detail` 的返回结构：

```python
# backend/app/services/agent/skills/loader.py
"""load_unified_skill_detail — Phase 1 实现 scan-core + prompt-effective。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.services.agent.skills.scan_core import (
    SCAN_CORE_SKILL_IDS,
    get_scan_core_skill_detail,
)
from app.services.agent.skills.prompt_skills import PROMPT_SKILL_AGENT_KEYS

# scan-core 展示字段默认值
_SCAN_CORE_DISPLAY_DEFAULTS: Dict[str, Any] = {
    "display_type": "PROMPT",
    "category": "",
    "goal": "",
    "task_list": [],
    "input_checklist": [],
    "example_input": "",
    "pitfalls": [],
    "sample_prompts": [],
    "phase_bindings": [],
    "mode_bindings": [],
    "evidence_view_support": False,
    "evidence_render_type": None,
    "legacy_visible": True,
}

# tool skill 旧字段兼容矩阵默认值
_TOOL_COMPAT_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "mirror_dir": "",
    "source_root": "",
    "source_dir": "",
    "source_skill_md": "",
    "aliases": [],
    "has_scripts": False,
    "has_bin": False,
    "has_assets": False,
    "files_count": 0,
    "workflow_content": None,
    "workflow_truncated": False,
    "workflow_error": "scan_core_static_catalog",
    "test_supported": False,
    "test_mode": "disabled",
    "test_reason": None,
    "default_test_project_name": "libplist",
    "tool_test_preset": None,
}


async def load_unified_skill_detail(
    *,
    db: Any,
    user_id: Optional[int],
    skill_id: str,
    include_workflow: bool = False,
) -> Dict[str, Any]:
    """加载统一 skill detail（Phase 1: scan-core + prompt-effective）。"""

    # ── 1. Scan-Core ──────────────────────────────────────────────────
    if skill_id in SCAN_CORE_SKILL_IDS:
        base = get_scan_core_skill_detail(skill_id)  # 现有实现返回的 dict
        result: Dict[str, Any] = {
            "skill_id": skill_id,
            "kind": "tool",
            "namespace": "scan-core",
            "source": "scan_core",
            "runtime_ready": True,
            "reason": "ready",
            "load_mode": "summary_only",
            "when_to_use": [],
            "how_to_apply": [],
            "constraints": [],
            "input_constraints": [],
            "usage_examples": [],
        }
        # 合并现有 get_scan_core_skill_detail 返回值（保持旧字段）
        result.update(base)
        # 追加展示字段默认值（不覆盖已有值）
        for k, v in _SCAN_CORE_DISPLAY_DEFAULTS.items():
            result.setdefault(k, v)
        # 追加旧字段兼容矩阵
        for k, v in _TOOL_COMPAT_DEFAULTS.items():
            result.setdefault(k, v)
        # 确保 test_supported / test_mode 遵循 scan_core 逻辑（已在 base 中）
        return result

    # ── 2. Prompt-Effective ───────────────────────────────────────────
    if skill_id.startswith("prompt-") and skill_id.endswith("@effective"):
        agent_key = skill_id[len("prompt-"):-len("@effective")]
        if agent_key in PROMPT_SKILL_AGENT_KEYS:
            # Phase 1: 基础 prompt detail（不调 DB 实时计算，需要 DB 时再扩展）
            detail: Dict[str, Any] = {
                "skill_id": skill_id,
                "name": skill_id,
                "display_name": f"Prompt: {agent_key.replace('_', ' ').title()}",
                "kind": "prompt",
                "namespace": "prompt",
                "source": "prompt_effective",
                "summary": f"Effective prompt skill for {agent_key} agent",
                "entrypoint": skill_id,
                "agent_key": agent_key,
                "runtime_ready": False,
                "reason": "no_active_prompt_sources",
                "load_mode": "summary_only",
                "when_to_use": [],
                "how_to_apply": [],
                "constraints": [],
                "prompt_sources": [],
                "effective_content": "",
                # 旧字段兼容
                "enabled": True,
                "mirror_dir": "",
                "source_root": "",
                "source_dir": "",
                "source_skill_md": "",
                "aliases": [],
                "has_scripts": False,
                "has_bin": False,
                "has_assets": False,
                "files_count": 0,
                "workflow_content": None,
                "workflow_truncated": False,
                "workflow_error": None,
                "test_supported": False,
                "test_mode": "disabled",
                "test_reason": None,
                "default_test_project_name": "libplist",
                "tool_test_preset": None,
            }
            return detail

    # ── 3. Not Found ──────────────────────────────────────────────────
    raise HTTPException(
        status_code=404,
        detail={"error_code": "skill_not_found", "detail": f"Skill '{skill_id}' not found", "skill_id": skill_id, "kind": None},
    )
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend && uv run python -m pytest tests/unit/test_skill_loader_unified.py -v 2>&1 | tail -20
```
Expected: 全部 `PASSED`

- [ ] **Step 6: commit**

```bash
cd backend
git add app/services/agent/skills/loader.py tests/unit/test_skill_loader_unified.py
git commit -m "feat: add load_unified_skill_detail with backward compat fields"
```

---

## Task 7：更新 API Endpoints（向后兼容）

**Files:**
- Modify: `backend/app/api/v1/endpoints/skills.py`
- Test: 运行现有集成测试确认无回归

**关键约束：** 不修改现有 `SkillCatalogItem` 和 `SkillDetailResponse` 的现有字段。通过追加可选字段和更新 endpoint 逻辑来实现。

- [ ] **Step 1: 先确认现有 API 测试通过（基线）**

```bash
cd backend && uv run python -m pytest tests/ -k "skill" -v 2>&1 | tail -30
```
记录当前测试状态。

- [ ] **Step 2: 读取完整的 skills.py**

```bash
# 在 agent 中用 Read 工具读取文件，不要用 cat
# Read: backend/app/api/v1/endpoints/skills.py
```

- [ ] **Step 3: 扩展 SkillCatalogItem（追加字段，现有字段不动）**

在 `SkillCatalogItem` 的现有字段后追加：

```python
class SkillCatalogItem(BaseModel):
    # ── 现有字段（保持不变）──
    skill_id: str
    name: str
    namespace: str
    summary: str
    entrypoint: str
    aliases: List[str] = Field(default_factory=list)
    has_scripts: bool = False
    has_bin: bool = False
    has_assets: bool = False
    # ── 新增字段（向后兼容，全部有默认值）──
    display_name: str = ""
    kind: str = "tool"
    source: str = "scan_core"
    selection_label: str = ""
    runtime_ready: bool = True
    reason: str = "ready"
    load_mode: str = "summary_only"
    deferred_tools: List[str] = Field(default_factory=list)
```

- [ ] **Step 4: 更新 `/skills/catalog` endpoint**

将 endpoint 改为调用 `build_unified_catalog`，并将返回结果映射到 `SkillCatalogResponse`：

```python
@router.get("/catalog", response_model=SkillCatalogResponse)
async def get_skills_catalog(
    namespace: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.skills.catalog import build_unified_catalog
    result = await build_unified_catalog(
        db=db,
        user_id=current_user.id,
        namespace=namespace,
        q=q,
        limit=limit,
        offset=offset,
    )
    return result
```

- [ ] **Step 5: 更新 `/skills/{skill_id}` endpoint**

找到 `/skills/{skill_id}` GET endpoint，将其内部实现改为调用 `load_unified_skill_detail`，保留现有 error handling 结构：

```python
@router.get("/{skill_id}")
async def get_skill_detail(
    skill_id: str,
    include_workflow: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.skills.loader import load_unified_skill_detail
    try:
        detail = await load_unified_skill_detail(
            db=db,
            user_id=current_user.id,
            skill_id=skill_id,
            include_workflow=include_workflow,
        )
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "load_failed", "detail": str(e), "skill_id": skill_id, "kind": None},
        )
```

- [ ] **Step 6: 验证 Python 语法无误**

```bash
cd backend && uv run python -c "import app.api.v1.endpoints.skills; print('import ok')"
```
Expected: `import ok`

- [ ] **Step 7: 运行 FastAPI 应用启动检查**

```bash
cd backend && uv run python -c "
from app.main import app
print('FastAPI app created ok, routes:', len(app.routes))
"
```
Expected: 无异常，打印 routes 数量

- [ ] **Step 8: 运行所有现有 skill 相关测试**

```bash
cd backend && uv run python -m pytest tests/ -k "skill" -v 2>&1 | tail -30
```
Expected: 与 Step 1 的基线一致（测试数量不减少，所有原来通过的仍通过）

- [ ] **Step 9: commit**

```bash
cd backend
git add app/api/v1/endpoints/skills.py
git commit -m "feat: update /skills/catalog and /skills/{id} to use unified catalog/loader"
```

---

## Task 8：`message_builder.py` Phase 2 存根

**Files:**
- Create: `backend/app/services/agent/runtime/message_builder.py`

**说明：** 原始规格要求新建此文件。Phase 1 只建立函数签名存根，不接入任何 agent，不影响现有行为。Phase 2 再实现完整的 `build_runtime_messages()`。

- [ ] **Step 1: 创建存根文件**

```python
# backend/app/services/agent/runtime/message_builder.py
"""build_runtime_messages — Phase 2 统一 prompt 注入入口（存根）。

Phase 1 只定义接口，不接入 agent。Phase 2 实现时将替换各 agent 中的
skills.md / shared.md / Prompt Skill 手工拼接路径。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.runtime.session import AgentOrWorkerSkillSession


def build_runtime_messages(
    agent_key: str,
    conversation_history: List[Dict[str, Any]],
    session: "AgentOrWorkerSkillSession",
    prompt_safe_memory: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """（Phase 2 存根）构建统一 runtime message 列表。

    Phase 1 中此函数不被调用，直接 raise 以防误用。
    """
    raise NotImplementedError(
        "build_runtime_messages is a Phase 2 feature and not yet implemented. "
        "Agents continue to use their existing prompt injection paths in Phase 1."
    )
```

- [ ] **Step 2: 确认 import 无副作用**

```bash
cd backend && uv run python -c "import app.services.agent.runtime.message_builder; print('message_builder stub ok')"
```
Expected: `message_builder stub ok`

- [ ] **Step 3: commit**

```bash
cd backend
git add app/services/agent/runtime/message_builder.py
git commit -m "feat: add message_builder stub for Phase 2 (not wired to agents)"
```

---

## Task 9：扩展 `/config` 端点新增 `unifiedSkillAvailability`

**Files:**
- Modify: `backend/app/api/v1/endpoints/` 中处理 `/config` 的文件（agent 需先用 Grep 定位）
- Test: 运行现有 config 相关测试确认无回归

**关键约束：** 保留原 `skillAvailability` 字段不变；新增 `unifiedSkillAvailability` 作为独立字段，两者共存。

- [ ] **Step 1: 定位 /config endpoint 文件**

```bash
cd backend && grep -r "skillAvailability\|/config" app/api/ --include="*.py" -l
```
记录文件路径，后续步骤用 Read 工具读取完整内容。

- [ ] **Step 2: 读取该文件并找到 skillAvailability 构建逻辑**

用 Read 工具读取 Step 1 找到的文件，定位 `skillAvailability` 字段的构建位置。

- [ ] **Step 3: 在同一位置追加 `unifiedSkillAvailability` 字段**

在 `skillAvailability` 字段构建逻辑**之后**追加（不修改现有逻辑）：

```python
# 追加 unifiedSkillAvailability（保持 skillAvailability 旧字段不变）
from app.services.agent.skills.scan_core import SCAN_CORE_SKILL_IDS
from app.services.agent.skills.prompt_skills import PROMPT_SKILL_AGENT_KEYS

unified_skill_availability = {}

# scan-core tools
for skill_id in SCAN_CORE_SKILL_IDS:
    unified_skill_availability[skill_id] = {
        "enabled": True,
        "startup_ready": True,
        "runtime_ready": True,
        "reason": "ready",
        "source": "scan_core",
        "kind": "tool",
        "load_mode": "summary_only",
    }

# prompt-effective skills
for agent_key in PROMPT_SKILL_AGENT_KEYS:
    skill_id = f"prompt-{agent_key}@effective"
    unified_skill_availability[skill_id] = {
        "enabled": True,
        "startup_ready": True,
        "runtime_ready": False,
        "reason": "no_active_prompt_sources",
        "source": "prompt_effective",
        "kind": "prompt",
        "load_mode": "summary_only",
    }
```

然后在返回的 config dict 中追加：
```python
"unifiedSkillAvailability": unified_skill_availability,
```

- [ ] **Step 4: 验证 Python 语法无误**

```bash
cd backend && uv run python -c "import app.api.v1.endpoints; print('config endpoint ok')"
```

- [ ] **Step 5: 验证 `/config` 响应包含新旧两个字段**

```bash
cd backend && uv run python -c "
import asyncio, httpx
from app.main import app
from httpx import AsyncClient, ASGITransport

async def check():
    transport = ASGITransport(app=app)
    # 只检查路由注册，不做实际 HTTP 请求（避免依赖 DB）
    route_paths = [r.path for r in app.routes if hasattr(r, 'path')]
    print('Routes found:', [p for p in route_paths if 'config' in p.lower()])
    print('App import OK')

asyncio.run(check())
"
```
Expected: 打印含 `config` 的路由路径，无异常

- [ ] **Step 6: 运行全量现有测试确认无回归**

```bash
cd backend && uv run python -m pytest tests/ -m "not integration" -q 2>&1 | tail -10
```
Expected: 与之前一致，无新增失败

- [ ] **Step 7: commit**

```bash
cd backend
git add app/api/v1/endpoints/
git commit -m "feat: add unifiedSkillAvailability to /config endpoint (preserves skillAvailability)"
```

---

## Task 10：验证扫描任务工具调用完整性

这是最关键的验收步骤。确保代码改动不影响实际扫描流程中的工具调用。

**Files:** 无修改，仅验证

- [ ] **Step 1: 运行全量后端测试**

```bash
cd backend && uv run python -m pytest tests/ -v --tb=short 2>&1 | tail -50
```
Expected: 无新增失败（与改动前基线一致）

- [ ] **Step 2: 验证 react_parser 现有行为不变**

```bash
cd backend && uv run python -c "
from app.services.agent.agents.react_parser import parse_react_response

# 现有 action 路径
r1 = parse_react_response('Thought: need to search\nAction: search_code\nAction Input: {\"query\": \"test\"}')
assert r1.action == 'search_code', f'action broken: {r1.action}'
assert r1.action_input == {'query': 'test'}, f'action_input broken: {r1.action_input}'
assert r1.selected_skill_id is None

# 现有 final answer 路径
r2 = parse_react_response('Final Answer: {\"findings\": []}')
assert r2.is_final is True
assert r2.selected_skill_id is None

print('react_parser backward compat: OK')
"
```
Expected: `react_parser backward compat: OK`

- [ ] **Step 3: 验证 scan_core skills catalog 完整性**

```bash
cd backend && uv run python -c "
import asyncio
from app.services.agent.skills.catalog import build_unified_catalog

async def check():
    result = await build_unified_catalog(db=None, user_id=None)
    assert result['total'] == 17, f'Expected 17 scan-core skills, got {result[\"total\"]}'
    assert result['error'] is None
    print(f'Unified catalog: {result[\"total\"]} skills, all scan-core')
    for item in result['items']:
        assert item['kind'] == 'tool'
        assert item['runtime_ready'] is True

asyncio.run(check())
print('Catalog integrity: OK')
"
```
Expected: `Catalog integrity: OK`

- [ ] **Step 4: 验证 enforcement guard 默认不阻断任何现有调用**

```bash
cd backend && uv run python -c "
from app.core.config import settings
print('SKILL_LOAD_GUARD_ENABLED =', settings.SKILL_LOAD_GUARD_ENABLED)
assert settings.SKILL_LOAD_GUARD_ENABLED is False, 'Guard must be disabled by default!'
print('Guard default state: OK (disabled)')
"
```
Expected: `Guard default state: OK (disabled)`

- [ ] **Step 5: 验证所有新模块 import 无副作用**

```bash
cd backend && uv run python -c "
import app.services.agent.runtime.state
import app.services.agent.runtime.session
import app.services.agent.skills.catalog
import app.services.agent.skills.loader
import app.services.agent.skills.enforcement
print('All new modules import clean: OK')
"
```
Expected: `All new modules import clean: OK`

- [ ] **Step 6: 最终回归测试**

```bash
cd backend && uv run python -m pytest tests/ -m "not integration" --tb=short -q 2>&1 | tail -20
```
Expected: 无新增失败，`passed` 数量 ≥ 改动前基线

---

## Task 11：前端 SkillCatalogItem 类型扩展（可选，不影响扫描）

**注意:** 本 task 仅追加前端类型定义，不删除现有代码，不影响扫描任务。

**Files:**
- Modify: `frontend/src/` 中 skills 相关类型文件（由 agent 自行通过 Glob 定位）

- [ ] **Step 1: 定位前端 skill 类型文件**

```bash
# Glob: frontend/src/**/*.ts, 搜索 SkillCatalogItem 或 SKILL_TOOLS_CATALOG
```

- [ ] **Step 2: 在现有类型定义后追加新字段（不修改现有字段）**

找到 skill catalog item 的 TypeScript interface/type，追加可选字段：

```typescript
// 追加到现有 interface（所有字段均为可选，保证向后兼容）
display_name?: string;
kind?: "tool" | "workflow" | "prompt";
source?: "scan_core" | "registry_manifest" | "prompt_effective";
selection_label?: string;
runtime_ready?: boolean;
reason?: string;
load_mode?: "summary_only";
deferred_tools?: string[];
```

- [ ] **Step 3: 确认前端构建无类型错误**

```bash
cd frontend && pnpm build 2>&1 | tail -20
```
Expected: 构建成功，无新增 TypeScript 错误

- [ ] **Step 4: commit**

```bash
cd frontend
git add src/
git commit -m "feat: extend skill catalog item type with unified fields (optional, backward compat)"
```

---

## 验收检查清单

在所有 Task 完成后，运行以下检查：

```bash
# 1. 全量后端单元测试
cd backend && uv run python -m pytest tests/ -m "not integration" -q 2>&1 | tail -5

# 2. ruff lint 检查
cd backend && uv run ruff check app/services/agent/runtime/ app/services/agent/skills/catalog.py app/services/agent/skills/loader.py app/services/agent/skills/enforcement.py app/api/v1/endpoints/skills.py

# 3. 应用启动检查
cd backend && uv run python -c "from app.main import app; print('app ok')"

# 4. 前端类型检查
cd frontend && pnpm lint 2>&1 | tail -10
```

所有检查必须通过后，宣布计划完成。

---

## 风险备注

1. **`get_scan_core_skill_detail` 返回结构**：在 Task 6 Step 1 中必须先确认其实际返回字段，loader 的 `result.update(base)` 依赖这个结构。如果有字段冲突，以 `base` 为准（通过 `.update` 覆盖默认值）。

2. **现有 `/skills/{skill_id}` endpoint 的 response_model**：若现有 endpoint 使用了严格的 `response_model=SkillDetailResponse`，切换为返回 dict 后 FastAPI 会做 model validation。需要确认 `SkillDetailResponse` 允许额外字段（`model_config = ConfigDict(extra="allow")`）或改为不指定 response_model。

3. **`scan_core.py` 中 `_SCAN_CORE_SKILLS` 是模块私有变量**：在 `catalog.py` 中从 `scan_core` import 时，已通过 `from app.services.agent.skills.scan_core import _SCAN_CORE_SKILLS` 访问。如 lint 报告 "protected member access"，改为在 `scan_core.py` 中新增 `SCAN_CORE_SKILLS_LIST = _SCAN_CORE_SKILLS` 公开别名并更新 import。
