export type AgentType =
  | "recon"
  | "analysis"
  | "verification"
  | "business-logic"
  | "business-logic-recon"
  | "business-logic-analysis";

export interface SseEvent {
  id: number;
  type: string;
  message?: string;
  tool_name?: string;
  tool_input?: unknown;
  tool_output?: string;
  data?: unknown;
  ts: number;
}

export interface QueuePeekItem {
  title: string;
  severity: string;
  vulnerability_type?: string;
  file_path?: string;
  line_start?: number | null;
  confidence?: number | null;
  description?: string;
}

export interface QueueInfo {
  label: string;
  size: number;
  peek: QueuePeekItem[];
  allItems: QueuePeekItem[];
}

export interface QueueSnapshot {
  vuln?: QueueInfo;
  recon?: QueueInfo;
  bl_recon?: QueueInfo;
}
