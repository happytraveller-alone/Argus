export type McpCatalogType = "mcp-server" | "skill-pack";

export interface McpDomainStatus {
  enabled: boolean;
  startup_ready: boolean;
  startup_error?: string | null;
}

export interface McpCatalogItem {
  id: string;
  name: string;
  type: McpCatalogType;
  enabled: boolean;
  description: string;
  executionFunctions: string[];
  inputInterface: string[];
  outputInterface: string[];
  includedSkills: string[];
  source: string;
  runtime_mode?: string;
  required?: boolean;
  startup_ready?: boolean;
  startup_error?: string | null;
  backend?: McpDomainStatus;
  sandbox?: McpDomainStatus;
}

export const DEFAULT_MCP_CATALOG: McpCatalogItem[] = [
  {
    id: "filesystem",
    name: "Filesystem MCP",
    type: "mcp-server",
    enabled: true,
    description: "项目文件系统访问与受控写入执行。",
    executionFunctions: [
      "read_file",
      "list_directory",
      "edit_file",
      "write_file",
    ],
    inputInterface: [
      "path/file_path",
      "start_line/end_line",
      "old_text/new_text",
      "reason/finding_id/todo_id",
    ],
    outputInterface: ["content", "metadata.file_path", "write_scope_*"],
    includedSkills: ["read_file", "list_files", "edit_file", "write_file"],
    source: "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: true,
    startup_error: null,
    backend: { enabled: true, startup_ready: true, startup_error: null },
    sandbox: { enabled: true, startup_ready: true, startup_error: null },
  },
  {
    id: "code_index",
    name: "Code Index MCP",
    type: "mcp-server",
    enabled: true,
    description: "代码索引、符号级检索与函数定位。",
    executionFunctions: [
      "search_code_advanced",
      "get_symbol_body",
      "get_file_summary",
    ],
    inputInterface: [
      "query/keyword",
      "path/file_path",
      "glob/file_pattern",
      "line_start/function_name",
    ],
    outputInterface: ["symbols", "matches", "file_summary", "metadata.engine"],
    includedSkills: [
      "search_code",
      "extract_function",
      "locate_enclosing_function",
      "code_search",
    ],
    source: "https://github.com/johnhuang316/code-index-mcp",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: true,
    startup_error: null,
    backend: { enabled: true, startup_ready: true, startup_error: null },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "memory",
    name: "Memory MCP",
    type: "mcp-server",
    enabled: false,
    description: "模型长期上下文记忆与任务摘要管理。",
    executionFunctions: ["memory_store", "memory_query", "memory_append"],
    inputInterface: ["task_id", "agent_name", "summary", "payload"],
    outputInterface: ["memory_hit", "memory_entries", "shared_summary"],
    includedSkills: ["memory_sync", "task_memory"],
    source: "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: false,
    startup_error: "disabled",
    backend: { enabled: false, startup_ready: false, startup_error: "disabled" },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "sequentialthinking",
    name: "Sequential Thinking MCP",
    type: "mcp-server",
    enabled: false,
    description: "序列化思考链路与步骤化推理辅助。",
    executionFunctions: ["sequential_thinking", "reasoning_trace"],
    inputInterface: ["goal", "constraints", "steps"],
    outputInterface: ["reasoning_steps", "next_action", "stop_signal"],
    includedSkills: ["brainstorming", "step_reasoning"],
    source:
      "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: false,
    startup_error: "disabled",
    backend: { enabled: false, startup_ready: false, startup_error: "disabled" },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "qmd",
    name: "QMD MCP",
    type: "mcp-server",
    enabled: false,
    description: "模型上下文快速检索与语义召回。",
    executionFunctions: ["qmd_query", "qmd_get", "qmd_multi_get", "qmd_status"],
    inputInterface: ["query/searches", "collections", "ids"],
    outputInterface: ["hits", "documents", "metadata.collections"],
    includedSkills: ["qmd_query", "qmd_get", "qmd_multi_get", "qmd_status"],
    source: "https://github.com/tobi/qmd",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: false,
    startup_error: "disabled",
    backend: { enabled: false, startup_ready: false, startup_error: "disabled" },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "codebadger",
    name: "CodeBadger MCP",
    type: "mcp-server",
    enabled: false,
    description: "基于 CPG 的深度流分析与可达性验证能力。",
    executionFunctions: ["joern_reachability_verify", "cpg_query"],
    inputInterface: ["file_path", "line_start", "call_chain", "query"],
    outputInterface: ["flow_paths", "control_conditions", "metadata.path_score"],
    includedSkills: ["joern_reachability_verify", "controlflow_analysis_light"],
    source: "https://github.com/codebadger-io/mcp",
    runtime_mode: "backend_only",
    required: true,
    startup_ready: false,
    startup_error: "disabled",
    backend: { enabled: false, startup_ready: false, startup_error: "disabled" },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "mcp-builder",
    name: "MCP Builder",
    type: "skill-pack",
    enabled: true,
    description: "快速创建 MCP server 的流程模板与落地规范。",
    executionFunctions: ["template_guidance", "spec_scaffold"],
    inputInterface: ["server_goal", "io_schema", "security_constraints"],
    outputInterface: ["mcp_design_plan", "integration_checklist"],
    includedSkills: ["mcp-builder"],
    source: "https://github.com/anthropics/skills/tree/main/skills/mcp-builder",
    runtime_mode: "n/a",
    required: false,
    startup_ready: true,
    startup_error: null,
  },
  {
    id: "skill-creator",
    name: "Skill Creator",
    type: "skill-pack",
    enabled: true,
    description: "创建和维护审计 skill 的模板规范。",
    executionFunctions: ["skill_design", "prompt_contract", "usage_examples"],
    inputInterface: ["skill_goal", "tool_bindings", "safety_rules"],
    outputInterface: ["skill_definition", "examples", "pitfalls"],
    includedSkills: ["skill-creator"],
    source: "https://github.com/anthropics/skills/tree/main/skills/skill-creator",
    runtime_mode: "n/a",
    required: false,
    startup_ready: true,
    startup_error: null,
  },
  {
    id: "planning-with-files",
    name: "Planning With Files",
    type: "skill-pack",
    enabled: true,
    description: "基于文件清单进行分步规划与执行。",
    executionFunctions: ["file_planning", "task_breakdown", "execution_queue"],
    inputInterface: ["file_targets", "goal", "constraints"],
    outputInterface: ["plan_steps", "file_actions", "progress_rules"],
    includedSkills: ["file_planning", "execution_planning"],
    source: "https://github.com/OthmanAdi/planning-with-files",
    runtime_mode: "n/a",
    required: false,
    startup_ready: true,
    startup_error: null,
  },
  {
    id: "superpowers",
    name: "Superpowers",
    type: "skill-pack",
    enabled: true,
    description: "头脑风暴与高阶协作执行模板集合。",
    executionFunctions: ["brainstorming", "strategy_generation", "review_loop"],
    inputInterface: ["problem_statement", "tradeoffs", "evidence"],
    outputInterface: ["strategy_options", "decision_rationale"],
    includedSkills: ["brainstorming", "strategy-superpowers"],
    source: "https://github.com/obra/superpowers",
    runtime_mode: "n/a",
    required: false,
    startup_ready: true,
    startup_error: null,
  },
];

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item ?? "").trim())
    .filter((item) => item.length > 0);
}

