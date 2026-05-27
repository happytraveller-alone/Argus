import { ArrowLeft, RefreshCw, Terminal } from "lucide-react";
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
import type { AgentFinding } from "@/shared/api/agentTasks";
import { getApiBaseUrl } from "@/shared/api/apiBase";
import {
	cancelIntelligentTask,
	getIntelligentTask,
	setIntelligentFindingVerdict,
	type IntelligentTaskEventLogEntry,
	type IntelligentTaskFinding,
	type IntelligentTaskRecord,
	type IntelligentTaskStatus,
} from "@/shared/api/intelligentTasks";
import {
	buildFindingDetailLocationState,
	buildFindingDetailPath,
} from "@/shared/utils/findingRoute";

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

function formatLocation(finding: IntelligentTaskFinding): string {
	const file = finding.file || "";
	const start = finding.lineStart != null ? String(finding.lineStart) : "";
	const end = finding.lineEnd != null && finding.lineEnd !== finding.lineStart
		? String(finding.lineEnd) : "";
	if (!file) return "-";
	const base = `${file}:${start}`;
	return end ? `${base}-${end}` : base;
}

function deriveFindingStatus(
	finding: IntelligentTaskFinding,
	record: IntelligentTaskRecord,
): string {
	if (record.status === "completed") {
		if (finding.userVerdict === "verified") return "真实";
		if (finding.userVerdict === "false_positive") return "误报";
		return "待确认";
	}
	const lastStage = findLastCompletedStage(record.eventLog);
	if (lastStage === "hunt") return "已搜寻";
	if (lastStage === "validate") {
		return finding.validationStatus === "rejected" ? "已驳回" : "已验证";
	}
	if (lastStage === "dedupe") return "已去重";
	if (lastStage === "trace") return "已追踪";
	if (lastStage === "report") return "报告生成中";
	return "扫描中";
}

function findLastCompletedStage(
	eventLog: IntelligentTaskEventLogEntry[],
): string | null {
	for (let i = eventLog.length - 1; i >= 0; i--) {
		const ev = eventLog[i];
		if (ev.kind === "agent_completed") {
			const s = (ev.data as Record<string, unknown> | undefined)?.stage;
			if (typeof s === "string") return s;
		}
	}
	return null;
}

function hasHuntCompleted(eventLog: IntelligentTaskEventLogEntry[]): boolean {
	return eventLog.some(
		(ev) =>
			ev.kind === "agent_completed" &&
			(ev.data as Record<string, unknown> | undefined)?.stage === "hunt",
	);
}

/**
 * Project an intelligent-task finding onto the unified `AgentFinding` shape
 * so it can be rendered by the shared finding-detail page without an extra
 * backend roundtrip. The page expects narrative sections under `### 根因解释`,
 * `### 业务影响`, `### 修复建议`, `### 验证结论` markdown headings, so we
 * synthesise them from the available evidence/trace fields.
 */
function buildAgentFindingSnapshot(
	finding: IntelligentTaskFinding,
	record: IntelligentTaskRecord,
): AgentFinding {
	const evidence = String(finding.evidence ?? "").trim();
	const traceSummary = String(finding.traceSummary ?? "").trim();
	const validationStatus = String(finding.validationStatus ?? "").trim();
	const isFalsePositive = finding.userVerdict === "false_positive";

	const sections: string[] = [];
	if (evidence) sections.push(`### 根因解释\n${evidence}`);
	const verificationParts: string[] = [];
	if (traceSummary) verificationParts.push(traceSummary);
	if (validationStatus) verificationParts.push(`验证状态：${validationStatus}`);
	if (finding.reachable != null) {
		verificationParts.push(`可达性：${finding.reachable ? "可达" : "不可达"}`);
	}
	if (verificationParts.length > 0) {
		sections.push(`### 验证结论\n${verificationParts.join("\n\n")}`);
	}
	const descriptionMarkdown = sections.join("\n\n");

	return {
		id: finding.id,
		task_id: record.taskId,
		vulnerability_type: finding.vulnClass ?? null,
		severity: finding.severity ?? null,
		title: finding.summary ?? null,
		display_title: finding.summary ?? null,
		description: evidence || null,
		description_markdown: descriptionMarkdown || evidence || null,
		file_path: finding.file ?? null,
		line_start: finding.lineStart ?? null,
		line_end: finding.lineEnd ?? null,
		code_snippet: null,
		code_context: null,
		confidence: finding.confidence ?? null,
		ai_confidence: finding.confidence ?? null,
		verdict: finding.userVerdict ?? null,
		status: isFalsePositive ? "false_positive" : (validationStatus || null),
		authenticity: isFalsePositive ? "false_positive" : null,
		verification_evidence: traceSummary || evidence || null,
	};
}

