import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Bot, Shield, Layers, ArrowRight, Clock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";
import {
	fetchTaskActivities,
	filterMixedActivities,
	formatCreatedAt,
	getActivityDurationLabel,
	getTaskProgressBarClassName,
	getTaskProgressPercent,
	getRelativeTime,
	getTaskStatusClassName,
	getTaskStatusText,
	summarizeTaskActivities,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";

const PAGE_SIZE = 5;

export default function TaskManagementOverview() {
	const [projects, setProjects] = useState<Project[]>([]);
	const [activities, setActivities] = useState<TaskActivityItem[]>([]);
	const [loading, setLoading] = useState(true);
	const [keyword, setKeyword] = useState("");
	const [page, setPage] = useState(1);
	const [nowTick, setNowTick] = useState(0);

	useEffect(() => {
		const timer = window.setInterval(() => {
			setNowTick((prev) => prev + 1);
		}, 1000);
		return () => window.clearInterval(timer);
	}, []);

	useEffect(() => {
		void loadData();
	}, []);

	const loadData = async () => {
		try {
			setLoading(true);
			const allProjects = await api.getProjects();
			setProjects(allProjects);
			const allActivities = await fetchTaskActivities(allProjects);
			setActivities(allActivities);
		} catch (error) {
			console.error("加载任务概览失败:", error);
			toast.error("加载任务概览失败");
		} finally {
			setLoading(false);
		}
	};

	const filteredActivities = useMemo(
		() => filterMixedActivities(activities, keyword),
		[activities, keyword],
	);

	const summary = useMemo(
		() => summarizeTaskActivities(activities),
		[activities],
	);

	const totalPages = Math.max(
		1,
		Math.ceil(filteredActivities.length / PAGE_SIZE),
	);

	useEffect(() => {
		setPage(1);
	}, [keyword]);

	useEffect(() => {
		if (page > totalPages) {
			setPage(totalPages);
		}
	}, [page, totalPages]);

	const pagedActivities = useMemo(() => {
		const start = (page - 1) * PAGE_SIZE;
		return filteredActivities.slice(start, start + PAGE_SIZE);
	}, [filteredActivities, page]);

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<p className="stat-label">静态扫描任务</p>
					<p className="stat-value">{summary.staticTotal}</p>
				</div>
				<div className="cyber-card p-4">
					<p className="stat-label">智能扫描任务</p>
					<p className="stat-value">{summary.intelligentTotal}</p>
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
						onChange={(e) => setKeyword(e.target.value)}
						placeholder="按项目名/任务类型/状态搜索"
						className="h-9 font-mono"
					/>
				</div>

				<div className="space-y-2">
					{loading ? (
						<div className="empty-state py-8">
							<p className="text-base text-muted-foreground">加载中...</p>
						</div>
					) : pagedActivities.length > 0 ? (
						pagedActivities.map((activity) => {
							void nowTick;
							const activityName =
								activity.kind === "rule_scan"
									? `${activity.projectName}-静态扫描`
									: `${activity.projectName}-智能审计`;
							return (
								<Link
									key={activity.id}
									to={activity.route}
									className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
								>
									<div className="space-y-3">
										<p className="text-base font-medium text-foreground">
											{activityName}
										</p>
										{activity.kind === "rule_scan" && (
											<span className="text-xs text-muted-foreground">
												Gitleaks扫描：
												{activity.gitleaksEnabled ? "已启用" : "未启用"}
											</span>
										)}
										<div className="grid grid-cols-1 md:grid-cols-3 gap-2">
											<div className="rounded-md bg-muted/30 px-2 py-1.5">
												<p className="text-xs text-muted-foreground">
													扫描状态
												</p>
												<p className="text-sm text-foreground font-medium">
													{getTaskStatusText(activity.status)}
												</p>
											</div>
											<div className="rounded-md bg-muted/30 px-2 py-1.5">
												<p className="text-xs text-muted-foreground">
													创建时间
												</p>
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
						})
					) : (
						<div className="empty-state py-8">
							<p className="text-base text-muted-foreground">暂无活动记录</p>
						</div>
					)}
				</div>

				{filteredActivities.length > 0 && (
					<div className="mt-4 flex items-center justify-between">
						<div className="text-xs text-muted-foreground">
							第 {page} / {totalPages} 页（每页 {PAGE_SIZE} 条）
						</div>
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
							<Button
								variant="outline"
								size="sm"
								className="cyber-btn-outline h-8 px-3"
								disabled={page >= totalPages}
								onClick={() =>
									setPage((prev) => Math.min(prev + 1, totalPages))
								}
							>
								下一页
							</Button>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
