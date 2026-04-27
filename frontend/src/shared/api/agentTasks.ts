/**
 * Agent Tasks API
 * Agent 扫描任务相关的 API 调用
 */

import { apiClient } from "./serverClient";
import { buildApiUrl } from "./apiBase";
import {
  buildReportDownloadBaseName,
  resolveFilenameFromDisposition,
} from "../utils/reportExportFilename";

// ============ Types ============

export interface AgentTask {
  id: string;
  project_id: string;
  name: string | null;
  description: string | null;
  task_type: string;
  status: string;
  current_phase: string | null;
  current_step: string | null;

  // 统计
  total_files: number;
  indexed_files: number;
  analyzed_files: number;
  files_with_findings: number;  // 有漏洞发现的文件数
  total_chunks: number;
  findings_count: number;
  verified_count: number;
  false_positive_count: number;

  // Agent 统计
  total_iterations: number;
  tool_calls_count: number;
  tokens_used: number;

  // 严重程度统计
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  verified_critical_count?: number;
  verified_high_count?: number;
  verified_medium_count?: number;
  verified_low_count?: number;
  defect_summary?: {
    scope: "all_findings";
    total_count: number;
    severity_counts: {
      critical: number;
      high: number;
      medium: number;
      low: number;
      info: number;
    };
    status_counts: {
      pending: number;
      verified: number;
      false_positive: number;
    };
  } | null;

  // 评分
  quality_score: number;
  security_score: number | null;

  // 时间
  created_at: string;
  started_at: string | null;
  completed_at: string | null;

  // 进度
  progress_percentage: number;

  // 配置
  audit_scope: AgentAuditScope | null;
  target_vulnerabilities: string[] | null;
  verification_level: string | null;
  tool_evidence_protocol?: "legacy" | "native_v1" | null;
  exclude_patterns: string[] | null;
  target_files: string[] | null;

  // 错误信息 / AgentFlow 报告快照
  error_message: string | null;
  report?: string | null;
  runtime_status?: string | null;
  run_id?: string | null;
  topology_version?: string | null;
  artifact_index?: AgentArtifactRef[] | null;
}

export interface TriggerFlowNode {
  index: number;
  file_path: string;
  function: string;
  start_line: number;
  end_line: number;
  code: string;
  code_truncated?: boolean;
}

export interface TriggerFlow {
  version: number;
  path_found?: boolean;
  path_score?: number;
  engine?: string;
  call_chain: string[];
  control_conditions?: string[];
  nodes: TriggerFlowNode[];
  generated_at?: string;
}

export interface PocTriggerChainNode {
  index: number;
  file_path: string;
  line: number;
  function: string;
  code: string;
  context?: string;
  context_start_line?: number;
  context_end_line?: number;
}

export interface PocTriggerChain {
  version: number;
  engine: "llm_dataflow_estimate" | string;
  source: {
    file_path: string;
    line: number;
    function: string;
    code: string;
  };
  sink: {
    file_path: string;
    line: number;
    function: string;
    code: string;
  };
  nodes: PocTriggerChainNode[];
  generated_at?: string | null;
}

export interface AgentFinding {
  id: string;
  task_id: string;
  vulnerability_type: string;
  severity: string;
  title: string;
  display_title?: string | null;
  description: string | null;
  description_markdown?: string | null;

  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  resolved_file_path?: string | null;
  resolved_line_start?: number | null;
  code_snippet: string | null;
  code_context: string | null;
  cwe_id?: string | null;
  cwe_name?: string | null;
  context_start_line: number | null;
  context_end_line: number | null;

  status: string;
  is_verified: boolean;
  verdict?: string | null;
  reachability: string | null;
  authenticity: string | null;
  verification_evidence: string | null;
  verification_todo_id?: string | null;
  verification_fingerprint?: string | null;
  reachability_file?: string | null;
  reachability_function?: string | null;
  reachability_function_start_line?: number | null;
  reachability_function_end_line?: number | null;
  flow_path_score?: number | null;
  flow_call_chain?: string[] | null;
  function_trigger_flow?: string[] | null;
  flow_control_conditions?: string[] | null;
  logic_authz_evidence?: string[] | null;
  has_poc: boolean;
  poc_code: string | null;
  trigger_flow?: TriggerFlow | null;
  poc_trigger_chain?: PocTriggerChain | null;

  suggestion: string | null;
  fix_code: string | null;
  report?: string | null;
  ai_explanation: string | null;
  ai_confidence: number | null;
  confidence?: number | null;
  impact?: string | null;
  remediation?: string | null;
  verification?: string | null;
  source_node_id?: string | null;
  source_node_name?: string | null;
  source_role?: string | null;
  artifact_refs?: AgentArtifactRef[] | null;
  data_flow?: unknown;
  risk_lifecycle?: unknown;
  confidence_history?: unknown;

  created_at: string;
}

