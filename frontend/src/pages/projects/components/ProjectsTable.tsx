import * as React from "react";
import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table";
import type { AppColumnDef } from "@/components/data-table";
import type { ProjectSeverityBreakdown } from "@/features/projects/services/projectCardPreview";
import type { ProjectsPageRowViewModel } from "../types";
import { PROJECT_ACTION_BTN_SUBTLE } from "../constants";

interface ProjectsTableProps {
  rows: ProjectsPageRowViewModel[];
  onCreateScan: (projectId: string) => void;
  onDeleteProject: (projectId: string, projectName: string) => void;
  deletingProjectId?: string | null;
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
  "border-b-2 border-border/95 bg-muted/75 text-center font-mono text-[14px] font-semibold uppercase tracking-[0.18em] text-foreground/80";
const HEADER_CONTENT_CLASSNAME = "text-[14px]";
const BODY_CELL_CLASSNAME = "border-b-2 border-border/95";
const DIVIDER_CELL_CLASSNAME = "border-r-2 border-border/90";
const SECTION_DIVIDER_CLASSNAME = "border-l-2 border-border/95";
const METRIC_GROUP_CLASSNAME =
  "flex items-center justify-center";
const METRIC_TRIGGER_CLASSNAME =
  "inline-flex items-center justify-center rounded-full bg-transparent p-0 text-center transition-transform duration-150 hover:scale-[1.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:cursor-default disabled:opacity-100";
const METRIC_POPOVER_CLASSNAME =
  "absolute left-1/2 top-[calc(100%+0.75rem)] z-30 w-[19rem] -translate-x-1/2 rounded-2xl border border-border/80 bg-background/95 p-4 text-left shadow-[0_24px_80px_rgba(15,23,42,0.42)] backdrop-blur-sm transition-all duration-150";
const METRIC_POPOVER_HIDDEN_CLASSNAME =
  "pointer-events-none translate-y-1 opacity-0";
const METRIC_POPOVER_VISIBLE_CLASSNAME =
  "translate-y-0 opacity-100";
const METRIC_POPOVER_HEADER_CLASSNAME =
  "mb-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-foreground/55";
const METRIC_POPOVER_GRID_CLASSNAME = "grid grid-cols-2 gap-2";
const METRIC_POPOVER_ITEM_CLASSNAME =
  "rounded-2xl border border-border/70 bg-muted/20 px-3 py-2";
const METRIC_POPOVER_ITEM_LABEL_CLASSNAME =
  "mb-2 block text-[12px] font-medium tracking-[0.08em] text-muted-foreground";

type MetricGroupKey = "vulnerabilities" | "ai-verified";

interface MetricSummaryCellProps {
  groupKey: MetricGroupKey;
  label: string;
  stats: ProjectSeverityBreakdown;
  metricsStatus: ProjectsPageRowViewModel["metricsStatus"];
  metricsStatusMessage: string | null;
  toneClassName: string;
}

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

function MetricSummaryCell({
  groupKey,
  label,
  stats,
  metricsStatus,
  metricsStatusMessage,
  toneClassName,
}: MetricSummaryCellProps) {
  const wrapperRef = React.useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = React.useState(false);
  const canInteract = metricsStatus === "ready";

  React.useEffect(() => {
    if (!open) return undefined;

    function handlePointerDown(event: MouseEvent | TouchEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!wrapperRef.current?.contains(target)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  function openPopover() {
    if (canInteract) {
      setOpen(true);
    }
  }

  function closePopover() {
    setOpen(false);
  }

  function togglePopover() {
    if (canInteract) {
      setOpen((current) => !current);
    }
  }

  function handleBlur(event: React.FocusEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && wrapperRef.current?.contains(nextTarget)) {
      return;
    }
    closePopover();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!canInteract) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      togglePopover();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closePopover();
    }
  }

  return (
    <div
      ref={wrapperRef}
      data-project-metric-group={groupKey}
      className={`${METRIC_GROUP_CLASSNAME} relative`}
      title={!canInteract ? metricsStatusMessage ?? undefined : undefined}
      onMouseEnter={openPopover}
      onMouseLeave={closePopover}
      onBlur={handleBlur}
    >
      <button
        type="button"
        data-project-metric-trigger={groupKey}
        className={METRIC_TRIGGER_CLASSNAME}
        aria-label={`${label} ${stats.total}`}
        aria-expanded={canInteract ? open : false}
        aria-haspopup={canInteract ? "dialog" : undefined}
        onClick={togglePopover}
        onFocus={openPopover}
        onKeyDown={handleKeyDown}
        disabled={!canInteract}
      >
        {renderMetricChip(stats.total, groupKey, toneClassName)}
      </button>
      <div
        data-project-metric-popover={groupKey}
        data-state={open && canInteract ? "open" : "closed"}
        aria-hidden={!open || !canInteract}
        className={`${METRIC_POPOVER_CLASSNAME} ${open && canInteract
          ? METRIC_POPOVER_VISIBLE_CLASSNAME
          : METRIC_POPOVER_HIDDEN_CLASSNAME
          }`}
      >
        <div className={METRIC_POPOVER_HEADER_CLASSNAME}>{label}</div>
        <div className={METRIC_POPOVER_GRID_CLASSNAME}>
          {VULNERABILITY_COLUMNS.map((column) => (
            <div
              key={`${groupKey}-${column.key}`}
              data-project-metric-item={column.key}
              className={METRIC_POPOVER_ITEM_CLASSNAME}
            >
              <span className={METRIC_POPOVER_ITEM_LABEL_CLASSNAME}>
                {column.label}
              </span>
              {renderMetricChip(
                stats[column.key],
                column.key,
                VULNERABILITY_METRIC_CHIP_CLASSNAMES[column.key],
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function buildColumns(
  onCreateScan: (projectId: string) => void,
  onDeleteProject: (projectId: string, projectName: string) => void,
  deletingProjectId?: string | null,
): AppColumnDef<ProjectsPageRowViewModel, unknown>[] {
  return [
    {
      accessorKey: "name",
      header: "项目名称",
      meta: {
        label: "项目",
        minWidth: 148,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <Link
          to={row.original.detailPath}
          state={row.original.detailState}
          title={row.original.name}
          className="mx-auto block max-w-[180px] truncate text-center text-[16px] font-semibold text-foreground transition-colors hover:text-primary"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      id: "sizeText",
      accessorFn: (row) => row.sizeBytes,
      header: "项目大小",
      meta: {
        label: "大小",
        minWidth: 110,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center text-[16px] text-muted-foreground`,
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
      accessorFn: (row) => row.vulnerabilityStats.total,
      header: "发现潜在漏洞",
      meta: {
        label: "发现漏洞",
        minWidth: 120,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <MetricSummaryCell
          groupKey="vulnerabilities"
          label="发现漏洞"
          stats={row.original.vulnerabilityStats}
          metricsStatus={row.original.metricsStatus}
          metricsStatusMessage={row.original.metricsStatusMessage}
          toneClassName="border-amber-500/30 bg-amber-500/12 text-amber-100"
        />
      ),
    },
    {
      id: "aiVerified",
      accessorFn: (row) => row.aiVerifiedStats.total,
      header: "AI验证漏洞",
      meta: {
        label: "AI验证",
        minWidth: 115,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <MetricSummaryCell
          groupKey="ai-verified"
          label="AI验证漏洞"
          stats={row.original.aiVerifiedStats}
          metricsStatus={row.original.metricsStatus}
          metricsStatusMessage={row.original.metricsStatusMessage}
          toneClassName="border-sky-500/30 bg-sky-500/12 text-sky-100"
        />
      ),
    },
    {
      id: "actions",
      header: "操作",
      enableSorting: false,
      meta: {
        label: "操作",
        plainHeader: true,
        minWidth: 244,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME} text-center`,
      },
      cell: ({ row }) => (
        <div className="flex flex-wrap items-center justify-center gap-2 text-[16px]">
          <Button
            asChild
            size="lg"
            variant="outline"
            className="cyber-btn-ghost h-8 px-2.5"
          >
            <Link to={row.original.detailPath} state={row.original.detailState}>
              查看详情
            </Link>
          </Button>
          {row.original.actions.canBrowseCode ? (
            <Button
              asChild
              size="lg"
              variant="outline"
              className="cyber-btn-ghost h-8 px-2.5 hover:bg-sky-500/10 hover:text-sky-200 hover:border-sky-500/30"
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
              className="cyber-btn-ghost h-8 px-2.5"
              disabled
              title={row.original.actions.browseCodeDisabledReason ?? undefined}
              aria-label={`代码浏览 ${row.original.name}（${row.original.actions.browseCodeDisabledReason ?? "暂不可用"}）`}
            >
              代码浏览
            </Button>
          )}
          <Button
            size="lg"
            className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 px-2.5`}
            onClick={() => onCreateScan(row.original.id)}
            disabled={!row.original.actions.canCreateScan}
          >
            创建扫描
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="cyber-btn-ghost h-8 px-2.5 border-rose-500/35 text-rose-200 hover:border-rose-500/55 hover:bg-rose-500/10 hover:text-rose-100"
            onClick={() =>
              onDeleteProject(row.original.id, row.original.name)
            }
            disabled={
              !row.original.actions.canDelete ||
              deletingProjectId === row.original.id
            }
          >
            {deletingProjectId === row.original.id ? "删除中..." : "删除项目"}
          </Button>
        </div>
      ),
    },
  ];
}

export default function ProjectsTable({
  rows,
  onCreateScan,
  onDeleteProject,
  deletingProjectId = null,
}: ProjectsTableProps) {
  const columns = buildColumns(
    onCreateScan,
    onDeleteProject,
    deletingProjectId,
  ) as ColumnDef<ProjectsPageRowViewModel>[];

  return (
    <DataTable
      data={rows}
      columns={columns}
      toolbar={false}
      pagination={false}
      className="overflow-visible"
      containerClassName="overflow-visible"
      tableContainerClassName="overflow-visible border-0 rounded-none"
      emptyState={{
        title: "暂无项目",
      }}
    />
  );
}