function toCatalogType(value: unknown): McpCatalogType {
  const raw = String(value ?? "").trim().toLowerCase();
  return raw === "skill-pack" ? "skill-pack" : "mcp-server";
}

function toDomainStatus(value: unknown): McpDomainStatus | undefined {
  if (!value || typeof value !== "object") return undefined;
  const item = value as Record<string, unknown>;
  return {
    enabled: Boolean(item.enabled),
    startup_ready: Boolean(item.startup_ready),
    startup_error:
      typeof item.startup_error === "string" ? item.startup_error : null,
  };
}

export function normalizeMcpCatalog(rawCatalog: unknown): McpCatalogItem[] {
  if (!Array.isArray(rawCatalog) || rawCatalog.length === 0) {
    return DEFAULT_MCP_CATALOG;
  }

  const normalized = rawCatalog
    .map((raw) => {
      if (!raw || typeof raw !== "object") return null;
      const item = raw as Record<string, unknown>;
      const id = String(item.id ?? "").trim();
      const name = String(item.name ?? "").trim();
      if (!id || !name) return null;
      return {
        id,
        name,
        type: toCatalogType(item.type),
        enabled: Boolean(item.enabled),
        description: String(item.description ?? "").trim(),
        executionFunctions: toStringArray(
          item.executionFunctions ?? item.execution_functions,
        ),
        inputInterface: toStringArray(item.inputInterface ?? item.input_interface),
        outputInterface: toStringArray(item.outputInterface ?? item.output_interface),
        includedSkills: toStringArray(item.includedSkills ?? item.included_skills),
        source: String(item.source ?? "").trim(),
        runtime_mode:
          typeof item.runtime_mode === "string"
            ? item.runtime_mode
            : typeof item.runtimeMode === "string"
              ? item.runtimeMode
              : undefined,
        required:
          typeof item.required === "boolean"
            ? item.required
            : undefined,
        startup_ready:
          typeof item.startup_ready === "boolean"
            ? item.startup_ready
            : undefined,
        startup_error:
          typeof item.startup_error === "string" ? item.startup_error : null,
        backend: toDomainStatus(item.backend),
        sandbox: toDomainStatus(item.sandbox),
      } satisfies McpCatalogItem;
    })
    .filter((item): item is McpCatalogItem => Boolean(item));

  if (!normalized.length) {
    return DEFAULT_MCP_CATALOG;
  }
  return normalized;
}