export interface AgentEvent {
  id: string;
  task_id: string;
  event_type: string;
  phase: string | null;
  message: string | null;
  tool_name: string | null;
  tool_input?: Record<string, unknown>;
  tool_output?: Record<string, unknown>;
  tool_duration_ms: number | null;
  finding_id: string | null;
  tokens_used?: number;
  metadata?: Record<string, unknown>;
  sequence: number;
  timestamp: string;
}

export interface AgentArtifactRef {
  path: string;
  type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  producer_node?: string | null;
  created_at?: string | null;
}

export interface CreateAgentTaskRequest {
  project_id: string;
  name?: string;
  description?: string;
  audit_scope?: AgentAuditScope;
  timeout_seconds?: number;
  use_prompt_skills?: boolean;
}

type LegacyAgentTaskCreateInput = CreateAgentTaskRequest & Partial<{
  target_vulnerabilities: unknown;
  verification_level: unknown;
  exclude_patterns: unknown;
  target_files: unknown;
  max_iterations: unknown;
  token_budget: unknown;
}>;

export function buildAgentTaskCreatePayload(
  data: LegacyAgentTaskCreateInput,
): CreateAgentTaskRequest {
  const payload: CreateAgentTaskRequest = {
    project_id: data.project_id,
  };
  if (typeof data.name === "string" && data.name.trim()) {
    payload.name = data.name;
  }
  if (typeof data.description === "string" && data.description.trim()) {
    payload.description = data.description;
  }
  if (data.audit_scope && typeof data.audit_scope === "object") {
    payload.audit_scope = data.audit_scope;
  }
  if (typeof data.timeout_seconds === "number" && Number.isFinite(data.timeout_seconds)) {
    payload.timeout_seconds = data.timeout_seconds;
  }
  if (typeof data.use_prompt_skills === "boolean") {
    payload.use_prompt_skills = data.use_prompt_skills;
  }
  return payload;
}

export interface AgentAuditScope extends Record<string, unknown> {
}

export interface AgentTaskSummary {
  task_id: string;
  status: string;
  progress_percentage: number;
  security_score: number;
  quality_score: number;
  statistics: {
    total_files: number;
    indexed_files: number;
    analyzed_files: number;
    files_with_findings: number;
    total_chunks: number;
    findings_count: number;
    verified_count: number;
    false_positive_count: number;
  };
  severity_distribution: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  vulnerability_types: Record<string, { total: number; verified: number }>;
  duration_seconds: number | null;
}

export interface AgentFindingStatusUpdateResponse {
  message: string;
  finding_id: string;
  status: string;
}

// ============ API Functions ============

/**
 * 创建 Agent 扫描任务
 */
export async function createAgentTask(data: LegacyAgentTaskCreateInput): Promise<AgentTask> {
  const response = await apiClient.post("/agent-tasks/", buildAgentTaskCreatePayload(data));
  return response.data;
}

/**
 * 获取 Agent 任务列表
 */
export async function getAgentTasks(params?: {
  project_id?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<AgentTask[]> {
  const response = await apiClient.get("/agent-tasks/", { params });
  return response.data;
}

/**
 * 获取 Agent 任务详情
 */
export async function getAgentTask(taskId: string): Promise<AgentTask> {
  const response = await apiClient.get(`/agent-tasks/${taskId}`);
  return response.data;
}

/**
 * 启动 Agent 任务
 */
export async function startAgentTask(taskId: string): Promise<{ message: string; task_id: string }> {
  const response = await apiClient.post(`/agent-tasks/${taskId}/start`);
  return response.data;
}

/**
 * 取消 Agent 任务
 */
export async function cancelAgentTask(taskId: string): Promise<{ message: string; task_id: string }> {
  const response = await apiClient.post(`/agent-tasks/${taskId}/cancel`);
  return response.data;
}

/**
 * 获取 Agent 任务事件列表
 */
export async function getAgentEvents(
  taskId: string,
  params?: { after_sequence?: number; limit?: number }
): Promise<AgentEvent[]> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/events/list`, { params });
  return response.data;
}

/**
 * 获取 Agent 任务发现列表
 */
export async function getAgentFindings(
  taskId: string,
  params?: {
    severity?: string;
    vulnerability_type?: string;
    is_verified?: boolean;
    include_false_positive?: boolean;
    skip?: number;
    limit?: number;
  }
): Promise<AgentFinding[]> {
  const normalizedParams =
    params && typeof params.is_verified === "boolean"
      ? { ...params, verified_only: params.is_verified }
      : params;
  const response = await apiClient.get(`/agent-tasks/${taskId}/findings`, { params: normalizedParams });
  return response.data;
}

/**
 * 获取单个发现详情
 */
export async function getAgentFinding(
  taskId: string,
  findingId: string,
  params?: {
    include_false_positive?: boolean;
  },
): Promise<AgentFinding> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/findings/${findingId}`, {
    params,
  });
  return response.data;
}

/**
 * 更新发现状态
 */
export async function updateAgentFinding(
  taskId: string,
  findingId: string,
  data: { status?: string }
): Promise<AgentFinding> {
  const response = await apiClient.patch(`/agent-tasks/${taskId}/findings/${findingId}`, data);
  return response.data;
}

