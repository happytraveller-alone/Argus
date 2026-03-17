import { apiClient } from "./serverClient";
import { retryProjectReads } from "./retryProjectReads";
import type {
  Profile,
  Project,
  ProjectMember,
  AuditTask,
  AuditIssue,
  InstantAnalysis,
  CreateProjectForm,
  CreateAuditTaskForm,
  InstantAnalysisForm,
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
  id: string;
  user_id: string;
  llmConfig: ConfigObject;
  otherConfig: ConfigObject;
  created_at: string;
  updated_at?: string;
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
  }): Promise<Project[]> {
    const params: Record<string, unknown> = {};
    if (typeof options?.skip === "number") {
      params.skip = options.skip;
    }
    if (typeof options?.limit === "number") {
      params.limit = options.limit;
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
    return res.data;
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

  async createProject(project: CreateProjectForm & { owner_id?: string }): Promise<Project> {
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
    project: CreateProjectForm & { owner_id?: string },
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

  // ==================== AuditTask 相关方法 ====================

  async getAuditTasks(projectId?: string): Promise<AuditTask[]> {
    const params = projectId ? { project_id: projectId } : {};
    const res = await apiClient.get('/tasks/', { params });
    return res.data;
  },

  async getAuditTaskById(id: string): Promise<AuditTask | null> {
    try {
      const res = await apiClient.get(`/tasks/${id}`);
      return res.data;
    } catch (_error) {
      return null;
    }
  },

  async createAuditTask(task: CreateAuditTaskForm & { created_by?: string }): Promise<AuditTask> {
    // Trigger scan on the project
    const scanRequest = {
      file_paths: task.scan_config?.file_paths,
      full_scan: !task.scan_config?.file_paths || task.scan_config.file_paths.length === 0,
      exclude_patterns: task.exclude_patterns || [],
    };
    const res = await apiClient.post(`/projects/${task.project_id}/scan`, scanRequest);
    // Fetch the created task
    const taskRes = await apiClient.get(`/tasks/${res.data.task_id}`);
    return taskRes.data;
  },

  async updateAuditTask(id: string, _updates: Partial<AuditTask>): Promise<AuditTask> {
    // Tasks are updated by backend workers, not frontend
    const current = await this.getAuditTaskById(id);
    return current || ({} as AuditTask);
  },

  async cancelAuditTask(id: string): Promise<void> {
    await apiClient.post(`/tasks/${id}/cancel`);
  },

  // ==================== AuditIssue 相关方法 ====================

  async getAuditIssues(taskId: string): Promise<AuditIssue[]> {
    const res = await apiClient.get(`/tasks/${taskId}/issues`);
    return res.data;
  },

  async createAuditIssue(_issue: Omit<AuditIssue, 'id' | 'created_at' | 'task' | 'resolver'>): Promise<AuditIssue> {
    // Issues are created by backend workers during scan
    return {} as AuditIssue;
  },

  async updateAuditIssue(taskId: string, issueId: string, updates: Partial<AuditIssue>): Promise<AuditIssue> {
    const res = await apiClient.patch(`/tasks/${taskId}/issues/${issueId}`, updates);
    return res.data;
  },

  // ==================== InstantAnalysis 相关方法 ====================

  async getInstantAnalyses(_userId?: string): Promise<InstantAnalysis[]> {
    try {
      const res = await apiClient.get('/scan/instant/history');
      return res.data;
    } catch (_error) {
      return [];
    }
  },

  async createInstantAnalysis(_analysis: InstantAnalysisForm & {
    user_id: string;
    analysis_result?: string;
    issues_count?: number;
    quality_score?: number;
    analysis_time?: number;
  }): Promise<InstantAnalysis> {
    // Instant analysis is handled via /scan/instant endpoint
    // This method is kept for compatibility
    return {} as InstantAnalysis;
  },

  async deleteInstantAnalysis(analysisId: string): Promise<void> {
    await apiClient.delete(`/scan/instant/history/${analysisId}`);
  },

  async deleteAllInstantAnalyses(): Promise<void> {
    await apiClient.delete('/scan/instant/history');
  },

  // ==================== 报告导出方法 ====================

  async exportTaskReportPDF(taskId: string): Promise<Blob> {
    const res = await apiClient.get(`/tasks/${taskId}/report/pdf`, {
      responseType: 'blob'
    });
    return res.data;
  },

  async exportInstantReportPDF(analysisId: string): Promise<Blob> {
    const res = await apiClient.get(`/scan/instant/history/${analysisId}/report/pdf`, {
      responseType: 'blob'
    });
    return res.data;
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
      const res = await apiClient.get('/config/defaults');
      return res.data;
    } catch (error) {
      console.error('Failed to get default config:', error);
      return null;
    }
  },

  async getUserConfig(): Promise<UserConfigPayload | null> {
    try {
      const res = await apiClient.get('/config/me');
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

  async updateUserConfig(config: {
    llmConfig?: ConfigObject;
    otherConfig?: ConfigObject;
  }): Promise<UserConfigPayload> {
    const res = await apiClient.put('/config/me', config);
    return res.data;
  },

  async deleteUserConfig(): Promise<void> {
    await apiClient.delete('/config/me');
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
    const res = await apiClient.post('/config/test-llm', params);
    return res.data;
  },

  async runAgentTaskPreflight(): Promise<AgentTaskPreflightPayload> {
    const res = await apiClient.post('/config/agent-task-preflight');
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
    const res = await apiClient.get('/config/llm-providers');
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
    const res = await apiClient.post('/config/fetch-llm-models', params);
    return res.data;
  }
};
