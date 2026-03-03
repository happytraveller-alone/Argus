import { Activity, Clock, Plus, Shield } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import CreateProjectAuditDialog from "@/components/audit/CreateProjectAuditDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	INTERRUPTED_STATUSES,
	fetchTaskActivities,
	filterActivitiesByKind,
	formatCreatedAt,
	getActivityDurationLabel,
	getTaskProgressBarClassName,
	getTaskProgressPercent,
	getRelativeTime,
	getTaskStatusClassName,
	getTaskStatusText,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";

const PAGE_SIZE = 3;

export default function TaskManagementStatic() {
	const [activities, setActivities] = useState<TaskActivityItem[]>([]);
	const [loading, setLoading] = useState(true);
	const [keyword, setKeyword] = useState("");
	const [finishedPage, setFinishedPage] = useState(1);
	const [runningPage, setRunningPage] = useState(1);
	const [nowTick, setNowTick] = useState(0);
	const [showCreateStaticDialog, setShowCreateStaticDialog] = useState(false);

	useEffect(() => {
		const timer = window.setInterval(() => {
			setNowTick((prev) => prev + 1);
		}, 1000);
		return () => window.clearInterval(timer);
	}, []);

	const loadData = useCallback(async () => {
		try {
			setLoading(true);
			const projects: Project[] = await api.getProjects();
			const allActivities = await fetchTaskActivities(projects);
			setActivities(allActivities);
		} catch (error) {
			console.error("加载静态任务失败:", error);
			toast.error("加载静态任务失败");
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		void loadData();
	}, [loadData]);

	const filteredActivities = useMemo(
		() => filterActivitiesByKind(activities, "rule_scan", keyword),
		[activities, keyword],
	);
	const staticActivities = useMemo(
		() => filterActivitiesByKind(activities, "rule_scan", ""),
		[activities],
	);

	const stats = useMemo(() => {
		return staticActivities.reduce(
			(acc, activity) => {
				acc.total += 1;
				if (activity.status === "completed") {
					acc.completed += 1;
				}
				if (activity.status === "running" || activity.status === "pending") {
					acc.running += 1;
				}
				return acc;
			},
			{ total: 0, completed: 0, running: 0 },
		);
	}, [staticActivities]);

	const runningActivities = useMemo(
		() =>
			filteredActivities.filter(
				(activity) => activity.status === "running" || activity.status === "pending",
			),
		[filteredActivities],
	);

	const finishedActivities = useMemo(
		() =>
			filteredActivities.filter(
				(activity) =>
					activity.status === "completed" ||
					activity.status === "failed" ||
					INTERRUPTED_STATUSES.has(activity.status) ||
					(activity.status !== "running" && activity.status !== "pending"),
			),
		[filteredActivities],
	);

	const finishedTotalPages = Math.max(
		1,
		Math.ceil(finishedActivities.length / PAGE_SIZE),
	);
	const runningTotalPages = Math.max(
		1,
		Math.ceil(runningActivities.length / PAGE_SIZE),
	);

	useEffect(() => {
		if (finishedPage > finishedTotalPages) {
			setFinishedPage(finishedTotalPages);
		}
	}, [finishedPage, finishedTotalPages]);

	useEffect(() => {
		if (runningPage > runningTotalPages) {
			setRunningPage(runningTotalPages);
		}
	}, [runningPage, runningTotalPages]);

	const pagedFinishedActivities = useMemo(() => {
		const start = (finishedPage - 1) * PAGE_SIZE;
		return finishedActivities.slice(start, start + PAGE_SIZE);
	}, [finishedActivities, finishedPage]);

	const pagedRunningActivities = useMemo(() => {
		const start = (runningPage - 1) * PAGE_SIZE;
		return runningActivities.slice(start, start + PAGE_SIZE);
	}, [runningActivities, runningPage]);

	const renderActivityCard = (activity: TaskActivityItem) => {
		void nowTick;
		return (
			<Link
				key={activity.id}
				to={activity.route}
				className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
			>
				<div className="space-y-3">
					<p className="text-base font-medium text-foreground">
						{activity.projectName}-静态扫描
					</p>
					<span className="text-xs text-muted-foreground">
						Gitleaks扫描：
						{activity.gitleaksEnabled ? "已启用" : "未启用"}
					</span>
					<div className="grid grid-cols-1 md:grid-cols-4 gap-2">
						<div className="rounded-md bg-muted/30 px-2 py-1.5">
							<p className="text-xs text-muted-foreground">扫描状态</p>
							<p className="text-sm text-foreground font-medium">
								{getTaskStatusText(activity.status)}
							</p>
						</div>
						<div className="rounded-md bg-muted/30 px-2 py-1.5">
							<p className="text-xs text-muted-foreground">创建时间</p>
							<p className="text-sm text-foreground font-medium">
								{formatCreatedAt(activity.createdAt)}（
								{getRelativeTime(activity.createdAt)}）
							</p>
						</div>
						<div className="rounded-md bg-muted/30 px-2 py-1.5">
							<p className="text-xs text-muted-foreground">用时</p>
							<p className="text-sm text-foreground font-medium inline-flex items-center gap-1">
								<Clock className="w-3 h-3" />
								{getActivityDurationLabel(activity)
									.replace("用时：", "")
									.replace("已运行：", "")}
							</p>
						</div>
						<div className="rounded-md bg-muted/30 px-2 py-1.5">
							<p className="text-xs text-muted-foreground">缺陷统计</p>
							<p className="text-sm text-foreground font-medium">
								总计 {activity.staticFindingStats?.total ?? 0}
							</p>
						</div>
					</div>
					<div className="space-y-1">
						<div className="flex items-center justify-between text-xs text-muted-foreground">
							<span>进度</span>
							<span className="font-medium text-foreground">
								{getTaskProgressPercent(activity)}%
							</span>
						</div>
						<div className="h-2 rounded bg-muted/50 overflow-hidden">
							<div
								className={`h-full transition-all ${getTaskProgressBarClassName(activity.status)}`}
								style={{
									width: `${getTaskProgressPercent(activity)}%`,
								}}
							/>
						</div>
					</div>
				</div>
			</Link>
		);
	};

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="grid grid-cols-1 sm:grid-cols-3 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">静态扫描任务</p>
							<p className="stat-value">{stats.total}</p>
						</div>
						<div className="stat-icon text-primary">
							<Activity className="w-6 h-6" />
						</div>
					</div>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">已完成</p>
					<p className="stat-value text-emerald-400">{stats.completed}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">进行中</p>
					<p className="stat-value text-sky-400">{stats.running}</p>
				</div>
			</div>

			<div className="cyber-card p-4 relative z-10">
				<div className="flex items-center justify-between gap-3">
					<div className="section-header">
						<Shield className="w-5 h-5 text-primary" />
						<h3 className="section-title">静态扫描任务</h3>
					</div>
					<div className="flex items-center gap-3">
						<Button
							size="sm"
							className="cyber-btn-primary h-8 px-3"
							onClick={() => setShowCreateStaticDialog(true)}
						>
							<Plus className="w-3.5 h-3.5 mr-1.5" />
							新建扫描任务
						</Button>
						<span className="text-xs text-muted-foreground">
							共 {filteredActivities.length} 条
						</span>
					</div>
				</div>

				<div className="space-y-3 mb-3 mt-3">
					<Input
						value={keyword}
						onChange={(e) => {
							setKeyword(e.target.value);
							setFinishedPage(1);
							setRunningPage(1);
						}}
						placeholder="按项目名/任务类型/状态搜索"
						className="h-9 font-mono"
					/>
				</div>

				<div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
					<div className="rounded-lg border border-border/60 bg-muted/15 p-3 space-y-3">
						<div className="flex items-center justify-between gap-2">
							<h4 className="text-sm font-semibold text-foreground">
								已结束（完成/失败/中止）
							</h4>
							<span className="text-xs text-muted-foreground">
								共 {finishedActivities.length} 条
							</span>
						</div>
						<div className="space-y-2">
							{loading ? (
								<div className="empty-state py-8">
									<p className="text-base text-muted-foreground">加载中...</p>
								</div>
							) : pagedFinishedActivities.length > 0 ? (
								pagedFinishedActivities.map(renderActivityCard)
							) : (
								<div className="empty-state py-8">
									<p className="text-base text-muted-foreground">暂无已结束任务</p>
								</div>
							)}
						</div>
						{finishedActivities.length > 0 && (
							<div className="pt-1 flex items-center justify-between">
								<div className="text-xs text-muted-foreground">
									第 {finishedPage} / {finishedTotalPages} 页（每页 {PAGE_SIZE} 条）
								</div>
								<div className="flex items-center gap-2">
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={finishedPage <= 1}
										onClick={() =>
											setFinishedPage((prev) => Math.max(prev - 1, 1))
										}
									>
										上一页
									</Button>
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={finishedPage >= finishedTotalPages}
										onClick={() =>
											setFinishedPage((prev) =>
												Math.min(prev + 1, finishedTotalPages),
											)
										}
									>
										下一页
									</Button>
								</div>
							</div>
						)}
					</div>

					<div className="rounded-lg border border-border/60 bg-muted/15 p-3 space-y-3">
						<div className="flex items-center justify-between gap-2">
							<h4 className="text-sm font-semibold text-foreground">
								进行中（运行/待处理）
							</h4>
							<span className="text-xs text-muted-foreground">
								共 {runningActivities.length} 条
							</span>
						</div>
						<div className="space-y-2">
							{loading ? (
								<div className="empty-state py-8">
									<p className="text-base text-muted-foreground">加载中...</p>
								</div>
							) : pagedRunningActivities.length > 0 ? (
								pagedRunningActivities.map(renderActivityCard)
							) : (
								<div className="empty-state py-8">
									<p className="text-base text-muted-foreground">暂无进行中任务</p>
								</div>
							)}
						</div>
						{runningActivities.length > 0 && (
							<div className="pt-1 flex items-center justify-between">
								<div className="text-xs text-muted-foreground">
									第 {runningPage} / {runningTotalPages} 页（每页 {PAGE_SIZE} 条）
								</div>
								<div className="flex items-center gap-2">
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={runningPage <= 1}
										onClick={() =>
											setRunningPage((prev) => Math.max(prev - 1, 1))
										}
									>
										上一页
									</Button>
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={runningPage >= runningTotalPages}
										onClick={() =>
											setRunningPage((prev) =>
												Math.min(prev + 1, runningTotalPages),
											)
										}
									>
										下一页
									</Button>
								</div>
							</div>
						)}
					</div>
				</div>
			</div>

			<CreateProjectAuditDialog
				open={showCreateStaticDialog}
				onOpenChange={setShowCreateStaticDialog}
				onTaskCreated={() => {
					void loadData();
				}}
				initialMode="static"
				lockMode
				allowUploadProject
				primaryCreateLabel="创建静态扫描任务"
			/>
		</div>
	);
}
