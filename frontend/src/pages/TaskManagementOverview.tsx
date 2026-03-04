import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, Bot, Clock, Layers, Shield } from "lucide-react";
import { toast } from "sonner";
import DeferredSection from "@/components/performance/DeferredSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTaskActivitiesSnapshot } from "@/features/tasks/hooks/useTaskActivitiesSnapshot";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import {
	INTERRUPTED_STATUSES,
	filterMixedActivities,
	formatCreatedAt,
	getActivityDurationLabel,
	getRelativeTime,
	getTaskKindText,
	getTaskProgressBarClassName,
	getTaskProgressPercent,
	getTaskStatusClassName,
	getTaskStatusText,
	summarizeTaskActivities,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";

const PAGE_SIZE = 3;

export default function TaskManagementOverview() {
	const { projects, activities, loading, error } = useTaskActivitiesSnapshot();
	const [keyword, setKeyword] = useState("");
	const [finishedPage, setFinishedPage] = useState(1);
	const [runningPage, setRunningPage] = useState(1);
	const errorRef = useRef<string | null>(null);

	useEffect(() => {
		if (!error || activities.length > 0 || errorRef.current === error) {
			return;
		}
		errorRef.current = error;
		console.error("加载任务概览失败:", error);
		toast.error("加载任务概览失败");
	}, [activities.length, error]);

	const shouldTickClock = useMemo(
		() =>
			activities.some(
				(activity) =>
					activity.status === "running" || activity.status === "pending",
			),
		[activities],
	);
	const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 5000 });

	const filteredActivities = useMemo(
		() => filterMixedActivities(activities, keyword),
		[activities, keyword],
	);

	const summary = useMemo(() => summarizeTaskActivities(activities), [activities]);

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
		const activityName = `${activity.projectName}-${getTaskKindText(activity)}`;
		return (
			<Link
				key={activity.id}
				to={activity.route}
				className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
			>
				<div className="space-y-3">
					<p className="text-base font-medium text-foreground">{activityName}</p>
					{activity.kind === "rule_scan" && (
						<span className="text-xs text-muted-foreground">
							Gitleaks扫描：
							{activity.gitleaksEnabled ? "已启用" : "未启用"}
						</span>
					)}
					<div className="grid grid-cols-1 md:grid-cols-3 gap-2">
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
								{getRelativeTime(activity.createdAt, nowMs)}）
							</p>
						</div>
						<div className="rounded-md bg-muted/30 px-2 py-1.5">
							<p className="text-xs text-muted-foreground">用时</p>
							<p className="text-sm text-foreground font-medium inline-flex items-center gap-1">
								<Clock className="w-3 h-3" />
								{getActivityDurationLabel(activity, nowMs)
									.replace("用时：", "")
									.replace("已运行：", "")}
							</p>
						</div>
					</div>
					<div className="space-y-1">
						<div className="flex items-center justify-between text-xs text-muted-foreground">
							<span>进度</span>
							<span className="font-medium text-foreground">
								{getTaskProgressPercent(activity, nowMs)}%
							</span>
						</div>
						<div className="h-2 rounded bg-muted/50 overflow-hidden">
							<div
								className={`h-full transition-all ${getTaskProgressBarClassName(activity.status)}`}
								style={{
									width: `${getTaskProgressPercent(activity, nowMs)}%`,
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

			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<p className="stat-label">静态扫描任务</p>
					<p className="stat-value">{summary.staticTotal}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">智能扫描任务</p>
					<p className="stat-value">{summary.intelligentTotal}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">混合扫描任务</p>
					<p className="stat-value">{summary.hybridTotal}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">运行中</p>
					<p className="stat-value text-sky-400">{summary.running}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">已完成</p>
					<p className="stat-value text-emerald-400">{summary.completed}</p>
				</div>
			</div>

			<div className="cyber-card p-4 relative z-10">
				<div className="section-header mb-3">
					<Layers className="w-5 h-5 text-primary" />
					<h3 className="section-title">任务分类导航</h3>
				</div>
				<div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
					<Link to="/tasks/static" className="block">
						<Button className="w-full h-10 justify-between cyber-btn-outline">
							<span className="inline-flex items-center gap-2">
								<Shield className="w-4 h-4" /> 静态扫描
							</span>
							<ArrowRight className="w-4 h-4" />
						</Button>
					</Link>
					<Link to="/tasks/intelligent" className="block">
						<Button className="w-full h-10 justify-between cyber-btn-outline">
							<span className="inline-flex items-center gap-2">
								<Bot className="w-4 h-4" /> 智能扫描
							</span>
							<ArrowRight className="w-4 h-4" />
						</Button>
					</Link>
					<Link to="/tasks/hybrid" className="block">
						<Button className="w-full h-10 justify-between cyber-btn-outline">
							<span className="inline-flex items-center gap-2">
								<Layers className="w-4 h-4" /> 混合扫描
							</span>
							<ArrowRight className="w-4 h-4" />
						</Button>
					</Link>
				</div>
			</div>

			<div className="cyber-card p-4 relative z-10">
				<div className="flex items-center justify-between gap-3">
					<div className="section-header">
						<Activity className="w-5 h-5 text-amber-400" />
						<h3 className="section-title">最近任务</h3>
					</div>
					<span className="text-xs text-muted-foreground">
						项目数：{projects.length} · 任务数：{filteredActivities.length}
					</span>
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

				<DeferredSection minHeight={480} priority>
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
				</DeferredSection>
			</div>
		</div>
	);
}
