interface SseEvent {
  id: number;
  type: string;
  message?: string;
  tool_name?: string;
  tool_input?: unknown;
  tool_output?: string;
  data?: unknown;
  ts: number;
}

const SKIP_TYPES = new Set([
  "thinking_token",
  "thinking_start",
  "thinking_end",
  "llm_start",
  "llm_complete",
  "phase_start",
  "phase_complete",
]);

const COLLAPSIBLE_TYPES = new Set([
  "llm_thought",
  "llm_observation",
]);

export const AGENT_TEST_EVENT_COLORS: Record<string, string> = {
  info: "text-cyan-400",
  thinking: "text-purple-400",
  llm_decision: "text-purple-300",
  llm_action: "text-blue-300",
  llm_thought: "text-slate-400",
  llm_observation: "text-slate-400",
  tool_call: "text-yellow-400",
  tool_result: "text-yellow-200",
  warning: "text-orange-400",
  error: "text-red-400",
  agent_error: "text-red-500",
  finding_new: "text-emerald-400",
  finding_verified: "text-green-400",
  result: "text-green-400",
  done: "text-green-300",
};

export const AGENT_TEST_EVENT_ICONS: Record<string, string> = {
  info: "ℹ",
  thinking: "",
  llm_decision: "◆",
  llm_action: "→",
  llm_thought: "…",
  llm_observation: "←",
  tool_call: "",
  tool_result: "✓",
  warning: "⚠",
  error: "✗",
  agent_error: "✗",
  finding_new: "🔴",
  finding_verified: "",
  result: "■",
  done: "■",
};

export function shouldShowAgentTestEvent(ev: SseEvent): boolean {
  if (SKIP_TYPES.has(ev.type)) return false;
  if (COLLAPSIBLE_TYPES.has(ev.type) && !ev.message?.trim()) return false;
  return true;
}

export function formatAgentTestEventMessage(ev: SseEvent): string {
  if (ev.type === "tool_call") {
    const inputStr = JSON.stringify(ev.tool_input ?? {});
    const truncated = inputStr.length > 200 ? `${inputStr.slice(0, 200)}…` : inputStr;
    return `${ev.tool_name ?? ""}(${truncated})`;
  }
  if (ev.type === "tool_result") {
    const out = String(ev.tool_output ?? "").trim();
    return out
      ? `${ev.tool_name ?? ""} → ${out.length > 300 ? `${out.slice(0, 300)}…` : out}`
      : `${ev.tool_name ?? ""} → (empty)`;
  }
  if (ev.type === "result") {
    return `最终结果 (${JSON.stringify(ev.data ?? {}).length} bytes)`;
  }
  return ev.message?.trim() || JSON.stringify(ev);
}
