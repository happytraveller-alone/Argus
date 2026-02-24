import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, ArrowLeft, ExternalLink, Search, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import FindingCodeWindow from "./FindingCodeWindow";

export type RealtimeMergedFindingItem = {
  id: string;
  fingerprint: string;
  title: string;
  display_title?: string | null;
  description?: string | null;
  severity: string;
  vulnerability_type: string;
  file_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  cwe_id?: string | null;
  code_snippet?: string | null;
  code_context?: string | null;
  function_trigger_flow?: string[] | null;
  reachability_file?: string | null;
  reachability_function?: string | null;
  reachability_function_start_line?: number | null;
  reachability_function_end_line?: number | null;
  context_start_line?: number | null;
  context_end_line?: number | null;
  verification_evidence?: string | null;
  timestamp?: string | null;
  is_verified: boolean;
};

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

const SEVERITY_LABEL_ZH: Record<string, string> = {
  critical: "严重",
  high: "高危",
  medium: "中危",
  low: "低危",
  info: "信息",
};

function normalizeSeverity(value: string): string {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "info";
  if (key in SEVERITY_ORDER) return key;
  return "info";
}

function severityToZh(value: string): string {
  const key = normalizeSeverity(value);
  return SEVERITY_LABEL_ZH[key] || SEVERITY_LABEL_ZH.info;
}

function formatLocation(item: RealtimeMergedFindingItem): string {
  const path = String(item.file_path || "").trim();
  const line = item.line_start;
  if (path && typeof line === "number" && Number.isFinite(line)) {
    return `${path}:${line}`;
  }
  if (path) return path;
  return "-";
}

function getRootCauseParagraph(item: RealtimeMergedFindingItem): string {
  const description = String(item.description || "").trim();
  if (description) return description;
  return "后端暂未返回漏洞根因文段。";
}

function pickRealtimeCode(item: RealtimeMergedFindingItem): {
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
} | null {
  const context = String(item.code_context || "").trim();
  if (context) {
    return {
      code: context,
      lineStart: item.context_start_line ?? item.line_start ?? null,
      lineEnd: item.context_end_line ?? item.line_end ?? null,
    };
  }
  const snippet = String(item.code_snippet || "").trim();
  if (snippet) {
    return {
      code: snippet,
      lineStart: item.line_start ?? null,
      lineEnd: item.line_end ?? null,
    };
  }
  return null;
}

