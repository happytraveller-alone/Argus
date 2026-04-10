import type {
  ExternalToolResourcePayload,
  ExternalToolType,
  PromptSkillDetailPayload,
  PromptSkillItemPayload,
  PromptSkillListPayload,
  SkillCatalogItemPayload,
} from "@/shared/api/database";
import {
  buildPromptSkillDisplayName,
  resolvePromptAgentLabel,
  scopeLabel,
} from "./promptSkillShared";

export type ExternalToolTypeFilter = "all" | ExternalToolType;
export type ExternalToolStatusFilter = "all" | "enabled" | "disabled";

export interface ExternalToolRow extends ExternalToolResourcePayload {
  capabilities: string[];
  agent_label: string | null;
  typeLabel: string;
  availabilityLabel: string;
}

export const EXTERNAL_TOOLS_PAGE_SIZE = 6;

export interface ExternalToolListState {
  filteredRows: ExternalToolRow[];
  pageRows: ExternalToolRow[];
  page: number;
  pageSize: number;
  totalRows: number;
  totalPages: number;
  startIndex: number;
  searchQuery: string;
}

function sanitizeCapabilities(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .map((value) => String(value || "").trim())
    .filter((value) => value.length > 0);
}

function readString(value: unknown): string {
  return String(value || "").trim();
}

function normalizeSummary(value: unknown) {
  return readString(value) || "暂无说明";
}

function inferEnabledLabel(isEnabled: boolean) {
  return isEnabled ? "启用" : "停用";
}

function inferAvailabilityLabel(isAvailable: boolean) {
  return isAvailable ? "可用" : "不可用";
}

function buildLegacySkillResource(
  skill: SkillCatalogItemPayload,
): ExternalToolResourcePayload | null {
  const toolId = readString(skill.skill_id);
  if (!toolId || !readString(skill.entrypoint)) {
    return null;
  }

  return {
    tool_type: "skill",
    tool_id: toolId,
    name: readString(skill.display_name) || readString(skill.name) || toolId,
    summary: normalizeSummary(skill.summary),
    entrypoint: readString(skill.entrypoint) || null,
    namespace: readString(skill.namespace) || "scan-core",
    resource_kind_label: "Scan Core",
    status_label: inferEnabledLabel(skill.is_enabled ?? true),
    is_enabled: skill.is_enabled ?? true,
    is_available: skill.is_available ?? true,
    detail_supported: skill.detail_supported ?? true,
    agent_key: skill.agent_key ?? null,
    agent_label: skill.agent_label ?? null,
    scope: skill.scope ?? null,
    capabilities: sanitizeCapabilities(skill.capabilities),
    content: typeof skill.content === "string" ? skill.content : null,
    is_builtin: false,
    can_toggle: false,
    can_edit: false,
    can_delete: false,
    display_name: skill.display_name ?? null,
  };
}

function buildUnifiedCatalogResource(
  skill: SkillCatalogItemPayload,
): ExternalToolResourcePayload | null {
  const toolType = readString(skill.tool_type) as ExternalToolType;
  const toolId = readString(skill.tool_id || skill.skill_id);
  if (!toolType || !toolId) {
    return null;
  }

  const isEnabled = skill.is_enabled ?? true;
  const isAvailable = skill.is_available ?? true;

  return {
    tool_type: toolType,
    tool_id: toolId,
    name:
      readString(skill.display_name) ||
      readString(skill.name) ||
      toolId,
    summary: normalizeSummary(skill.summary),
    entrypoint: readString(skill.entrypoint) || null,
    namespace: readString(skill.namespace) || null,
    resource_kind_label:
      readString(skill.resource_kind_label) ||
      (toolType === "skill"
        ? "Scan Core"
        : toolType === "prompt-builtin"
          ? "Builtin Prompt Skill"
          : "Custom Prompt Skill"),
    status_label: readString(skill.status_label) || inferEnabledLabel(isEnabled),
    is_enabled: isEnabled,
    is_available: isAvailable,
    detail_supported: skill.detail_supported ?? true,
    agent_key: skill.agent_key ?? null,
    agent_label: skill.agent_label ?? null,
    scope: skill.scope ?? null,
    capabilities: sanitizeCapabilities(skill.capabilities),
    content: typeof skill.content === "string" ? skill.content : null,
    is_builtin:
      typeof skill.tool_type === "string"
        ? skill.tool_type === "prompt-builtin"
        : undefined,
    can_toggle: toolType !== "skill",
    can_edit: toolType === "prompt-custom",
    can_delete: toolType === "prompt-custom",
    display_name: skill.display_name ?? null,
  };
}

