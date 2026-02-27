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
  verificationTools: string[];
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
    description: "任务解压目录挂载（只读），支持项目文件读取与目录访问。",
    executionFunctions: ["read_file", "list_directory", "search_files", "get_file_info"],
    inputInterface: [
      "path/file_path",
      "directory",
      "pattern",
    ],
    outputInterface: ["content", "metadata.file_path", "entries"],
    includedSkills: ["read_file", "search_code"],
    verificationTools: ["read_file", "search_code"],
    source: "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    runtime_mode: "sandbox_only",
    required: true,
    startup_ready: true,
    startup_error: null,
    backend: { enabled: false, startup_ready: false, startup_error: "disabled" },
    sandbox: { enabled: true, startup_ready: true, startup_error: null },
  },
  {
    id: "code_index",
    name: "Code Index MCP",
    type: "mcp-server",
    enabled: true,
    description: "代码索引、符号级检索与函数定位。",
    executionFunctions: [
      "find_files",
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
      "extract_function",
      "list_files",
      "locate_enclosing_function",
      "function_context",
    ],
    verificationTools: ["extract_function", "list_files", "locate_enclosing_function"],
    source: "https://github.com/johnhuang316/code-index-mcp",
    runtime_mode: "backend_then_sandbox",
    required: true,
    startup_ready: true,
    startup_error: null,
    backend: { enabled: true, startup_ready: true, startup_error: null },
    sandbox: { enabled: false, startup_ready: false, startup_error: "disabled" },
  },
  {
    id: "sequentialthinking",
    name: "Sequential Thinking MCP",
    type: "mcp-server",
    enabled: true,
    description: "序列化思考链路与步骤化推理辅助。",
    executionFunctions: ["sequential_thinking", "reasoning_trace"],
    inputInterface: ["goal", "constraints", "steps"],
    outputInterface: ["reasoning_steps", "next_action", "stop_signal"],
    includedSkills: ["sequential_thinking", "reasoning_trace", "brainstorming", "step_reasoning"],
    verificationTools: ["sequential_thinking", "reasoning_trace"],
    source:
      "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
    runtime_mode: "backend_then_sandbox",
    required: false,
    startup_ready: true,
    startup_error: null,
    backend: { enabled: true, startup_ready: true, startup_error: null },
    sandbox: { enabled: true, startup_ready: true, startup_error: null },
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
        verificationTools: toStringArray(
          item.verificationTools ?? item.verification_tools,
        ),
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
            : true,
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
