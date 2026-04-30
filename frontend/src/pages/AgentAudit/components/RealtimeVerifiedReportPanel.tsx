import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Download, FileText, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type { RealtimeMergedFindingItem } from "./RealtimeFindingsPanel";

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const SEVERITY_BADGE_CLASS: Record<string, string> = {
  critical: "bg-rose-500/20 text-rose-600 dark:text-rose-300 border-rose-500/40",
  high: "bg-orange-500/20 text-orange-600 dark:text-orange-300 border-orange-500/40",
  medium: "bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/40",
  low: "bg-sky-500/20 text-sky-600 dark:text-sky-300 border-sky-500/40",
  info: "bg-zinc-500/20 text-zinc-700 dark:text-zinc-300 border-zinc-500/40",
};

function normalizeSeverity(value: string): string {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "info";
  if (key in SEVERITY_ORDER) return key;
  return "info";
}

function toSafeFilename(value: string): string {
  const text = String(value || "").trim();
  if (!text) return "task";
  return text.replace(/[^\w.-]+/g, "_").slice(0, 60) || "task";
}

function downloadTextFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function formatLocation(item: AgentFinding): string {
  if (!item.file_path) return "未定位文件";
  if (item.line_start && item.line_end && item.line_end !== item.line_start) {
    return `${item.file_path}:${item.line_start}-${item.line_end}`;
  }
  if (item.line_start) return `${item.file_path}:${item.line_start}`;
  return item.file_path;
}

