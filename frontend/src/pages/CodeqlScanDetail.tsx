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
	getCodeqlScanTask,
	getCodeqlScanFindings,
	interruptCodeqlScanTask,
	type OpengrepScanTask,
	type OpengrepFinding,
} from "@/shared/api/opengrep";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);

function isTerminal(status: string): boolean {
	return TERMINAL_STATUSES.has(status);
}

function StatusPill({ status }: { status: string }) {
	let className = "font-mono text-xs";
	if (status === "completed") {
		className += " border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
	} else if (status === "running" || status === "pending" || status === "queued") {
		className += " border-sky-500/30 bg-sky-500/10 text-sky-300";
	} else if (status === "failed" || status === "interrupted") {
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

function SeverityBadge({ severity }: { severity: string }) {
	const sev = severity.toUpperCase();
	let className = "font-mono text-xs";
	if (sev === "ERROR" || sev === "CRITICAL" || sev === "HIGH") {
		className += " border-rose-500/40 bg-rose-500/10 text-rose-300";
	} else if (sev === "WARNING" || sev === "MEDIUM") {
		className += " border-orange-500/40 bg-orange-500/10 text-orange-300";
	} else {
		className += " border-sky-500/40 bg-sky-500/10 text-sky-300";
	}
	return (
		<Badge variant="outline" className={className}>
			{severity}
		</Badge>
	);
}

export default function CodeqlScanDetail() {
	const { taskId } = useParams<{ taskId: string }>();
	const [task, setTask] = useState<OpengrepScanTask | null>(null);
	const [findings, setFindings] = useState<OpengrepFinding[]>([]);
	const [loading, setLoading] = useState(true);
	const [fetchError, setFetchError] = useState<string | null>(null);
	const [cancelling, setCancelling] = useState(false);
	const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const taskTerminal = task ? isTerminal(task.status) : false;

	const sseUrl = taskId
		? `${getApiBaseUrl()}/static-tasks/codeql/tasks/${taskId}/stream`
		: "";

	const { events: sseEvents, isConnected, isComplete } = useSseStream(sseUrl, {
		enabled: Boolean(taskId) && !taskTerminal,
	});

	const fetchTask = async () => {
		if (!taskId) return;
		try {
			const data = await getCodeqlScanTask(taskId);
			setTask(data);
			setFetchError(null);
			// Fetch findings once we have a task
			try {
				const foundFindings = await getCodeqlScanFindings({ taskId });
				setFindings(foundFindings);
			} catch {
				// findings fetch failure is non-fatal
			}
		} catch (err) {
			setFetchError(err instanceof Error ? err.message : "获取任务详情失败");
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void fetchTask();
	}, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

	// Poll every 3s while non-terminal
	useEffect(() => {
		if (!task) return;
		if (isTerminal(task.status)) {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
			return;
		}
		pollingRef.current = setInterval(() => {
			void fetchTask();
		}, 3000);
		return () => {
			if (pollingRef.current) {
				clearInterval(pollingRef.current);
				pollingRef.current = null;
			}
		};
	}, [task?.status]); // eslint-disable-line react-hooks/exhaustive-deps

	const handleCancel = async () => {
		if (!taskId) return;
		setCancelling(true);
		try {
			await interruptCodeqlScanTask(taskId);
			toast.success("已提交取消请求");
			void fetchTask();
		} catch (err) {
			toast.error(`取消失败：${err instanceof Error ? err.message : "未知错误"}`);
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

	if (fetchError || !task) {
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
						void fetchTask();
					}}
				>
					重试
				</Button>
			</div>
		);
	}

	const canCancel = task.status === "pending" || task.status === "running" || task.status === "queued";

	// Derive severity summary from findings
	const findingsBySeverity = findings.reduce<Record<string, number>>(
		(acc, f) => {
			const sev = (f.severity ?? "unknown").toUpperCase();
			acc[sev] = (acc[sev] ?? 0) + 1;
			return acc;
		},
		{},
	);

	const isStreaming = isConnected && !isComplete;

	return (
		<div className="relative flex min-h-screen flex-col gap-6 bg-background p-6 font-mono">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{/* Header */}
			<div className="relative flex flex-wrap items-start justify-between gap-3">
				<div className="flex flex-col gap-1">
					<h1 className="text-lg font-semibold tracking-tight text-foreground">
						CodeQL 扫描任务详情
					</h1>
					<p className="font-mono text-xs text-muted-foreground">{task.id}</p>
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
					<Field label="任务 ID" value={task.id} />
					<Field label="项目 ID" value={task.project_id} />
					<div className="flex flex-col gap-0.5">
						<span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
							状态
						</span>
						<StatusPill status={task.status} />
					</div>
					<Field label="任务名称" value={task.name} />
					<Field label="目标路径" value={task.target_path} />
					<Field label="创建时间" value={task.created_at} />
					<Field label="更新时间" value={task.updated_at ?? "-"} />
					<Field label="扫描文件数" value={String(task.files_scanned)} />
					<Field label="扫描行数" value={String(task.lines_scanned)} />
					<Field
						label="耗时 (ms)"
						value={task.scan_duration_ms ? String(task.scan_duration_ms) : "-"}
					/>
					<Field label="发现总数" value={String(task.total_findings)} />
				</div>
			</div>

			{/* Step progress */}
			{sseEvents.length > 0 && (
				<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
					<SectionTitle>执行进度</SectionTitle>
					<StepProgressIndicator events={sseEvents} />
				</div>
			)}

			{/* LLM Reasoning */}
			{(sseEvents.length > 0 || isStreaming) && (
				<div className="relative rounded-lg border border-purple-500/20 bg-card/40 p-4">
					<SectionTitle>LLM 推理过程</SectionTitle>
					<LlmReasoningPanel events={sseEvents} isStreaming={isStreaming} />
				</div>
			)}

			{/* Failure info */}
			{(task.status === "failed" || task.status === "interrupted") && (
				<div className="relative rounded-lg border border-rose-500/30 bg-rose-500/5 p-4">
					<SectionTitle>失败信息</SectionTitle>
					<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
						<Field label="错误数" value={String(task.error_count)} />
						<Field label="警告数" value={String(task.warning_count)} />
					</div>
				</div>
			)}

			{/* Findings */}
			<div className="relative rounded-lg border border-border/60 bg-card/40 p-4">
				<SectionTitle>发现问题 ({findings.length})</SectionTitle>
				{findings.length === 0 ? (
					<p className="font-mono text-xs text-muted-foreground">
						{taskTerminal ? "0 findings" : "扫描进行中，等待结果…"}
					</p>
				) : (
					<>
						{/* Severity summary */}
						{Object.keys(findingsBySeverity).length > 0 && (
							<div className="mb-3 flex flex-wrap gap-2">
								{Object.entries(findingsBySeverity).map(([sev, count]) => (
									<Badge key={sev} variant="outline" className="font-mono text-xs">
										{sev}: {count}
									</Badge>
								))}
							</div>
						)}
						<div className="flex flex-col gap-2">
							{findings.map((finding) => (
								<div
									key={finding.id}
									className="rounded border border-border/50 bg-muted/20 p-3"
								>
									<div className="flex flex-wrap items-center gap-2">
										<SeverityBadge severity={finding.severity} />
										{finding.confidence && (
											<Badge variant="outline" className="font-mono text-xs text-muted-foreground">
												{finding.confidence}
											</Badge>
										)}
										<span className="font-mono text-xs text-muted-foreground">
											{finding.id}
										</span>
									</div>
									{finding.rule_name && (
										<p className="mt-1 font-mono text-xs text-foreground/80">
											{finding.rule_name}
										</p>
									)}
									<p className="mt-1 font-mono text-xs text-muted-foreground">
										{finding.file_path}
										{finding.start_line ? `:${finding.start_line}` : ""}
									</p>
									{finding.description && (
										<p className="mt-1 text-sm text-foreground/90">{finding.description}</p>
									)}
								</div>
							))}
						</div>
					</>
				)}
			</div>
		</div>
	);
}