export default function RealtimeFindingsPanel(props: {
  items: RealtimeMergedFindingItem[];
  isRunning: boolean;
  onClear: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [severity, setSeverity] = useState<"all" | string>("all");
  const [detailItem, setDetailItem] = useState<RealtimeMergedFindingItem | null>(null);
  const detailText = useMemo(
    () => (detailItem ? getRootCauseParagraph(detailItem) : ""),
    [detailItem],
  );

  const counts = useMemo(() => {
    return { total: props.items.length };
  }, [props.items]);

  const severityCounts = useMemo(() => {
    const next = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      info: 0,
    };
    for (const item of props.items) {
      const key = normalizeSeverity(item.severity);
      if (key === "critical") next.critical += 1;
      else if (key === "high") next.high += 1;
      else if (key === "medium") next.medium += 1;
      else if (key === "low") next.low += 1;
      else next.info += 1;
    }
    return next;
  }, [props.items]);

  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    const sorted = [...props.items].sort((a, b) => {
      const aKey = normalizeSeverity(a.severity);
      const bKey = normalizeSeverity(b.severity);
      const aOrder = SEVERITY_ORDER[aKey] ?? 99;
      const bOrder = SEVERITY_ORDER[bKey] ?? 99;
      if (aOrder !== bOrder) return aOrder - bOrder;
      // prefer latest seen first
      return String(b.timestamp || "").localeCompare(String(a.timestamp || ""));
    });

    return sorted.filter((item) => {
      const sevKey = normalizeSeverity(item.severity);
      const okSeverity = severity === "all" || sevKey === severity;
      if (!okSeverity) return false;
      if (!key) return true;
      return (
        String(item.title || "").toLowerCase().includes(key) ||
        String(item.vulnerability_type || "").toLowerCase().includes(key) ||
        String(item.file_path || "").toLowerCase().includes(key)
      );
    });
  }, [props.items, keyword, severity]);

  return (
    <div className="h-full flex flex-col border border-border rounded-xl bg-card/70 overflow-hidden">
      <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold">潜在缺陷</span>
            <Badge variant="outline" className="text-[11px]">
              {counts.total}
            </Badge>
            <Badge
              variant="outline"
              className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
            >
              全部已验证
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

          <Button
            size="sm"
            variant="outline"
            onClick={props.onClear}
            disabled={props.items.length === 0}
          >
            <Trash2 className="w-3.5 h-3.5 mr-2" />
            清空
          </Button>
        </div>

        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索标题/类型/文件..."
              className="pl-9"
            />
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={severity === "all" ? "default" : "outline"}
              onClick={() => setSeverity("all")}
            >
              全部
            </Button>
            <Button
              size="sm"
              variant={severity === "critical" ? "default" : "outline"}
              onClick={() => setSeverity("critical")}
            >
              严重
            </Button>
            <Button
              size="sm"
              variant={severity === "high" ? "default" : "outline"}
              onClick={() => setSeverity("high")}
            >
              高危
            </Button>
            <Button
              size="sm"
              variant={severity === "medium" ? "default" : "outline"}
              onClick={() => setSeverity("medium")}
            >
              中危
            </Button>
            <Button
              size="sm"
              variant={severity === "low" ? "default" : "outline"}
              onClick={() => setSeverity("low")}
            >
              低危
            </Button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {severityCounts.critical > 0 ? (
            <button type="button" onClick={() => setSeverity("critical")}>
              <Badge
                variant="outline"
                className={`text-[11px] border ${SEVERITY_BADGE_CLASS.critical} ${
                  severity === "critical" ? "ring-1 ring-primary/40" : ""
                }`}
              >
                严重 {severityCounts.critical}
              </Badge>
            </button>
          ) : null}
          {severityCounts.high > 0 ? (
            <button type="button" onClick={() => setSeverity("high")}>
              <Badge
                variant="outline"
                className={`text-[11px] border ${SEVERITY_BADGE_CLASS.high} ${
                  severity === "high" ? "ring-1 ring-primary/40" : ""
                }`}
              >
                高危 {severityCounts.high}
              </Badge>
            </button>
          ) : null}
          {severityCounts.medium > 0 ? (
            <button type="button" onClick={() => setSeverity("medium")}>
              <Badge
                variant="outline"
                className={`text-[11px] border ${SEVERITY_BADGE_CLASS.medium} ${
                  severity === "medium" ? "ring-1 ring-primary/40" : ""
                }`}
              >
                中危 {severityCounts.medium}
              </Badge>
            </button>
          ) : null}
          {severityCounts.low > 0 ? (
            <button type="button" onClick={() => setSeverity("low")}>
              <Badge
                variant="outline"
                className={`text-[11px] border ${SEVERITY_BADGE_CLASS.low} ${
                  severity === "low" ? "ring-1 ring-primary/40" : ""
                }`}
              >
                低危 {severityCounts.low}
              </Badge>
            </button>
          ) : null}
          {severityCounts.info > 0 ? (
            <button type="button" onClick={() => setSeverity("info")}>
              <Badge
                variant="outline"
                className={`text-[11px] border ${SEVERITY_BADGE_CLASS.info} ${
                  severity === "info" ? "ring-1 ring-primary/40" : ""
                }`}
              >
                信息 {severityCounts.info}
              </Badge>
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {filtered.length === 0 ? (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            <div className="flex flex-col items-center gap-2 text-center px-6">
              <AlertTriangle className="w-5 h-5 opacity-60" />
              <span className="text-sm">
                {props.isRunning ? "等待新缺陷..." : "暂无缺陷"}
              </span>
            </div>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="p-3 space-y-2">
              {filtered.map((item) => {
                const sevKey = normalizeSeverity(item.severity);
                return (
                  <div
                    key={item.id}
                    className="rounded-lg border border-border bg-background/40 hover:border-primary/30 transition-colors px-3 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge
                            className={`border text-[11px] ${SEVERITY_BADGE_CLASS[sevKey] || SEVERITY_BADGE_CLASS.info}`}
                          >
                            {severityToZh(sevKey)}
                          </Badge>
                          <span className="text-sm font-semibold break-words line-clamp-2">
                            {item.display_title || item.title || "未命名缺陷"}
                          </span>
                        </div>

                        <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
                          <span>类型: {item.vulnerability_type || "-"}</span>
                          <span>定位: {formatLocation(item)}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Badge
                          variant="outline"
                          className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                        >
                          已验证
                        </Badge>

                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2.5 text-[11px]"
                          onClick={() => setDetailItem(item)}
                        >
                          查看详情
                          <ExternalLink className="w-3.5 h-3.5 ml-1.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </div>

      <Dialog
        open={detailItem !== null}
        onOpenChange={(open) => {
          if (!open) setDetailItem(null);
        }}
      >
        <DialogContent className="max-w-3xl h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader className="border-b border-border pb-3">
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="flex items-center gap-2">
                <ExternalLink className="w-4 h-4" />
                缺陷详情
              </DialogTitle>
              <button
                type="button"
                onClick={() => setDetailItem(null)}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                返回
              </button>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto custom-scrollbar py-4 space-y-4">
            {detailItem ? (
              <section className="rounded-lg border border-border bg-card/70 p-3.5 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">
                    {severityToZh(detailItem.severity)}
                  </Badge>
                </div>

                <h3 className="text-sm font-semibold break-words">
                  {detailItem.display_title || detailItem.title || "未命名缺陷"}
                </h3>

                <div className="space-y-2 pt-2">
                  <div className="text-xs font-semibold text-muted-foreground">漏洞详情（根因）</div>
                  <div className="text-[11px] text-muted-foreground">
                    根因文段由后端统一生成并下发，前端仅做展示。
                  </div>
                  <div className="text-sm bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words leading-6">
                    {detailText}
                  </div>
                </div>

                {(() => {
                  const code = pickRealtimeCode(detailItem);
                  if (!code) return null;
                  return (
                    <div className="pt-2">
                      <FindingCodeWindow
                        code={code.code}
                        filePath={detailItem.file_path}
                        lineStart={code.lineStart}
                        lineEnd={code.lineEnd}
                        title="命中代码"
                      />
                    </div>
                  );
                })()}
              </section>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
