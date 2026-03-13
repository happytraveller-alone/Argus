import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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
import {
	TASK_ACTIVITIES_TABLE_COLSPAN,
	TASK_ACTIVITIES_TABLE_HEADERS,
} from "@/features/tasks/components/taskActivitiesTableConfig";
import { appendReturnTo } from "@/shared/utils/findingRoute";

interface TaskActivitiesListTableProps {
	activities: TaskActivityItem[];
	loading?: boolean;
	nowMs: number;
	emptyText?: string;
	pageSize?: number;
}

function getDefectSummaryLabel(activity: TaskActivityItem): string {
	if (!activity.staticFindingStats) {
		return "-";
	}
	const { severe, hint, total } = activity.staticFindingStats;
	return `高危 ${severe} / 中危 ${hint} / 低危 ${total}`;
}

export default function TaskActivitiesListTable({
	activities,
	loading = false,
	nowMs,
	emptyText = "暂无任务",
	pageSize = 10,
}: TaskActivitiesListTableProps) {
	const location = useLocation();
	const [page, setPage] = useState(1);
	const currentRoute = `${location.pathname}${location.search}`;

	const totalPages = Math.max(1, Math.ceil(activities.length / pageSize));

	useEffect(() => {
		if (page > totalPages) {
			setPage(totalPages);
		}
	}, [page, totalPages]);

	const pagedActivities = useMemo(() => {
		const start = (page - 1) * pageSize;
		return activities.slice(start, start + pageSize);
	}, [activities, page, pageSize]);

	const getDetailRoute = (activity: TaskActivityItem): string => {
		return appendReturnTo(activity.route, currentRoute);
	};

	return (
		<div className="flex h-full min-h-0 flex-col gap-3">
			<div className="min-h-0 flex-1 [&_[data-slot=table-container]]:h-full">
					<Table>
						<TableHeader>
							<TableRow>
								<TableHead className="w-[80px] text-center">{TASK_ACTIVITIES_TABLE_HEADERS[0]}</TableHead>
								<TableHead className="min-w-[160px]">{TASK_ACTIVITIES_TABLE_HEADERS[1]}</TableHead>
								<TableHead className="min-w-[180px]">{TASK_ACTIVITIES_TABLE_HEADERS[2]}</TableHead>
								<TableHead className="w-[120px]">{TASK_ACTIVITIES_TABLE_HEADERS[3]}</TableHead>
								<TableHead className="min-w-[220px]">{TASK_ACTIVITIES_TABLE_HEADERS[4]}</TableHead>
								<TableHead className="min-w-[140px]">{TASK_ACTIVITIES_TABLE_HEADERS[5]}</TableHead>
								<TableHead className="min-w-[160px]">{TASK_ACTIVITIES_TABLE_HEADERS[6]}</TableHead>
								<TableHead className="w-[120px]">{TASK_ACTIVITIES_TABLE_HEADERS[7]}</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{loading && activities.length === 0 ? (
								<TableRow>
									<TableCell colSpan={TASK_ACTIVITIES_TABLE_COLSPAN} className="text-center text-muted-foreground py-8">
										加载中...
									</TableCell>
								</TableRow>
						) : pagedActivities.length > 0 ? (
							pagedActivities.map((activity, index) => {
								const progress = getTaskProgressPercent(activity, nowMs);
								const rawDuration = getActivityDurationLabel(activity, nowMs);
								const durationText = rawDuration
									.replace("用时：", "")
									.replace("已运行：", "");
								const rowNumber = (page - 1) * pageSize + index + 1;
								return (
									<TableRow key={activity.id}>
										<TableCell className="text-center text-muted-foreground">
											{rowNumber}
										</TableCell>
										<TableCell className="font-medium text-foreground">
											{activity.projectName}
										</TableCell>
										<TableCell className="text-sm text-muted-foreground">
											<div>{formatCreatedAt(activity.createdAt)}</div>
											<div className="text-xs">{getRelativeTime(activity.createdAt, nowMs)}</div>
										</TableCell>
										<TableCell className="font-mono text-foreground">{durationText}</TableCell>
										<TableCell>
											<div className="space-y-1 min-w-[210px]">
												<div className="flex items-center justify-between text-xs text-muted-foreground">
													<span>进度</span>
													<span className="font-medium text-foreground">{progress}%</span>
												</div>
												<div className="h-2 rounded bg-muted/50 overflow-hidden">
													<div
														className={`h-full transition-all ${getTaskProgressBarClassName(activity.status)}`}
														style={{ width: `${progress}%` }}
													/>
												</div>
											</div>
										</TableCell>
										<TableCell>
											<Badge className={getTaskStatusBadgeClassName(activity.status)}>
												{getTaskStatusText(activity.status)}
											</Badge>
										</TableCell>
										<TableCell className="text-sm text-muted-foreground">
											{getDefectSummaryLabel(activity)}
										</TableCell>
										<TableCell>
											<Button
												asChild
												size="sm"
												variant="outline"
												className="cyber-btn-ghost h-8 px-3"
											>
												<Link to={getDetailRoute(activity)}>详情</Link>
											</Button>
										</TableCell>
									</TableRow>
								);
							})
						) : (
							<TableRow>
								<TableCell colSpan={TASK_ACTIVITIES_TABLE_COLSPAN} className="text-center text-muted-foreground py-8">
									{emptyText}
								</TableCell>
							</TableRow>
						)}
					</TableBody>
				</Table>
			</div>

			<div className="mt-auto flex flex-wrap items-center justify-between gap-3">
				<div className="text-xs text-muted-foreground">共 {activities.length} 条</div>
				<div className="flex items-center gap-2">
					<Button
						variant="outline"
						size="sm"
						className="cyber-btn-outline h-8 px-3"
						disabled={page <= 1}
						onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
					>
						上一页
					</Button>
					<div className="text-xs text-muted-foreground">
						第 {page} / {totalPages} 页
					</div>
					<Button
						variant="outline"
						size="sm"
						className="cyber-btn-outline h-8 px-3"
						disabled={page >= totalPages}
						onClick={() => setPage((prev) => Math.min(prev + 1, totalPages))}
					>
						下一页
					</Button>
				</div>
			</div>
		</div>
	);
}
