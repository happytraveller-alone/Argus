import { memo, useEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";

export interface ThinkingBlock {
  nodeId: string;
  role: string;
  content: string;
  timestamp: string;
  isActive: boolean;
}

interface ThinkingTimelineProps {
  blocks: ThinkingBlock[];
  currentToken: string;
  currentNodeId: string | null;
  isThinking: boolean;
}

const ROLE_COLORS: Record<string, string> = {
  "env-inter": "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
  "vuln-reasoner": "bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30",
  "audit-reporter": "bg-green-500/15 text-green-700 dark:text-green-300 border-green-500/30",
  runner: "bg-gray-500/15 text-gray-700 dark:text-gray-300 border-gray-500/30",
};

function roleColor(role: string): string {
  return ROLE_COLORS[role] || ROLE_COLORS.runner;
}

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

const ThinkingTimeline = memo(function ThinkingTimeline({
  blocks,
  currentToken,
  currentNodeId,
  isThinking,
}: ThinkingTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = () => {
      userScrolledUp.current = el.scrollTop + el.clientHeight < el.scrollHeight - 50;
    };
    el.addEventListener("scroll", handler, { passive: true });
    return () => el.removeEventListener("scroll", handler);
  }, []);

  useEffect(() => {
    if (!userScrolledUp.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [blocks, currentToken]);

  if (blocks.length === 0 && !isThinking) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-md border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
          {"暂无思考过程数据，运行事件到达后会自动展示。"}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pr-1 custom-scrollbar"
    >
      {blocks.map((block, idx) => (
        <div key={`${block.nodeId}-${idx}`} className="rounded-lg border border-border/60 bg-background/40 p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <Badge variant="outline" className={`text-[10px] ${roleColor(block.role)}`}>
              {block.role || block.nodeId}
            </Badge>
            <span className="text-[10px] text-muted-foreground">{formatTime(block.timestamp)}</span>
          </div>
          <div className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
            {block.content}
          </div>
        </div>
      ))}

      {isThinking && currentToken && (
        <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-3">
          <div className="mb-1.5 flex items-center gap-2">
            <Badge variant="outline" className={`text-[10px] ${roleColor(currentNodeId || "runner")}`}>
              {currentNodeId || "agent"}
            </Badge>
            <span className="text-[10px] text-muted-foreground">
              {"正在思考..."}
            </span>
            <span className="inline-block h-3 w-0.5 animate-pulse bg-blue-500" />
          </div>
          <div className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
            {currentToken}
          </div>
        </div>
      )}
    </div>
  );
});

export default ThinkingTimeline;
