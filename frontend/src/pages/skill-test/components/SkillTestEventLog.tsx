import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";

import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";
import { parseToolEvidenceFromLog } from "@/pages/AgentAudit/toolEvidence";
import {
  AGENT_TEST_EVENT_COLORS,
  AGENT_TEST_EVENT_ICONS,
  formatAgentTestEventMessage,
  shouldShowAgentTestEvent,
} from "@/pages/agent-test/eventLogUtils";
import type { SkillTestEvent } from "@/pages/skill-test/types";

const EXTRA_EVENT_COLORS: Record<string, string> = {
  project_prepare: "text-cyan-300",
  project_cleanup: "text-emerald-300",
};

const EXTRA_EVENT_ICONS: Record<string, string> = {
  project_prepare: "",
  project_cleanup: "🧹",
};

function formatSkillEventMessage(event: SkillTestEvent): string {
  if (event.type === "project_prepare" || event.type === "project_cleanup") {
    const tempDir = String(event.metadata?.temp_dir ?? "").trim();
    return tempDir ? `${event.message ?? ""} (${tempDir})` : event.message?.trim() || event.type;
  }
  return formatAgentTestEventMessage(event as never);
}

export default function SkillTestEventLog({
  events,
  running,
}: {
  events: SkillTestEvent[];
  running: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const visibleEvents = useMemo(() => events.filter((event) => shouldShowAgentTestEvent(event as never)), [events]);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }
  }, [autoScroll, visibleEvents.length]);

  useEffect(() => {
    if (running) {
      setAutoScroll(true);
    }
  }, [running]);

  const handleScroll = () => {
    const node = containerRef.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setAutoScroll(distance < 40);
  };

  return (
    <div className="relative">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-[420px] w-full overflow-y-auto rounded border border-border/40 bg-black/60 font-mono text-xs"
      >
        <div className="space-y-3 p-3">
          {visibleEvents.length === 0 ? (
            <p className="py-8 text-center italic text-muted-foreground">等待执行…点击「运行测试」启动 Skill</p>
          ) : null}
          {visibleEvents.map((event) => {
            const evidence = event.type === "tool_result"
              ? parseToolEvidenceFromLog({
                  toolName: event.tool_name,
                  toolOutput: event.tool_output,
                  toolMetadata: event.metadata ?? null,
                })
              : null;
            const colorClass = EXTRA_EVENT_COLORS[event.type] ?? AGENT_TEST_EVENT_COLORS[event.type] ?? "text-foreground/70";
            const icon = EXTRA_EVENT_ICONS[event.type] ?? AGENT_TEST_EVENT_ICONS[event.type] ?? "·";

            return (
              <div key={event.id} className="space-y-2 rounded border border-border/30 bg-background/20 p-2.5">
                <div className={`flex gap-2 leading-relaxed ${colorClass}`}>
                  <span className="shrink-0 w-4 text-center opacity-80">{icon}</span>
                  <span className="shrink-0 text-muted-foreground/50">[{new Date(event.ts * 1000).toLocaleTimeString()}]</span>
                  {event.type === "llm_thought" ? (
                    <details className="min-w-0 flex-1">
                      <summary className="cursor-pointer list-none break-all whitespace-pre-wrap">思考（已折叠）</summary>
                      <div className="mt-2 break-all whitespace-pre-wrap text-slate-300">{event.message?.trim() || "(empty)"}</div>
                    </details>
                  ) : (
                    <span className="break-all whitespace-pre-wrap">{formatSkillEventMessage(event)}</span>
                  )}
                </div>
                {evidence?.payload ? <ToolEvidencePreview evidence={evidence} /> : null}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>

      {!autoScroll && visibleEvents.length > 0 ? (
        <button
          onClick={() => {
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            setAutoScroll(true);
          }}
          className="absolute bottom-3 right-3 flex items-center gap-1 rounded-full border border-cyan-700/60 bg-cyan-900/80 px-2.5 py-1 text-[11px] text-cyan-300 shadow transition-colors hover:bg-cyan-800/80"
        >
          <ArrowDown className="w-3 h-3" />
          跳到底部
        </button>
      ) : null}
    </div>
  );
}
