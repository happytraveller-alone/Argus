import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";

import DeferredSection from "@/components/performance/DeferredSection";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import TaskActivitiesListTable from "@/features/tasks/components/TaskActivitiesListTable";
import TaskManagementSummaryCards from "@/features/tasks/components/TaskManagementSummaryCards";
import { useTaskActivitiesSnapshot } from "@/features/tasks/hooks/useTaskActivitiesSnapshot";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import { filterActivitiesByKind } from "@/features/tasks/services/taskActivities";

const CreateProjectScanDialog = lazy(
	() => import("@/components/scan/CreateProjectScanDialog"),
);

export default function TaskManagementStatic() {
	const { activities, loading, error, refresh } = useTaskActivitiesSnapshot({
		forceInitial: true,
		pollingIntervalMs: 5000,
		idlePollingIntervalMs: 15_000,
	});
	const [keyword, setKeyword] = useState("");
	const [showCreateStaticDialog, setShowCreateStaticDialog] = useState(false);
	const [searchParams, setSearchParams] = useSearchParams();
	const errorRef = useRef<string | null>(null);
	const autoOpenHandledRef = useRef(false);

	useEffect(() => {
		if (autoOpenHandledRef.current) return;
		if (searchParams.get("openCreate") !== "1") return;

		autoOpenHandledRef.current = true;
		setShowCreateStaticDialog(true);
		const nextParams = new URLSearchParams(searchParams);
		nextParams.delete("openCreate");
		setSearchParams(nextParams, { replace: true });
	}, [searchParams, setSearchParams]);

	useEffect(() => {
		if (!error || activities.length > 0 || errorRef.current === error) {
			return;
		}
		errorRef.current = error;
		console.error("加载静态任务失败:", error);
		toast.error("加载静态任务失败");
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

	const staticActivities = useMemo(
		() => filterActivitiesByKind(activities, "rule_scan", ""),
		[activities],
	);
	const filteredStaticActivities = useMemo(
		() => filterActivitiesByKind(activities, "rule_scan", keyword),
		[activities, keyword],
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

	return (
		<div className="relative flex h-screen flex-col gap-6 overflow-hidden bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<TaskManagementSummaryCards
				taskLabel="静态审计任务"
				total={stats.total}
				completed={stats.completed}
				running={stats.running}
			/>

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
				</div>
				<div className="flex shrink-0 items-center gap-3">
					<Button
						size="sm"
						className="cyber-btn-primary h-8 px-3"
						onClick={() => setShowCreateStaticDialog(true)}
					>
						<Plus className="w-3.5 h-3.5 mr-1.5" />
						新建扫描任务
					</Button>
				</div>
			</div>

			<DeferredSection className="-mt-3 min-h-0 flex-1" minHeight={0} priority>
				<TaskActivitiesListTable
					activities={filteredStaticActivities}
					loading={loading}
					nowMs={nowMs}
					emptyText="暂无静态审计任务"
				/>
			</DeferredSection>

			{showCreateStaticDialog ? (
				<Suspense fallback={null}>
					<CreateProjectScanDialog
						open={showCreateStaticDialog}
						onOpenChange={setShowCreateStaticDialog}
						onTaskCreated={() => {
							void refresh();
						}}
						initialMode="static"
						lockMode
						allowUploadProject
						primaryCreateLabel="创建静态审计任务"
					/>
				</Suspense>
			) : null}
		</div>
	);
}
