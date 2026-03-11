/**
 * Agent 单体测试页面
 * 用于独立测试 ReconAgent / AnalysisAgent / VerificationAgent / BusinessLogicScanAgent
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  Play,
  Square,
  Trash2,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Cpu,
  Search,
  Shield,
  Code2,
  Database,
  ArrowDown,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";

const API_BASE = "/api/v1/agent-test";

// ─────────────────── Types ───────────────────

type AgentType = "recon" | "analysis" | "verification" | "business-logic";

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

interface QueuePeekItem {
  title: string;
  severity: string;
  vulnerability_type?: string;
  file_path?: string;
  line_start?: number | null;
  confidence?: number | null;
  description?: string;
}

interface QueueInfo {
  label: string;
  size: number;
  peek: QueuePeekItem[];
  allItems: QueuePeekItem[]; // 跨多次 SSE 事件累积的全量条目
}

interface QueueSnapshot {
  vuln?: QueueInfo;
  recon?: QueueInfo;
}

// ─────────────────── SSE streaming hook ───────────────────

function useAgentStream() {
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [queueSnapshot, setQueueSnapshot] = useState<QueueSnapshot>({});
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);

  const run = useCallback(async (agentType: AgentType, body: object) => {
    if (running) return;

    setEvents([]);
    setResult(null);
    setQueueSnapshot({});
    setRunning(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`${API_BASE}/${agentType}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        let detail = errText;
        try { detail = JSON.parse(errText)?.detail ?? errText; } catch { /* noop */ }
        toast.error(`请求失败: ${detail}`);
        setRunning(false);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          if (!part.trim()) continue;
          const lines = part.split("\n");
          let data = "";
          for (const line of lines) {
            if (line.startsWith("data:")) data = line.slice(5).trim();
          }
          if (!data) continue;
          try {
            const parsed = JSON.parse(data) as SseEvent & { queues?: QueueSnapshot };
            const ev = { ...parsed, id: idRef.current++ };
            if (ev.type === "result") {
              setResult(ev.data);
            } else if (ev.type === "queue_snapshot" && parsed.queues) {
              // peek 现在携带全量条目（后端 limit=500），直接用作 allItems
              const merged: QueueSnapshot = {};
              for (const [key, info] of Object.entries(parsed.queues) as [string, QueueInfo][]) {
                merged[key as keyof QueueSnapshot] = { ...info, allItems: info.peek ?? [] };
              }
              setQueueSnapshot(merged);
              continue;
            }
            setEvents((prev) => [...prev, ev]);
          } catch { /* skip bad json */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        toast.error(`连接错误: ${(err as Error)?.message}`);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [running]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    setResult(null);
    setQueueSnapshot({});
  }, []);

  return { events, running, result, queueSnapshot, run, stop, clear };
}

// ─────────────────── Event Log Component ───────────────────

// 完全丢弃的事件类型
const SKIP_TYPES = new Set([
  "thinking_token",
  "thinking_start",
  "thinking_end",
  "llm_start",
  "llm_complete",
  "phase_start",
  "phase_complete",
]);

// 空消息时不展示
const COLLAPSIBLE_TYPES = new Set([
  "llm_thought",
  "llm_observation",
]);

