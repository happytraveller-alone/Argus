import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
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
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Search,
} from "lucide-react";
import type { FindingsViewFilters } from "../types";
import {
  AGENT_AUDIT_FINDINGS_PAGE_SIZE,
  buildFindingTableState,
  shouldResetFindingPage,
} from "../detailViewModel";
import { buildAgentFindingDetailRoute } from "@/shared/utils/findingRoute";

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
  taskId: string;
  items: RealtimeMergedFindingItem[];
  isRunning: boolean;
  filters: FindingsViewFilters;
  onFiltersChange: (next: FindingsViewFilters) => void;
}) {
  const location = useLocation();
  const [page, setPage] = useState(1);
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
        pageSize: AGENT_AUDIT_FINDINGS_PAGE_SIZE,
      }),
    [page, props.filters, props.items],
  );

  useEffect(() => {
    if (page !== tableState.page) {
      setPage(tableState.page);
    }
  }, [page, tableState.page]);

  const currentRoute = `${location.pathname}${location.search}`;

  return (
    <div className="cyber-card flex h-full flex-col p-4 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm font-semibold">漏洞列表</span>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_160px_160px]">
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-0 flex w-11 items-center justify-center text-muted-foreground">
            <Search className="h-4 w-4" />
          </span>
          <Input
            value={props.filters.keyword}
            onChange={(event) =>
              props.onFiltersChange({
                ...props.filters,
                keyword: event.target.value,
              })
            }
            placeholder="搜索漏洞类型 / 标题 / 文件"
            className="cyber-input h-10 pl-11 pr-3 text-sm"
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

      <div className="flex items-center justify-between gap-2 flex-wrap text-xs text-muted-foreground">
        <span>
          符合筛选 {tableState.totalRows.toLocaleString()} 条，当前第 {tableState.page} / {tableState.totalPages} 页
        </span>
        <span>排序规则：危害降序；同危害按置信度降序；其后按路径+行号升序</span>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border">
        <div className="h-full overflow-auto custom-scrollbar">
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
            <Table className="min-w-[1180px]">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">序号</TableHead>
                  <TableHead className="min-w-[260px]">类型 / 标题</TableHead>
                  <TableHead className="min-w-[260px]">命中位置</TableHead>
                  <TableHead className="w-[120px]">漏洞危害</TableHead>
                  <TableHead className="w-[110px]">置信度</TableHead>
                  <TableHead className="w-[120px]">处理状态</TableHead>
                  <TableHead className="w-[160px] text-center">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tableState.rows.map((row, index) => {
                  const detailRoute = buildAgentFindingDetailRoute({
                    taskId: props.taskId,
                    findingId: row.id,
                    currentRoute,
                  });

                  return (
                    <TableRow key={row.id}>
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
                        <Button asChild type="button" size="sm" variant="outline" className="cyber-btn-ghost h-8 px-3">
                          <Link to={detailRoute}>
                            详情
                            <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs text-muted-foreground">
          共 {tableState.totalRows.toLocaleString()} 条，当前显示 {tableState.rows.length.toLocaleString()} 条
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8"
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
            className="cyber-btn-outline h-8"
            disabled={tableState.page >= tableState.totalPages}
            onClick={() => setPage((value) => Math.min(value + 1, tableState.totalPages))}
          >
            下一页
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