export default function RealtimeVerifiedReportPanel(props: {
  taskId: string;
  taskName?: string | null;
  realtimeVerified: RealtimeMergedFindingItem[];
  persistedVerifiedFindings: AgentFinding[];
  isRunning: boolean;
  onRefresh: () => void;
  onOpenDetail: (finding: AgentFinding) => void;
  onOpenExportDialog: () => void;
}) {
  const displayPersisted = props.persistedVerifiedFindings.length > 0;
  const stats = useMemo(() => {
    const counts: Record<string, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    };
    if (displayPersisted) {
      for (const f of props.persistedVerifiedFindings) {
        const key = normalizeSeverity(f.severity || "info");
        counts[key] = (counts[key] || 0) + 1;
      }
    } else {
      for (const f of props.realtimeVerified) {
        const key = normalizeSeverity(f.severity || "info");
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    return counts;
  }, [displayPersisted, props.persistedVerifiedFindings, props.realtimeVerified]);

  const sortedPersisted = useMemo(() => {
    return [...props.persistedVerifiedFindings].sort((a, b) => {
      const aKey = normalizeSeverity(a.severity || "info");
      const bKey = normalizeSeverity(b.severity || "info");
      const aOrder = SEVERITY_ORDER[aKey] ?? 99;
      const bOrder = SEVERITY_ORDER[bKey] ?? 99;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [props.persistedVerifiedFindings]);

  const sortedRealtime = useMemo(() => {
    return [...props.realtimeVerified].sort((a, b) => {
      const aKey = normalizeSeverity(a.severity || "info");
      const bKey = normalizeSeverity(b.severity || "info");
      const aOrder = SEVERITY_ORDER[aKey] ?? 99;
      const bOrder = SEVERITY_ORDER[bKey] ?? 99;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return String(b.timestamp || "").localeCompare(String(a.timestamp || ""));
    });
  }, [props.realtimeVerified]);

  const handleExport = (format: "json" | "markdown") => {
    const base = `verified_report_${toSafeFilename(props.taskName || props.taskId.slice(0, 8))}_${new Date().toISOString().slice(0, 10)}`;
    if (format === "json") {
      if (displayPersisted) {
        downloadTextFile(
          JSON.stringify(sortedPersisted, null, 2),
          `${base}.json`,
          "application/json",
        );
      } else {
        downloadTextFile(
          JSON.stringify(sortedRealtime, null, 2),
          `${base}.json`,
          "application/json",
        );
      }
      return;
    }

    const lines: string[] = [];
    lines.push(`# 已验证漏洞报告`);
    lines.push("");
    lines.push(`- 任务: ${props.taskName || props.taskId}`);
    lines.push(`- 生成时间: ${new Date().toLocaleString("zh-CN")}`);
    lines.push(
      `- 已验证数量: ${displayPersisted ? sortedPersisted.length : sortedRealtime.length}`,
    );
    lines.push("");
    lines.push(`## 概览`);
    lines.push(`- Critical: ${stats.critical || 0}`);
    lines.push(`- High: ${stats.high || 0}`);
    lines.push(`- Medium: ${stats.medium || 0}`);
    lines.push(`- Low: ${stats.low || 0}`);
    lines.push(`- Info: ${stats.info || 0}`);
    lines.push("");
    lines.push(`## 清单`);
    if (displayPersisted) {
      for (const f of sortedPersisted) {
        const sevKey = normalizeSeverity(f.severity || "info");
        lines.push("");
        lines.push(`### [${sevKey.toUpperCase()}] ${f.title || "未命名漏洞"}`);
        lines.push(`- 类型: ${f.vulnerability_type || "-"}`);
        lines.push(`- 位置: ${formatLocation(f)}`);
        if (f.reachability_file || f.reachability_function) {
          lines.push(
            `- 可达性证据: ${[f.reachability_file, f.reachability_function]
              .filter(Boolean)
              .join(" :: ")}`,
          );
        }
        if (f.description) {
          lines.push(`- 描述: ${f.description}`);
        }
        if (f.verification_evidence) {
          lines.push("");
          lines.push("验证证据:");
          lines.push("```text");
          lines.push(String(f.verification_evidence));
          lines.push("```");
        }
        if (f.suggestion) {
          lines.push("");
          lines.push("修复建议:");
          lines.push("```text");
          lines.push(String(f.suggestion));
          lines.push("```");
        }
        if (f.fix_code) {
          lines.push("");
          lines.push("修复代码:");
          lines.push("```text");
          lines.push(String(f.fix_code));
          lines.push("```");
        }
      }
    } else {
      for (const f of sortedRealtime) {
        const sevKey = normalizeSeverity(f.severity || "info");
        lines.push("");
        lines.push(`### [${sevKey.toUpperCase()}] ${f.title || "未命名漏洞"}`);
        lines.push(`- 类型: ${f.vulnerability_type || "-"}`);
        const loc =
          f.file_path && f.line_start ? `${f.file_path}:${f.line_start}` : (f.file_path || "-");
        lines.push(`- 位置: ${loc}`);
      }
      lines.push("");
      lines.push("> 注：当前为实时事件视图，详细证据/上下文需等待结果入库后刷新。");
    }

    downloadTextFile(lines.join("\n"), `${base}.md`, "text/markdown");
  };

  return (
    <div className="h-full flex flex-col border border-border rounded-xl bg-card/70 overflow-hidden">
      <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
            <span className="text-sm font-semibold">实时漏洞报告（已验证）</span>
            <Badge variant="outline" className="text-[11px]">
              {displayPersisted ? sortedPersisted.length : sortedRealtime.length}
            </Badge>
            {props.isRunning ? (
              <Badge
                variant="outline"
                className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
              >
                实时
              </Badge>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={props.onRefresh}>
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              刷新
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline">
                  <Download className="w-3.5 h-3.5 mr-2" />
                  导出
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleExport("json")}>
                  导出为 JSON
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport("markdown")}>
                  导出为 Markdown
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={props.onOpenExportDialog}>
                  打开报告导出
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {(["critical", "high", "medium", "low", "info"] as const).map((key) => (
            <Badge
              key={key}
              className={`border text-[11px] ${SEVERITY_BADGE_CLASS[key] || SEVERITY_BADGE_CLASS.info}`}
            >
              {key.toUpperCase()}: {stats[key] || 0}
            </Badge>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {displayPersisted ? (
          sortedPersisted.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <div className="text-sm">
                {props.isRunning ? "等待已验证结果..." : "暂无已验证漏洞"}
              </div>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-3 space-y-2">
                {sortedPersisted.map((item) => {
                  const sevKey = normalizeSeverity(item.severity || "info");
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => props.onOpenDetail(item)}
                      className="w-full text-left rounded-lg border border-border bg-background/40 hover:border-primary/30 transition-colors px-3 py-2.5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <Badge
                              className={`border text-[11px] ${SEVERITY_BADGE_CLASS[sevKey] || SEVERITY_BADGE_CLASS.info}`}
                            >
                              {sevKey.toUpperCase()}
                            </Badge>
                            <span className="text-sm font-semibold break-words line-clamp-2">
                              {item.title || "未命名漏洞"}
                            </span>
                          </div>

                          <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
                            <span>类型: {item.vulnerability_type || "-"}</span>
                            <span>定位: {formatLocation(item)}</span>
                            {item.reachability_file || item.reachability_function ? (
                              <span>
                                证据: {[
                                  item.reachability_file,
                                  item.reachability_function,
                                ]
                                  .filter(Boolean)
                                  .join(" :: ")}
                              </span>
                            ) : null}
                          </div>
                        </div>

                        <Badge
                          variant="outline"
                          className="text-[11px] border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10"
                        >
                          已验证
                        </Badge>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          )
        ) : (
          sortedRealtime.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <div className="text-sm">
                {props.isRunning ? "等待已验证结果..." : "暂无已验证漏洞"}
              </div>
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="p-3 space-y-2">
                {sortedRealtime.map((item) => {
                  const sevKey = normalizeSeverity(item.severity || "info");
                  const loc =
                    item.file_path && item.line_start
                      ? `${item.file_path}:${item.line_start}`
                      : item.file_path || "-";
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        props.onRefresh();
                        toast.info("已触发刷新，详细报告需等待结果入库后查看");
                      }}
                      className="w-full text-left rounded-lg border border-border bg-background/40 hover:border-primary/30 transition-colors px-3 py-2.5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <Badge
                              className={`border text-[11px] ${SEVERITY_BADGE_CLASS[sevKey] || SEVERITY_BADGE_CLASS.info}`}
                            >
                              {sevKey.toUpperCase()}
                            </Badge>
                            <span className="text-sm font-semibold break-words line-clamp-2">
                              {item.title || "未命名漏洞"}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
                            <span>类型: {item.vulnerability_type || "-"}</span>
                            <span>定位: {loc}</span>
                          </div>
                        </div>

                        <Badge
                          variant="outline"
                          className="text-[11px] border-emerald-500/40 text-emerald-700 dark:text-emerald-300 bg-emerald-500/10"
                        >
                          已验证
                        </Badge>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          )
        )}
      </div>
    </div>
  );
}