const EVENT_COLORS: Record<string, string> = {
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

const EVENT_ICONS: Record<string, string> = {
  info: "ℹ",
  thinking: "🧠",
  llm_decision: "◆",
  llm_action: "→",
  llm_thought: "…",
  llm_observation: "←",
  tool_call: "🔧",
  tool_result: "✓",
  warning: "⚠",
  error: "✗",
  agent_error: "✗",
  finding_new: "🔴",
  finding_verified: "✅",
  result: "■",
  done: "■",
};

function shouldShowEvent(ev: SseEvent): boolean {
  if (SKIP_TYPES.has(ev.type)) return false;
  if (COLLAPSIBLE_TYPES.has(ev.type) && !ev.message?.trim()) return false;
  return true;
}

function formatEventMessage(ev: SseEvent): string {
  if (ev.type === "tool_call") {
    const inputStr = JSON.stringify(ev.tool_input ?? {});
    const truncated = inputStr.length > 200 ? inputStr.slice(0, 200) + "…" : inputStr;
    return `${ev.tool_name ?? ""}(${truncated})`;
  }
  if (ev.type === "tool_result") {
    const out = String(ev.tool_output ?? "").trim();
    return out
      ? `${ev.tool_name ?? ""} → ${out.length > 300 ? out.slice(0, 300) + "…" : out}`
      : `${ev.tool_name ?? ""} → (empty)`;
  }
  if (ev.type === "result") {
    return `最终结果 (${JSON.stringify(ev.data ?? {}).length} bytes)`;
  }
  return ev.message?.trim() || JSON.stringify(ev);
}

function EventLog({ events, running }: { events: SseEvent[]; running: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  // track whether the user has manually scrolled (to suppress auto-scroll bounce)
  const userScrolledRef = useRef(false);

  const visibleEvents = events.filter(shouldShowEvent);

  // auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "instant" });
    }
  }, [visibleEvents.length, autoScroll]);

  // when running starts, re-enable auto-scroll
  useEffect(() => {
    if (running) {
      setAutoScroll(true);
      userScrolledRef.current = false;
    }
  }, [running]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distFromBottom < 40) {
      // near bottom → re-enable auto-scroll
      setAutoScroll(true);
      userScrolledRef.current = false;
    } else {
      // scrolled up → pause auto-scroll
      userScrolledRef.current = true;
      setAutoScroll(false);
    }
  };

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setAutoScroll(true);
  };

  return (
    <div className="relative">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-[420px] w-full overflow-y-auto rounded border border-border/40 bg-black/60 font-mono text-xs"
      >
        <div className="p-3 space-y-0.5">
          {visibleEvents.length === 0 && (
            <p className="text-muted-foreground italic py-8 text-center">
              等待执行…点击「运行」启动 Agent
            </p>
          )}
          {visibleEvents.map((ev) => (
            <div
              key={ev.id}
              className={`flex gap-2 leading-relaxed ${EVENT_COLORS[ev.type] ?? "text-foreground/60"}`}
            >
              <span className="shrink-0 w-4 text-center opacity-70">
                {EVENT_ICONS[ev.type] ?? "·"}
              </span>
              <span className="shrink-0 text-muted-foreground/40">
                [{new Date(ev.ts * 1000).toLocaleTimeString()}]
              </span>
              <span className="break-all whitespace-pre-wrap">{formatEventMessage(ev)}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* scroll-to-bottom button, shown when auto-scroll is paused */}
      {!autoScroll && visibleEvents.length > 0 && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-cyan-900/80 border border-cyan-700/60 px-2.5 py-1 text-[11px] text-cyan-300 shadow hover:bg-cyan-800/80 transition-colors"
        >
          <ArrowDown className="w-3 h-3" />
          跳到底部
        </button>
      )}
    </div>
  );
}

function ResultPanel({ result }: { result: unknown }) {
  if (!result) return null;
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold text-muted-foreground mb-1">最终输出 (JSON)</p>
      <ScrollArea className="h-[280px] rounded border border-green-800/40 bg-black/60">
        <pre className="p-3 text-xs text-green-300 whitespace-pre-wrap break-all font-mono">
          {JSON.stringify(result, null, 2)}
        </pre>
      </ScrollArea>
    </div>
  );
}

function RunBar({
  running,
  eventCount,
  onRun,
  onStop,
  onClear,
}: {
  running: boolean;
  eventCount: number;
  onRun: () => void;
  onStop: () => void;
  onClear: () => void;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {!running ? (
        <Button size="sm" onClick={onRun} className="gap-1.5">
          <Play className="w-3.5 h-3.5" /> 运行
        </Button>
      ) : (
        <Button size="sm" variant="destructive" onClick={onStop} className="gap-1.5">
          <Square className="w-3.5 h-3.5" /> 停止
        </Button>
      )}
      <Button size="sm" variant="outline" onClick={onClear} className="gap-1.5">
        <Trash2 className="w-3.5 h-3.5" /> 清空
      </Button>
      {running && (
        <Badge variant="outline" className="gap-1 text-cyan-400 border-cyan-800 animate-pulse">
          <Cpu className="w-3 h-3" /> 运行中…
        </Badge>
      )}
      {eventCount > 0 && !running && (
        <Badge variant="outline" className="text-muted-foreground">
          {eventCount} 条日志
        </Badge>
      )}
    </div>
  );
}

