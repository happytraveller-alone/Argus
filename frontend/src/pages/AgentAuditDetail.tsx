import { ArrowLeft, CheckCircle2, Circle, Loader2, RefreshCw, Terminal } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
	type AppColumnDef,
	createDefaultDataTableState,
	DataTable,
	type DataTableQueryState,
} from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { type SseEvent, useSseStream } from "@/hooks/useSseStream";
import { getApiBaseUrl } from "@/shared/api/apiBase";
import {
	cancelIntelligentTask,
	getIntelligentTask,
	type IntelligentTaskFinding,
	type IntelligentTaskRecord,
	type IntelligentTaskStatus,
} from "@/shared/api/intelligentTasks";

const TERMINAL_STATUSES: Set<IntelligentTaskStatus> = new Set([
	"completed",
	"failed",
	"cancelled",
]);

function isTerminal(status: string): boolean {
	return TERMINAL_STATUSES.has(status as IntelligentTaskStatus);
}

function formatDuration(durationMs?: number): string {
	if (durationMs === undefined) return "-";
	if (durationMs < 1000) return `${durationMs}ms`;
	const seconds = Math.round(durationMs / 1000);
	if (seconds < 60) return `${seconds}s`;
	const minutes = Math.floor(seconds / 60);
	const restSeconds = seconds % 60;
	return `${minutes}m ${restSeconds}s`;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
	return (
		<h3 className="mb-2 font-mono text-xs font-semibold uppercase tracking-widest text-foreground/60">
			{children}
		</h3>
	);
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
	return (
		<div className="flex min-w-0 flex-col gap-0.5">
			<span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
				{label}
			</span>
			<span className="font-mono text-sm text-foreground">{value ?? "-"}</span>
		</div>
	);
}

type IntelligentScanStage = "pending" | "recon" | "hunt" | "validate" | "gapfill" | "dedupe" | "trace" | "feedback" | "report" | "completed" | "failed";

const INTELLIGENT_STAGE_ORDER: IntelligentScanStage[] = [
	"recon", "hunt", "validate", "gapfill", "dedupe", "trace", "feedback", "report",
];

function resolveIntelligentScanStage(
	status: string | undefined,
	events: SseEvent[],
): IntelligentScanStage {
	const s = String(status || "").trim().toLowerCase();
	if (s === "completed") return "completed";
	if (s === "failed" || s === "cancelled") return "failed";
	if (s === "pending") return "pending";
	let lastActive: string | null = null;
	const completedSteps = new Set<string>();
	for (const ev of events) {
		const step = typeof ev.data?.step === "string" ? ev.data.step : null;
		if (!step) continue;
		if (ev.kind === "step_completed") completedSteps.add(step);
		else if (ev.kind === "step_started") lastActive = step;
	}
	if (completedSteps.has("report")) return "completed";
	if (lastActive && INTELLIGENT_STAGE_ORDER.includes(lastActive as IntelligentScanStage)) {
		return lastActive as IntelligentScanStage;
	}
	for (let i = INTELLIGENT_STAGE_ORDER.length - 1; i >= 0; i--) {
		if (completedSteps.has(INTELLIGENT_STAGE_ORDER[i])) {
			const next = INTELLIGENT_STAGE_ORDER[i + 1];
			return next ?? "completed";
		}
	}
	return "recon";
}

const STAGE_LABELS: Record<string, string> = {
	recon: "侦察",
	hunt: "搜寻",
	validate: "验证",
	gapfill: "补漏",
	dedupe: "去重",
	trace: "追踪",
	feedback: "反馈",
	report: "报告",
};