// ── Verdict button with double-click-to-revert ──────────────────────────

let lastVerdictClick: {
	btn: "verified" | "false_positive";
	findingId: string;
	ts: number;
} | null = null;

function VerdictButton({
	finding,
	target,
	disabled,
	onVerdict,
}: {
	finding: IntelligentTaskFinding;
	target: "verified" | "false_positive";
	disabled?: boolean;
	onVerdict: (findingId: string, verdict: string | null) => void;
}) {
	const isActive = finding.userVerdict === target;
	const label = target === "verified" ? "判真" : "判假";
	const now = Date.now();
	const last = lastVerdictClick;

	const handleClick = () => {
		if (disabled) return;
		// Double-click same button within 300ms → revert to null
		if (
			isActive &&
			last &&
			last.btn === target &&
			last.findingId === finding.id &&
			now - last.ts < 300
		) {
			onVerdict(finding.id, null);
			lastVerdictClick = null;
			return;
		}
		onVerdict(finding.id, target);
		lastVerdictClick = { btn: target, findingId: finding.id, ts: now };
	};

	return (
		<Button
			size="sm"
			variant={isActive ? "default" : "outline"}
			className={`h-6 px-2 font-mono text-[11px] ${
				isActive
					? target === "verified"
						? "bg-emerald-600 hover:bg-emerald-700"
						: "bg-rose-600 hover:bg-rose-700"
					: ""
			}`}
			disabled={disabled}
			onClick={handleClick}
		>
			{label}
		</Button>
	);
}

// ── Column builder (depends on VerdictButton above) ────────────────────

