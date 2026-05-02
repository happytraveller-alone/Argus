import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LlmReasoningPanel } from "@/components/scan/LlmReasoningPanel";
import { StepProgressIndicator } from "@/components/scan/StepProgressIndicator";
import { useSseStream } from "@/hooks/useSseStream";
import { getApiBaseUrl } from "@/shared/api/apiBase";
import {
	cancelIntelligentTask,
	getIntelligentTask,
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

function StatusPill({ status }: { status: string }) {
	let className = "font-mono text-xs";
	if (status === "completed") {
		className +=
			" border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
	} else if (status === "running" || status === "pending") {
		className += " border-sky-500/30 bg-sky-500/10 text-sky-300";
	} else if (status === "failed") {
		className += " border-rose-500/30 bg-rose-500/10 text-rose-300";
	} else {
		className += " border-orange-500/30 bg-orange-500/10 text-orange-300";
	}
	return <Badge className={className}>{status}</Badge>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
	return (
		<h3 className="mb-2 font-mono text-xs font-semibold uppercase tracking-widest text-foreground/60">
			{children}
		</h3>
	);
}

function Field({
	label,
	value,
}: {
	label: string;
	value: React.ReactNode;
}) {
	return (
		<div className="flex min-w-0 flex-col gap-0.5">
			<span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
				{label}
			</span>
			<span className="font-mono text-sm text-foreground">{value ?? "-"}</span>
		</div>
	);
}

export default function AgentAuditDetail() {
	const { taskId } = useParams<{ taskId: string }>();
	const [record, setRecord] = useState<IntelligentTaskRecord | null>(null);
	const [loading, setLoading] = useState(true);
	const [fetchError, setFetchError] = useState<string | null>(null);
	const [cancelling, setCancelling] = useState(false);
	const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const taskTerminal = record ? isTerminal(record.status) : false;
	const sseUrl = taskId
		? `${getApiBaseUrl()}/intelligent-tasks/${taskId}/stream`
		: "";
	const {
		events: sseEvents,
		isConnected: sseConnected,
		isComplete: sseComplete,
	} = useSseStream(sseUrl, { enabled: Boolean(taskId) && !taskTerminal });

	const fetchRecord = async () => {
		if (!taskId) return;
		try {
			const data = await getIntelligentTask(taskId);
			setRecord(data);
			setFetchError(null);
		} catch (err) {
			setFetchError(
				err instanceof Error ? err.message : "获取任务详情失败",
			);
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void fetchRecord();
	}, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

	// Polling: 3s while non-terminal
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
	}, [record?.status]); // eslint-disable-line react-hooks/exhaustive-deps

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
				<span className="font-mono text-sm text-muted-foreground">
					加载中…
				</span>
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

	const canCancel =
		record.status === "pending" || record.status === "running";

	const findings = Array.isArray(record.findings) ? record.findings : [];
	const eventLog = Array.isArray(record.eventLog) ? record.eventLog : [];

	// Derive severity counts from findings
	const findingsBySeverity = findings.reduce<Record<string, number>>(
		(acc, f) => {
			const sev = (f.severity ?? "unknown").toLowerCase();
			acc[sev] = (acc[sev] ?? 0) + 1;
			return acc;
		},
		{},
	);

	return (
		<div className="relative flex min-h-screen flex-col gap-6 bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{/* Header */}
			<div className="relative flex flex-wrap items-start justify-between gap-3">
				<div className="flex flex-col gap-1">
					<h1 className="text-lg font-semibold tracking-tight text-foreground">
						智能审计任务详情
					</h1>
					<p className="font-mono text-xs text-muted-foreground">
						{record.taskId}
					</p>
				</div>
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
			</div>

			{/* Metadata card */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>基本信息</SectionTitle>
				<div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
					<Field label="任务 ID" value={record.taskId} />
					<Field label="项目 ID" value={record.projectId} />
					<div className="flex flex-col gap-0.5">
						<span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
							状态
						</span>
						<StatusPill status={record.status} />
					</div>
					<Field label="创建时间" value={record.createdAt} />
					<Field
						label="开始时间"
						value={record.startedAt ?? "-"}
					/>
					<Field
						label="完成时间"
						value={record.completedAt ?? "-"}
					/>
					<Field
						label="耗时 (ms)"
						value={
							record.durationMs !== undefined
								? String(record.durationMs)
								: "-"
						}
					/>
					<Field label="LLM 模型" value={record.llmModel} />
					<Field
						label="LLM Fingerprint"
						value={record.llmFingerprint}
					/>
				</div>
			</div>

			{/* Step progress */}
			{(sseEvents.length > 0 || (!taskTerminal && !sseComplete)) && (
				<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
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

			{/* LLM Reasoning */}
			{(sseEvents.length > 0 || eventLog.length > 0) && (
				<div className="relative rounded-lg border border-purple-500/20 bg-card/40 p-4">
					<SectionTitle>LLM 推理过程</SectionTitle>
					<LlmReasoningPanel
						events={
							sseEvents.length > 0
								? sseEvents
								: (eventLog as typeof sseEvents)
						}
						isStreaming={sseConnected && !sseComplete}
					/>
				</div>
			)}

			{/* Failure info */}
			{record.status === "failed" && (
				<div className="relative rounded-lg border border-rose-500/30 bg-rose-500/5 p-4">
					<SectionTitle>失败信息</SectionTitle>
					<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<Field
							label="失败阶段"
							value={record.failureStage ?? "-"}
						/>
						<Field
							label="失败原因"
							value={record.failureReason ?? "-"}
						/>
					</div>
				</div>
			)}

			{/* Input summary */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>输入摘要</SectionTitle>
				<pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-muted/30 p-3 font-mono text-xs text-foreground/90">
					{record.inputSummary || "-"}
				</pre>
			</div>

			{/* Report summary */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>报告摘要</SectionTitle>
				<p className="text-sm text-foreground/90">
					{record.reportSummary || "-"}
				</p>
			</div>

			{/* Findings */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>
					发现问题 ({findings.length})
				</SectionTitle>
				{findings.length === 0 ? (
					<p className="font-mono text-xs text-muted-foreground">
						0 findings (lifecycle proof captured)
					</p>
				) : (
					<>
						{/* Severity summary */}
						{Object.keys(findingsBySeverity).length > 0 && (
							<div className="mb-3 flex flex-wrap gap-2">
								{Object.entries(findingsBySeverity).map(
									([sev, count]) => (
										<Badge
											key={sev}
											variant="outline"
											className="font-mono text-xs"
										>
											{sev}: {count}
										</Badge>
									),
								)}
							</div>
						)}
						<div className="flex flex-col gap-2">
							{findings.map((finding) => (
								<div
									key={finding.id}
									className="rounded border border-border/50 bg-muted/20 p-3"
								>
									<div className="flex items-center gap-2">
										<Badge
											variant="outline"
											className="font-mono text-xs"
										>
											{finding.severity}
										</Badge>
										<span className="font-mono text-xs text-muted-foreground">
											{finding.id}
										</span>
									</div>
									<p className="mt-1 text-sm text-foreground/90">
										{finding.summary}
									</p>
									{finding.evidence && (
										<p className="mt-1 font-mono text-xs text-muted-foreground">
											{finding.evidence}
										</p>
									)}
								</div>
							))}
						</div>
					</>
				)}
			</div>

			{/* Event log */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>事件日志 ({eventLog.length})</SectionTitle>
				{eventLog.length === 0 ? (
					<p className="font-mono text-xs text-muted-foreground">
						暂无事件
					</p>
				) : (
					<div className="overflow-auto">
						<table className="w-full min-w-[540px] border-collapse font-mono text-xs">
							<thead>
								<tr className="border-b border-border/60">
									<th className="py-1.5 pr-4 text-left font-semibold uppercase tracking-wider text-foreground/60">
										类型
									</th>
									<th className="py-1.5 pr-4 text-left font-semibold uppercase tracking-wider text-foreground/60">
										时间
									</th>
									<th className="py-1.5 text-left font-semibold uppercase tracking-wider text-foreground/60">
										消息
									</th>
								</tr>
							</thead>
							<tbody>
								{eventLog.map((entry, idx) => (
									<tr
										key={idx}
										className="border-b border-border/30 last:border-0"
									>
										<td className="py-1.5 pr-4 text-sky-300">
											{entry.kind}
										</td>
										<td className="py-1.5 pr-4 text-muted-foreground">
											{entry.timestamp}
										</td>
										<td className="py-1.5 text-foreground/80">
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
	);
}
