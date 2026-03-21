import { memo } from "react";
import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  EVENT_LOG_GRID_TEMPLATE,
  LOG_TYPE_CONFIG,
} from "../constants";
import type { LogEntryProps } from "../types";
import { sanitizeAuditText } from "../utils";
import {
  localizeAuditText,
} from "../localization";
import { isToolEvidenceCapableTool } from "../toolEvidence";
import type { LogItem } from "../types";

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
  return sanitizeAuditText(localizeAuditText(title));
}

function formatCodeWindowLocation(entry: {
  filePath: string;
  startLine: number;
  endLine: number;
}): string {
  if (entry.startLine === entry.endLine) {
    return `${entry.filePath}:${entry.startLine}`;
  }
  return `${entry.filePath}:${entry.startLine}-${entry.endLine}`;
}

function buildToolListSummary(item: LogItem): string {
  const primaryTitle = String(item.tool?.name || "").trim() || formatTitle(item.title);

  if (item.tool?.status === "running") {
    return `${primaryTitle} · 正在执行`;
  }

  const evidence = item.toolEvidence;
  if (evidence?.renderType === "search_hits") {
    const count = evidence.entries.length;
    return `${primaryTitle} · ${count} 条命中`;
  }

  if (evidence?.renderType === "code_window") {
    const first = evidence.entries[0];
    const location = first ? formatCodeWindowLocation(first) : "详情可查看代码窗口";
    return `${primaryTitle} · 代码窗口 · ${location}`;
  }

  if (evidence?.renderType === "execution_result") {
    const first = evidence.entries[0];
    const exitCode = first?.exitCode;
    return typeof exitCode === "number"
      ? `${primaryTitle} · 执行结果 · 退出码 ${exitCode}`
      : `${primaryTitle} · 执行结果已生成`;
  }

  if (item.tool?.status === "failed") {
    return `${primaryTitle} · 执行失败，详情可查看原始结果`;
  }

  if (item.tool?.status === "cancelled") {
    return `${primaryTitle} · 已取消，详情可查看原始结果`;
  }

  return `${primaryTitle} · 已完成，详情可查看原始结果`;
}

export const LogEntry = memo(function LogEntry({
  item,
  onOpenDetail,
  anchorId,
  highlighted = false,
}: LogEntryProps) {
  const config = LOG_TYPE_CONFIG[item.type] || LOG_TYPE_CONFIG.info;
  const typeLabel = LOG_TYPE_LABELS[item.type] || "日志";
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
  const formattedTitle =
    formatTitle(item.title) || sanitizeAuditText(localizeAuditText(item.title));
  const sanitizedContent = item.content
    ? sanitizeAuditText(localizeAuditText(item.content))
    : "";
  const contentPreview = sanitizedContent
    ? sanitizedContent.slice(0, 220) + (sanitizedContent.length > 220 ? "..." : "")
    : "";
  const normalizedTitle = formattedTitle.replace(/\.\.\.$/, "").trim();
  const normalizedPreview = contentPreview.replace(/\.\.\.$/, "").trim();
  const isToolRow = item.type === "tool" && Boolean(item.tool?.name);
  const toolListSummary = isToolRow ? buildToolListSummary(item) : null;
  const isEvidenceTool = isToolEvidenceCapableTool(item.tool?.name);
  const shouldRenderPreview =
    Boolean(contentPreview) &&
    !isToolRow &&
    normalizedPreview !== formattedTitle &&
    normalizedPreview !== normalizedTitle &&
    !(normalizedTitle && normalizedPreview.startsWith(normalizedTitle));
  const summaryText = isToolRow
    ? toolListSummary || formattedTitle
    : formattedTitle;
  const summaryTitle = isToolRow
    ? toolListSummary || formattedTitle
    : shouldRenderPreview
      ? `${formattedTitle} · ${contentPreview}`
      : formattedTitle;
  const typeBadgeClass =
    item.type === "error"
      ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
      : item.type === "tool"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
        : item.type === "progress"
          ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
          : "border-border/70 bg-background/60 text-muted-foreground";
  return (
    <div
      id={anchorId}
      className={
        highlighted
          ? "bg-primary/5 ring-1 ring-primary/50 transition-colors"
          : "transition-colors"
      }
    >
      <div className="px-2 py-2.5 hover:bg-muted/35">
        <div
          className="flex flex-col gap-2 md:grid md:items-center md:gap-3"
          style={{ gridTemplateColumns: EVENT_LOG_GRID_TEMPLATE }}
        >
          <div className="text-xs font-mono text-muted-foreground tabular-nums">
            {item.time}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-muted-foreground/80">{typeIcon}</span>
            <Badge
              variant="outline"
              className={`h-6 rounded-full px-2 text-[10px] font-medium ${typeBadgeClass}`}
            >
              {typeLabel}
            </Badge>
          </div>

          <div className="min-w-0">
            <p
              className="line-clamp-1 break-words text-sm font-semibold leading-5 text-foreground"
              title={summaryTitle}
            >
              {summaryText}
            </p>
            {!isToolRow && shouldRenderPreview ? (
              <p className="sr-only">{contentPreview}</p>
            ) : null}
            {isEvidenceTool && !item.toolEvidence && item.tool?.status !== "running" ? (
              <span className="sr-only">原始结果</span>
            ) : null}
          </div>

          <div className="min-w-0">
            {item.phaseLabel ? (
              <span className="block truncate text-xs text-primary" title={item.phaseLabel}>
                {item.phaseLabel}
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">-</span>
            )}
          </div>

          <div className="flex justify-start md:justify-start">
            <button
              type="button"
              onClick={onOpenDetail}
              className="inline-flex items-center gap-1.5 rounded-md border border-border/70 px-2.5 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
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