// ─────────────────── Queue Status Panel ───────────────────

const SEVERITY_COLORS: Record<string, string> = {
  critical: "text-red-500",
  high: "text-orange-400",
  medium: "text-yellow-400",
  low: "text-blue-400",
  info: "text-slate-400",
};

const SEVERITY_BG: Record<string, string> = {
  critical: "bg-red-950/40 border-red-800/40",
  high: "bg-orange-950/40 border-orange-800/40",
  medium: "bg-yellow-950/40 border-yellow-800/40",
  low: "bg-blue-950/40 border-blue-800/40",
  info: "bg-slate-900/40 border-slate-700/40",
};

function QueueItemDetail({ item, index }: { item: QueuePeekItem; index: number }) {
  const sev = item.severity.toLowerCase();
  return (
    <div className={`rounded border p-2 text-[11px] space-y-1 ${SEVERITY_BG[sev] ?? "bg-muted/20 border-border/40"}`}>
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground/50 shrink-0">#{index + 1}</span>
        <span className={`font-semibold shrink-0 ${SEVERITY_COLORS[sev] ?? "text-foreground/60"}`}>
          [{item.severity.toUpperCase()}]
        </span>
        <span className="font-medium text-foreground/90 truncate">{item.title}</span>
      </div>
      {item.vulnerability_type && (
        <div className="flex gap-1 text-muted-foreground/60">
          <span className="shrink-0">类型:</span>
          <span className="text-cyan-400/80 font-mono">{item.vulnerability_type}</span>
        </div>
      )}
      {item.file_path && (
        <div className="flex gap-1 text-muted-foreground/60">
          <span className="shrink-0">位置:</span>
          <span className="font-mono text-foreground/70 truncate">
            {item.file_path}{item.line_start != null ? `:${item.line_start}` : ""}
          </span>
        </div>
      )}
      {item.confidence != null && (
        <div className="flex gap-1 text-muted-foreground/60">
          <span className="shrink-0">置信度:</span>
          <span className="text-foreground/70">{(item.confidence * 100).toFixed(0)}%</span>
        </div>
      )}
      {item.description && (
        <div className="text-muted-foreground/70 leading-relaxed">{item.description}</div>
      )}
    </div>
  );
}

