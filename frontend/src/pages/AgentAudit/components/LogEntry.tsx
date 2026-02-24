import { memo } from "react";
import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { LOG_TYPE_CONFIG, SEVERITY_COLORS } from "../constants";
import type { LogEntryProps, ToolStatus } from "../types";
import { sanitizeAuditText } from "../utils";

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

const TOOL_STATUS_LABELS: Record<ToolStatus, string> = {
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const TOOL_STATUS_CLASS: Record<ToolStatus, string> = {
  running: "border-amber-500/40 text-amber-600 dark:text-amber-300 bg-amber-500/10",
  completed: "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10",
  failed: "border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10",
  cancelled: "border-zinc-500/40 text-zinc-600 dark:text-zinc-300 bg-zinc-500/10",
};

function formatTitle(title: string): string {
  return sanitizeAuditText(title);
}

export const LogEntry = memo(function LogEntry({
  item,
  onOpenDetail,
  anchorId,
  highlighted = false,
}: LogEntryProps) {
  const config = LOG_TYPE_CONFIG[item.type] || LOG_TYPE_CONFIG.info;
  const typeLabel = LOG_TYPE_LABELS[item.type] || "日志";
  const toolStatus = item.tool?.status;
  const isProgressCompleted =
    item.type === "progress" && item.progressStatus === "completed";
  const typeIcon =
    item.type === "progress" ? (
      isProgressCompleted ? (
        <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
      ) : (
        <Loader2 className="w-4 h-4 text-cyan-600 dark:text-cyan-400 animate-spin" />
      )
    ) : (
      config.icon
    );
  const formattedTitle = formatTitle(item.title) || sanitizeAuditText(item.title);
  const sanitizedContent = item.content ? sanitizeAuditText(item.content) : "";
  const contentPreview = sanitizedContent
    ? sanitizedContent.slice(0, 220) + (sanitizedContent.length > 220 ? "..." : "")
    : "";
  const normalizedTitle = formattedTitle.replace(/\.\.\.$/, "").trim();
  const normalizedPreview = contentPreview.replace(/\.\.\.$/, "").trim();
  const shouldRenderPreview =
    Boolean(contentPreview) &&
    normalizedPreview !== formattedTitle &&
    normalizedPreview !== normalizedTitle &&
    !(normalizedTitle && normalizedPreview.startsWith(normalizedTitle));

  return (
    <div
      id={anchorId}
      className={
        highlighted
          ? "rounded-lg ring-2 ring-primary/60 transition-shadow"
          : ""
      }
    >
      <div className="rounded-lg border border-border bg-card/80 px-3.5 py-3 hover:border-primary/30 transition-colors">
        <div className="flex flex-col gap-2 md:grid md:grid-cols-[88px_72px_minmax(0,1fr)_130px_112px_auto] md:items-start md:gap-3">
          <div className="text-xs font-mono text-muted-foreground tabular-nums">
            {item.time}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground/80">{typeIcon}</span>
            <span className="text-xs font-mono uppercase text-muted-foreground tracking-wide">
              {typeLabel}
            </span>
          </div>

          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground leading-5 line-clamp-2 break-words">
              {formattedTitle}
            </p>
            {shouldRenderPreview && (
              <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap break-words line-clamp-2">
                {contentPreview}
              </p>
            )}
          </div>

          <div className="min-w-0">
            {item.agentName ? (
              <Badge
                variant="outline"
                className="h-6 px-2 text-[11px] uppercase tracking-wide border-primary/40 text-primary bg-primary/10 max-w-full truncate"
              >
                {item.agentName}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">-</span>
            )}
          </div>

          <div className="min-w-0">
            {toolStatus ? (
              <Badge
                variant="outline"
                className={`h-6 px-2 text-[11px] font-medium ${TOOL_STATUS_CLASS[toolStatus]}`}
              >
                {toolStatus === "running" && (
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                )}
                {TOOL_STATUS_LABELS[toolStatus]}
              </Badge>
            ) : item.type === "progress" ? (
              <Badge
                variant="outline"
                className={`h-6 px-2 text-[11px] font-medium ${
                  isProgressCompleted
                    ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                    : "border-cyan-500/40 text-cyan-600 dark:text-cyan-300 bg-cyan-500/10"
                }`}
              >
                {isProgressCompleted ? "已完成" : "进行中"}
              </Badge>
            ) : item.severity ? (
              <Badge
                className={`h-6 px-2 text-[11px] uppercase ${SEVERITY_COLORS[item.severity] || SEVERITY_COLORS.info}`}
              >
                {item.severity}
              </Badge>
            ) : (
              <span className="text-xs text-muted-foreground">-</span>
            )}
          </div>

          <div className="flex justify-start md:justify-end">
            <button
              type="button"
              onClick={onOpenDetail}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
            >
              查看详情
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

export default LogEntry;
