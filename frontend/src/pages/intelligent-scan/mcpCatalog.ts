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

export const DEFAULT_MCP_CATALOG: McpCatalogItem[] = [];

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

  const normalized = rawCatalog.reduce<McpCatalogItem[]>((acc, raw) => {
    if (!raw || typeof raw !== "object") return acc;
    const item = raw as Record<string, unknown>;
    const id = String(item.id ?? "").trim();
    const name = String(item.name ?? "").trim();
    if (!id || !name) return acc;

    acc.push({
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
            : "stdio_only",
      required: typeof item.required === "boolean" ? item.required : true,
      startup_ready:
        typeof item.startup_ready === "boolean" ? item.startup_ready : true,
      startup_error:
        typeof item.startup_error === "string" ? item.startup_error : null,
      backend: toDomainStatus(item.backend),
      sandbox: toDomainStatus(item.sandbox),
    });
    return acc;
  }, []);

  if (normalized.length === 0) {
    return DEFAULT_MCP_CATALOG;
  }

  const visibleIds = new Set(DEFAULT_MCP_CATALOG.map((item) => item.id));
  const filtered = normalized.filter((item) => visibleIds.has(item.id));
  return filtered.length > 0 ? filtered : DEFAULT_MCP_CATALOG;
}
