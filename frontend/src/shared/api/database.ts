import { apiClient } from "./serverClient";
import { retryProjectReads } from "./retryProjectReads";
import type {
  Profile,
  Project,
  ProjectMember,
  CreateProjectForm,
  StaticScanOverviewResponse,
  ProjectDescriptionGenerateResponse,
  DashboardSnapshotResponse,
} from "../types/index";

type ConfigObject = Record<string, unknown>;

interface DefaultConfigPayload {
  llmConfig: ConfigObject;
  otherConfig: ConfigObject;
}

interface UserConfigPayload {
  llmConfig: ConfigObject;
  otherConfig: ConfigObject;
}

interface LlmQuickConfigSnapshotPayload {
  provider: string;
  model: string;
  baseUrl: string;
  apiKey: string;
}

interface AgentTaskPreflightPayload {
  ok: boolean;
  stage?: "llm_config" | "llm_test";
  message: string;
  reasonCode?:
    | "default_config"
    | "missing_fields"
    | "llm_test_failed"
    | "llm_test_timeout"
    | "llm_test_exception";
  missingFields?: Array<"llmModel" | "llmBaseUrl" | "llmApiKey">;
  effectiveConfig: LlmQuickConfigSnapshotPayload;
  savedConfig?: LlmQuickConfigSnapshotPayload | null;
}

export interface SkillCatalogItemPayload {
  skill_id: string;
  name: string;
  namespace: string;
  summary: string;
  category?: string;
  capabilities?: string[] | null;
  entrypoint: string;
  aliases: string[];
  has_scripts: boolean;
  has_bin: boolean;
  has_assets: boolean;
  display_name?: string;
  kind?: "tool" | "workflow" | "prompt";
  source?: "scan_core" | "registry_manifest" | "prompt_effective";
  selection_label?: string;
  runtime_ready?: boolean;
  reason?: string;
  load_mode?: "summary_only";
  deferred_tools?: string[];
  tool_type?: ExternalToolType;
  tool_id?: string;
  resource_kind_label?: string;
  status_label?: string;
  is_enabled?: boolean;
  is_available?: boolean;
  detail_supported?: boolean;
  agent_key?: string | null;
  agent_label?: string | null;
  scope?: PromptSkillScopePayload | null;
  content?: string | null;
}

interface SkillCatalogResponsePayload {
  enabled: boolean;
  total: number;
  limit: number;
  offset: number;
  supported_agent_keys?: string[];
  items: SkillCatalogItemPayload[];
  error?: string | null;
}

export type PromptSkillScopePayload = "global" | "agent_specific";

export interface PromptSkillItemPayload {
  id: string;
  name: string;
  content: string;
  scope: PromptSkillScopePayload;
  agent_key: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  agent_label?: string | null;
  display_name?: string | null;
}

export interface PromptSkillBuiltinItemPayload {
  agent_key: string;
  content: string;
  is_active: boolean;
  agent_label?: string | null;
  display_name?: string | null;
}

interface PromptSkillListResponsePayload {
  enabled: boolean;
  total: number;
  limit: number;
  offset: number;
  supported_agent_keys: string[];
  builtin_items: PromptSkillBuiltinItemPayload[];
  items: PromptSkillItemPayload[];
}

export interface PromptSkillListPayload {
  builtinItems: PromptSkillBuiltinItemPayload[];
  items: PromptSkillItemPayload[];
  supportedAgentKeys: string[];
}

export type ExternalToolType = "skill" | "prompt-builtin" | "prompt-custom";

export interface ExternalToolScanCoreDetailPayload {
  enabled: boolean;
  skill_id: string;
  name: string;
  namespace: string;
  summary: string;
  category: string;
  goal: string;
  task_list: string[];
  input_checklist: string[];
  example_input: string;
  pitfalls: string[];
  sample_prompts: string[];
  entrypoint: string;
  mirror_dir: string;
  source_root: string;
  source_dir: string;
  source_skill_md: string;
  aliases: string[];
  has_scripts: boolean;
  has_bin: boolean;
  has_assets: boolean;
  files_count: number;
  workflow_content: string | null;
  workflow_truncated: boolean | null;
  workflow_error: string | null;
  test_supported: boolean;
  test_mode: "single_skill_strict" | "structured_tool" | "disabled";
  test_reason: string | null;
  default_test_project_name: "libplist";
  tool_test_preset: Record<string, unknown> | null;
}

