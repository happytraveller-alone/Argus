import type {
  PromptSkillCreatePayload,
  PromptSkillDetailPayload,
  PromptSkillItemPayload,
  PromptSkillScopePayload,
  PromptSkillUpdatePayload,
} from "@/shared/api/database";

export const PROMPT_AGENT_LABEL_FALLBACKS: Record<string, string> = {
  recon: "Recon Agent",
  business_logic_recon: "Business Logic Recon Agent",
  analysis: "Analysis Agent",
  business_logic_analysis: "Business Logic Analysis Agent",
  verification: "Verification Agent",
};

export type PromptSkillFormState = {
  name: string;
  content: string;
  scope: PromptSkillScopePayload;
  agent_key: string;
  is_active: boolean;
};

export const DEFAULT_PROMPT_SKILL_FORM: PromptSkillFormState = {
  name: "",
  content: "",
  scope: "global",
  agent_key: "",
  is_active: true,
};

export function extractPromptSkillErrorMessage(error: unknown): string {
  const maybeAxios = error as {
    response?: {
      data?: {
        detail?: string;
      };
    };
    message?: string;
  };
  const detail = maybeAxios?.response?.data?.detail;
  if (detail && String(detail).trim()) {
    return String(detail);
  }
  return String(maybeAxios?.message || "请求失败");
}

export function scopeLabel(scope: PromptSkillScopePayload): string {
  return scope === "global" ? "通用" : "智能体专属";
}

export function resolvePromptAgentLabel({
  agentKey,
  agentLabel,
  displayName,
}: {
  agentKey?: string | null;
  agentLabel?: string | null;
  displayName?: string | null;
}): string {
  const normalizedDisplayName = String(displayName || "").trim();
  if (normalizedDisplayName) {
    return normalizedDisplayName;
  }
  const normalizedAgentLabel = String(agentLabel || "").trim();
  if (normalizedAgentLabel) {
    return normalizedAgentLabel;
  }
  const normalizedAgentKey = String(agentKey || "").trim();
  if (normalizedAgentKey) {
    return PROMPT_AGENT_LABEL_FALLBACKS[normalizedAgentKey] || normalizedAgentKey;
  }
  return "全部智能体";
}

export function buildPromptSkillDisplayName({
  name,
  agentKey,
  agentLabel,
  displayName,
}: {
  name?: string | null;
  agentKey?: string | null;
  agentLabel?: string | null;
  displayName?: string | null;
}) {
  const normalizedName = String(name || "").trim();
  if (normalizedName) {
    return normalizedName;
  }
  return `${resolvePromptAgentLabel({ agentKey, agentLabel, displayName })} Prompt Skill`;
}

export function buildPromptSkillFormState(
  detail?: Pick<PromptSkillDetailPayload, "name" | "content" | "scope" | "agent_key" | "is_enabled"> | null,
): PromptSkillFormState {
  if (!detail) {
    return DEFAULT_PROMPT_SKILL_FORM;
  }
  return {
    name: detail.name,
    content: detail.content,
    scope: detail.scope ?? "global",
    agent_key: detail.agent_key || "",
    is_active: detail.is_enabled,
  };
}

export function normalizePromptSkillCreatePayload(
  form: PromptSkillFormState,
): PromptSkillCreatePayload {
  return {
    name: form.name.trim(),
    content: form.content.trim(),
    scope: form.scope,
    agent_key: form.scope === "agent_specific" ? form.agent_key || null : null,
    is_active: form.is_active,
  };
}

export function normalizePromptSkillUpdatePayload(
  form: PromptSkillFormState,
): PromptSkillUpdatePayload {
  return {
    name: form.name.trim(),
    content: form.content.trim(),
    scope: form.scope,
    agent_key: form.scope === "agent_specific" ? form.agent_key || null : null,
    is_active: form.is_active,
  };
}

export function buildPromptSkillAgentOptions({
  supportedAgentKeys,
  builtinAgentKeys = [],
  customAgentKeys = [],
}: {
  supportedAgentKeys?: string[];
  builtinAgentKeys?: string[];
  customAgentKeys?: Array<string | null | undefined>;
}) {
  const keys = new Set<string>();
  for (const key of supportedAgentKeys ?? []) {
    if (String(key || "").trim()) {
      keys.add(String(key).trim());
    }
  }
  for (const key of builtinAgentKeys) {
    if (String(key || "").trim()) {
      keys.add(String(key).trim());
    }
  }
  for (const key of customAgentKeys) {
    if (String(key || "").trim()) {
      keys.add(String(key).trim());
    }
  }
  if (keys.size === 0) {
    Object.keys(PROMPT_AGENT_LABEL_FALLBACKS).forEach((key) => keys.add(key));
  }
  return Array.from(keys)
    .sort()
    .map((key) => ({
      key,
      label: resolvePromptAgentLabel({ agentKey: key }),
    }));
}

export function findPromptSkillItemById(
  items: PromptSkillItemPayload[],
  promptSkillId: string,
) {
  return items.find((item) => item.id === promptSkillId) ?? null;
}