function buildFindingColumns(
	record: IntelligentTaskRecord | null,
	navigate: ReturnType<typeof useNavigate>,
	onVerdict: (findingId: string, verdict: string | null) => void,
): AppColumnDef<IntelligentTaskFinding, unknown>[] {
	return [
		{
			id: "rowNumber",
			header: "序号",
			enableSorting: false,
			meta: { label: "序号", align: "center", width: 64 },
			cell: ({ row, table }) =>
				table.getState().pagination.pageIndex *
					table.getState().pagination.pageSize +
				table.getRowModel().rows.findIndex((r) => r.id === row.id) +
				1,
		},
		{
			id: "severity",
			accessorFn: (row) => row.severity,
			header: "危害",
			enableHiding: false,
			meta: {
				label: "危害", width: 90,
				filterVariant: "select",
				filterOptions: [
					{ label: "严重", value: "critical" },
					{ label: "高危", value: "high" },
					{ label: "中危", value: "medium" },
					{ label: "低危", value: "low" },
				],
			},
			cell: ({ row }) => (
				<Badge variant="outline" className="font-mono text-[11px]">
					{row.original.severity || "-"}
				</Badge>
			),
		},
		{
			id: "location",
			accessorFn: (row) => formatLocation(row),
			header: "位置",
			enableSorting: false,
			enableColumnFilter: false,
			meta: { label: "位置", minWidth: 260, plainHeader: true },
			cell: ({ row }) => {
				const loc = formatLocation(row.original);
				return (
					<button
						type="button"
						className="block w-full whitespace-normal break-all text-left font-mono text-[11px] text-sky-300 hover:underline cursor-pointer"
						title={`点击复制: ${loc}`}
						onClick={() => {
							void navigator.clipboard.writeText(loc);
							toast.success("路径已复制");
						}}
					>
						{loc}
					</button>
				);
			},
		},
		{
			id: "status",
			accessorFn: (row) => row.id,
			header: "状态",
			enableSorting: false,
			meta: { label: "状态", width: 100 },
			cell: ({ row }) => {
				const status = deriveFindingStatus(row.original, record!);
				return (
					<span className="font-mono text-[11px] text-muted-foreground">
						{status}
					</span>
				);
			},
		},
		{
			id: "actions",
			header: "操作",
			enableSorting: false,
			meta: { label: "操作", width: 220, align: "center" },
			cell: ({ row }) => {
				const finding = row.original;
				const done = record?.status === "completed";
				return (
					<div className="flex items-center justify-center gap-1.5">
						<Button
							size="sm"
							variant="outline"
							className="h-6 px-2 font-mono text-[11px]"
							onClick={() => {
								if (!record) return;
								const snapshot = buildAgentFindingSnapshot(finding, record);
								navigate(
									buildFindingDetailPath({
										source: "agent",
										taskId: record.taskId,
										findingId: finding.id,
									}),
									{ state: buildFindingDetailLocationState(snapshot) },
								);
							}}
						>
							详情
						</Button>
						<VerdictButton
							finding={finding}
							target="verified"
							disabled={!done}
							onVerdict={onVerdict}
						/>
						<VerdictButton
							finding={finding}
							target="false_positive"
							disabled={!done}
							onVerdict={onVerdict}
						/>
					</div>
				);
			},
		},
	];
}

