import { Link } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DataTable,
  type AppColumnDef,
  type DataTableQueryState,
} from "@/components/data-table";
import {
  appendReturnTo,
  buildFindingDetailPath,
} from "@/shared/utils/findingRoute";
import type { FindingStatus, UnifiedFindingRow } from "./viewModel";
import {
  getStaticAnalysisConfidenceBadgeClass,
  getStaticAnalysisConfidenceLabel,
  getStaticAnalysisSeverityBadgeClass,
  getStaticAnalysisSeverityLabel,
} from "./viewModel";

const YES_BADGE_CLASS = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
const NO_BADGE_CLASS = "bg-muted text-muted-foreground border-border";

function getEngineLabel(engine: UnifiedFindingRow["engine"]) {
  if (engine === "opengrep") return "Opengrep";
  if (engine === "gitleaks") return "Gitleaks";
  if (engine === "bandit") return "Bandit";
  if (engine === "phpstan") return "PHPStan";
  return "YASA";
}

function getEngineBadgeClass(engine: UnifiedFindingRow["engine"]) {
  if (engine === "opengrep") {
    return "bg-sky-500/20 text-sky-300 border-sky-500/30";
  }
  if (engine === "gitleaks") {
    return "bg-amber-500/20 text-amber-300 border-amber-500/30";
  }
  if (engine === "bandit") {
    return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
  }
  if (engine === "phpstan") {
    return "bg-violet-500/20 text-violet-300 border-violet-500/30";
  }
  return "bg-cyan-500/20 text-cyan-300 border-cyan-500/30";
}

