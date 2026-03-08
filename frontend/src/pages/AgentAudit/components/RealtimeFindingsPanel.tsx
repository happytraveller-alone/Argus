import { useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Search,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { FindingsViewFilters } from "../types";
import {
  buildFindingTableState,
  shouldResetFindingPage,
} from "../detailViewModel";
import FindingCodeWindow from "./FindingCodeWindow";
import FindingNarrativeMarkdown from "./FindingNarrativeMarkdown";
import { collectRawEvidenceEntries } from "./findingNarrative";

export type RealtimeVerificationProgress = "pending" | "verified";
export type RealtimeDisplaySeverity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "invalid";

export type RealtimeMergedFindingItem = {
  id: string;
  merge_key?: string;
  fingerprint: string;
  title: string;
  display_title?: string | null;
  description?: string | null;
  description_markdown?: string | null;
  severity: string;
  display_severity: RealtimeDisplaySeverity;
  verification_progress: RealtimeVerificationProgress;
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
  confidence?: number | null;
  timestamp?: string | null;
  is_verified: boolean;
};

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

function getRawEvidenceFromRealtimeItem(item: RealtimeMergedFindingItem) {
  return collectRawEvidenceEntries({
    description: item.description,
    verification_evidence: item.verification_evidence,
    function_trigger_flow: item.function_trigger_flow,
    reachability_file: item.reachability_file,
    reachability_function: item.reachability_function,
    reachability_function_start_line: item.reachability_function_start_line,
    reachability_function_end_line: item.reachability_function_end_line,
  });
}

function getSeverityBadgeClass(severity: string): string {
  if (severity === "critical") {
    return "border-rose-500/30 bg-rose-500/15 text-rose-300";
  }
  if (severity === "high") {
    return "border-amber-500/30 bg-amber-500/15 text-amber-300";
  }
  if (severity === "medium") {
    return "border-sky-500/30 bg-sky-500/15 text-sky-300";
  }
  if (severity === "low") {
    return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
  }
  return "border-border bg-muted text-muted-foreground";
}

function getConfidenceBadgeClass(confidenceLabel: string): string {
  if (confidenceLabel === "高") {
    return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
  }
  if (confidenceLabel === "中") {
    return "border-amber-500/30 bg-amber-500/15 text-amber-300";
  }
  if (confidenceLabel === "低") {
    return "border-sky-500/30 bg-sky-500/15 text-sky-300";
  }
  return "border-border bg-muted text-muted-foreground";
}

function getVerificationBadgeClass(verification: string): string {
  if (verification === "verified") {
    return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
  }
  return "border-amber-500/30 bg-amber-500/15 text-amber-300";
}

export default function RealtimeFindingsPanel(props: {
  items: RealtimeMergedFindingItem[];
  isRunning: boolean;
  filters: FindingsViewFilters;
  onFiltersChange: (next: FindingsViewFilters) => void;
}) {
  const [page, setPage] = useState(1);
  const [detailItem, setDetailItem] = useState<RealtimeMergedFindingItem | null>(null);
  const previousFiltersRef = useRef<FindingsViewFilters>(props.filters);

  useEffect(() => {
    if (shouldResetFindingPage(previousFiltersRef.current, props.filters)) {
      setPage(1);
    }
    previousFiltersRef.current = props.filters;
  }, [props.filters]);

  const tableState = useMemo(
    () =>
      buildFindingTableState({
        items: props.items,
        filters: props.filters,
        page,
        pageSize: 10,
      }),
    [page, props.filters, props.items],
  );

  useEffect(() => {
    if (page !== tableState.page) {
      setPage(tableState.page);
    }
  }, [page, tableState.page]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card/70">
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">漏洞列表</span>
            <Badge variant="outline" className="text-[11px]">
              {props.items.length}
            </Badge>
            {props.isRunning ? (
              <Badge
                variant="outline"
                className="border-emerald-500/40 bg-emerald-500/10 text-[11px] text-emerald-300"
              >
                实时更新
              </Badge>
            ) : null}
          </div>
          <div className="text-[11px] text-muted-foreground">
            数据按严重度、置信度与位置排序
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_160px_160px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={props.filters.keyword}
              onChange={(event) =>
                props.onFiltersChange({
                  ...props.filters,
                  keyword: event.target.value,
                })
              }
              placeholder="搜索类型 / 标题 / 文件路径"
              className="cyber-input pl-9"
            />
          </div>
          <Select
            value={props.filters.severity}
            onValueChange={(value) =>
              props.onFiltersChange({
                ...props.filters,
                severity: value,
              })
            }
          >
            <SelectTrigger className="cyber-input">
              <SelectValue placeholder="严重度" />
            </SelectTrigger>
            <SelectContent className="cyber-dialog border-border">
              <SelectItem value="all">全部严重度</SelectItem>
              <SelectItem value="critical">严重</SelectItem>
              <SelectItem value="high">高危</SelectItem>
              <SelectItem value="medium">中危</SelectItem>
              <SelectItem value="low">低危</SelectItem>
              <SelectItem value="invalid">无效</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={props.filters.verification}
            onValueChange={(value) =>
              props.onFiltersChange({
                ...props.filters,
                verification: value,
              })
            }
          >
            <SelectTrigger className="cyber-input">
              <SelectValue placeholder="验证状态" />
            </SelectTrigger>
            <SelectContent className="cyber-dialog border-border">
              <SelectItem value="all">全部验证状态</SelectItem>
              <SelectItem value="pending">待验证</SelectItem>
              <SelectItem value="verified">已验证</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto custom-scrollbar">
        {tableState.rows.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <div className="flex flex-col items-center gap-2 px-6 text-center">
              <AlertTriangle className="h-5 w-5 opacity-60" />
              <span className="text-sm">
                {props.isRunning ? "等待新的漏洞结果..." : "暂无符合条件的漏洞"}
              </span>
            </div>
          </div>
        ) : (
          <div className="p-3">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[64px] whitespace-nowrap">序号</TableHead>
                  <TableHead className="w-[22%] whitespace-nowrap">类型</TableHead>
                  <TableHead className="w-[34%] whitespace-nowrap">路径</TableHead>
                  <TableHead className="w-[10%] whitespace-nowrap">危害</TableHead>
                  <TableHead className="w-[10%] whitespace-nowrap">置信度</TableHead>
                  <TableHead className="w-[10%] whitespace-nowrap">状态</TableHead>
                  <TableHead className="w-[14%] whitespace-nowrap text-center">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tableState.rows.map((row, index) => {
                  const active = detailItem?.id === row.id;
                  return (
                    <TableRow key={row.id} className={active ? "bg-primary/5" : undefined}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {(tableState.pageStart + index + 1).toLocaleString()}
                      </TableCell>
                      <TableCell className="align-top">
                        <div className="min-w-0">
                          <div
                            className="truncate text-sm font-medium text-foreground"
                            title={row.typeLabel}
                          >
                            {row.typeLabel}
                          </div>
                          <div
                            className="mt-1 truncate text-xs text-muted-foreground"
                            title={row.title}
                          >
                            {row.title}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell
                        className="font-mono text-xs text-muted-foreground whitespace-normal break-all"
                        title={row.location}
                      >
                        {row.location}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[11px] ${getSeverityBadgeClass(row.severity)}`}
                        >
                          {row.severityLabel}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[11px] ${getConfidenceBadgeClass(row.confidenceLabel)}`}
                        >
                          {row.confidenceLabel}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-[11px] ${getVerificationBadgeClass(row.verification)}`}
                        >
                          {row.verificationLabel}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 px-2.5"
                          onClick={() => setDetailItem(row.raw as RealtimeMergedFindingItem)}
                        >
                          详情
                          <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-border bg-card px-4 py-3">
        <div className="text-xs text-muted-foreground">
          共 {tableState.totalRows.toLocaleString()} 条，当前显示 {tableState.rows.length.toLocaleString()} 条
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8 px-2.5"
            disabled={tableState.page <= 1}
            onClick={() => setPage((value) => Math.max(value - 1, 1))}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            上一页
          </Button>
          <span className="text-xs text-muted-foreground">
            第 {tableState.page} / {tableState.totalPages} 页
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8 px-2.5"
            disabled={tableState.page >= tableState.totalPages}
            onClick={() =>
              setPage((value) => Math.min(value + 1, tableState.totalPages))
            }
          >
            下一页
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <Dialog
        open={detailItem !== null}
        onOpenChange={(open) => {
          if (!open) setDetailItem(null);
        }}
      >
        <DialogContent className="flex h-[80vh] max-w-3xl flex-col overflow-hidden">
          <DialogHeader className="border-b border-border pb-3">
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="flex items-center gap-2">
                <ExternalLink className="h-4 w-4" />
                缺陷详情
              </DialogTitle>
              <button
                type="button"
                onClick={() => setDetailItem(null)}
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:border-primary/40 hover:text-primary"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                返回
              </button>
            </div>
          </DialogHeader>

          <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto py-4">
            {detailItem ? (
              <section className="space-y-2 rounded-lg border border-border bg-card/70 p-3.5">
                <h3 className="text-sm font-semibold break-words">
                  {detailItem.display_title || detailItem.title || "未命名缺陷"}
                </h3>

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
                        highlightStartLine={detailItem.line_start ?? code.lineStart}
                        highlightEndLine={detailItem.line_end ?? code.lineEnd}
                        focusLine={detailItem.line_start ?? code.lineStart}
                        title="命中代码"
                      />
                    </div>
                  );
                })()}

                <div className="space-y-2 pt-2">
                  <div className="text-xs font-semibold text-muted-foreground">
                    漏洞详情（根因）
                  </div>
                  <FindingNarrativeMarkdown
                    finding={{
                      description: detailItem.description,
                      description_markdown: detailItem.description_markdown,
                      code_context: detailItem.code_context,
                      code_snippet: detailItem.code_snippet,
                      file_path: detailItem.file_path,
                      line_start: detailItem.line_start,
                      line_end: detailItem.line_end,
                      function_trigger_flow: detailItem.function_trigger_flow,
                      verification_evidence: detailItem.verification_evidence,
                      reachability_file: detailItem.reachability_file,
                      reachability_function: detailItem.reachability_function,
                      reachability_function_start_line:
                        detailItem.reachability_function_start_line,
                      reachability_function_end_line:
                        detailItem.reachability_function_end_line,
                    }}
                    className="rounded-md border border-border bg-background p-3"
                  />

                  <Collapsible className="rounded-md border border-border bg-card/60">
                    <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground">
                      <span>原始证据</span>
                      <ChevronDown className="h-4 w-4" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-2 px-3 pb-3">
                      {getRawEvidenceFromRealtimeItem(detailItem).map((item) => (
                        <div key={item.key} className="space-y-1">
                          <div className="font-mono text-[11px] text-muted-foreground">
                            {item.label}
                            {item.truncated ? " (已截断至 2000 字)" : ""}
                          </div>
                          <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-background p-2 text-xs font-mono">
                            {item.value}
                          </pre>
                        </div>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              </section>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
