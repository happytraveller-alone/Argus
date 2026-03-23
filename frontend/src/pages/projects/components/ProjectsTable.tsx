import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table";
import type { AppColumnDef } from "@/components/data-table";
import type { ProjectsPageRowViewModel } from "../types";
import { PROJECT_ACTION_BTN_SUBTLE } from "../constants";

interface ProjectsTableProps {
  rows: ProjectsPageRowViewModel[];
  onCreateScan: (projectId: string) => void;
}

// const EXECUTION_COLUMNS = [
//   {
//     key: "completed",
//     label: "已完成",
//     cellClassName: "text-center",
//   },
//   {
//     key: "running",
//     label: "进行中",
//     cellClassName: "text-center",
//   },
// ] as const;

const VULNERABILITY_COLUMNS = [
  {
    key: "critical",
    label: "严重",
    cellClassName: "text-center",
  },
  {
    key: "high",
    label: "高危",
    cellClassName: "text-center",
  },
  {
    key: "medium",
    label: "中危",
    cellClassName: "text-center",
  },
  {
    key: "low",
    label: "低危",
    cellClassName: "text-center",
  },
] as const;

const METRIC_CHIP_CLASSNAME =
  "inline-flex min-w-[3.25rem] items-center justify-center rounded-full border px-3 py-1 text-center leading-none shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]";
// const EXECUTION_METRIC_CHIP_CLASSNAME =
//   "border-sky-500/20 bg-sky-500/8 text-foreground";
const VULNERABILITY_METRIC_CHIP_CLASSNAMES = {
  critical: "border-rose-500/30 bg-rose-500/12 text-rose-100",
  high: "border-orange-500/28 bg-orange-500/12 text-orange-100",
  medium: "border-amber-500/30 bg-amber-500/12 text-amber-100",
  low: "border-slate-400/30 bg-slate-400/12 text-slate-100",
} as const;
const METRIC_CHIP_VALUE_CLASSNAME =
  "text-center font-semibold tabular-nums text-[18px]";
const HEADER_CELL_CLASSNAME =
  "border-b-2 border-border/95 bg-muted/75 text-center font-mono text-[15px] font-semibold uppercase tracking-[0.18em] text-foreground/80";
const BODY_CELL_CLASSNAME = "border-b-2 border-border/95";
const DIVIDER_CELL_CLASSNAME = "border-r-2 border-border/90";
const SECTION_DIVIDER_CLASSNAME = "border-l-2 border-border/95";
const METRIC_GROUP_CLASSNAME =
  "flex items-center justify-center gap-2.5 whitespace-nowrap";
const METRIC_GROUP_ITEM_CLASSNAME =
  "inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/40 px-2 py-1";
const METRIC_GROUP_LABEL_CLASSNAME =
  "text-[14px] font-medium tracking-[0.08em] text-muted-foreground";
const METRIC_EMPTY_TEXT_CLASSNAME =
  "text-[14px] font-medium tracking-[0.08em] text-muted-foreground";

function renderMetricChip(value: number, tone: string, chipClassName: string) {
  return (
    <span
      data-project-metric-tone={tone}
      className={`${METRIC_CHIP_CLASSNAME} ${chipClassName}`}
    >
      <span className={METRIC_CHIP_VALUE_CLASSNAME}>{value}</span>
    </span>
  );
}