function buildPromptBuiltinResource(
  builtinItem: PromptSkillListPayload["builtinItems"][number],
): ExternalToolResourcePayload {
  const agentLabel = resolvePromptAgentLabel({
    agentKey: builtinItem.agent_key,
    agentLabel: builtinItem.agent_label,
    displayName: builtinItem.display_name,
  });
  return {
    tool_type: "prompt-builtin",
    tool_id: builtinItem.agent_key,
    name: buildPromptSkillDisplayName({
      agentKey: builtinItem.agent_key,
      agentLabel: builtinItem.agent_label,
      displayName: builtinItem.display_name,
    }),
    summary: normalizeSummary(builtinItem.content),
    entrypoint: null,
    namespace: "prompt-skill",
    resource_kind_label: "Builtin Prompt Skill",
    status_label: inferEnabledLabel(builtinItem.is_active),
    is_enabled: builtinItem.is_active,
    is_available: true,
    detail_supported: true,
    agent_key: builtinItem.agent_key,
    agent_label: agentLabel,
    scope: null,
    capabilities: [],
    content: builtinItem.content,
    is_builtin: true,
    can_toggle: true,
    can_edit: false,
    can_delete: false,
    display_name: builtinItem.display_name ?? null,
  };
}

function buildPromptCustomResource(
  item: PromptSkillItemPayload,
): ExternalToolResourcePayload {
  const agentLabel =
    item.scope === "agent_specific"
      ? resolvePromptAgentLabel({
          agentKey: item.agent_key,
          agentLabel: item.agent_label,
          displayName: item.display_name,
        })
      : "全部智能体";

  return {
    tool_type: "prompt-custom",
    tool_id: item.id,
    name: buildPromptSkillDisplayName({
      name: item.name,
      agentKey: item.agent_key,
      agentLabel: item.agent_label,
      displayName: item.display_name,
    }),
    summary: normalizeSummary(item.content),
    entrypoint: null,
    namespace: "prompt-skill",
    resource_kind_label: "Custom Prompt Skill",
    status_label: inferEnabledLabel(item.is_active),
    is_enabled: item.is_active,
    is_available: true,
    detail_supported: true,
    agent_key: item.agent_key,
    agent_label: agentLabel,
    scope: item.scope,
    capabilities: [],
    content: item.content,
    is_builtin: false,
    can_toggle: true,
    can_edit: true,
    can_delete: true,
    display_name: item.display_name ?? null,
  };
}

export function buildPromptSkillDetail(
  resource: ExternalToolResourcePayload,
): PromptSkillDetailPayload {
  return {
    ...resource,
    tool_type:
      resource.tool_type === "prompt-builtin"
        ? "prompt-builtin"
        : "prompt-custom",
    content: readString(resource.content),
    is_builtin: resource.tool_type === "prompt-builtin",
    can_toggle: resource.can_toggle ?? true,
    can_edit: resource.can_edit ?? resource.tool_type === "prompt-custom",
    can_delete: resource.can_delete ?? resource.tool_type === "prompt-custom",
  };
}

