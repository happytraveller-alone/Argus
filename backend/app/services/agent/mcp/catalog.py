from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional

from app.core.config import settings


MCPCatalogType = Literal["mcp-server", "skill-pack"]


@dataclass(frozen=True)
class McpDomainStatus:
    enabled: bool
    startup_ready: bool
    startup_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class McpCatalogItem:
    id: str
    name: str
    type: MCPCatalogType
    enabled: bool
    description: str
    executionFunctions: List[str]
    inputInterface: List[str]
    outputInterface: List[str]
    includedSkills: List[str]
    source: str
    runtime_mode: str = "backend_then_sandbox"
    backend: Optional[McpDomainStatus] = None
    sandbox: Optional[McpDomainStatus] = None
    required: bool = True
    startup_ready: bool = True
    startup_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        output = asdict(self)
        if self.backend is not None:
            output["backend"] = self.backend.to_dict()
        if self.sandbox is not None:
            output["sandbox"] = self.sandbox.to_dict()
        return output


def _command_ready(command: str) -> tuple[bool, Optional[str]]:
    executable = str(command or "").strip()
    if not executable:
        return False, "missing_command"
    if os.path.isabs(executable):
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return True, None
        return False, "command_not_found"
    if shutil.which(executable):
        return True, None
    return False, "command_not_found"


def _http_endpoint_ready(url: Optional[str]) -> tuple[bool, Optional[str]]:
    endpoint = str(url or "").strip()
    if not endpoint:
        return False, "missing_endpoint"
    return True, None


def _runtime_entry(
    runtime_policy: Optional[Dict[str, Any]],
    mcp_id: str,
) -> Dict[str, Any]:
    if isinstance(runtime_policy, dict):
        candidate = runtime_policy.get(mcp_id)
        if isinstance(candidate, dict):
            return candidate
    return {}