function buildColumns(
  onCreateScan: (projectId: string) => void,
): AppColumnDef<ProjectsPageRowViewModel, unknown>[] {
  return [
    {
      accessorKey: "name",
      header: "项目名称",
      meta: {
        label: "项目",
        plainHeader: true,
        minWidth: 176,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <Link
          to={row.original.detailPath}
          state={row.original.detailState}
          title={row.original.name}
          className="mx-auto block max-w-[180px] truncate text-center text-[18px] font-semibold text-foreground transition-colors hover:text-primary"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      id: "sizeText",
      accessorFn: (row) => row.sizeText,
      header: "项目大小",
      meta: {
        label: "大小",
        plainHeader: true,
        minWidth: 132,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center text-[17px] text-muted-foreground`,
      },
      cell: ({ row }) => (
        <span title={row.original.metricsStatusMessage ?? undefined}>
          {row.original.sizeText}
        </span>
      ),
    },
    // {
    //   id: "execution",
    //   header: "执行任务",
    //   meta: {
    //     label: "执行任务",
    //     plainHeader: true,
    //     minWidth: 228,
    //     headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
    //     cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
    //   },
    //   cell: ({ row }) => (
    //     <div
    //       data-project-metric-group="execution"
    //       className={METRIC_GROUP_CLASSNAME}
    //       title={
    //         row.original.metricsStatus !== "ready"
    //           ? row.original.metricsStatusMessage ?? undefined
    //           : undefined
    //       }
    //     >
    //       {EXECUTION_COLUMNS.map((column) => (
    //         <span
    //           key={column.key}
    //           data-project-metric-item={column.key}
    //           className={METRIC_GROUP_ITEM_CLASSNAME}
    //         >
    //           <span className={METRIC_GROUP_LABEL_CLASSNAME}>{column.label}</span>
    //           {renderMetricChip(
    //             row.original.executionStats[column.key],
    //             "execution",
    //             EXECUTION_METRIC_CHIP_CLASSNAME,
    //           )}
    //         </span>
    //       ))}
    //     </div>
    //   ),
    // },
    {
      id: "vulnerabilities",
      header: "发现潜在漏洞",
      meta: {
        label: "发现漏洞",
        plainHeader: true,
        minWidth: 420,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      cell: ({ row }) => {
        const visibleColumns = VULNERABILITY_COLUMNS.filter(
          (column) => row.original.vulnerabilityStats[column.key] > 0,
        );

        return (
          <div
            data-project-metric-group="vulnerabilities"
            className={METRIC_GROUP_CLASSNAME}
            title={
              row.original.metricsStatus !== "ready"
                ? row.original.metricsStatusMessage ?? undefined
                : undefined
            }
          >
            {visibleColumns.length > 0 ? (
              visibleColumns.map((column) => (
                <span
                  key={column.key}
                  data-project-metric-item={column.key}
                  className={METRIC_GROUP_ITEM_CLASSNAME}
                >
                  <span className={METRIC_GROUP_LABEL_CLASSNAME}>{column.label}</span>
                  {renderMetricChip(
                    row.original.vulnerabilityStats[column.key],
                    column.key,
                    VULNERABILITY_METRIC_CHIP_CLASSNAMES[column.key],
                  )}
                </span>
              ))
            ) : (
              <span className={METRIC_EMPTY_TEXT_CLASSNAME}>暂未发现漏洞</span>
            )}
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
        plainHeader: true,
        minWidth: 320,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
        cellClassName: `${BODY_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <div className="flex items-center justify-center gap-2 whitespace-nowrap text-[16px]">
          <Button
            asChild
            size="sm"
            variant="outline"
            className="cyber-btn-ghost h-8 px-3"
          >
            <Link to={row.original.detailPath} state={row.original.detailState}>
              查看详情
            </Link>
          </Button>
          {row.original.actions.canBrowseCode ? (
            <Button
              asChild
              size="sm"
              variant="outline"
              className="cyber-btn-ghost h-8 px-3 hover:bg-sky-500/10 hover:text-sky-200 hover:border-sky-500/30"
            >
              <Link
                to={row.original.actions.browseCodePath}
                state={row.original.actions.browseCodeState}
              >
                代码浏览
              </Link>
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="cyber-btn-ghost h-8 px-3"
              disabled
              title={row.original.actions.browseCodeDisabledReason ?? undefined}
              aria-label={`代码浏览 ${row.original.name}（${row.original.actions.browseCodeDisabledReason ?? "暂不可用"}）`}
            >
              代码浏览
            </Button>
          )}
          <Button
            size="sm"
            className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 px-3`}
            onClick={() => onCreateScan(row.original.id)}
            disabled={!row.original.actions.canCreateScan}
          >
            创建扫描
          </Button>
        </div>
      ),
    },
  ];
}

export default function ProjectsTable({
  rows,
  onCreateScan,
}: ProjectsTableProps) {
  const columns = buildColumns(onCreateScan) as ColumnDef<ProjectsPageRowViewModel>[];

  return (
    <DataTable
      data={rows}
      columns={columns}
      toolbar={false}
      pagination={false}
      tableClassName="min-w-[1280px]"
      emptyState={{
        title: "暂无项目",
      }}
    />
  );
}
