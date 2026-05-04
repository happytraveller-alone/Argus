import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
	type AppColumnDef,
	createDefaultDataTableState,
	DataTable,
	type DataTableQueryState,
} from "@/components/data-table";
import { StepProgressIndicator } from "@/components/scan/StepProgressIndicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
					<p className="w-full font-mono text-xs text-muted-foreground">
						{record.taskId}
					</p>
				</div>
				<div className="flex items-center gap-2">
					{canCancel && (
						<Button
							size="sm"
							variant="outline"
							className="cyber-btn-ghost h-8 border-rose-500/35 px-3 text-rose-200 hover:border-rose-500/55 hover:bg-rose-500/10 hover:text-rose-100"
							disabled={cancelling}
							onClick={() => void handleCancel()}
						>
							{cancelling ? "取消中…" : "取消任务"}
						</Button>
					)}
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

			{/* Two-column main grid: left = findings table; right = execution progress + event log */}
			<div className="relative grid min-h-0 gap-5 lg:h-[calc(100vh-11rem)] lg:grid-cols-[minmax(0,6fr)_minmax(0,4fr)]">
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

				{/* Right column: execution progress + event log */}
				<div className="flex min-h-[28rem] min-w-0 flex-col gap-5 overflow-y-auto pr-1 lg:h-full">
					{/* Step progress section */}
					{(sseEvents.length > 0 || (!taskTerminal && !sseComplete)) && (
						<div className="rounded-lg border border-border/60 bg-card/40 p-4">
							<SectionTitle>执行进度</SectionTitle>
							<StepProgressIndicator
								events={
									sseEvents.length > 0
										? sseEvents
										: (eventLog as typeof sseEvents)
								}
							/>
						</div>
					)}

					{/* Event log */}
					<div className="rounded-lg border border-border/60 bg-card/40 p-4">
						<SectionTitle>事件日志 ({eventLog.length})</SectionTitle>
						{eventLog.length === 0 ? (
							<p className="font-mono text-xs text-muted-foreground">
								暂无事件
							</p>
						) : (
							<div className="overflow-auto font-mono text-xs">
								<table className="min-w-[540px]">
									<thead>
										<tr className="grid grid-cols-[6rem_10rem_minmax(0,1fr)] gap-x-4 border-b border-border/60 py-1.5 text-left font-semibold uppercase tracking-wider text-foreground/60">
											<th scope="col">类型</th>
											<th scope="col">时间</th>
											<th scope="col">消息</th>
										</tr>
									</thead>
									<tbody>
										{eventLog.map((entry) => (
											<tr
												key={`${entry.kind}:${entry.timestamp}:${entry.message ?? ""}`}
												className="grid grid-cols-[6rem_10rem_minmax(0,1fr)] gap-x-4 border-b border-border/30 py-1.5 last:border-0"
											>
												<td className="text-sky-300">{entry.kind}</td>
												<td className="text-muted-foreground">
													{entry.timestamp}
												</td>
												<td className="text-foreground/80">
													{entry.message ?? "-"}
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						)}
					</div>
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
		</div>
	);
}
