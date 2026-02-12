import { memo } from "react";
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  Play,
  Wifi,
  XOctagon,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { LOG_TYPE_CONFIG, SEVERITY_COLORS } from "../constants";
import type { LogEntryProps } from "../types";

const LOG_TYPE_LABELS: Record<string, string> = {
  thinking: "思考",
  tool: "工具",
  phase: "阶段",
  finding: "漏洞",
  dispatch: "调度",
  info: "信息",
  error: "错误",
  user: "用户",
  progress: "进度",
};

function formatTitle(title: string): string {
  return title
    .replace(/[\u{1F300}-\u{1F9FF}]/gu, "")
    .replace(/[\u{2600}-\u{26FF}]/gu, "")
    .replace(/[✅🔗🛑✕⚠️❌⚡🔄🔍💡📁📄🐛🛡️]/g, "")
    .trim();
}

function getStatusIcon(title: string) {
  const lowerTitle = title.toLowerCase();
  if (lowerTitle.includes("connect") || lowerTitle.includes("stream")) {
    return <Wifi className="w-3 h-3 text-green-400" />;
  }
  if (
    lowerTitle.includes("complete") ||
    lowerTitle.includes("success") ||
    lowerTitle.includes("done")
  ) {
    return <CheckCircle2 className="w-3 h-3 text-green-400" />;
  }
  if (lowerTitle.includes("cancel") || lowerTitle.includes("abort")) {
    return <XOctagon className="w-3 h-3 text-yellow-400" />;
  }
  if (
    lowerTitle.includes("start") ||
    lowerTitle.includes("begin") ||
    lowerTitle.includes("init")
  ) {
    return <Play className="w-3 h-3 text-cyan-400" />;
  }
  return null;
}

export const LogEntry = memo(function LogEntry({
  item,
  onOpenDetail,
  anchorId,
  highlighted = false,
}: LogEntryProps) {
  const config = LOG_TYPE_CONFIG[item.type] || LOG_TYPE_CONFIG.info;
  const isThinking = item.type === "thinking";
  const isTool = item.type === "tool";
  const isFinding = item.type === "finding";
  const isError = item.type === "error";
  const isInfo = item.type === "info";
  const isProgress = item.type === "progress";
  const isDispatch = item.type === "dispatch";
  const formattedTitle = formatTitle(item.title) || item.title;
  const statusIcon = isInfo ? getStatusIcon(formattedTitle) : null;
  const contentPreview = item.content
    ? item.content.slice(0, 180) + (item.content.length > 180 ? "..." : "")
    : "";

  return (
    <div
      id={anchorId}
      className={highlighted ? "rounded-lg ring-2 ring-primary/60 transition-shadow" : ""}
    >
      <div
        className={`
          relative rounded-lg border-l-3 overflow-hidden
          ${config.borderColor}
          bg-card/50
          ${isFinding ? "border border-rose-500/30 !bg-rose-950/20" : "border border-border"}
          ${isError ? "border border-red-500/30 !bg-red-950/20" : ""}
          ${isDispatch ? "border-sky-500/30 !bg-sky-950/20" : ""}
          ${isThinking ? "!bg-violet-950/20 border-violet-500/30" : ""}
          ${isTool ? "!bg-amber-950/20 border-amber-500/30" : ""}
        `}
      >
        <div className="px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex-shrink-0">{config.icon}</div>
            <span
              className={`
                text-xs font-mono font-bold uppercase tracking-wider px-2 py-1 rounded-md border
                ${isThinking ? "bg-violet-500/20 text-violet-600 dark:text-violet-300 border-violet-500/30" : ""}
                ${isTool ? "bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/30" : ""}
                ${isFinding ? "bg-rose-500/20 text-rose-600 dark:text-rose-300 border-rose-500/30" : ""}
                ${isError ? "bg-red-500/20 text-red-600 dark:text-red-300 border-red-500/30" : ""}
                ${isInfo ? "bg-muted/80 text-foreground border-border/50" : ""}
                ${isProgress ? "bg-cyan-500/20 text-cyan-600 dark:text-cyan-300 border-cyan-500/30" : ""}
                ${isDispatch ? "bg-sky-500/20 text-sky-600 dark:text-sky-300 border-sky-500/30" : ""}
              `}
            >
              {LOG_TYPE_LABELS[item.type] || "LOG"}
            </span>
            <span className="text-xs text-muted-foreground font-mono flex-shrink-0 tabular-nums">
              {item.time}
            </span>
            <Zap className="w-3 h-3 text-muted-foreground/50 flex-shrink-0" />
            {statusIcon && <span className="flex-shrink-0">{statusIcon}</span>}
            <span className="text-sm text-foreground font-medium whitespace-normal break-words flex-1 min-w-0">
              {formattedTitle}
            </span>
            {item.tool?.status === "running" && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-500" />
            )}
            {item.agentName && (
              <Badge
                variant="outline"
                className="h-6 px-2 text-xs uppercase tracking-wider border-primary/40 text-primary bg-primary/10 flex-shrink-0"
              >
                {item.agentName}
              </Badge>
            )}
            {item.severity && (
              <Badge className={`text-xs uppercase ${SEVERITY_COLORS[item.severity] || SEVERITY_COLORS.info}`}>
                {item.severity}
              </Badge>
            )}
            <button
              type="button"
              onClick={onOpenDetail}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
            >
              查看详情
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
          {contentPreview && (
            <div className="mt-2 text-xs font-mono text-muted-foreground whitespace-pre-wrap break-words">
              {contentPreview}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

export default LogEntry;
