import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
	isTaskActivityCancellable,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { appendReturnTo } from "@/shared/utils/findingRoute";

interface TaskActivitiesListTableProps {
	activities: TaskActivityItem[];
	loading?: boolean;
	nowMs: number;
	emptyText?: string;
	pageSize?: number;
	onCancelActivity?: (activity: TaskActivityItem) => void | Promise<void>;
	cancellingActivityId?: string | null;
	cancelDisabledReason?: string | null;
}

const TASK_ACTIVITIES_TABLE_HEADER_CELL_CLASSNAME =
	"border-b-2 border-border/95 bg-muted/75 text-center font-mono text-[14px] font-semibold uppercase tracking-[0.18em] text-foreground/80";
const TASK_ACTIVITIES_TABLE_HEADER_CONTENT_CLASSNAME = "text-[14px]";
const TASK_ACTIVITIES_TABLE_BODY_CELL_CLASSNAME =
	"border-b-2 border-border/95 text-center";
const TASK_ACTIVITIES_TABLE_BODY_TEXT_CLASSNAME = "text-sm";
const TASK_ACTIVITIES_TABLE_ACTION_BUTTON_CLASSNAME =
	"cyber-btn-ghost h-8 px-2.5";
const TASK_ACTIVITIES_TABLE_CANCEL_BUTTON_CLASSNAME =
	"cyber-btn-ghost h-8 border-rose-500/35 px-2.5 text-rose-200 hover:border-rose-500/55 hover:bg-rose-500/10 hover:text-rose-100";
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
		headerClassName: TASK_ACTIVITIES_TABLE_HEADER_CELL_CLASSNAME,
		headerContentClassName: TASK_ACTIVITIES_TABLE_HEADER_CONTENT_CLASSNAME,
		cellClassName: TASK_ACTIVITIES_TABLE_BODY_CELL_CLASSNAME,
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

function getColumns(input: {
	nowMs: number;
	currentRoute: string;
	onRequestCancel: (activity: TaskActivityItem) => void;
	cancellingActivityId?: string | null;
	cancelDisabledReason?: string | null;
}): AppColumnDef<TaskActivityItem, unknown>[] {
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
				cellClassName: `${TASK_ACTIVITIES_TABLE_BODY_CELL_CLASSNAME} text-left`,
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
				<div className="text-center text-sm leading-tight text-muted-foreground">
					<div className="truncate" title={formatCreatedAt(row.original.createdAt)}>
						{formatCreatedAt(row.original.createdAt)}
					</div>
					<div className="text-sm text-muted-foreground/80">
						{getRelativeTime(row.original.createdAt, input.nowMs)}
					</div>
				</div>
			),
		},
		{
			id: "duration",
			accessorFn: (row) => getActivityDurationLabel(row, input.nowMs),
			header: "用时",
			meta: createTaskActivitiesTableMeta({
				label: "用时",
				width: 88,
			}),
			cell: ({ row }) => {
				const rawDuration = getActivityDurationLabel(row.original, input.nowMs);
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
				const progress = getTaskProgressPercent(row.original, input.nowMs);

				return (
					<div className="flex items-center justify-center">
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
				align: "center",
				width: 176,
			}),
			cell: ({ row }) => {
				const canCancel = isTaskActivityCancellable(row.original);
				const cancelling = input.cancellingActivityId === row.original.id;
				return (
					<div className="flex flex-wrap items-center justify-center gap-2 text-[16px]">
						<Button
							asChild
							size="lg"
							variant="outline"
							className={TASK_ACTIVITIES_TABLE_ACTION_BUTTON_CLASSNAME}
						>
							<Link to={appendReturnTo(row.original.route, input.currentRoute)}>
								详情
							</Link>
						</Button>
						{canCancel ? (
							<Button
								type="button"
								size="lg"
								variant="outline"
								className={TASK_ACTIVITIES_TABLE_CANCEL_BUTTON_CLASSNAME}
								disabled={Boolean(input.cancelDisabledReason) || cancelling}
								title={input.cancelDisabledReason || "中止任务"}
								onClick={() => input.onRequestCancel(row.original)}
							>
								{cancelling ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
								中止
							</Button>
						) : null}
					</div>
				);
			},
		},
	];
}

export default function TaskActivitiesListTable({
	activities,
	loading = false,
	nowMs,
	emptyText = "暂无任务",
	pageSize = 10,
	onCancelActivity,
	cancellingActivityId = null,
	cancelDisabledReason = null,
}: TaskActivitiesListTableProps) {
	const location = useLocation();
	const currentRoute = `${location.pathname}${location.search}`;
	const [pendingCancelActivity, setPendingCancelActivity] =
		useState<TaskActivityItem | null>(null);

	const columns = useMemo<ColumnDef<TaskActivityItem>[]>(
		() =>
			getColumns({
				nowMs,
				currentRoute,
				onRequestCancel: setPendingCancelActivity,
				cancellingActivityId,
				cancelDisabledReason,
			}),
		[currentRoute, nowMs, cancellingActivityId, cancelDisabledReason],
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
					className="flex h-full min-h-0 flex-col"
					containerClassName="min-h-0 flex-1 overflow-auto"
					pagination={{
						enabled: true,
						pageSizeOptions: [10, 20, 50],
						infoLabel: () => `共 ${activities.length} 条`,
					}}
					tableClassName="min-w-[820px]"
					fillContainerWidth
				/>
			</div>
			{pendingCancelActivity ? (
			<AlertDialog
				open={Boolean(pendingCancelActivity)}
				onOpenChange={(open) => {
					if (!open) setPendingCancelActivity(null);
				}}
			>
				<AlertDialogContent className="cyber-dialog border-border">
					<AlertDialogHeader>
						<AlertDialogTitle>确认中止任务？</AlertDialogTitle>
						<AlertDialogDescription>
							即将中止 {pendingCancelActivity?.projectName || "当前"} 任务。中止请求提交后会刷新列表。
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={Boolean(cancellingActivityId)}>
							取消
						</AlertDialogCancel>
						<AlertDialogAction
							disabled={Boolean(cancellingActivityId)}
							className="bg-rose-600 hover:bg-rose-500"
							onClick={(event) => {
								event.preventDefault();
								if (!pendingCancelActivity || !onCancelActivity) return;
								void Promise.resolve(onCancelActivity(pendingCancelActivity)).finally(
									() => setPendingCancelActivity(null),
								);
							}}
						>
							{cancellingActivityId ? (
								<span className="inline-flex items-center gap-1.5">
									<Loader2 className="h-3.5 w-3.5 animate-spin" />
									处理中...
								</span>
							) : (
								"确认中止"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
			) : null}
		</div>
	);
}