export interface ExternalToolResourcePayload {
  tool_type: ExternalToolType;
  tool_id: string;
  name: string;
  summary: string;
  entrypoint: string | null;
  namespace: string | null;
  resource_kind_label: string;
  status_label: string;
  is_enabled: boolean;
  is_available: boolean;
  detail_supported: boolean;
  agent_key: string | null;
  agent_label?: string | null;
  scope: PromptSkillScopePayload | null;
  capabilities?: string[] | null;
  content?: string | null;
  is_builtin?: boolean;
  can_toggle?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
  display_name?: string | null;
  scan_core_detail?: ExternalToolScanCoreDetailPayload | null;
}

export interface PromptSkillDetailPayload extends ExternalToolResourcePayload {
  tool_type: "prompt-builtin" | "prompt-custom";
  content: string;
  is_builtin: boolean;
  can_toggle: boolean;
  can_edit: boolean;
  can_delete: boolean;
}

export interface ExternalToolCatalogPayload {
  supportedAgentKeys: string[];
  items: ExternalToolResourcePayload[];
}

export interface PromptSkillCreatePayload {
  name: string;
  content: string;
  scope: PromptSkillScopePayload;
  agent_key?: string | null;
  is_active?: boolean;
}

export interface PromptSkillUpdatePayload {
  name?: string;
  content?: string;
  scope?: PromptSkillScopePayload;
  agent_key?: string | null;
  is_active?: boolean;
}

export interface ProjectTransferItem {
  source_project_id: string;
  name?: string | null;
  project_id?: string | null;
  reason?: string | null;
  existing_project_id?: string | null;
}

export interface ProjectImportResponse {
  imported_projects: ProjectTransferItem[];
  skipped_projects: ProjectTransferItem[];
  failed_projects: ProjectTransferItem[];
  warnings: string[];
}

export interface ProjectFileContentResponse {
  file_path: string;
  content: string;
  size: number;
  encoding: string;
  is_text: boolean;
  is_cached?: boolean;
  created_at?: string;
}

type ProjectFileContentResponseNormalizationOptions = {
  requestedFilePath?: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readString(
  value: unknown,
): string | null {
  if (typeof value !== "string") return null;
  return value;
}

function readFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    if (value === "true") return true;
    if (value === "false") return false;
  }
  return null;
}

export function normalizeProjectFileContentResponse(
  payload: unknown,
  options?: ProjectFileContentResponseNormalizationOptions,
): ProjectFileContentResponse | null {
  const record = asRecord(payload);
  if (!record) return null;

  const requestedFilePath = String(options?.requestedFilePath || "").trim();
  const filePath =
    readString(record.file_path) ??
    readString(record.filePath) ??
    requestedFilePath;
  const content =
    readString(record.content) ??
    readString(record.text) ??
    null;
  const encoding =
    readString(record.encoding) ??
    readString(record.charset) ??
    "utf-8";
  const isText = readBoolean(record.is_text ?? record.isText);
  const size =
    readFiniteNumber(record.size) ??
    readFiniteNumber(record.file_size) ??
    readFiniteNumber(record.byte_length) ??
    (typeof content === "string" ? content.length : null);

  if (!filePath || typeof content !== "string" || !encoding || size === null) {
    return null;
  }
  if (typeof isText !== "boolean") {
    return null;
  }

  const normalized: ProjectFileContentResponse = {
    file_path: filePath,
    content,
    size,
    encoding,
    is_text: isText,
  };

  const isCached = readBoolean(record.is_cached);
  if (isCached !== null) {
    normalized.is_cached = isCached;
  }
  const createdAt = readString(record.created_at);
  if (createdAt) {
    normalized.created_at = createdAt;
  }

  return normalized;
}

