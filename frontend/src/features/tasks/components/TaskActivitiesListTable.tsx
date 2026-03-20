import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table";
import type { AppColumnDef, DataTableQueryState } from "@/components/data-table";
import {
  formatCreatedAt,
  getActivityDurationLabel,
  getRelativeTime,
  getTaskProgressBarClassName,
  getTaskProgressPercent,
  getTaskStatusBadgeClassName,
  getTaskStatusText,
  type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { appendReturnTo } from "@/shared/utils/findingRoute";

interface TaskActivitiesListTableProps {
  activities: TaskActivityItem[];
  loading?: boolean;
  nowMs: number;
  emptyText?: string;
  pageSize?: number;
}

function getDefectSummaryLabel(activity: TaskActivityItem): string {
  if (activity.agentFindingStats) {
    const { critical, high, medium, low } = activity.agentFindingStats;
    return `严重 ${critical} / 高危 ${high} / 中危 ${medium} / 低危 ${low}`;
  }
  if (!activity.staticFindingStats) {
    return "-";
  }
  const { critical, high, medium, low } = activity.staticFindingStats;
  return `严重 ${critical} / 高危 ${high} / 中危 ${medium} / 低危 ${low}`;
}

function getColumns(
  nowMs: number,
  currentRoute: string,
): AppColumnDef<TaskActivityItem, unknown>[] {
  return [
    {
      id: "rowNumber",
      header: "序号",
      enableSorting: false,
      meta: {
        label: "序号",
        align: "center",
        width: 80,
      },
      cell: ({ row, table }) =>
        table.getState().pagination.pageIndex * table.getState().pagination.pageSize +
        row.index +
        1,
    },
    {
      accessorKey: "projectName",
      header: "项目",
      meta: {
        label: "项目",
        minWidth: 160,
        filterVariant: "text",
      },
      cell: ({ row }) => <span className="font-medium text-foreground">{row.original.projectName}</span>,
    },
    {
      id: "createdAt",
      accessorFn: (row) => row.createdAt,
      header: "创建时间",
      sortingFn: "datetime",
      meta: {
        label: "创建时间",
        minWidth: 180,
      },
      cell: ({ row }) => (
        <div className="text-sm text-muted-foreground">
          <div>
            {formatCreatedAt(row.original.createdAt)} {getRelativeTime(row.original.createdAt, nowMs)}
          </div>
        </div>
      ),
    },
    {
      id: "duration",
      accessorFn: (row) => getActivityDurationLabel(row, nowMs),
      header: "用时",
      meta: {
        label: "用时",
        width: 120,
      },
      cell: ({ row }) => {
        const rawDuration = getActivityDurationLabel(row.original, nowMs);
        const durationText = rawDuration.replace("用时：", "").replace("已运行：", "");
        return <span className="font-mono text-foreground">{durationText}</span>;
      },
    },
    {
      id: "progress",
      accessorFn: (row) => getTaskProgressPercent(row, nowMs),
      header: "进度",
      meta: {
        label: "进度",
        minWidth: 220,
      },
      cell: ({ row }) => {
        const progress = getTaskProgressPercent(row.original, nowMs);
        return (
          <div className="min-w-[210px] space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>进度</span>
              <span className="font-medium text-foreground">{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-muted/50">
              <div
                className={`h-full transition-all ${getTaskProgressBarClassName(row.original.status)}`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        );
      },
    },
    {
      accessorKey: "status",
      header: "状态",
      meta: {
        label: "状态",
        minWidth: 140,
        filterVariant: "select",
        filterOptions: [
          { label: "等待中", value: "pending" },
          { label: "运行中", value: "running" },
          { label: "已完成", value: "completed" },
          { label: "失败", value: "failed" },
        ],
      },
      cell: ({ row }) => (
        <Badge className={getTaskStatusBadgeClassName(row.original.status)}>
          {getTaskStatusText(row.original.status)}
        </Badge>
      ),
    },
    {
      id: "defects",
      accessorFn: (row) => getDefectSummaryLabel(row),
      header: "缺陷摘要",
      meta: {
        label: "缺陷摘要",
        minWidth: 260,
      },
      cell: ({ row }) => {
        const summary = getDefectSummaryLabel(row.original);
        if (summary === "-") return "-";
        return (
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            {summary}
          </span>
        );
      },
    },
    {
      id: "actions",
      header: "操作",
      enableSorting: false,
      meta: {
        label: "操作",
        width: 120,
      },
      cell: ({ row }) => (
        <Button
          asChild
          size="sm"
          variant="outline"
          className="cyber-btn-ghost h-8 px-3"
        >
          <Link to={appendReturnTo(row.original.route, currentRoute)}>详情</Link>
        </Button>
      ),
    },
  ];
}

export default function TaskActivitiesListTable({
  activities,
  loading = false,
  nowMs,
  emptyText = "暂无任务",
  pageSize = 10,
}: TaskActivitiesListTableProps) {
  const location = useLocation();
  const currentRoute = `${location.pathname}${location.search}`;

  const columns = useMemo<ColumnDef<TaskActivityItem>[]>(
    () => getColumns(nowMs, currentRoute),
    [currentRoute, nowMs],
  );

  const defaultState = useMemo<Partial<DataTableQueryState>>(
    () => ({
      pagination: {
        pageIndex: 0,
        pageSize,
      },
    }),
    [pageSize],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="min-h-0 flex-1 [&_[data-slot=table-container]]:h-full">
        <DataTable
          data={activities}
          columns={columns}
          loading={loading && activities.length === 0}
          defaultState={defaultState}
          emptyState={{
            title: emptyText,
          }}
          toolbar={{
            searchPlaceholder: "搜索项目或任务状态",
          }}
          pagination={{
            enabled: true,
            pageSizeOptions: [10, 20, 50],
            infoLabel: () => `共 ${activities.length} 条`,
          }}
          tableClassName="min-w-[1320px]"
        />
      </div>
    </div>
  );
}