function IntelligentScanStages({ stage }: { stage: IntelligentScanStage }) {
	const ORDER: Record<string, number> = { pending: -1, recon: 0, hunt: 1, validate: 2, gapfill: 3, dedupe: 4, trace: 5, feedback: 6, report: 7, completed: 8, failed: 8 };
	const currentIndex = ORDER[stage] ?? -1;

	return (
		<div className="flex items-center gap-0">
			{INTELLIGENT_STAGE_ORDER.map((key, i) => {
				const isDone = currentIndex > i || stage === "completed";
				const isActive = currentIndex === i && stage !== "completed" && stage !== "failed" && stage !== "pending";
				const isFailed = stage === "failed" && currentIndex === i;
				return (
					<div key={key} className="flex items-center">
						<div className="flex flex-col items-center gap-1">
							<div className={`flex h-6 w-6 items-center justify-center rounded-full border text-xs font-medium transition-colors ${
								isDone
									? "border-emerald-500/60 bg-emerald-500/20 text-emerald-300"
									: isActive
									? "border-sky-400/70 bg-sky-500/20 text-sky-300"
									: isFailed
									? "border-rose-500/60 bg-rose-500/20 text-rose-300"
									: "border-border bg-muted/30 text-muted-foreground"
							}`}>
								{isDone ? (
									<CheckCircle2 className="h-3.5 w-3.5" />
								) : isActive ? (
									<Loader2 className="h-3 w-3 animate-spin" />
								) : (
									<Circle className="h-3 w-3" />
								)}
							</div>
							<span className={`text-[11px] whitespace-nowrap ${
								isDone ? "text-emerald-300" : isActive ? "text-sky-300" : "text-muted-foreground"
							}`}>
								{STAGE_LABELS[key]}
							</span>
						</div>
						{i < INTELLIGENT_STAGE_ORDER.length - 1 && (
							<div className={`mx-1.5 mb-4 h-px w-5 ${isDone ? "bg-emerald-500/40" : "bg-border"}`} />
						)}
					</div>
				);
			})}
		</div>
	);
}

const findingColumns: AppColumnDef<IntelligentTaskFinding, unknown>[] = [
	{
		id: "rowNumber",
		header: "序号",
		enableSorting: false,
		meta: {
			label: "序号",
			align: "center",
			width: 72,
		},
		cell: ({ row, table }) =>
			table.getState().pagination.pageIndex *
				table.getState().pagination.pageSize +
			table.getRowModel().rows.findIndex((r) => r.id === row.id) +
			1,
	},
	{
		id: "id",
		accessorFn: (row) => row.id,
		header: "问题 ID",
		enableSorting: false,
		meta: {
			label: "问题 ID",
			align: "left",
			width: 220,
			minWidth: 180,
			filterVariant: "text",
		},
		cell: ({ row }) => (
			<span
				className="block max-w-full truncate font-mono text-sm"
				title={row.original.id}
			>
				{row.original.id || "-"}
			</span>
		),
	},
	{
		id: "severity",
		accessorFn: (row) => row.severity,
		header: "危害",
		enableHiding: false,
		meta: {
			label: "漏洞危害",
			width: 140,
			filterVariant: "select",
			filterOptions: [
				{ label: "严重", value: "critical" },
				{ label: "高危", value: "high" },
				{ label: "中危", value: "medium" },
				{ label: "低危", value: "low" },
			],
		},
		cell: ({ row }) => (
			<Badge variant="outline" className="font-mono text-xs">
				{row.original.severity || "-"}
			</Badge>
		),
	},
	{
		id: "summary",
		accessorFn: (row) => row.summary,
		header: "问题摘要",
		enableSorting: false,
		enableHiding: false,
		meta: {
			label: "问题摘要",
			align: "left",
			minWidth: 360,
			filterVariant: "text",
		},
		cell: ({ row }) => (
			<span className="block max-w-[34rem] whitespace-normal text-sm text-foreground/90">
				{row.original.summary || "-"}
			</span>
		),
	},
	{
		id: "evidence",
		accessorFn: (row) => row.evidence,
		header: "证据",
		enableSorting: false,
		meta: {
			label: "证据",
			align: "left",
			minWidth: 420,
			filterVariant: "text",
		},
		cell: ({ row }) => (
			<span className="block max-w-[42rem] whitespace-normal font-mono text-xs text-muted-foreground">
				{row.original.evidence || "-"}
			</span>
		),
	},
];