function encodeProjectFilePath(filePath: string): string {
  return String(filePath || "")
    .split("/")
    .filter((segment) => segment.length > 0)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

// Implement the same interface as the original localDatabase.ts but using backend API
export const api = {
  // ==================== Profile 相关方法 ====================

  async getProfilesById(_id: string): Promise<Profile | null> {
    try {
      const res = await apiClient.get('/users/me');
      return res.data;
    } catch (_error) {
      return null;
    }
  },

  async getProfilesCount(): Promise<number> {
    try {
      const res = await apiClient.get('/users/');
      return res.data.length;
    } catch (_error) {
      return 0;
    }
  },

  async createProfiles(profile: Partial<Profile>): Promise<Profile> {
    // 用户创建由后端统一处理
    return profile as Profile;
  },

  async updateProfile(id: string, updates: Partial<Profile>): Promise<Profile> {
    const res = await apiClient.patch(`/users/${id}`, updates);
    return res.data;
  },

  async getAllProfiles(): Promise<Profile[]> {
    const res = await apiClient.get('/users/');
    return res.data;
  },

  // ==================== Project 相关方法 ====================

  async getProjects(options?: {
    skip?: number;
    limit?: number;
    includeMetrics?: boolean;
  }): Promise<Project[]> {
    const params: Record<string, unknown> = {};
    if (typeof options?.skip === "number") {
      params.skip = options.skip;
    }
    if (typeof options?.limit === "number") {
      params.limit = options.limit;
    }
    if (options?.includeMetrics) {
      params.include_metrics = true;
    }
    const res = await retryProjectReads(() =>
      apiClient.get('/projects/', { params }),
    );
    return res.data;
  },

  async getProjectById(id: string): Promise<Project | null> {
    try {
      const res = await apiClient.get(`/projects/${id}`);
      return res.data;
    } catch (_error) {
      return null;
    }
  },

  async getProjectFiles(id: string, excludePatterns?: string[]): Promise<Array<{ path: string; size: number }>> {
    try {
      const params: Record<string, string> = {};
      if (excludePatterns && excludePatterns.length > 0) {
        params.exclude_patterns = JSON.stringify(excludePatterns);
      }
      const res = await apiClient.get(`/projects/${id}/files`, { params });
      return res.data;
    } catch (_error) {
      return [];
    }
  },

  async getProjectFileContent(
    id: string,
    filePath: string,
    options?: {
      encoding?: string;
      useCache?: boolean;
      stream?: boolean;
    },
  ): Promise<ProjectFileContentResponse> {
    const res = await retryProjectReads(() =>
      apiClient.get(`/projects/${id}/files/${encodeProjectFilePath(filePath)}`, {
        params: {
          encoding: options?.encoding ?? "utf-8",
          use_cache: options?.useCache ?? true,
          stream: options?.stream ?? false,
        },
      }),
    );
    const normalized = normalizeProjectFileContentResponse(res.data, {
      requestedFilePath: filePath,
    });
    if (normalized) {
      return normalized;
    }
    return {
      file_path: filePath,
      content: "",
      size: 0,
      encoding: "utf-8",
      is_text: false,
    };
  },

  async uploadProjectZip(id: string, file: File): Promise<{ message: string; original_filename: string; file_size: number }> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await apiClient.post(`/projects/${id}/zip`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
  },

  async generateProjectDescription(params: {
    file: File;
    project_name?: string;
  }): Promise<ProjectDescriptionGenerateResponse> {
    const formData = new FormData();
    formData.append("file", params.file);
    if (params.project_name?.trim()) {
      formData.append("project_name", params.project_name.trim());
    }
    const res = await apiClient.post(
      "/projects/description/generate",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      },
    );
    return res.data;
  },

  async generateStoredProjectDescription(
    projectId: string,
  ): Promise<ProjectDescriptionGenerateResponse> {
    const res = await apiClient.post(
      `/projects/${projectId}/description/generate`,
    );
    return res.data;
  },

  async createProject(project: CreateProjectForm): Promise<Project> {
    const res = await apiClient.post('/projects/', {
      name: project.name,
      description: project.description,
      source_type: project.source_type || 'zip',
      repository_url: project.repository_url,
      repository_type: project.repository_type,
      default_branch: project.default_branch,
      programming_languages: project.programming_languages,
    });
    return res.data;
  },

  async createProjectWithZip(
    project: CreateProjectForm,
    file: File,
  ): Promise<Project> {
    const formData = new FormData();
    formData.append("name", project.name);
    formData.append("file", file);
    if (project.description?.trim()) {
      formData.append("description", project.description.trim());
    }
    if (project.default_branch?.trim()) {
      formData.append("default_branch", project.default_branch.trim());
    }
    for (const language of project.programming_languages || []) {
      formData.append("programming_languages", language);
    }

    const res = await apiClient.post("/projects/create-with-zip", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  async updateProject(id: string, updates: Partial<CreateProjectForm>): Promise<Project> {
    const res = await apiClient.put(`/projects/${id}`, updates);
    return res.data;
  },

  async deleteProject(id: string): Promise<void> {
    await apiClient.delete(`/projects/${id}`);
  },

  async downloadProjectArchive(
    projectId: string,
  ): Promise<{ blob: Blob; filename: string }> {
    const res = await apiClient.get(`/projects/${projectId}/archive`, {
      responseType: "blob",
    });

    const disposition = String(res.headers["content-disposition"] || "");
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const basicMatch = disposition.match(/filename="?([^";]+)"?/i);
    const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
    const filename = decodedUtf8 || basicMatch?.[1] || `project-${projectId}.zip`;

    return {
      blob: res.data,
      filename,
    };
  },

  async exportProjectBundle(params?: {
    projectIds?: string[];
    includeArchives?: boolean;
  }): Promise<{ blob: Blob; filename: string }> {
    const res = await apiClient.post(
      "/projects/export",
      {
        project_ids: params?.projectIds?.length ? params.projectIds : null,
        include_archives: params?.includeArchives ?? true,
      },
      {
        responseType: "blob",
      },
    );

    const disposition = String(res.headers["content-disposition"] || "");
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const basicMatch = disposition.match(/filename="?([^";]+)"?/i);
    const decodedUtf8 = utf8Match?.[1] ? decodeURIComponent(utf8Match[1]) : null;
    const filename = decodedUtf8 || basicMatch?.[1] || "deepaudit-project-export.zip";

    return {
      blob: res.data,
      filename,
    };
  },

  async importProjectBundle(file: File): Promise<ProjectImportResponse> {
    const formData = new FormData();
    formData.append("bundle", file);
    const res = await apiClient.post("/projects/import", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  // ==================== ProjectMember 相关方法 ====================

  async getProjectMembers(projectId: string): Promise<ProjectMember[]> {
    try {
      const res = await apiClient.get(`/projects/${projectId}/members`);
      return res.data;
    } catch (_error) {
      return [];
    }
  },

  async addProjectMember(projectId: string, userId: string, role: string = 'member'): Promise<ProjectMember> {
    const res = await apiClient.post(`/projects/${projectId}/members`, {
      user_id: userId,
      role: role
    });
    return res.data;
  },

  async removeProjectMember(projectId: string, memberId: string): Promise<void> {
    await apiClient.delete(`/projects/${projectId}/members/${memberId}`);
  },

  // ==================== 统计相关方法 ====================

  async getProjectStats(): Promise<{
    total_projects: number;
    active_projects: number;
    total_tasks: number;
    completed_tasks: number;
    interrupted_tasks: number;
    running_tasks: number;
    failed_tasks: number;
    total_issues: number;
    resolved_issues: number;
    avg_quality_score: number;
  }> {
    try {
      const res = await apiClient.get('/projects/stats');
      return res.data;
    } catch (_error) {
      return {
        total_projects: 0,
        active_projects: 0,
        total_tasks: 0,
        completed_tasks: 0,
        interrupted_tasks: 0,
        running_tasks: 0,
        failed_tasks: 0,
        total_issues: 0,
        resolved_issues: 0,
        avg_quality_score: 0
      };
    }
  },

  async getDashboardSnapshot(
    topN = 10,
    rangeDays: 7 | 14 | 30 = 14,
  ): Promise<DashboardSnapshotResponse> {
    const safeTopN = Number.isFinite(topN) ? Math.min(Math.max(Math.floor(topN), 1), 50) : 10;
    const safeRangeDays = rangeDays === 7 || rangeDays === 30 ? rangeDays : 14;
    const res = await apiClient.get('/projects/dashboard-snapshot', {
      params: { top_n: safeTopN, range_days: safeRangeDays },
    });
    return res.data;
  },

  async getStaticScanOverview(params?: {
    page?: number;
    page_size?: number;
    keyword?: string;
  }): Promise<StaticScanOverviewResponse> {
    try {
      const res = await apiClient.get('/projects/static-scan-overview', {
        params: {
          page: params?.page,
          page_size: params?.page_size,
          keyword: params?.keyword,
        },
      });
      return res.data;
    } catch (_error) {
      return {
        items: [],
        total: 0,
        page: params?.page || 1,
        page_size: params?.page_size || 6,
        total_pages: 1,
      };
    }
  },

  // ==================== 用户配置相关方法 ====================

  async getDefaultConfig(): Promise<DefaultConfigPayload | null> {
    try {
      const res = await apiClient.get('/system-config/defaults');
      return res.data;
    } catch (error) {
      console.error('Failed to get default config:', error);
      return null;
    }
  },

  async getUserConfig(): Promise<UserConfigPayload | null> {
    try {
      const res = await apiClient.get('/system-config');
      console.log('[API] getUserConfig 成功:', {
        hasLlmConfig: !!res.data?.llmConfig,
        hasApiKey: !!res.data?.llmConfig?.llmApiKey,
        provider: res.data?.llmConfig?.llmProvider,
      });
      return res.data;
    } catch (error: unknown) {
      const apiError = error as {
        response?: { status?: number };
        message?: string;
      };
      console.error('[API] getUserConfig 失败:', apiError?.response?.status, apiError?.message);
      return null;
    }
  },

  async getSkillCatalog(params?: {
    q?: string;
    namespace?: string;
    limit?: number;
    offset?: number;
  }): Promise<SkillCatalogItemPayload[]> {
    try {
      const res = await apiClient.get<SkillCatalogResponsePayload>("/skills/catalog", {
        params: {
          q: params?.q ?? "",
          namespace: params?.namespace,
          limit: params?.limit ?? 200,
          offset: params?.offset ?? 0,
        },
      });
      return Array.isArray(res.data?.items) ? res.data.items : [];
    } catch (error) {
      console.error("[API] getSkillCatalog 失败:", error);
      return [];
    }
  },

  async getPromptSkills(params?: {
    scope?: PromptSkillScopePayload;
    agent_key?: string;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<PromptSkillListPayload> {
    const res = await apiClient.get<PromptSkillListResponsePayload>("/skills/prompt-skills", {
      params: {
        scope: params?.scope,
        agent_key: params?.agent_key,
        is_active: params?.is_active,
        limit: params?.limit ?? 500,
        offset: params?.offset ?? 0,
      },
    });
    return {
      builtinItems: Array.isArray(res.data?.builtin_items) ? res.data.builtin_items : [],
      items: Array.isArray(res.data?.items) ? res.data.items : [],
      supportedAgentKeys: Array.isArray(res.data?.supported_agent_keys)
        ? res.data.supported_agent_keys
        : [],
    };
  },

  async getExternalToolCatalog(params?: {
    q?: string;
    namespace?: string;
    limit?: number;
    offset?: number;
  }): Promise<ExternalToolCatalogPayload> {
    const res = await apiClient.get<SkillCatalogResponsePayload>("/skills/catalog", {
      params: {
        q: params?.q ?? "",
        namespace: params?.namespace,
        resource_mode: "external_tools",
        limit: params?.limit ?? 200,
        offset: params?.offset ?? 0,
      },
    });

    return {
      supportedAgentKeys: Array.isArray(res.data?.supported_agent_keys)
        ? res.data.supported_agent_keys
        : [],
      items: Array.isArray(res.data?.items)
        ? (res.data.items as ExternalToolResourcePayload[])
        : [],
    };
  },

  async getExternalToolResourceDetail(
    toolType: ExternalToolType,
    toolId: string,
  ): Promise<ExternalToolResourcePayload> {
    const res = await apiClient.get<ExternalToolResourcePayload>(
      `/skills/resources/${encodeURIComponent(toolType)}/${encodeURIComponent(toolId)}`,
    );
    return res.data;
  },

  async createPromptSkill(payload: PromptSkillCreatePayload): Promise<PromptSkillItemPayload> {
    const res = await apiClient.post<PromptSkillItemPayload>("/skills/prompt-skills", payload);
    return res.data;
  },

  async updatePromptSkill(
    promptSkillId: string,
    payload: PromptSkillUpdatePayload,
  ): Promise<PromptSkillItemPayload> {
    const res = await apiClient.put<PromptSkillItemPayload>(
      `/skills/prompt-skills/${encodeURIComponent(promptSkillId)}`,
      payload,
    );
    return res.data;
  },

  async updateBuiltinPromptSkill(
    agentKey: string,
    payload: { is_active: boolean },
  ): Promise<PromptSkillBuiltinItemPayload> {
    const res = await apiClient.put<PromptSkillBuiltinItemPayload>(
      `/skills/prompt-skills/builtin/${encodeURIComponent(agentKey)}`,
      payload,
    );
    return res.data;
  },

  async deletePromptSkill(promptSkillId: string): Promise<void> {
    await apiClient.delete(`/skills/prompt-skills/${encodeURIComponent(promptSkillId)}`);
  },

  async updateUserConfig(config: {
    llmConfig?: ConfigObject;
    otherConfig?: ConfigObject;
  }): Promise<UserConfigPayload> {
    const res = await apiClient.put('/system-config', config);
    return res.data;
  },

  async deleteUserConfig(): Promise<void> {
    await apiClient.delete('/system-config');
  },

  async testLLMConnection(params: {
    provider: string;
    apiKey: string;
    model?: string;
    baseUrl?: string;
    customHeaders?: string;
  }): Promise<{
    success: boolean;
    message: string;
    model?: string;
    response?: string;
  }> {
    const res = await apiClient.post('/system-config/test-llm', params);
    return res.data;
  },

  async runAgentTaskPreflight(): Promise<AgentTaskPreflightPayload> {
    const res = await apiClient.post('/system-config/agent-preflight');
    return res.data;
  },

  async getLLMProviders(): Promise<{
    providers: Array<{
      id: string;
      name: string;
      description: string;
      defaultModel: string;
      models: string[];
      defaultBaseUrl: string;
      requiresApiKey: boolean;
      supportsModelFetch: boolean;
      fetchStyle: "openai_compatible" | "anthropic" | "azure_openai" | "native_static";
      exampleBaseUrls?: string[];
      supportsCustomHeaders?: boolean;
    }>;
  }> {
    const res = await apiClient.get('/system-config/llm-providers');
    return res.data;
  },

  async fetchLLMModels(params: {
    provider: string;
    apiKey: string;
    baseUrl?: string;
    customHeaders?: string;
  }): Promise<{
    success: boolean;
    message: string;
    provider: string;
    resolvedProvider: string;
    models: string[];
    defaultModel: string;
    source: "online" | "fallback_static";
    baseUrlUsed?: string;
    modelMetadata?: Record<
      string,
      {
        contextWindow?: number | null;
        maxOutputTokens?: number | null;
        recommendedMaxTokens?: number | null;
        source?: string;
      }
    >;
    tokenRecommendationSource?: string;
  }> {
    const res = await apiClient.post('/system-config/fetch-llm-models', params);
    return res.data;
  }
};
