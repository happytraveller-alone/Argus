import { Activity, Info, Layers, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import CreateProjectAuditDialog from "@/components/audit/CreateProjectAuditDialog";
import { Button } from "@/components/ui/button";
import {
	fetchTaskActivities,
	summarizeTaskStatus,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";

export default function TaskManagementHybrid() {
	const [activities, setActivities] = useState<TaskActivityItem[]>([]);
	const [loading, setLoading] = useState(true);
	const [showCreateHybridDialog, setShowCreateHybridDialog] = useState(false);

	const loadData = async () => {
		try {
			setLoading(true);
			const projects: Project[] = await api.getProjects();
			const allActivities = await fetchTaskActivities(projects);
			setActivities(allActivities);
		} catch (error) {
			console.error("加载混合任务统计失败:", error);
			toast.error("加载混合任务统计失败");
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void loadData();
	}, []);

	const stats = useMemo(() => summarizeTaskStatus(activities), [activities]);

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="grid grid-cols-1 sm:grid-cols-3 gap-4 relative z-10">
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

			<div className="cyber-card p-6 relative z-10">
				<div className="mb-4 flex items-center justify-between gap-3">
					<div className="section-header mb-0">
						<Layers className="w-5 h-5 text-primary" />
						<h3 className="section-title">混合扫描</h3>
					</div>
					<Button
						size="sm"
						className="cyber-btn-primary h-8 px-3"
						onClick={() => setShowCreateHybridDialog(true)}
					>
						<Plus className="w-3.5 h-3.5 mr-1.5" />
						新建扫描任务
					</Button>
				</div>

				<div className="rounded-lg border border-border bg-muted/20 p-4 space-y-3">
					<div className="inline-flex items-center gap-2 text-primary">
						<Info className="w-4 h-4" />
						<span className="font-semibold">功能占位</span>
					</div>
					<p className="text-sm text-muted-foreground leading-relaxed">
						当前版本先提供混合扫描入口与页面骨架，暂不引入新的后端任务类型或聚合协议。
						后续将基于统一任务视图补充混合扫描规则与数据筛选策略。
					</p>
					<p className="text-xs text-muted-foreground">
						{loading
							? "统计加载中..."
							: "当前统计已汇总静态扫描与智能扫描任务。"}
					</p>
				</div>
			</div>

			<CreateProjectAuditDialog
				open={showCreateHybridDialog}
				onOpenChange={setShowCreateHybridDialog}
				onTaskCreated={() => {
					void loadData();
				}}
				initialMode="static"
				allowUploadProject
				primaryCreateLabel="创建混合扫描任务"
			/>
		</div>
	);
}
