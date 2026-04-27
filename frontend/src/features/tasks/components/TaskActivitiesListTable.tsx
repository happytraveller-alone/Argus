import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table";
import type {
	AppColumnDef,
	DataTableQueryState,
} from "@/components/data-table";
import {
	formatCreatedAt,
	getActivityDurationLabel,
	getRelativeTime,
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

const TASK_ACTIVITIES_TABLE_HEADER_CONTENT_CLASSNAME = "text-sm";
const TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME = "text-sm";
const DEFECT_SUMMARY_ITEMS = [
	{ key: "critical", label: "严重" },
	{ key: "high", label: "高危" },
	{ key: "medium", label: "中危" },
	{ key: "low", label: "低危" },
] as const;

function createTaskActivitiesTableMeta(
	meta: AppColumnDef<TaskActivityItem, unknown>["meta"],
) {
	return {
		headerContentClassName: TASK_ACTIVITIES_TABLE_HEADER_CONTENT_CLASSNAME,
		...meta,
	};
}

function getDefectSummaryLabel(activity: TaskActivityItem): string {
	const stats = activity.agentFindingStats ?? activity.staticFindingStats;
	if (!stats) {
		return "-";
	}

	const visibleItems = DEFECT_SUMMARY_ITEMS.flatMap(({ key, label }) => {
		const count = stats[key];
		return count > 0 ? [`${label} ${count}`] : [];
	});

	return visibleItems.length > 0 ? visibleItems.join(" / ") : "-";
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
			meta: createTaskActivitiesTableMeta({
				label: "序号",
				align: "center",
				width: 64,
			}),
			cell: ({ row, table }) => {
				const pageRowIndex = table
					.getRowModel()
					.rows.findIndex((r) => r.id === row.id);
				return (
					table.getState().pagination.pageIndex *
						table.getState().pagination.pageSize +
					pageRowIndex +
					1
				);
			},
		},
		{
			accessorKey: "projectName",
			header: "项目",
			meta: createTaskActivitiesTableMeta({
				label: "项目",
				minWidth: 132,
				filterVariant: "text",
			}),
			cell: ({ row }) => (
				<span
					className={`${TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME} font-medium text-foreground`}
				>
					{row.original.projectName}
				</span>
			),
		},
		{
			id: "createdAt",
			accessorFn: (row) => row.createdAt,
			header: "创建时间",
			sortingFn: "datetime",
			meta: createTaskActivitiesTableMeta({
				label: "创建时间",
				width: 128,
				maxWidth: 136,
			}),
			cell: ({ row }) => (
				<div className="text-base leading-tight text-muted-foreground">
					<div className="truncate" title={formatCreatedAt(row.original.createdAt)}>
						{formatCreatedAt(row.original.createdAt)}
					</div>
					<div className="text-sm text-muted-foreground/80">
						{getRelativeTime(row.original.createdAt, nowMs)}
					</div>
				</div>
			),
		},
		{
			id: "duration",
			accessorFn: (row) => getActivityDurationLabel(row, nowMs),
			header: "用时",
			meta: createTaskActivitiesTableMeta({
				label: "用时",
				width: 88,
			}),
			cell: ({ row }) => {
				const rawDuration = getActivityDurationLabel(row.original, nowMs);
				const durationText = rawDuration
					.replace("用时：", "")
					.replace("已运行：", "");
				return (
					<span
						className={`${TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME} font-mono text-foreground`}
					>
						{durationText}
					</span>
				);
			},
		},
		{
			accessorKey: "status",
			header: "状态",
			meta: createTaskActivitiesTableMeta({
				label: "状态",
				minWidth: 132,
				filterVariant: "select",
				filterOptions: [
					{ label: "等待中", value: "pending" },
					{ label: "运行中", value: "running" },
					{ label: "已完成", value: "completed" },
					{ label: "失败", value: "failed" },
				],
			}),
			cell: ({ row }) => {
				const status = String(row.original.status || "")
					.trim()
					.toLowerCase();
				const progress = getTaskProgressPercent(row.original, nowMs);

				return (
					<div className="flex items-center">
						<Badge
							className={`${getTaskStatusBadgeClassName(
								row.original.status,
							)} max-w-full gap-2 px-2.5`}
						>
							<span>{getTaskStatusText(row.original.status)}</span>
							{status === "running" ? (
								<span className="rounded-[2px] border border-current/20 bg-black/10 px-1.5 py-0.5 text-[13px] leading-none tracking-normal">
									{progress}%
								</span>
							) : null}
						</Badge>
					</div>
				);
			},
		},
		{
			id: "defects",
			accessorFn: (row) => getDefectSummaryLabel(row),
			header: "缺陷摘要",
			meta: createTaskActivitiesTableMeta({
				label: "缺陷摘要",
				minWidth: 192,
				maxWidth: 240,
			}),
			cell: ({ row }) => {
				const summary = getDefectSummaryLabel(row.original);
				if (summary === "-") return "-";
				return (
					<span
						className={`block truncate ${TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME} text-muted-foreground`}
						title={summary}
					>
						{summary}
					</span>
				);
			},
		},
		{
			id: "actions",
			header: "操作",
			enableSorting: false,
			meta: createTaskActivitiesTableMeta({
				label: "操作",
				align: "left",
				width: 132,
			}),
			cell: ({ row }) => (
				<div className="flex justify-start">
					<Button
						asChild
						size="sm"
						variant="outline"
						className="cyber-btn-ghost h-8 px-3"
					>
						<Link to={appendReturnTo(row.original.route, currentRoute)}>
							详情
						</Link>
					</Button>
				</div>
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
					toolbar={false}
					pagination={{
						enabled: true,
						pageSizeOptions: [10, 20, 50],
						infoLabel: () => `共 ${activities.length} 条`,
					}}
					tableClassName="min-w-[760px]"
					fillContainerWidth
				/>
			</div>
		</div>
	);
}
