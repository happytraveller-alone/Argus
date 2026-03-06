import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Layers, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import DeferredSection from "@/components/performance/DeferredSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import TaskActivitiesListTable from "@/features/tasks/components/TaskActivitiesListTable";
import { useTaskActivitiesSnapshot } from "@/features/tasks/hooks/useTaskActivitiesSnapshot";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import { filterHybridActivities } from "@/features/tasks/services/taskActivities";

const CreateProjectAuditDialog = lazy(
	() => import("@/components/audit/CreateProjectAuditDialog"),
);

export default function TaskManagementHybrid() {
	const { activities, loading, error, refresh } = useTaskActivitiesSnapshot();
	const [keyword, setKeyword] = useState("");
	const [showCreateHybridDialog, setShowCreateHybridDialog] = useState(false);
	const errorRef = useRef<string | null>(null);

	useEffect(() => {
		if (!error || activities.length > 0 || errorRef.current === error) {
			return;
		}
		errorRef.current = error;
		console.error("加载混合任务失败:", error);
		toast.error("加载混合任务失败");
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

	const hybridActivities = useMemo(
		() => filterHybridActivities(activities, ""),
		[activities],
	);
	const normalizedKeyword = keyword.trim().toLowerCase();
	const filteredActivities = useMemo(() => {
		if (!normalizedKeyword) return hybridActivities;
		return hybridActivities.filter((activity) =>
			activity.projectName.toLowerCase().includes(normalizedKeyword),
		);
	}, [hybridActivities, normalizedKeyword]);

	const stats = useMemo(() => {
		return hybridActivities.reduce(
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
	}, [hybridActivities]);

	return (
		<div className="relative flex h-screen flex-col gap-6 overflow-hidden bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="relative z-10 grid shrink-0 grid-cols-1 gap-4 sm:grid-cols-3">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">混合扫描任务</p>
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

			<div className="cyber-card relative z-10 flex min-h-0 flex-1 flex-col p-4">
				<div className="flex flex-wrap items-center justify-between gap-3">
					<div className="flex min-w-0 flex-1 items-center gap-3">
						<div className="section-header shrink-0">
							<Layers className="w-5 h-5 text-primary" />
							<h3 className="section-title">混合扫描任务</h3>
						</div>
						<div className="relative w-full max-w-sm">
							<Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
							<Input
								value={keyword}
								onChange={(e) => setKeyword(e.target.value)}
								placeholder="搜索项目名"
								className="h-9 pl-9 font-mono"
							/>
						</div>
					</div>
					<div className="flex shrink-0 items-center gap-3">
						<Button
							size="sm"
							className="cyber-btn-primary h-8 px-3"
							onClick={() => setShowCreateHybridDialog(true)}
						>
							<Plus className="w-3.5 h-3.5 mr-1.5" />
							新建扫描任务
						</Button>
						<span className="text-xs text-muted-foreground">
							共 {filteredActivities.length} 条
						</span>
					</div>
				</div>

				<DeferredSection className="mt-3 min-h-0 flex-1" minHeight={0} priority>
					<TaskActivitiesListTable
						activities={filteredActivities}
						loading={loading}
						nowMs={nowMs}
						emptyText="暂无混合扫描任务"
					/>
				</DeferredSection>
			</div>

			{showCreateHybridDialog ? (
				<Suspense fallback={null}>
					<CreateProjectAuditDialog
						open={showCreateHybridDialog}
						onOpenChange={setShowCreateHybridDialog}
						onTaskCreated={() => {
							void refresh();
						}}
						initialMode="hybrid"
						lockMode
						allowUploadProject
						primaryCreateLabel="创建混合扫描任务"
					/>
				</Suspense>
			) : null}
		</div>
	);
}
