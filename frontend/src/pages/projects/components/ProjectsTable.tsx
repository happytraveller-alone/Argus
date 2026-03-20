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

const EXECUTION_COLUMNS = [
  {
    key: "completed",
    label: "已完成",
    cellClassName: "text-center",
  },
  {
    key: "running",
    label: "进行中",
    cellClassName: "text-center",
  },
] as const;

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
  "inline-block min-w-[2ch] text-center leading-none";
const METRIC_CHIP_VALUE_CLASSNAME =
  "text-center font-semibold tabular-nums text-[18px]";
const HEADER_CELL_CLASSNAME =
  "border-b border-border/60 bg-muted/75 text-center font-mono text-[15px] font-semibold uppercase tracking-[0.18em] text-foreground/80";
const SUBHEADER_CELL_CLASSNAME =
  "border-b border-border/85 bg-muted/40 text-center font-mono text-[14px] font-medium tracking-[0.14em] text-muted-foreground";
const BODY_CELL_CLASSNAME = "border-b border-border/85";
const DIVIDER_CELL_CLASSNAME = "border-r border-border/75";
const SECTION_DIVIDER_CLASSNAME = "border-l border-border/85";

function buildColumns(
  onCreateScan: (projectId: string) => void,
): AppColumnDef<ProjectsPageRowViewModel, unknown>[] {
  return [
    {
      id: "project",
      header: "项目",
      meta: {
        label: "项目",
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
      },
      columns: [
        {
          accessorKey: "name",
          header: "项目名称",
          meta: {
            label: "项目名称",
            plainHeader: true,
            minWidth: 176,
            headerClassName: `${SUBHEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
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
      ],
    },
    {
      id: "size",
      header: "大小",
      meta: {
        label: "大小",
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
      },
      columns: [
        {
          id: "sizeText",
          accessorFn: (row) => row.sizeText,
          header: "项目大小",
          meta: {
            label: "项目大小",
            plainHeader: true,
            minWidth: 132,
            headerClassName: `${SUBHEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
            cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center text-[17px] text-muted-foreground`,
          },
          cell: ({ row }) => (
            <span title={row.original.metricsStatusMessage ?? undefined}>
              {row.original.sizeText}
            </span>
          ),
        },
      ],
    },
    {
      id: "execution",
      header: "执行任务",
      meta: {
        label: "执行任务",
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      columns: EXECUTION_COLUMNS.map((column) => ({
        id: column.key,
        accessorFn: (row: ProjectsPageRowViewModel) => row.executionStats[column.key],
        header: column.label,
        meta: {
          label: column.label,
          plainHeader: true,
          headerClassName: `${SUBHEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
          cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} ${column.cellClassName}`,
          align: "center",
        },
        cell: ({ row }) => (
          <span
            data-project-metric-chip={column.key}
            className={METRIC_CHIP_CLASSNAME}
            title={
              row.original.metricsStatus !== "ready"
                ? row.original.metricsStatusMessage ?? undefined
                : undefined
            }
          >
            <span className={METRIC_CHIP_VALUE_CLASSNAME}>
              {row.original.executionStats[column.key]}
            </span>
          </span>
        ),
      })),
    },
    {
      id: "vulnerabilities",
      header: "发现漏洞",
      meta: {
        label: "发现漏洞",
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      columns: VULNERABILITY_COLUMNS.map((column, index) => ({
        id: column.key,
        accessorFn: (row: ProjectsPageRowViewModel) => row.vulnerabilityStats[column.key],
        header: column.label,
        meta: {
          label: column.label,
          plainHeader: true,
          headerClassName: `${SUBHEADER_CELL_CLASSNAME} ${
            index === VULNERABILITY_COLUMNS.length - 1 ? "" : DIVIDER_CELL_CLASSNAME
          }`,
          cellClassName: `${BODY_CELL_CLASSNAME} ${
            index === VULNERABILITY_COLUMNS.length - 1 ? "" : DIVIDER_CELL_CLASSNAME
          } ${column.cellClassName}`,
          align: "center",
        },
        cell: ({ row }) => (
          <span
            data-project-metric-chip={column.key}
            className={METRIC_CHIP_CLASSNAME}
            title={
              row.original.metricsStatus !== "ready"
                ? row.original.metricsStatusMessage ?? undefined
                : undefined
            }
          >
            <span className={METRIC_CHIP_VALUE_CLASSNAME}>
              {row.original.vulnerabilityStats[column.key]}
            </span>
          </span>
        ),
      })),
    },
    {
      id: "actionsGroup",
      header: "操作",
      meta: {
        label: "操作",
        headerClassName: `${HEADER_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
      },
      columns: [
        {
          id: "actions",
          header: "操作",
          enableSorting: false,
          meta: {
            label: "操作",
            plainHeader: true,
            minWidth: 320,
            headerClassName: `${SUBHEADER_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
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
      ],
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
