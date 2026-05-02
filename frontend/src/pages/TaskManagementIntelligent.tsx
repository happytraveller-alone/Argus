import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DeferredSection from "@/components/performance/DeferredSection";
import {
	cancelIntelligentTask,
	createIntelligentTask,
	listIntelligentTasks,
	type IntelligentTaskRecord,
} from "@/shared/api/intelligentTasks";
import { apiClient } from "@/shared/api/serverClient";

interface ProjectOption {
	id: string;
	name: string;
}

function StatusBadge({ status }: { status: string }) {
	let className = "font-mono text-xs";
	if (status === "completed") {
		className += " border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
	} else if (status === "running" || status === "pending") {
		className += " border-sky-500/30 bg-sky-500/10 text-sky-300";
	} else if (status === "failed") {
		className += " border-rose-500/30 bg-rose-500/10 text-rose-300";
	} else {
		className += " border-orange-500/30 bg-orange-500/10 text-orange-300";
	}
	return <Badge className={className}>{status}</Badge>;
}

export default function TaskManagementIntelligent() {
	const navigate = useNavigate();
	const [projects, setProjects] = useState<ProjectOption[]>([]);
	const [selectedProjectId, setSelectedProjectId] = useState<string>("");
	const [tasks, setTasks] = useState<IntelligentTaskRecord[]>([]);
	const [loadingTasks, setLoadingTasks] = useState(true);
	const [creating, setCreating] = useState(false);
	const [cancellingId, setCancellingId] = useState<string | null>(null);
	const [keyword, setKeyword] = useState("");
	const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

	// Load projects once
	useEffect(() => {
		apiClient
			.get<ProjectOption[]>("/projects/")
			.then((res) => {
				const list = Array.isArray(res.data) ? res.data : [];
				setProjects(list);
				if (list.length > 0) {
					setSelectedProjectId((prev) => prev || list[0].id);
				}
			})
			.catch(() => {
				// silently ignore project load failure
			});
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	const fetchTasks = async () => {
		try {
			const data = await listIntelligentTasks(50);
			setTasks(data);
		} catch {
			// keep stale data
		} finally {
			setLoadingTasks(false);
		}
	};

	useEffect(() => {
		void fetchTasks();
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	// Auto-refresh every 5s
	useEffect(() => {
		pollingRef.current = setInterval(() => {
			void fetchTasks();
		}, 5000);
		return () => {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
		};
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	const handleCreate = async () => {
		if (!selectedProjectId) {
			toast.error("请先选择项目");
			return;
		}
		setCreating(true);
		try {
			const task = await createIntelligentTask(selectedProjectId);
			toast.success("智能审计任务已创建");
			void navigate(`/agent-audit/${task.taskId}`);
		} catch (err) {
			toast.error(
				`创建失败：${err instanceof Error ? err.message : "未知错误"}`,
			);
		} finally {
			setCreating(false);
		}
	};

	const handleCancel = async (task: IntelligentTaskRecord) => {
		setCancellingId(task.taskId);
		try {
			await cancelIntelligentTask(task.taskId);
			toast.success("已提交取消请求");
			await fetchTasks();
		} catch (err) {
			toast.error(
				`取消失败：${err instanceof Error ? err.message : "未知错误"}`,
			);
		} finally {
			setCancellingId(null);
		}
	};

	const filteredTasks = useMemo(() => {
		const trimmed = keyword.trim().toLowerCase();
		if (!trimmed) return tasks;
		return tasks.filter(
			(t) =>
				t.taskId.toLowerCase().includes(trimmed) ||
				t.projectId.toLowerCase().includes(trimmed) ||
				t.status.toLowerCase().includes(trimmed),
		);
	}, [tasks, keyword]);

	const stats = useMemo(
		() =>
			tasks.reduce(
				(acc, t) => {
					acc.total += 1;
					if (t.status === "completed") acc.completed += 1;
					if (t.status === "running" || t.status === "pending")
						acc.running += 1;
					if (t.status === "failed") acc.failed += 1;
					return acc;
				},
				{ total: 0, completed: 0, running: 0, failed: 0 },
			),
		[tasks],
	);

	return (
		<div className="relative flex h-screen flex-col gap-6 overflow-hidden bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{/* Header */}
			<div className="relative flex flex-wrap items-center justify-between gap-3">
				<h1 className="text-lg font-semibold tracking-tight text-foreground">
					智能审计
				</h1>
			</div>

			{/* Create action row */}
			<div className="relative flex flex-wrap items-center gap-3">
				<select
					value={selectedProjectId}
					onChange={(e) => setSelectedProjectId(e.target.value)}
					className="h-9 rounded-md border border-input bg-background px-3 font-mono text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
				>
					{projects.length === 0 ? (
						<option value="">（暂无项目）</option>
					) : (
						projects.map((p) => (
							<option key={p.id} value={p.id}>
								{p.name}
							</option>
						))
					)}
				</select>
				<Button
					size="sm"
					className="cyber-btn-primary h-8 px-3"
					disabled={creating || !selectedProjectId}
					onClick={() => void handleCreate()}
				>
					<Plus className="mr-1.5 h-3.5 w-3.5" />
					新建智能审计任务
				</Button>
			</div>

			{/* Stats + search row */}
			<div className="relative flex flex-wrap items-center justify-between gap-3">
				<div className="relative w-full max-w-sm">
					<Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
					<Input
						value={keyword}
						onChange={(e) => setKeyword(e.target.value)}
						placeholder="搜索任务 ID / 项目 / 状态"
						className="h-9 pl-9 font-mono"
					/>
				</div>
				<div className="flex items-center gap-2">
					<Badge className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
						已完成{" "}
						<span className="font-semibold tabular-nums">
							{stats.completed}
						</span>
					</Badge>
					<Badge className="gap-1.5 border-sky-500/30 bg-sky-500/10 text-sky-300">
						进行中{" "}
						<span className="font-semibold tabular-nums">
							{stats.running}
						</span>
					</Badge>
					<Badge className="gap-1.5 border-rose-500/30 bg-rose-500/10 text-rose-300">
						异常{" "}
						<span className="font-semibold tabular-nums">
							{stats.failed}
						</span>
					</Badge>
				</div>
			</div>

			{/* Task list */}
			<DeferredSection className="-mt-3 min-h-0 flex-1" minHeight={0} priority>
				{loadingTasks ? (
					<div className="flex items-center justify-center py-12">
						<span className="font-mono text-sm text-muted-foreground">
							加载中…
						</span>
					</div>
				) : filteredTasks.length === 0 ? (
					<div className="flex items-center justify-center py-12">
						<span className="font-mono text-sm text-muted-foreground">
							暂无智能审计任务
						</span>
					</div>
				) : (
					<div className="overflow-auto">
						<table className="w-full min-w-[720px] border-collapse font-mono text-xs">
							<thead>
								<tr className="border-b-2 border-border/95">
									<th className="bg-muted/75 px-3 py-2 text-left font-semibold uppercase tracking-[0.18em] text-foreground/80">
										任务 ID
									</th>
									<th className="bg-muted/75 px-3 py-2 text-left font-semibold uppercase tracking-[0.18em] text-foreground/80">
										项目 ID
									</th>
									<th className="bg-muted/75 px-3 py-2 text-center font-semibold uppercase tracking-[0.18em] text-foreground/80">
										状态
									</th>
									<th className="bg-muted/75 px-3 py-2 text-left font-semibold uppercase tracking-[0.18em] text-foreground/80">
										创建时间
									</th>
									<th className="bg-muted/75 px-3 py-2 text-right font-semibold uppercase tracking-[0.18em] text-foreground/80">
										耗时 (ms)
									</th>
									<th className="bg-muted/75 px-3 py-2 text-center font-semibold uppercase tracking-[0.18em] text-foreground/80">
										操作
									</th>
								</tr>
							</thead>
							<tbody>
								{filteredTasks.map((task) => {
									const canCancel =
										task.status === "pending" ||
										task.status === "running";
									return (
										<tr
											key={task.taskId}
											className="border-b-2 border-border/95 hover:bg-muted/20"
										>
											<td className="px-3 py-2">
												<Link
													to={`/agent-audit/${task.taskId}`}
													className="font-mono text-sky-400 hover:underline"
												>
													{task.taskId.length > 16
														? `${task.taskId.slice(0, 16)}…`
														: task.taskId}
												</Link>
											</td>
											<td className="px-3 py-2 text-foreground/80">
												{task.projectId.length > 16
													? `${task.projectId.slice(0, 16)}…`
													: task.projectId}
											</td>
											<td className="px-3 py-2 text-center">
												<StatusBadge status={task.status} />
											</td>
											<td className="px-3 py-2 text-muted-foreground">
												{task.createdAt}
											</td>
											<td className="px-3 py-2 text-right text-foreground/80">
												{task.durationMs !== undefined
													? String(task.durationMs)
													: "-"}
											</td>
											<td className="px-3 py-2 text-center">
												{canCancel ? (
													<Button
														size="sm"
														variant="outline"
														className="cyber-btn-ghost h-7 border-rose-500/35 px-2 text-rose-200 hover:border-rose-500/55 hover:bg-rose-500/10 hover:text-rose-100"
														disabled={
															cancellingId === task.taskId
														}
														onClick={() =>
															void handleCancel(task)
														}
													>
														取消
													</Button>
												) : (
													<Link
														to={`/agent-audit/${task.taskId}`}
														className="font-mono text-xs text-muted-foreground hover:text-foreground"
													>
														详情
													</Link>
												)}
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>
				)}
			</DeferredSection>
		</div>
	);
}
