/**
 * Agent Scan Types
 * Type definitions for the Agent Scan page
 */

import type { AgentTask, AgentFinding, AgentTreeNode } from "@/shared/api/agentTasks";
import type { AgentAuditStatsSummary } from "./detailViewModel";
import type { ToolEvidencePayload } from "./toolEvidence";

// ============ Log Types ============

export type LogType =
  | 'thinking'
  | 'tool'
  | 'phase'
  | 'finding'
  | 'info'
  | 'error'
  | 'user'
  | 'dispatch'
  | 'progress';

export type ToolStatus = 'running' | 'completed' | 'failed' | 'cancelled';
export type ProgressStatus = 'running' | 'completed';
export type TerminalFailureClass =
  | 'timeout'
  | 'mcp'
  | 'network'
  | 'validation_repairable'
  | 'cancelled_user'
  | 'cancelled_system'
  | 'non_retryable'
  | 'unknown';

export type LateToolCallPolicy = 'ignore' | 'recovery';

export interface TerminalRecoveryState {
  active: boolean;
  attempts: number;
  reasonKey: string;
  triggeredAt: number;
}

export interface FindingCodeHighlightRange {
  highlightStartLine?: number | null;
  highlightEndLine?: number | null;
  focusLine?: number | null;
}

export interface LogItem {
  id: string;
  time: string;
  eventTimestamp?: string | null;
  type: LogType;
  phaseLabel?: string | null;
  title: string;
  content?: string;
  isStreaming?: boolean;
  detail?: Record<string, unknown>;
  tool?: {
    name: string;
    duration?: number;
    status?: ToolStatus;
    callId?: string;
  };
  toolEvidence?: ToolEvidencePayload | null;
  severity?: string;
  agentName?: string;
  agentRawName?: string;
  progressKey?: string; // 用于标识进度日志的唯一键，如 "index_progress"
  progressStatus?: ProgressStatus;
}

// ============ Connection Types ============

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

// ============ State Types ============

export interface AgentAuditState {
  task: AgentTask | null;
  findings: AgentFinding[];
  agentTree: AgentTreeResponse | null;
  logs: LogItem[];
  selectedAgentId: string | null;
  showAllLogs: boolean;
  isLoading: boolean;
  error: string | null;
  connectionStatus: ConnectionStatus;
  isAutoScroll: boolean;
  expandedLogIds: Set<string>;
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

// ============ Action Types ============

export type AgentAuditAction =
  | { type: 'SET_TASK'; payload: AgentTask }
  | { type: 'SET_FINDINGS'; payload: AgentFinding[] }
  | { type: 'ADD_FINDING'; payload: Partial<AgentFinding> & { id: string } }
  | { type: 'SET_AGENT_TREE'; payload: AgentTreeResponse }
  | { type: 'SET_LOGS'; payload: LogItem[] }
  | {
      type: 'ADD_LOG';
      payload: Omit<LogItem, 'id' | 'time'> & {
        id?: string;
        time?: string;
        eventTimestamp?: string | null;
      };
    }
  | { type: 'UPDATE_LOG'; payload: { id: string; updates: Partial<LogItem> } }
  | {
      type: 'UPDATE_OR_ADD_PROGRESS_LOG';
      payload: {
        progressKey: string;
        title: string;
        agentName?: string;
        phaseLabel?: string | null;
        progressStatus?: ProgressStatus;
        time?: string;
        eventTimestamp?: string | null;
      };
    }
  | { type: 'COMPLETE_TOOL_LOG'; payload: { toolName: string; output: string; duration: number } }
  | { type: 'REMOVE_LOG'; payload: string }
  | { type: 'SELECT_AGENT'; payload: string | null }
  | { type: 'TOGGLE_SHOW_ALL_LOGS' }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_CONNECTION_STATUS'; payload: ConnectionStatus }
  | { type: 'SET_AUTO_SCROLL'; payload: boolean }
  | { type: 'TOGGLE_LOG_EXPANDED'; payload: string }
  | { type: 'RESET' };

// ============ Component Props ============

export interface AgentTreeNodeItemProps {
  node: AgentTreeNode;
  depth?: number;
  selectedId: string | null;
  highlightedId?: string | null;
  onSelect: (id: string) => void;
}

export interface LogEntryProps {
  item: LogItem;
  onOpenDetail: () => void;
  anchorId: string;
  highlighted?: boolean;
}

export interface AgentDetailPanelProps {
  agentId: string;
  treeNodes: AgentTreeNode[];
  onClose: () => void;
}

export interface StatsPanelProps {
  summary: AgentAuditStatsSummary | null;
  projectName?: string | null;
}

export interface HeaderProps {
  title: string;
  task: AgentTask | null;
  isRunning: boolean;
  isCancelling: boolean;
  phaseLabel?: string | null;
  phaseHint?: string | null;
  onBack: () => void;
  onCancel: () => void;
  onExport: () => void;
}

export interface ActivityLogProps {
  logs: LogItem[];
  filteredLogs: LogItem[];
  isConnected: boolean;
  isRunning: boolean;
  isAutoScroll: boolean;
  expandedIds: Set<string>;
  selectedAgentId: string | null;
  showAllLogs: boolean;
  onToggleAutoScroll: () => void;
  onToggleExpand: (id: string) => void;
  onClearFilter: () => void;
}

export interface AgentTreePanelProps {
  treeNodes: AgentTreeNode[];
  agentTree: AgentTreeResponse | null;
  selectedAgentId: string | null;
  showAllLogs: boolean;
  isRunning: boolean;
  onSelectAgent: (id: string) => void;
  onClearSelection: () => void;
}

export interface FindingsViewFilters {
  keyword: string;
  severity: string;
  showFiltered?: boolean;
}

export interface FindingsFiltersChangeOptions {
  source?: "user" | "system";
}

export interface BootstrapInputsSummary {
  taskId: string;
  source: string;
  totalFindings: number;
  candidateCount: number;
}

export interface DetailViewState {
  detailType: "log" | "finding" | "agent";
  detailId: string;
  anchorId: string;
  activeTab: "logs" | "findings";
  logsScrollTop: number;
  findingsScrollTop: number;
  agentScrollTop: number;
  filters: FindingsViewFilters;
}

// ============ Stream Event Types ============

export interface StreamEvent {
  type: string;
  message?: string;
  metadata?: {
    agent_name?: string;
    agent?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface StreamOptions {
  includeThinking?: boolean;
  includeToolCalls?: boolean;
  onEvent?: (event: StreamEvent) => void;
  onThinkingStart?: () => void;
  onThinkingToken?: (token: string, accumulated: string) => void;
  onThinkingEnd?: (response: string) => void;
  onToolStart?: (name: string, input: Record<string, unknown>) => void;
  onToolEnd?: (name: string, output: unknown, duration: number) => void;
  onFinding?: (finding: Record<string, unknown>) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

// Re-export from API
export type { AgentTask, AgentFinding, AgentTreeNode };
