import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";

import DeferredSection from "@/components/performance/DeferredSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import TaskActivitiesListTable from "@/features/tasks/components/TaskActivitiesListTable";
import { Badge } from "@/components/ui/badge";
import { useIntelligentTasksSnapshot } from "@/features/tasks/hooks/useIntelligentTasksSnapshot";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import { deleteIntelligentTask } from "@/shared/api/intelligentTasks";
import {
	getTaskStatusText,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";

const CreateProjectScanDialog = lazy(
	() => import("@/components/scan/CreateProjectScanDialog"),
);

export default function TaskManagementIntelligent() {
	const { activities, loading, error, refresh, cancel } =
		useIntelligentTasksSnapshot({
			pollingIntervalMs: 3000,
		});
	const [keyword, setKeyword] = useState("");
	const [showCreateDialog, setShowCreateDialog] = useState(false);
	const [cancellingActivityId, setCancellingActivityId] = useState<string | null>(null);
	const [deletingActivityId, setDeletingActivityId] = useState<string | null>(null);
	const errorRef = useRef<string | null>(null);

	useEffect(() => {
		if (!error || activities.length > 0 || errorRef.current === error) {
			return;
		}
		errorRef.current = error;
		console.error("加载智能审计任务失败:", error);
		toast.error("加载智能审计任务失败");
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

	const filteredIntelligentActivities = useMemo(() => {
		const trimmed = keyword.trim().toLowerCase();
		if (!trimmed) return activities;
		const kindText = "智能审计";
		return activities.filter((activity) => {
			return (
				activity.projectName.toLowerCase().includes(trimmed) ||
				kindText.includes(trimmed) ||
				getTaskStatusText(activity.status).toLowerCase().includes(trimmed)
			);
		});
	}, [activities, keyword]);

	const handleCancelActivity = async (activity: TaskActivityItem) => {
		if (activity.cancelTarget?.mode !== "intelligent") {
			toast.error("当前智能审计任务缺少可中止目标");
			return;
		}
		setCancellingActivityId(activity.id);
		try {
			await cancel(activity.cancelTarget.taskId);
			toast.success("已提交智能审计任务中止请求");
		} catch (error) {
			toast.error(`中止任务失败：${error instanceof Error ? error.message : "未知错误"}`);
		} finally {
			setCancellingActivityId(null);
		}
	};

	const handleDeleteActivity = async (activity: TaskActivityItem) => {
		if (activity.cancelTarget?.mode !== "intelligent") {
			toast.error("当前智能审计任务缺少可删除目标");
			return;
		}
		setDeletingActivityId(activity.id);
		try {
			await deleteIntelligentTask(activity.cancelTarget.taskId);
			toast.success("智能审计任务已删除");
			await refresh();
		} catch (error) {
			toast.error(`删除任务失败：${error instanceof Error ? error.message : "未知错误"}`);
		} finally {
			setDeletingActivityId(null);
		}
	};

	const stats = useMemo(() => {
		return activities.reduce(
			(acc, activity) => {
				acc.total += 1;
				if (activity.status === "completed") {
					acc.completed += 1;
				}
				if (activity.status === "running" || activity.status === "pending") {
					acc.running += 1;
				}
				if (activity.status === "failed") {
					acc.failed += 1;
				}
				return acc;
			},
			{ total: 0, completed: 0, running: 0, failed: 0 },
		);
	}, [activities]);

	return (
		<div className="relative flex h-screen flex-col gap-6 overflow-hidden bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
				<div>
					<h1 className="text-xl font-semibold tracking-[0.12em] text-foreground">智能审计任务</h1>
				</div>
			</div>

			<div className="flex flex-wrap items-center justify-end gap-3">
				<div className="flex min-w-0 flex-1 items-center gap-3">
					<div className="relative w-full max-w-sm">
						<Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
						<Input
							value={keyword}
							onChange={(e) => setKeyword(e.target.value)}
							placeholder="搜索项目名"
							className="h-9 pl-9 font-mono"
						/>
					</div>
					<div className="flex items-center gap-2">
						<Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300 gap-1.5">
							已完成 <span className="font-semibold tabular-nums">{stats.completed}</span>
						</Badge>
						<Badge className="border-sky-500/30 bg-sky-500/10 text-sky-300 gap-1.5">
							进行中 <span className="font-semibold tabular-nums">{stats.running}</span>
						</Badge>
						<Badge className="border-rose-500/30 bg-rose-500/10 text-rose-300 gap-1.5">
							异常 <span className="font-semibold tabular-nums">{stats.failed}</span>
						</Badge>
					</div>
				</div>
				<div className="flex shrink-0 items-center gap-3">
					<Button
						size="sm"
						className="cyber-btn-primary h-8 px-3"
						onClick={() => setShowCreateDialog(true)}
					>
						<Plus className="w-3.5 h-3.5 mr-1.5" />
						创建扫描
					</Button>
				</div>
			</div>

			<DeferredSection className="-mt-3 min-h-0 flex-1" minHeight={0} priority>
				<TaskActivitiesListTable
					activities={filteredIntelligentActivities}
					loading={loading}
					nowMs={nowMs}
					emptyText="暂无智能审计任务"
					onCancelActivity={handleCancelActivity}
					onDeleteActivity={handleDeleteActivity}
					cancellingActivityId={cancellingActivityId}
					deletingActivityId={deletingActivityId}
				/>
			</DeferredSection>

			{showCreateDialog ? (
				<Suspense fallback={null}>
					<CreateProjectScanDialog
						open={showCreateDialog}
						onOpenChange={setShowCreateDialog}
						onTaskCreated={() => {
							void refresh();
						}}
						initialMode="intelligent"
						navigateOnSuccess={false}
					/>
				</Suspense>
			) : null}
		</div>
	);
}
