import { Activity, Bot, Clock, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import CreateProjectAuditDialog from "@/components/audit/CreateProjectAuditDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	fetchTaskActivities,
	filterActivitiesByKind,
	formatCreatedAt,
	getActivityDurationLabel,
	getTaskProgressBarClassName,
	getTaskProgressPercent,
	getRelativeTime,
	getTaskStatusClassName,
	getTaskStatusText,
	summarizeTaskStatus,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";

const PAGE_SIZE = 5;

export default function TaskManagementIntelligent() {
	const [activities, setActivities] = useState<TaskActivityItem[]>([]);
	const [loading, setLoading] = useState(true);
	const [keyword, setKeyword] = useState("");
	const [page, setPage] = useState(1);
	const [nowTick, setNowTick] = useState(0);
	const [showCreateIntelligentDialog, setShowCreateIntelligentDialog] =
		useState(false);

	useEffect(() => {
		const timer = window.setInterval(() => {
			setNowTick((prev) => prev + 1);
		}, 1000);
		return () => window.clearInterval(timer);
	}, []);

	const loadData = async () => {
		try {
			setLoading(true);
			const projects: Project[] = await api.getProjects();
			const allActivities = await fetchTaskActivities(projects);
			setActivities(allActivities);
		} catch (error) {
			console.error("加载智能任务失败:", error);
			toast.error("加载智能任务失败");
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void loadData();
	}, []);

	const filteredActivities = useMemo(
		() => filterActivitiesByKind(activities, "intelligent_audit", keyword),
		[activities, keyword],
	);
	const intelligentActivities = useMemo(
		() => filterActivitiesByKind(activities, "intelligent_audit", ""),
		[activities],
	);
	const stats = useMemo(
		() => summarizeTaskStatus(intelligentActivities),
		[intelligentActivities],
	);

	const totalPages = Math.max(
		1,
		Math.ceil(filteredActivities.length / PAGE_SIZE),
	);

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

			<div className="grid grid-cols-1 sm:grid-cols-3 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">智能扫描任务</p>
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
						<Bot className="w-5 h-5 text-primary" />
						<h3 className="section-title">智能扫描任务</h3>
					</div>
					<div className="flex items-center gap-3">
						<Button
							size="sm"
							className="cyber-btn-primary h-8 px-3"
							onClick={() => setShowCreateIntelligentDialog(true)}
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
							setPage(1);
						}}
						placeholder="按项目名/任务类型/状态搜索"
						className="h-9 font-mono"
					/>
					<div className="text-xs text-muted-foreground">
						仅展示 intelligent_audit（Agent 审计）任务
					</div>
				</div>

				<div className="space-y-2">
					{loading ? (
						<div className="empty-state py-8">
							<p className="text-base text-muted-foreground">加载中...</p>
						</div>
					) : pagedActivities.length > 0 ? (
						pagedActivities.map((activity) => {
							void nowTick;
							return (
								<Link
									key={activity.id}
									to={activity.route}
									className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
								>
									<div className="space-y-3">
										<p className="text-base font-medium text-foreground">
											{activity.projectName}-智能审计
										</p>
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
							<p className="text-base text-muted-foreground">
								暂无智能扫描任务
							</p>
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

			<CreateProjectAuditDialog
				open={showCreateIntelligentDialog}
				onOpenChange={setShowCreateIntelligentDialog}
				onTaskCreated={() => {
					void loadData();
				}}
				initialMode="agent"
				lockMode
				allowUploadProject
				primaryCreateLabel="创建智能扫描任务"
			/>
		</div>
	);
}