export default function AgentAuditDetail() {
	const { taskId } = useParams<{ taskId: string }>();
	const location = useLocation();
	const navigate = useNavigate();
	const [record, setRecord] = useState<IntelligentTaskRecord | null>(null);
	const [loading, setLoading] = useState(true);
	const [fetchError, setFetchError] = useState<string | null>(null);
	const [cancelling, setCancelling] = useState(false);
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createDefaultDataTableState({
			pagination: { pageIndex: 0, pageSize: 15 },
		}),
	);
	const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
	const [showLlmLog, setShowLlmLog] = useState(false);

	const taskTerminal = record ? isTerminal(record.status) : false;
	const sseUrl = taskId
		? `${getApiBaseUrl()}/intelligent-tasks/${taskId}/stream`
		: "";
	const { events: sseEvents, isComplete: sseComplete } = useSseStream(sseUrl, {
		enabled: Boolean(taskId) && !taskTerminal,
	});

	const fetchRecord = useCallback(async () => {
		if (!taskId) return;
		try {
			const data = await getIntelligentTask(taskId);
			setRecord(data);
			setFetchError(null);
		} catch (err) {
			setFetchError(err instanceof Error ? err.message : "获取任务详情失败");
		} finally {
			setLoading(false);
		}
	}, [taskId]);

	useEffect(() => {
		void fetchRecord();
	}, [fetchRecord]);

	useEffect(() => {
		if (!record) return;
		if (isTerminal(record.status)) {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
			return;
		}
		pollingRef.current = setInterval(() => {
			void fetchRecord();
		}, 3000);
		return () => {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
		};
	}, [fetchRecord, record]);

	const handleCancel = async () => {
		if (!taskId) return;
		setCancelling(true);
		try {
			const updated = await cancelIntelligentTask(taskId);
			setRecord(updated);
			toast.success("已提交取消请求");
		} catch (err) {
			toast.error(
				`取消失败：${err instanceof Error ? err.message : "未知错误"}`,
			);
		} finally {
			setCancelling(false);
		}
	};

	if (loading) {
		return (
			<div className="flex h-screen items-center justify-center bg-background">
				<span className="font-mono text-sm text-muted-foreground">加载中…</span>
			</div>
		);
	}

	if (fetchError || !record) {
		return (
			<div className="flex h-screen flex-col items-center justify-center gap-3 bg-background">
				<span className="font-mono text-sm text-rose-400">
					{fetchError ?? "任务不存在"}
				</span>
				<Button
					size="sm"
					variant="outline"
					className="font-mono text-xs"
					onClick={() => {
						setLoading(true);
						void fetchRecord();
					}}
				>
					重试
				</Button>
			</div>
		);
	}

	const canCancel = record.status === "pending" || record.status === "running";

	const findings = Array.isArray(record.findings) ? record.findings : [];
	const eventLog = Array.isArray(record.eventLog) ? record.eventLog : [];
	const replayEvents: SseEvent[] = eventLog.map((event) => ({
		kind: event.kind,
		timestamp: event.timestamp,
		message: event.message,
		data:
			event.data && typeof event.data === "object" && !Array.isArray(event.data)
				? (event.data as Record<string, unknown>)
				: undefined,
	}));
	const activeEvents: SseEvent[] =
		sseEvents.length > 0 ? sseEvents : replayEvents;
	const progressPercent = taskTerminal
		? record.status === "completed"
			? 100
			: 0
		: activeEvents.some((event) => event.kind === "step_completed")
			? 70
			: activeEvents.length > 0
				? 35
				: 0;
	const headerTags = [
		record.projectName?.trim() || record.projectId || "-",
		`${progressPercent}%`,
		formatDuration(record.durationMs),
		`发现问题 ${findings.length.toLocaleString()}`,
	];

	const scanStage = resolveIntelligentScanStage(record.status, activeEvents);

	const returnToParam =
		new URLSearchParams(location.search).get("returnTo") || "";
	const returnTo =
		returnToParam.startsWith("/") && !returnToParam.startsWith("//")
			? returnToParam
			: "";
	const handleBack = () => {
		if (returnTo) {
			navigate(returnTo);
			return;
		}
		navigate(-1);
	};

	return (
		<div className="relative flex min-h-screen flex-col gap-6 bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{/* Header */}
			<div className="relative flex flex-wrap items-center justify-between gap-3">
				<div className="flex min-w-0 flex-wrap items-center gap-3">
					<h1 className="text-2xl font-bold uppercase tracking-wider text-foreground">
						智能审计
					</h1>
					<fieldset className="m-0 flex min-w-0 flex-wrap items-center gap-2 border-0 p-0">
						<legend className="sr-only">智能审计概要标签</legend>
						{headerTags.map((tag) => (
							<Badge
								key={tag}
								className="cyber-badge cyber-badge-info max-w-[18rem] truncate normal-case tracking-normal"
								title={tag}
							>
								{tag}
							</Badge>
						))}
					</fieldset>
				</div>
				<div className="flex items-center gap-2">
					{canCancel && (
						<Button
							size="sm"
							variant="outline"
							className="cyber-btn-ghost h-8 border-rose-500/35 px-3 text-rose-200 hover:bg-rose-500/10 hover:text-rose-100"
							disabled={cancelling}
							onClick={() => void handleCancel()}
						>
							{cancelling ? "取消中…" : "取消任务"}
						</Button>
					)}
					<Button
						size="sm"
						variant="outline"
						className="cyber-btn-ghost h-8 px-3"
						onClick={() => setShowLlmLog(true)}
					>
						<Terminal className="mr-1.5 h-3.5 w-3.5" />
						时间日志
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={() => {
							setLoading(true);
							void fetchRecord();
						}}
						disabled={loading}
					>
						<RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
						刷新
					</Button>
					<Button
						size="sm"
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={handleBack}
					>
						<ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
						返回
					</Button>
				</div>
			</div>

			{/* Progress stage indicator — always visible */}
			<div className="relative flex items-center gap-4 rounded border border-border bg-card/40 px-4 py-3">
				<span className="text-xs text-muted-foreground shrink-0">扫描阶段</span>
				<IntelligentScanStages stage={scanStage} />
			</div>

			{/* Findings table — full width */}
			<div className="relative min-h-[28rem] lg:h-[calc(100vh-14rem)]">
				<div className="min-h-[28rem] min-w-0 overflow-y-auto rounded-md pr-1 lg:h-full">
					<DataTable
						data={findings}
						columns={findingColumns}
						state={tableState}
						onStateChange={setTableState}
						emptyState={{
							title: "暂无发现问题",
							description: "0 findings (lifecycle proof captured)",
						}}
						toolbar={{
							searchPlaceholder: "搜索问题、危害或证据",
							showGlobalSearch: true,
							showColumnVisibility: false,
							showDensityToggle: false,
							showReset: false,
						}}
						pagination={{
							enabled: true,
							pageSizeOptions: [10, 20, 50],
							infoLabel: ({ table, filteredCount }) =>
								`共 ${filteredCount.toLocaleString()} 条，第 ${
									table.getState().pagination.pageIndex + 1
								} / ${Math.max(1, table.getPageCount())} 页`,
						}}
						className="flex h-full min-h-0 flex-col rounded-md border border-border"
						containerClassName="min-h-0 flex-1 max-w-full overflow-auto custom-scrollbar-dark"
						tableContainerClassName="overflow-x-auto rounded-sm"
						tableClassName="min-w-[1280px]"
						fillContainerWidth
					/>
				</div>
			</div>

			{/* Below the grid (full width) */}

			{/* Failure info */}
			{record.status === "failed" && (
				<div className="relative rounded-lg border border-rose-500/30 bg-rose-500/5 p-4">
					<SectionTitle>失败信息</SectionTitle>
					<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<Field label="失败阶段" value={record.failureStage ?? "-"} />
						<Field label="失败原因" value={record.failureReason ?? "-"} />
					</div>
				</div>
			)}

			{/* LLM Interaction Log Dialog */}
			<Dialog open={showLlmLog} onOpenChange={setShowLlmLog}>
				<DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
					<DialogHeader>
						<DialogTitle>时间日志 ({eventLog.length})</DialogTitle>
					</DialogHeader>
					<div className="flex-1 overflow-y-auto">
						<div className="flex flex-col gap-0">
							{eventLog.length === 0 ? (
								<p className="py-8 text-center text-sm text-muted-foreground">暂无交互记录</p>
							) : (
								eventLog.map((ev, idx) => {
									const data = ev.data && typeof ev.data === "object" ? (ev.data as Record<string, unknown>) : null;
									const isLlm = ev.kind === "llm_attempt";
									const isAgent = ev.kind === "agent_started" || ev.kind === "agent_completed";
									return (
										<div key={idx} className="flex items-start gap-3 border-b border-border/30 px-2 py-2.5 last:border-b-0">
											<div className="flex flex-col items-center">
												<div className={`flex h-5 w-5 items-center justify-center rounded-full border ${
													isLlm
														? "border-violet-400/40 bg-violet-500/10"
														: isAgent
														? "border-emerald-400/40 bg-emerald-500/10"
														: "border-sky-400/40 bg-sky-500/10"
												}`}>
													<span className={`h-1.5 w-1.5 rounded-full ${
														isLlm ? "bg-violet-400" : isAgent ? "bg-emerald-400" : "bg-sky-400"
													}`} />
												</div>
												{idx < eventLog.length - 1 && (
													<div className="mt-0.5 w-px flex-1 bg-border/30" style={{ minHeight: "0.75rem" }} />
												)}
											</div>
											<div className="min-w-0 flex-1">
												<div className="flex items-baseline gap-2">
													<span className={`font-mono text-xs font-medium ${
														isLlm ? "text-violet-300" : isAgent ? "text-emerald-300" : "text-sky-300"
													}`}>{ev.kind}</span>
													<span className="font-mono text-[10px] text-muted-foreground">{ev.timestamp}</span>
												</div>
												{ev.message && (
													<p className="mt-0.5 text-xs text-foreground/80">{ev.message}</p>
												)}
												{isLlm && data && (
													<div className="mt-1.5 space-y-1 rounded border border-violet-500/20 bg-violet-500/5 px-2.5 py-1.5">
														<div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
															<span className="text-muted-foreground">模型: <span className="text-violet-200">{String(data.model || "-")}</span></span>
															<span className="text-muted-foreground">提供商: <span className="text-violet-200">{String(data.provider || "-")}</span></span>
															<span className="text-muted-foreground">状态: <span className={data.success ? "text-emerald-300" : "text-rose-300"}>{data.success ? "成功" : "失败"}</span></span>
														</div>
														<div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
															<span className="text-muted-foreground">开始: <span className="text-foreground/70">{String(data.started || "-")}</span></span>
															<span className="text-muted-foreground">完成: <span className="text-foreground/70">{String(data.completed || "-")}</span></span>
														</div>
														{data.redacted_error && (
															<p className="text-[11px] text-rose-300">错误: {String(data.redacted_error)}</p>
														)}
													</div>
												)}
												{isAgent && data && (
													<div className="mt-1 text-[11px] text-muted-foreground">
														Agent: <span className="text-emerald-200">{String(data.agent || data.stage || "-")}</span>
													</div>
												)}
											</div>
										</div>
									);
								})
							)}
						</div>
					</div>
				</DialogContent>
			</Dialog>
		</div>
	);
}