/**
 * 更新发现状态
 */
export async function updateAgentFindingStatus(
  taskId: string,
  findingId: string,
  status: string,
): Promise<AgentFindingStatusUpdateResponse> {
  const response = await apiClient.patch(
    `/agent-tasks/${taskId}/findings/${findingId}/status`,
    undefined,
    {
      params: {
        status,
      },
    },
  );
  return response.data;
}

/**
 * 获取任务摘要
 */
export async function getAgentTaskSummary(taskId: string): Promise<AgentTaskSummary> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/summary`);
  return response.data;
}

/**
 * 创建 SSE 事件源
 */
export function createAgentEventSource(taskId: string, afterSequence = 0): EventSource {
  const url = buildAgentTaskEventsUrl(taskId, afterSequence);

  // 注意：EventSource 不支持自定义 headers，需要通过 URL 参数或 cookie 传递认证
  // 如果需要认证，可以考虑使用 fetch + ReadableStream 替代
  return new EventSource(url, { withCredentials: true });
}

export function buildAgentTaskEventsUrl(taskId: string, afterSequence = 0): string {
  return `${buildApiUrl(`/agent-tasks/${taskId}/events`)}?after_sequence=${afterSequence}`;
}

/**
 * 使用 fetch 流式获取事件（支持自定义 headers）
 */
export async function* streamAgentEvents(
  taskId: string,
  afterSequence = 0,
  signal?: AbortSignal
): AsyncGenerator<AgentEvent, void, unknown> {
  const url = buildAgentTaskEventsUrl(taskId, afterSequence);

  const response = await fetch(url, {
    headers: {
      Accept: "text/event-stream",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Failed to connect to event stream: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("No response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // 解析 SSE 格式
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          try {
            const event = JSON.parse(data) as AgentEvent;
            yield event;
          } catch {
            // 忽略解析错误
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ============ Agent Tree Types ============

export interface AgentTreeNode {
  id: string;
  agent_id: string;
  agent_name: string;
  agent_type: string;
  parent_agent_id: string | null;
  depth: number;
  task_description: string | null;
  status: "created" | "running" | "completed" | "failed" | "waiting" | "cancelled" | string;
  role?: string | null;
  heartbeat_at?: string | null;
  result_summary: string | null;
  findings_count: number;
  verified_findings_count: number;
  iterations: number;
  tokens_used: number;
  tool_calls: number;
  duration_ms: number | null;
  checkpoint_id?: string | null;
  artifact_refs?: AgentArtifactRef[] | null;
  metadata?: Record<string, unknown> | null;
  children: AgentTreeNode[];
}

export interface AgentTreeResponse {
  task_id: string;
  root_agent_id: string | null;
  total_agents: number;
  running_agents: number;
  completed_agents: number;
  failed_agents: number;
  total_findings: number;
  verified_total_findings: number;
  nodes: AgentTreeNode[];
}

export interface AgentCheckpoint {
  id: string;
  agent_id: string;
  agent_name: string;
  agent_type: string;
  iteration: number;
  status: string;
  total_tokens: number;
  tool_calls: number;
  findings_count: number;
  checkpoint_type: "auto" | "manual" | "error" | "final";
  checkpoint_name: string | null;
  created_at: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface CheckpointDetail extends AgentCheckpoint {
  task_id: string;
  parent_agent_id: string | null;
  state_data: Record<string, unknown>;
  metadata: Record<string, unknown> | null;
}

// ============ Agent Tree API Functions ============

/**
 * 获取任务的 Agent 树结构
 */
export async function getAgentTree(taskId: string): Promise<AgentTreeResponse> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/agent-tree`);
  return response.data;
}

/**
 * 获取任务的检查点列表
 */
export async function getAgentCheckpoints(
  taskId: string,
  params?: { agent_id?: string; limit?: number }
): Promise<AgentCheckpoint[]> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/checkpoints`, { params });
  return response.data;
}

/**
 * 获取检查点详情
 */
export async function getCheckpointDetail(
  taskId: string,
  checkpointId: string
): Promise<CheckpointDetail> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/checkpoints/${checkpointId}`);
  return response.data;
}


/**
 * 下载 Agent 任务报告
 */
export async function downloadAgentReport(taskId: string, format: "markdown" | "json" | "pdf" = "markdown"): Promise<void> {
  const response = await apiClient.get(`/agent-tasks/${taskId}/report`, {
    params: { format },
    responseType: 'blob',
  });

  // Create download link
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;

  // Calculate filename
  const baseName = buildReportDownloadBaseName(undefined, taskId.slice(0, 8));
  let filename = `${baseName}.md`;
  if (format === 'json') {
    filename = `${baseName}.json`;
  } else if (format === 'pdf') {
    filename = `${baseName}.pdf`;
  }

  // Try to get filename from header
  const contentDisposition = response.headers['content-disposition'];
  filename = resolveFilenameFromDisposition(contentDisposition, filename);

  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.parentNode?.removeChild(link);
  window.URL.revokeObjectURL(url);
}