function QueueStatusPanel({ snapshot }: { snapshot: QueueSnapshot }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  // 每个队列的当前分页页数（每页 PAGE_SIZE 条）
  const [pages, setPages] = useState<Record<string, number>>({});

  const PAGE_SIZE = 10;

  const entries = Object.entries(snapshot).filter(([, info]) => info !== undefined) as [string, QueueInfo][];
  if (entries.length === 0) return null;

  const toggle = (key: string) => setExpandedKey((prev) => (prev === key ? null : key));

  return (
    <div className="flex gap-3 flex-wrap mb-3">
      {entries.map(([key, info]) => {
        const isExpanded = expandedKey === key;
        const allItems = info.allItems ?? info.peek;
        const currentPage = pages[key] ?? 0;
        const totalPages = Math.ceil(allItems.length / PAGE_SIZE);
        const pageItems = allItems.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

        const goPage = (p: number) => setPages((prev) => ({ ...prev, [key]: p }));

        return (
          <div
            key={key}
            className="flex-1 min-w-[220px] rounded border border-border/40 bg-muted/20 overflow-hidden"
          >
            {/* ── Header (always visible, clickable) ── */}
            <button
              type="button"
              onClick={() => toggle(key)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/30 transition-colors text-left"
            >
              <Database className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
              <span className="text-xs font-semibold text-muted-foreground flex-1">{info.label}</span>
              <Badge
                variant="outline"
                className="text-cyan-400 border-cyan-800 text-[10px] px-1.5 py-0 shrink-0"
              >
                {info.size} 条
              </Badge>
              {allItems.length > 0 && (
                isExpanded
                  ? <ChevronUp className="w-3 h-3 text-muted-foreground/50 shrink-0" />
                  : <ChevronDown className="w-3 h-3 text-muted-foreground/50 shrink-0" />
              )}
            </button>

            {/* ── Collapsed preview (show first 3 only) ── */}
            {!isExpanded && allItems.length > 0 && (
              <div className="px-3 pb-2 space-y-0.5">
                {allItems.slice(0, 3).map((item, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px]">
                    <span className={`shrink-0 font-bold ${SEVERITY_COLORS[item.severity.toLowerCase()] ?? "text-foreground/60"}`}>
                      [{item.severity.toUpperCase().slice(0, 4)}]
                    </span>
                    <span className="text-foreground/70 truncate">{item.title}</span>
                  </div>
                ))}
                {allItems.length > 3 && (
                  <p className="text-[10px] text-muted-foreground/40 pt-0.5">
                    还有 {allItems.length - 3} 条…点击展开查看全部
                  </p>
                )}
              </div>
            )}

            {/* ── Expanded detail with pagination ── */}
            {isExpanded && (
              <div className="px-3 pb-3 space-y-2">
                {allItems.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground/50 py-1">队列为空</p>
                ) : (
                  <>
                    {/* 可滚动列表区域 */}
                    <div className="max-h-[420px] overflow-y-auto space-y-2 pr-1">
                      {pageItems.map((item, i) => (
                        <QueueItemDetail key={i} item={item} index={currentPage * PAGE_SIZE + i} />
                      ))}
                    </div>

                    {/* 分页控件 */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-between pt-1">
                        <button
                          type="button"
                          disabled={currentPage === 0}
                          onClick={() => goPage(currentPage - 1)}
                          className="flex items-center gap-1 text-[10px] text-muted-foreground/60 hover:text-foreground/80 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                          <ChevronUp className="w-3 h-3 rotate-[-90deg]" />
                          上一页
                        </button>
                        <span className="text-[10px] text-muted-foreground/50">
                          {currentPage + 1} / {totalPages}（已收集 {allItems.length} 条）
                        </span>
                        <button
                          type="button"
                          disabled={currentPage >= totalPages - 1}
                          onClick={() => goPage(currentPage + 1)}
                          className="flex items-center gap-1 text-[10px] text-muted-foreground/60 hover:text-foreground/80 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                          下一页
                          <ChevronDown className="w-3 h-3 rotate-[-90deg]" />
                        </button>
                      </div>
                    )}

                    {/* 总量提示（无分页时） */}
                    {totalPages <= 1 && info.size > allItems.length && (
                      <p className="text-[10px] text-muted-foreground/40">
                        已收集 {allItems.length} 条，队列总计 {info.size} 条
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────── Recon Panel ───────────────────

function ReconPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } = useAgentStream();
  const [projectPath, setProjectPath] = useState("");
  const [projectName, setProjectName] = useState("test-project");
  const [frameworkHint, setFrameworkHint] = useState("");
  const [maxIter, setMaxIter] = useState("6");

  const handleRun = () => {
    if (!projectPath.trim()) { toast.error("请填写项目路径"); return; }
    run("recon", {
      project_path: projectPath.trim(),
      project_name: projectName.trim() || "test-project",
      framework_hint: frameworkHint.trim() || null,
      max_iterations: parseInt(maxIter) || 6,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目名称</label>
          <Input
            placeholder="my-webapp"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">框架提示（可选）</label>
          <Input
            placeholder="django / fastapi / express / spring"
            value={frameworkHint}
            onChange={(e) => setFrameworkHint(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
      </div>
      <RunBar running={running} eventCount={events.length} onRun={handleRun} onStop={stop} onClear={clear} />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

// ─────────────────── Analysis Panel ───────────────────

function AnalysisPanel() {
  const { events, running, result, queueSnapshot, run, stop, clear } = useAgentStream();
  const [projectPath, setProjectPath] = useState("");
  const [projectName, setProjectName] = useState("test-project");
  const [highRiskAreas, setHighRiskAreas] = useState("");
  const [entryPoints, setEntryPoints] = useState("");
  const [taskDesc, setTaskDesc] = useState("");
  const [maxIter, setMaxIter] = useState("8");

  const handleRun = () => {
    if (!projectPath.trim()) { toast.error("请填写项目路径"); return; }
    run("analysis", {
      project_path: projectPath.trim(),
      project_name: projectName.trim() || "test-project",
      high_risk_areas: highRiskAreas.split("\n").map((s) => s.trim()).filter(Boolean),
      entry_points: entryPoints.split("\n").map((s) => s.trim()).filter(Boolean),
      task_description: taskDesc.trim(),
      max_iterations: parseInt(maxIter) || 8,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目名称</label>
          <Input
            placeholder="my-webapp"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">审计任务描述（可选）</label>
          <Input
            placeholder="重点检查用户认证和权限控制逻辑"
            value={taskDesc}
            onChange={(e) => setTaskDesc(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">高风险区域（每行一个）</label>
          <Textarea
            placeholder={"app/api/user.py\napp/api/payment.py"}
            value={highRiskAreas}
            onChange={(e) => setHighRiskAreas(e.target.value)}
            disabled={running}
            rows={4}
            className="font-mono text-xs resize-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">入口点（每行一个）</label>
          <Textarea
            placeholder={"GET /api/users/{id}\nPOST /api/orders"}
            value={entryPoints}
            onChange={(e) => setEntryPoints(e.target.value)}
            disabled={running}
            rows={4}
            className="font-mono text-xs resize-none"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
      </div>
      <RunBar running={running} eventCount={events.length} onRun={handleRun} onStop={stop} onClear={clear} />
      <QueueStatusPanel snapshot={queueSnapshot} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

// ─────────────────── Verification Panel ───────────────────

const FINDING_PLACEHOLDER = JSON.stringify([
  {
    title: "SQL 注入漏洞",
    vulnerability_type: "sql_injection",
    severity: "high",
    file_path: "app/api/user.py",
    function_name: "get_user",
    line_start: 42,
    description: "用户输入直接拼接到 SQL 查询中",
    code_snippet: "query = f\"SELECT * FROM users WHERE id={user_id}\"",
  },
], null, 2);

function VerificationPanel() {
  const { events, running, result, run, stop, clear } = useAgentStream();
  const [projectPath, setProjectPath] = useState("");
  const [findingsJson, setFindingsJson] = useState(FINDING_PLACEHOLDER);
  const [maxIter, setMaxIter] = useState("6");

  const handleRun = () => {
    if (!projectPath.trim()) { toast.error("请填写项目路径"); return; }
    let findings: unknown;
    try {
      findings = JSON.parse(findingsJson);
      if (!Array.isArray(findings)) { toast.error("漏洞列表必须是 JSON 数组"); return; }
    } catch {
      toast.error("漏洞列表 JSON 格式错误");
      return;
    }
    run("verification", {
      project_path: projectPath.trim(),
      findings,
      max_iterations: parseInt(maxIter) || 6,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">最大迭代次数</label>
          <Input
            type="number"
            min={1}
            max={20}
            value={maxIter}
            onChange={(e) => setMaxIter(e.target.value)}
            disabled={running}
            className="w-24"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">
            待验证漏洞列表（JSON 数组）
          </label>
          <Textarea
            value={findingsJson}
            onChange={(e) => setFindingsJson(e.target.value)}
            disabled={running}
            rows={12}
            className="font-mono text-xs resize-none"
          />
        </div>
      </div>
      <RunBar running={running} eventCount={events.length} onRun={handleRun} onStop={stop} onClear={clear} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

// ─────────────────── BusinessLogic Panel ───────────────────

function BusinessLogicPanel() {
  const { events, running, result, run, stop, clear } = useAgentStream();
  const [projectPath, setProjectPath] = useState("");
  const [entryPoints, setEntryPoints] = useState("");
  const [frameworkHint, setFrameworkHint] = useState("");
  const [maxIter, setMaxIter] = useState("8");
  const [quickMode, setQuickMode] = useState(false);

  const handleRun = () => {
    if (!projectPath.trim()) { toast.error("请填写项目路径"); return; }
    run("business-logic", {
      project_path: projectPath.trim(),
      entry_points_hint: entryPoints.split("\n").map((s) => s.trim()).filter(Boolean),
      framework_hint: frameworkHint.trim() || null,
      max_iterations: parseInt(maxIter) || 8,
      quick_mode: quickMode,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">项目绝对路径 *</label>
          <Input
            placeholder="/path/to/your/project"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            disabled={running}
            className="font-mono text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">框架提示（可选）</label>
          <Input
            placeholder="flask / fastapi / django / express / spring"
            value={frameworkHint}
            onChange={(e) => setFrameworkHint(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs text-muted-foreground">
            入口点列表（每行一个，格式：<code className="text-cyan-400">文件路径:函数名</code>）
          </label>
          <Textarea
            placeholder={"app/api/user.py:update_profile\napp/api/order.py:create_order\napp/api/admin.py:reset_password"}
            value={entryPoints}
            onChange={(e) => setEntryPoints(e.target.value)}
            disabled={running}
            rows={5}
            className="font-mono text-xs resize-none"
          />
          <p className="text-xs text-muted-foreground/60">
            留空则启用全局模式（自动发现所有 HTTP 入口点）
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">最大迭代次数</label>
            <Input
              type="number"
              min={1}
              max={20}
              value={maxIter}
              onChange={(e) => setMaxIter(e.target.value)}
              disabled={running}
              className="w-24"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer mt-5">
            <input
              type="checkbox"
              checked={quickMode}
              onChange={(e) => setQuickMode(e.target.checked)}
              disabled={running}
              className="accent-cyan-400"
            />
            <span className="text-xs text-muted-foreground">快速模式</span>
          </label>
        </div>
      </div>
      <RunBar running={running} eventCount={events.length} onRun={handleRun} onStop={stop} onClear={clear} />
      <EventLog events={events} running={running} />
      <ResultPanel result={result} />
    </div>
  );
}

// ─────────────────── Page ───────────────────

export default function AgentTestPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-background font-mono">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      <div className="relative z-10 flex flex-col h-full p-6 gap-4">
        {/* Header */}
        <div className="flex items-center gap-3 shrink-0">
          <Bot className="w-6 h-6 text-primary" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">Agent 单体测试</h1>
            <p className="text-xs text-muted-foreground">
              独立测试单个 Agent 的能力，实时查看执行过程
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground/60">
            <ChevronRight className="w-3 h-3" />
            <span>直连 Agent，不创建审计任务</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="cyber-card flex-1 min-h-0 p-4 overflow-hidden flex flex-col">
          <Tabs defaultValue="recon" className="flex flex-col flex-1 min-h-0">
            <TabsList className="shrink-0 grid grid-cols-4 w-full max-w-xl mb-4">
              <TabsTrigger value="recon" className="gap-1.5 text-xs">
                <Search className="w-3.5 h-3.5" /> Recon
              </TabsTrigger>
              <TabsTrigger value="analysis" className="gap-1.5 text-xs">
                <Cpu className="w-3.5 h-3.5" /> Analysis
              </TabsTrigger>
              <TabsTrigger value="verification" className="gap-1.5 text-xs">
                <Shield className="w-3.5 h-3.5" /> Verification
              </TabsTrigger>
              <TabsTrigger value="business-logic" className="gap-1.5 text-xs">
                <Code2 className="w-3.5 h-3.5" /> Business Logic
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 min-h-0 overflow-y-auto pr-1">
              <TabsContent value="recon" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">ReconAgent</strong> —
                    信息收集阶段：扫描项目结构、识别技术栈、发现 HTTP 入口点和高风险区域。
                  </p>
                </div>
                <ReconPanel />
              </TabsContent>

              <TabsContent value="analysis" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">AnalysisAgent</strong> —
                    漏洞分析阶段：深度分析代码，发现 SQL 注入、XSS、越权等安全漏洞。
                    可提供 Recon 阶段的入口点和高风险区域作为上下文。
                  </p>
                </div>
                <AnalysisPanel />
              </TabsContent>

              <TabsContent value="verification" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">VerificationAgent</strong> —
                    漏洞验证阶段：对已发现的漏洞进行深度代码审查，验证真实性并评估可利用性。
                    以 JSON 数组形式输入待验证的漏洞列表。
                  </p>
                </div>
                <VerificationPanel />
              </TabsContent>

              <TabsContent value="business-logic" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">BusinessLogicScanAgent</strong> —
                    业务逻辑漏洞扫描：检测 IDOR、权限绕过、金额篡改、批量赋值、竞态条件等业务逻辑缺陷。
                    指定入口点列表可启用聚焦模式，留空则全局扫描。
                  </p>
                </div>
                <BusinessLogicPanel />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