export function buildExternalToolResources({
  skillCatalog,
  promptSkills,
}: {
  skillCatalog: SkillCatalogItemPayload[];
  promptSkills: PromptSkillListPayload | null;
}): ExternalToolResourcePayload[] {
  const resources = new Map<string, ExternalToolResourcePayload>();

  for (const skill of skillCatalog) {
    const normalized =
      buildUnifiedCatalogResource(skill) || buildLegacySkillResource(skill);
    if (!normalized) {
      continue;
    }
    resources.set(`${normalized.tool_type}:${normalized.tool_id}`, normalized);
  }

  for (const builtinItem of promptSkills?.builtinItems ?? []) {
    const normalized = buildPromptBuiltinResource(builtinItem);
    resources.set(`${normalized.tool_type}:${normalized.tool_id}`, normalized);
  }

  for (const item of promptSkills?.items ?? []) {
    const normalized = buildPromptCustomResource(item);
    resources.set(`${normalized.tool_type}:${normalized.tool_id}`, normalized);
  }

  return Array.from(resources.values()).sort((left, right) =>
    left.name.localeCompare(right.name, "zh-CN"),
  );
}

export function buildExternalToolRows({
  resources,
}: {
  resources: ExternalToolResourcePayload[];
}): ExternalToolRow[] {
  return resources.map((resource) => {
    const agentLabel =
      resource.tool_type === "skill"
        ? null
        : resource.agent_label ||
          (resource.scope === "global"
            ? "全部智能体"
            : resolvePromptAgentLabel({ agentKey: resource.agent_key }));
    const capabilityCandidates = sanitizeCapabilities(resource.capabilities);
    const fallbackCapabilities = capabilityCandidates.length
      ? capabilityCandidates
      : [
        resource.tool_type === "prompt-custom"
          ? `${scopeLabel(resource.scope || "global")} · ${agentLabel || "全部智能体"}`
          : resource.summary,
      ];

    return {
      ...resource,
      capabilities: fallbackCapabilities,
      agent_label: agentLabel,
      typeLabel: resource.resource_kind_label,
      availabilityLabel: inferAvailabilityLabel(resource.is_available),
    };
  });
}

export function buildExternalToolListState({
  rows,
  searchQuery,
  typeFilter,
  statusFilter,
  page,
  pageSize = EXTERNAL_TOOLS_PAGE_SIZE,
}: {
  rows: ExternalToolRow[];
  searchQuery: string;
  typeFilter: ExternalToolTypeFilter;
  statusFilter: ExternalToolStatusFilter;
  page: number;
  pageSize?: number;
}): ExternalToolListState {
  const normalizedQuery = String(searchQuery || "").trim().toLowerCase();
  const safePageSize = Math.max(1, Math.floor(pageSize) || EXTERNAL_TOOLS_PAGE_SIZE);
  const filteredRows = rows.filter((row) => {
    if (typeFilter !== "all" && row.tool_type !== typeFilter) {
      return false;
    }
    if (statusFilter === "enabled" && !row.is_enabled) {
      return false;
    }
    if (statusFilter === "disabled" && row.is_enabled) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    const searchable = [
      row.name,
      row.summary,
      row.typeLabel,
      row.status_label,
      row.availabilityLabel,
      row.agent_label || "",
      row.scope ? scopeLabel(row.scope) : "",
      ...row.capabilities,
    ]
      .join(" ")
      .toLowerCase();
    return searchable.includes(normalizedQuery);
  });
  const totalRows = filteredRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / safePageSize));
  const normalizedPage =
    totalRows === 0 ? 1 : Math.min(Math.max(1, Math.floor(page) || 1), totalPages);
  const startIndex = totalRows === 0 ? 0 : (normalizedPage - 1) * safePageSize;

  return {
    filteredRows,
    pageRows: filteredRows.slice(startIndex, startIndex + safePageSize),
    page: normalizedPage,
    pageSize: safePageSize,
    totalRows,
    totalPages,
    startIndex,
    searchQuery: String(searchQuery || ""),
  };
}