// ── Page component ──────────────────────────────────────────────────────

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
	const { events: sseEvents } = useSseStream(sseUrl, {
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
		}, 5000);
		return () => {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
		};
	}, [fetchRecord, record]);

	const handleVerdict = useCallback(
		(findingId: string, verdict: string | null) => {
			if (!taskId) return;
			// Optimistic UI: update local record immediately.
			if (record) {
				const updated = { ...record };
				const idx = updated.findings?.findIndex((f) => f.id === findingId) ?? -1;
				if (idx >= 0 && updated.findings) {
					updated.findings = [...updated.findings];
					updated.findings[idx] = {
						...updated.findings[idx],
						userVerdict: verdict,
					};
				}
				setRecord(updated);
			}
			// Fire API call; rollback on failure.
			setIntelligentFindingVerdict(taskId, findingId, verdict).catch((err) => {
				toast.error(
					`判定失败：${err instanceof Error ? err.message : "未知错误"}`,
				);
				// Rollback: re-fetch the full record.
				void fetchRecord();
			});
		},
		[taskId, record, fetchRecord],
	);

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
	const headerTags = [
		record.projectName?.trim() || record.projectId || "-",
		formatDuration(record.durationMs),
		`发现问题 ${findings.length.toLocaleString()}`,
	];

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

			{/* Findings table — full width */}
			<div className="relative min-h-[28rem] lg:h-[calc(100vh-14rem)]">
				<div className="min-h-[28rem] min-w-0 overflow-y-auto rounded-md pr-1 lg:h-full">
					<DataTable
						data={findings}
						columns={buildFindingColumns(record, navigate, handleVerdict)}
						state={tableState}
						onStateChange={setTableState}
						emptyState={{
							title: hasHuntCompleted(record.eventLog ?? [])
								? "暂无发现问题"
								: "搜寻阶段进行中…",
							description: hasHuntCompleted(record.eventLog ?? [])
								? "0 findings (lifecycle proof captured)"
								: "等待第一批 findings",
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
						<DialogTitle>时间日志 ({activeEvents.length})</DialogTitle>
					</DialogHeader>
					<div className="flex-1 overflow-y-auto">
						<div className="flex flex-col gap-0">
							{activeEvents.length === 0 ? (
								<p className="py-8 text-center text-sm text-muted-foreground">暂无交互记录</p>
							) : (
								activeEvents.map((ev, idx) => {
									const data = ev.data && typeof ev.data === "object" ? (ev.data as Record<string, unknown>) : null;
									const redactedError = data?.redacted_error;
									const isLlm = ev.kind === "llm_attempt";
									const isAgent = ev.kind === "agent_started" || ev.kind === "agent_completed";
									const promptPreview = data?.promptPreview;
									const responsePreview = data?.responsePreview;
									const rawBodyPreview = data?.rawBodyPreview;
									const httpStatus = data?.httpStatus;
									const attemptsCount = data?.attempts;
									const promptChars = data?.promptChars;
									const responseChars = data?.responseChars;
									const stageLabel = data?.stage;
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
												{idx < activeEvents.length - 1 && (
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
													<div className="mt-1.5 space-y-1.5 rounded border border-violet-500/20 bg-violet-500/5 px-2.5 py-1.5">
														<div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
															{stageLabel ? (
																<span className="text-muted-foreground">阶段: <span className="text-violet-200">{String(stageLabel)}</span></span>
															) : null}
															<span className="text-muted-foreground">模型: <span className="text-violet-200">{String(data.model || "-")}</span></span>
															<span className="text-muted-foreground">提供商: <span className="text-violet-200">{String(data.provider || "-")}</span></span>
															<span className="text-muted-foreground">状态: <span className={data.success ? "text-emerald-300" : "text-rose-300"}>{data.success ? "成功" : "失败"}</span></span>
															{attemptsCount != null ? (
																<span className="text-muted-foreground">HTTP尝试: <span className="text-violet-200">{String(attemptsCount)}</span></span>
															) : null}
															{httpStatus != null ? (
																<span className="text-muted-foreground">HTTP状态: <span className={Number(httpStatus) >= 200 && Number(httpStatus) < 300 ? "text-emerald-300" : "text-rose-300"}>{String(httpStatus)}</span></span>
															) : null}
														</div>
														<div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
															<span className="text-muted-foreground">开始: <span className="text-foreground/70">{String(data.started || "-")}</span></span>
															<span className="text-muted-foreground">完成: <span className="text-foreground/70">{String(data.completed || "-")}</span></span>
														</div>
														{promptPreview ? (
															<details className="rounded border border-violet-500/15 bg-violet-500/5 px-2 py-1">
																<summary className="cursor-pointer text-[11px] text-violet-300/90">
																	请求摘要{promptChars != null ? ` (${String(promptChars)} 字符)` : ""}
																</summary>
																<pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words text-[10.5px] text-foreground/80">{String(promptPreview)}</pre>
															</details>
														) : null}
														{responsePreview ? (
															<details className="rounded border border-violet-500/15 bg-violet-500/5 px-2 py-1">
																<summary className="cursor-pointer text-[11px] text-violet-300/90">
																	响应摘要{responseChars != null ? ` (${String(responseChars)} 字符)` : ""}
																</summary>
																<pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words text-[10.5px] text-foreground/80">{String(responsePreview)}</pre>
															</details>
														) : null}
														{rawBodyPreview ? (
															<details className="rounded border border-rose-500/20 bg-rose-500/5 px-2 py-1" open={Boolean(redactedError)}>
																<summary className="cursor-pointer text-[11px] text-rose-300/90">原始响应体（用于诊断解析错误）</summary>
																<pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words text-[10.5px] text-foreground/80">{String(rawBodyPreview)}</pre>
															</details>
														) : null}
														{redactedError ? (
															<p className="text-[11px] text-rose-300">错误: {String(redactedError)}</p>
														) : null}
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