def _default_runtime_mode(
    runtime_policy: Optional[Dict[str, Any]],
    fallback: str = "backend_then_sandbox",
) -> str:
    if isinstance(runtime_policy, dict):
        mode = runtime_policy.get("default_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return fallback


def _build_domain_status(
    *,
    enabled: bool,
    checker: tuple[bool, Optional[str]],
) -> McpDomainStatus:
    ready, reason = checker
    if not enabled:
        return McpDomainStatus(enabled=False, startup_ready=False, startup_error="disabled")
    return McpDomainStatus(enabled=True, startup_ready=bool(ready), startup_error=reason)


def _combine_startup_status(domains: List[McpDomainStatus], enabled: bool) -> tuple[bool, Optional[str]]:
    if not enabled:
        return False, "disabled"
    errors = [domain.startup_error for domain in domains if not domain.startup_ready]
    if errors:
        return False, "; ".join(str(item) for item in errors if item)
    return True, None


def build_mcp_catalog(
    *,
    mcp_enabled: Optional[bool] = None,
    runtime_policy: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    runtime_enabled = (
        bool(getattr(settings, "MCP_ENABLED", True))
        if mcp_enabled is None
        else bool(mcp_enabled)
    )
    source_override = str(getattr(settings, "MCP_CATALOG_SOURCE_URL", "") or "").strip()

    default_mode = _default_runtime_mode(
        runtime_policy,
        str(getattr(settings, "MCP_RUNTIME_MODE_DEFAULT", "backend_then_sandbox")),
    )

    def _runtime_mode_for(mcp_id: str, setting_name: str) -> str:
        entry = _runtime_entry(runtime_policy, mcp_id)
        mode = entry.get("runtime_mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
        return str(getattr(settings, setting_name, default_mode) or default_mode)

    def _domain_enabled_for(mcp_id: str, domain: str, setting_name: str) -> bool:
        entry = _runtime_entry(runtime_policy, mcp_id)
        policy_key = f"{domain}_enabled"
        if isinstance(entry.get(policy_key), bool):
            return bool(entry[policy_key])
        return bool(getattr(settings, setting_name, False))

    filesystem_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("filesystem", "backend", "MCP_FILESYSTEM_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_FILESYSTEM_COMMAND", "npx"))),
    )
    filesystem_sandbox = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for("filesystem", "sandbox", "MCP_FILESYSTEM_SANDBOX_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_FILESYSTEM_SANDBOX_COMMAND", "npx"))),
    )
    filesystem_enabled = bool(filesystem_backend.enabled or filesystem_sandbox.enabled)
    filesystem_startup_ready, filesystem_startup_error = _combine_startup_status(
        [filesystem_backend, filesystem_sandbox],
        filesystem_enabled,
    )

    code_index_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("code_index", "backend", "MCP_CODE_INDEX_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_CODE_INDEX_COMMAND", "code-index-mcp"))),
    )
    code_index_sandbox = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for("code_index", "sandbox", "MCP_CODE_INDEX_SANDBOX_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_CODE_INDEX_SANDBOX_COMMAND", "code-index-mcp"))),
    )
    code_index_enabled = bool(code_index_backend.enabled or code_index_sandbox.enabled)
    code_index_startup_ready, code_index_startup_error = _combine_startup_status(
        [code_index_backend, code_index_sandbox],
        code_index_enabled,
    )

    memory_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("memory", "backend", "MCP_MEMORY_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_MEMORY_COMMAND", "npx"))),
    )
    memory_sandbox = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("memory", "sandbox", "MCP_MEMORY_SANDBOX_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_MEMORY_SANDBOX_COMMAND", "npx"))),
    )
    memory_enabled = bool(memory_backend.enabled or memory_sandbox.enabled)
    memory_startup_ready, memory_startup_error = _combine_startup_status(
        [memory_backend, memory_sandbox],
        memory_enabled,
    )

    seq_backend = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for(
            "sequentialthinking",
            "backend",
            "MCP_SEQUENTIAL_THINKING_ENABLED",
        ),
        checker=_command_ready(str(getattr(settings, "MCP_SEQUENTIAL_THINKING_COMMAND", "npx"))),
    )
    seq_sandbox = _build_domain_status(
        enabled=runtime_enabled
        and _domain_enabled_for(
            "sequentialthinking",
            "sandbox",
            "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED",
        ),
        checker=_command_ready(str(getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND", "npx"))),
    )
    seq_enabled = bool(seq_backend.enabled or seq_sandbox.enabled)
    seq_startup_ready, seq_startup_error = _combine_startup_status(
        [seq_backend, seq_sandbox],
        seq_enabled,
    )

    qmd_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("qmd", "backend", "MCP_QMD_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_QMD_COMMAND", "qmd"))),
    )
    qmd_sandbox = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("qmd", "sandbox", "MCP_QMD_SANDBOX_ENABLED"),
        checker=_command_ready(str(getattr(settings, "MCP_QMD_SANDBOX_COMMAND", "qmd"))),
    )
    qmd_enabled = bool(qmd_backend.enabled or qmd_sandbox.enabled)
    qmd_startup_ready, qmd_startup_error = _combine_startup_status(
        [qmd_backend, qmd_sandbox],
        qmd_enabled,
    )

    codebadger_backend = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("codebadger", "backend", "MCP_CODEBADGER_ENABLED"),
        checker=_http_endpoint_ready(getattr(settings, "MCP_CODEBADGER_BACKEND_URL", None)),
    )
    codebadger_sandbox = _build_domain_status(
        enabled=runtime_enabled and _domain_enabled_for("codebadger", "sandbox", "MCP_CODEBADGER_ENABLED"),
        checker=_http_endpoint_ready(getattr(settings, "MCP_CODEBADGER_SANDBOX_URL", None)),
    )
    codebadger_enabled = bool(codebadger_backend.enabled or codebadger_sandbox.enabled)
    codebadger_startup_ready, codebadger_startup_error = _combine_startup_status(
        [codebadger_backend, codebadger_sandbox],
        codebadger_enabled,
    )

    items = [
        McpCatalogItem(
            id="filesystem",
            name="Filesystem MCP",
            type="mcp-server",
            enabled=filesystem_enabled,
            description="项目文件读取、目录查看与受控写入执行。",
            executionFunctions=["read_file", "list_directory", "edit_file", "write_file"],
            inputInterface=["path/file_path", "start_line/end_line", "old_text/new_text"],
            outputInterface=["content", "metadata.file_path", "metadata.write_scope_*"],
            includedSkills=["read_file", "list_files", "edit_file", "write_file"],
            source="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
            runtime_mode=_runtime_mode_for("filesystem", "MCP_FILESYSTEM_RUNTIME_MODE"),
            backend=filesystem_backend,
            sandbox=filesystem_sandbox,
            required=True,
            startup_ready=filesystem_startup_ready,
            startup_error=filesystem_startup_error,
        ),
        McpCatalogItem(
            id="code_index",
            name="Code Index MCP",
            type="mcp-server",
            enabled=code_index_enabled,
            description="代码检索、符号提取、文件摘要与函数定位能力。",
            executionFunctions=["search_code_advanced", "get_symbol_body", "get_file_summary"],
            inputInterface=["query/keyword", "path/file_path", "glob/file_pattern", "line_start"],
            outputInterface=["matches", "symbols", "file_summary", "metadata.engine"],
            includedSkills=[
                "search_code",
                "extract_function",
                "locate_enclosing_function",
                "code_search",
            ],
            source="https://github.com/johnhuang316/code-index-mcp",
            runtime_mode=_runtime_mode_for("code_index", "MCP_CODE_INDEX_RUNTIME_MODE"),
            backend=code_index_backend,
            sandbox=code_index_sandbox,
            required=True,
            startup_ready=code_index_startup_ready,
            startup_error=code_index_startup_error,
        ),
        McpCatalogItem(
            id="memory",
            name="Memory MCP",
            type="mcp-server",
            enabled=memory_enabled,
            description="模型记忆管理与任务摘要持久化。",
            executionFunctions=["memory_store", "memory_query", "memory_append"],
            inputInterface=["task_id", "agent_name", "summary", "payload"],
            outputInterface=["memory_entries", "memory_hit", "summary_text"],
            includedSkills=["memory_sync", "task_memory"],
            source="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
            runtime_mode=_runtime_mode_for("memory", "MCP_MEMORY_RUNTIME_MODE"),
            backend=memory_backend,
            sandbox=memory_sandbox,
            required=True,
            startup_ready=memory_startup_ready,
            startup_error=memory_startup_error,
        ),
        McpCatalogItem(
            id="sequentialthinking",
            name="Sequential Thinking MCP",
            type="mcp-server",
            enabled=seq_enabled,
            description="序列化推理与分步思考能力。",
            executionFunctions=["sequential_thinking", "reasoning_trace"],
            inputInterface=["goal", "constraints", "step_index"],
            outputInterface=["reasoning_steps", "next_action", "stop_signal"],
            includedSkills=["brainstorming", "step_reasoning"],
            source="https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
            runtime_mode=_runtime_mode_for(
                "sequentialthinking",
                "MCP_SEQUENTIAL_THINKING_RUNTIME_MODE",
            ),
            backend=seq_backend,
            sandbox=seq_sandbox,
            required=True,
            startup_ready=seq_startup_ready,
            startup_error=seq_startup_error,
        ),
        McpCatalogItem(
            id="qmd",
            name="QMD MCP",
            type="mcp-server",
            enabled=qmd_enabled,
            description="模型上下文快速检索与语义召回。",
            executionFunctions=["qmd_query", "qmd_get", "qmd_multi_get", "qmd_status"],
            inputInterface=["query/searches", "collections", "ids"],
            outputInterface=["hits", "documents", "metadata.collections"],
            includedSkills=["qmd_query", "qmd_get", "qmd_multi_get", "qmd_status"],
            source="https://github.com/tobi/qmd",
            runtime_mode=_runtime_mode_for("qmd", "MCP_QMD_RUNTIME_MODE"),
            backend=qmd_backend,
            sandbox=qmd_sandbox,
            required=True,
            startup_ready=qmd_startup_ready,
            startup_error=qmd_startup_error,
        ),
        McpCatalogItem(
            id="codebadger",
            name="CodeBadger MCP",
            type="mcp-server",
            enabled=codebadger_enabled,
            description="基于 CPG 的深度流分析与可达性验证能力。",
            executionFunctions=["joern_reachability_verify", "cpg_query"],
            inputInterface=["file_path", "line_start", "call_chain", "query"],
            outputInterface=["flow_paths", "control_conditions", "metadata.path_score"],
            includedSkills=["joern_reachability_verify", "controlflow_analysis_light"],
            source="https://github.com/codebadger-io/mcp",
            runtime_mode=_runtime_mode_for("codebadger", "MCP_CODEBADGER_RUNTIME_MODE"),
            backend=codebadger_backend,
            sandbox=codebadger_sandbox,
            required=True,
            startup_ready=codebadger_startup_ready,
            startup_error=codebadger_startup_error,
        ),
        McpCatalogItem(
            id="mcp-builder",
            name="MCP Builder",
            type="skill-pack",
            enabled=True,
            description="快速创建 MCP 服务的规范化模板与流程。",
            executionFunctions=["template_guidance", "spec_scaffold"],
            inputInterface=["server_goal", "io_schema", "security_constraints"],
            outputInterface=["mcp_design_plan", "integration_checklist"],
            includedSkills=["mcp-builder"],
            source="https://github.com/anthropics/skills/tree/main/skills/mcp-builder",
            runtime_mode="n/a",
            required=False,
            startup_ready=True,
            startup_error=None,
        ),
        McpCatalogItem(
            id="skill-creator",
            name="Skill Creator",
            type="skill-pack",
            enabled=True,
            description="快速创建与维护 skill 的模板化能力。",
            executionFunctions=["skill_design", "prompt_contract", "usage_examples"],
            inputInterface=["skill_goal", "tool_bindings", "safety_rules"],
            outputInterface=["skill_definition", "example_prompts", "pitfalls"],
            includedSkills=["skill-creator"],
            source="https://github.com/anthropics/skills/tree/main/skills/skill-creator",
            runtime_mode="n/a",
            required=False,
            startup_ready=True,
            startup_error=None,
        ),
        McpCatalogItem(
            id="planning-with-files",
            name="Planning With Files",
            type="skill-pack",
            enabled=True,
            description="面向文件目标的任务拆解与执行规划。",
            executionFunctions=["file_planning", "task_breakdown", "execution_queue"],
            inputInterface=["file_targets", "goal", "constraints"],
            outputInterface=["plan_steps", "file_actions", "progress_rules"],
            includedSkills=["file_planning", "execution_planning"],
            source="https://github.com/OthmanAdi/planning-with-files",
            runtime_mode="n/a",
            required=False,
            startup_ready=True,
            startup_error=None,
        ),
        McpCatalogItem(
            id="superpowers",
            name="Superpowers",
            type="skill-pack",
            enabled=True,
            description="头脑风暴与协作执行策略模板集合。",
            executionFunctions=["brainstorming", "strategy_generation", "review_loop"],
            inputInterface=["problem_statement", "tradeoffs", "evidence"],
            outputInterface=["strategy_options", "decision_rationale"],
            includedSkills=["brainstorming", "strategy-superpowers"],
            source="https://github.com/obra/superpowers",
            runtime_mode="n/a",
            required=False,
            startup_ready=True,
            startup_error=None,
        ),
    ]

    catalog = [item.to_dict() for item in items]
    if source_override:
        for item in catalog:
            item["catalog_source"] = source_override
    return catalog