function getColumns(input: {
  currentRoute: string;
  updatingKey: string | null;
  onToggleStatus: (row: UnifiedFindingRow, target: FindingStatus) => void;
}): AppColumnDef<UnifiedFindingRow, unknown>[] {
  return [
    {
      id: "rowNumber",
      header: "序号",
      enableSorting: false,
      meta: {
        label: "序号",
        align: "center",
        width: 72,
      },
      cell: ({ row, table }) =>
        table.getState().pagination.pageIndex * table.getState().pagination.pageSize +
        row.index +
        1,
    },
    {
      id: "engine",
      accessorFn: (row) => row.engine,
      header: "所属引擎",
      meta: {
        label: "所属引擎",
        width: 110,
        filterVariant: "select",
        filterOptions: [
          { label: "Opengrep", value: "opengrep" },
          { label: "Gitleaks", value: "gitleaks" },
          { label: "Bandit", value: "bandit" },
          { label: "PHPStan", value: "phpstan" },
          { label: "YASA", value: "yasa" },
        ],
      },
      cell: ({ row }) => (
        <Badge className={getEngineBadgeClass(row.original.engine)}>
          {getEngineLabel(row.original.engine)}
        </Badge>
      ),
    },
    {
      id: "rule",
      accessorFn: (row) => row.rule,
      header: "命中规则",
      meta: {
        label: "命中规则",
        minWidth: 220,
        filterVariant: "text",
      },
      cell: ({ row }) => <span className="text-sm break-all">{row.original.rule || "-"}</span>,
    },
    {
      id: "location",
      accessorFn: (row) => `${row.filePath}${row.line ? `:${row.line}` : ""}`,
      header: "命中位置",
      meta: {
        label: "命中位置",
        minWidth: 240,
      },
      cell: ({ row }) => (
        <span className="font-mono text-xs break-all">
          {row.original.filePath}
          {row.original.line ? `:${row.original.line}` : ""}
        </span>
      ),
    },
    {
      id: "severity",
      accessorFn: (row) => row.severity,
      header: "漏洞危害",
      sortingFn: (left, right) => right.original.severityScore - left.original.severityScore,
      meta: {
        label: "漏洞危害",
        width: 120,
        filterVariant: "select",
        filterOptions: [
          { label: "严重", value: "CRITICAL" },
          { label: "高危", value: "HIGH" },
          { label: "中危", value: "MEDIUM" },
          { label: "低危", value: "LOW" },
        ],
      },
      cell: ({ row }) => (
        <Badge className={getStaticAnalysisSeverityBadgeClass(row.original.severity)}>
          {getStaticAnalysisSeverityLabel(row.original.severity)}
        </Badge>
      ),
    },
    {
      id: "confidence",
      accessorFn: (row) => row.confidence,
      header: "置信度",
      sortingFn: (left, right) => right.original.confidenceScore - left.original.confidenceScore,
      meta: {
        label: "置信度",
        width: 110,
        filterVariant: "select",
        filterOptions: [
          { label: "高", value: "HIGH" },
          { label: "中", value: "MEDIUM" },
          { label: "低", value: "LOW" },
        ],
      },
      cell: ({ row }) => (
        <Badge className={getStaticAnalysisConfidenceBadgeClass(row.original.confidence)}>
          {getStaticAnalysisConfidenceLabel(row.original.confidence)}
        </Badge>
      ),
    },
    {
      id: "status",
      accessorFn: (row) => row.status,
      header: "处理状态",
      meta: {
        label: "处理状态",
        minWidth: 220,
        filterVariant: "select",
        filterOptions: [
          { label: "未处理", value: "open" },
          { label: "已验证", value: "verified" },
          { label: "误报", value: "false_positive" },
          { label: "已修复", value: "fixed" },
        ],
      },
      cell: ({ row }) => {
        const rowStatus = String(row.original.status || "open").toLowerCase();
        const processed = rowStatus !== "open";
        const verified = rowStatus === "verified";
        const falsePositive = rowStatus === "false_positive";
        return (
          <div className="flex items-center gap-1.5 flex-nowrap whitespace-nowrap">
            <Badge className={processed ? YES_BADGE_CLASS : NO_BADGE_CLASS}>
              处理：{processed ? "是" : "否"}
            </Badge>
            <Badge className={verified ? YES_BADGE_CLASS : NO_BADGE_CLASS}>
              验证：{verified ? "是" : "否"}
            </Badge>
            <Badge className={falsePositive ? YES_BADGE_CLASS : NO_BADGE_CLASS}>
              误报：{falsePositive ? "是" : "否"}
            </Badge>
          </div>
        );
      },
    },
    {
      id: "actions",
      header: "操作",
      enableSorting: false,
      meta: {
        label: "操作",
        minWidth: 280,
      },
      cell: ({ row }) => {
        const rowStatus = String(row.original.status || "open").toLowerCase();
        const isOpengrep = row.original.engine === "opengrep";
        const verifyUpdating = input.updatingKey === `${row.original.engine}:${row.original.id}:verified`;
        const falsePositiveUpdating =
          input.updatingKey === `${row.original.engine}:${row.original.id}:false_positive`;
        const fixedUpdating = input.updatingKey === `${row.original.engine}:${row.original.id}:fixed`;
        const detailRoute = appendReturnTo(
          buildFindingDetailPath({
            source: "static",
            taskId: row.original.taskId,
            findingId: row.original.id,
            engine: row.original.engine,
          }),
          input.currentRoute,
        );

        return (
          <div className="flex items-center gap-1.5 flex-wrap">
            <Button
              asChild
              size="sm"
              variant="outline"
              className="cyber-btn-outline h-7 px-2.5"
            >
              <Link to={detailRoute}>详情</Link>
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
              disabled={Boolean(input.updatingKey)}
              onClick={() => input.onToggleStatus(row.original, "verified")}
            >
              {verifyUpdating ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : rowStatus === "verified" ? (
                "取消验证"
              ) : (
                "验证"
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="cyber-btn-outline h-7 px-2.5 border-amber-500/40 text-amber-500 hover:bg-amber-500/10"
              disabled={Boolean(input.updatingKey)}
              onClick={() => input.onToggleStatus(row.original, "false_positive")}
            >
              {falsePositiveUpdating ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : rowStatus === "false_positive" ? (
                "取消误报"
              ) : (
                "误报"
              )}
            </Button>
            {isOpengrep ? null : (
              <Button
                size="sm"
                variant="outline"
                className="cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                disabled={Boolean(input.updatingKey)}
                onClick={() => input.onToggleStatus(row.original, "fixed")}
              >
                {fixedUpdating ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : rowStatus === "fixed" ? (
                  "取消修复"
                ) : (
                  "修复"
                )}
              </Button>
            )}
          </div>
        );
      },
    },
  ];
}

export default function StaticAnalysisFindingsTable({
  currentRoute,
  loadingInitial,
  rows,
  state,
  onStateChange,
  updatingKey,
  onToggleStatus,
}: {
  currentRoute: string;
  loadingInitial: boolean;
  rows: UnifiedFindingRow[];
  state: DataTableQueryState;
  onStateChange: (state: DataTableQueryState) => void;
  updatingKey: string | null;
  onToggleStatus: (row: UnifiedFindingRow, target: FindingStatus) => void;
}) {
  const columns = getColumns({
    currentRoute,
    updatingKey,
    onToggleStatus,
  }) as ColumnDef<UnifiedFindingRow>[];

  return (
    <DataTable
      data={rows}
      columns={columns}
      state={state}
      onStateChange={onStateChange}
      loading={loadingInitial}
      emptyState={{
        title: "暂无符合条件的漏洞",
        description: loadingInitial ? undefined : "可尝试调整筛选条件或稍后刷新",
      }}
      toolbar={{
        searchPlaceholder: "搜索规则、位置或状态",
        filters: [
          {
            columnId: "engine",
            label: "所属引擎",
            variant: "select",
            options: [
              { label: "Opengrep", value: "opengrep" },
              { label: "Gitleaks", value: "gitleaks" },
              { label: "Bandit", value: "bandit" },
              { label: "PHPStan", value: "phpstan" },
              { label: "YASA", value: "yasa" },
            ],
          },
          {
            columnId: "status",
            label: "状态筛选",
            variant: "select",
            options: [
              { label: "未处理", value: "open" },
              { label: "已验证", value: "verified" },
              { label: "误报", value: "false_positive" },
              { label: "已修复", value: "fixed" },
            ],
          },
          {
            columnId: "severity",
            label: "漏洞危害",
            variant: "select",
            options: [
              { label: "严重", value: "CRITICAL" },
              { label: "高危", value: "HIGH" },
              { label: "中危", value: "MEDIUM" },
              { label: "低危", value: "LOW" },
            ],
          },
          {
            columnId: "confidence",
            label: "置信度筛选",
            variant: "select",
            options: [
              { label: "高", value: "HIGH" },
              { label: "中", value: "MEDIUM" },
              { label: "低", value: "LOW" },
            ],
          },
        ],
        showColumnVisibility: false,
      }}
      pagination={{
        enabled: true,
        pageSizeOptions: [10, 20, 50],
        infoLabel: ({ table, filteredCount }) =>
          `共 ${filteredCount.toLocaleString()} 条，第 ${
            table.getState().pagination.pageIndex + 1
          } / ${Math.max(1, table.getPageCount())} 页`,
      }}
      className="border border-border rounded-md"
      tableClassName="min-w-[1400px]"
    />
  );
}
