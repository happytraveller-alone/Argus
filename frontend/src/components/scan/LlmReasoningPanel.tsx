import { useState } from "react";

import type { SseEvent } from "@/hooks/useSseStream";

interface ThinkingBlock {
  id: number;
  startTimestamp: string;
  content: string;
}

function buildThinkingBlocks(events: SseEvent[]): ThinkingBlock[] {
  const blocks: ThinkingBlock[] = [];
  let current: ThinkingBlock | null = null;
  let idCounter = 0;

  for (const ev of events) {
    if (ev.kind === "thinking_start") {
      current = { id: idCounter++, startTimestamp: ev.timestamp, content: "" };
    } else if (ev.kind === "thinking_token" && current !== null) {
      const token = typeof ev.data?.content === "string" ? ev.data.content : "";
      current.content += token;
    } else if (ev.kind === "thinking_end" && current !== null) {
      blocks.push(current);
      current = null;
    }
  }

  // Push in-progress block
  if (current !== null) {
    blocks.push(current);
  }

  return blocks;
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

interface BlockCardProps {
  block: ThinkingBlock;
  defaultExpanded: boolean;
}

function BlockCard({ block, defaultExpanded }: BlockCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="rounded border border-purple-500/20 bg-purple-500/5">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[10px] text-muted-foreground shrink-0">
            {formatTimestamp(block.startTimestamp)}
          </span>
          <span className="font-mono text-xs font-semibold text-purple-300 uppercase tracking-widest">
            LLM推理
          </span>
          {block.content.length > 0 && (
            <span className="font-mono text-[10px] text-muted-foreground truncate">
              {block.content.slice(0, 60).replace(/\n/g, " ")}
              {block.content.length > 60 ? "…" : ""}
            </span>
          )}
        </div>
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {expanded && (
        <div className="border-t border-purple-500/10 px-3 py-2">
          {block.content ? (
            <pre className="whitespace-pre-wrap font-mono text-xs text-purple-200/80 leading-relaxed">
              {block.content}
            </pre>
          ) : (
            <span className="font-mono text-xs text-muted-foreground">（推理内容为空）</span>
          )}
        </div>
      )}
    </div>
  );
}

interface LlmReasoningPanelProps {
  events: SseEvent[];
  isStreaming?: boolean;
}

export function LlmReasoningPanel({ events, isStreaming = false }: LlmReasoningPanelProps) {
  const blocks = buildThinkingBlocks(events);

  if (blocks.length === 0) {
    return (
      <div className="flex items-center gap-2 py-3">
        <span
          className={`inline-block h-2 w-2 rounded-full bg-purple-400 ${isStreaming ? "animate-pulse" : "opacity-30"}`}
        />
        <span className="font-mono text-xs text-muted-foreground">等待LLM推理...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {blocks.map((block, idx) => {
        const isLast = idx === blocks.length - 1;
        // Latest block expanded when streaming; all collapsed when done
        const defaultExpanded = isStreaming ? isLast : false;
        return (
          <BlockCard key={block.id} block={block} defaultExpanded={defaultExpanded} />
        );
      })}
    </div>
  );
}
