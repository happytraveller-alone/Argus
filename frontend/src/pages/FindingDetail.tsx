import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import FindingCodeWindow from "@/pages/AgentAudit/components/FindingCodeWindow";
import { buildFindingDetailCodeSections } from "@/pages/finding-detail/viewModel";
import {
	getAgentFinding,
	type AgentFinding,
} from "@/shared/api/agentTasks";
import {
	getOpengrepFindingContext,
	getOpengrepScanFinding,
	getOpengrepScanTask,
	type OpengrepFinding,
	type OpengrepFindingContext,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import {
	getGitleaksFinding,
	getGitleaksScanTask,
	type GitleaksFinding,
	type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
	isFindingDetailLocationState,
	normalizeReturnToPath,
	resolveFindingDetailBackTarget,
} from "@/shared/utils/findingRoute";

type FindingSource = "static" | "agent";
type StaticEngine = "opengrep" | "gitleaks";

type CodeViewItem = {
	id: string;
	title: string;
	filePath: string | null;
	code: string;
	lineStart: number | null;
	lineEnd: number | null;
	highlightStartLine: number | null;
	highlightEndLine: number | null;
	focusLine: number | null;
};

function decodePathParam(raw: string | undefined): string {
	try {
		return decodeURIComponent(String(raw || "")).trim();
	} catch {
		return String(raw || "").trim();
	}
}

function resolveFindingSource(raw: string | undefined): FindingSource | null {
	const value = decodePathParam(raw);
	if (value === "static" || value === "agent") return value;
	return null;
}

function resolveStaticEngine(raw: string | null): StaticEngine {
	const value = decodePathParam(raw ?? undefined).toLowerCase();
	if (value === "gitleaks") return "gitleaks";
	return "opengrep";
}

function parseStaticEndLine(finding: OpengrepFinding): number | null {
	const rule = finding.rule as {
		end?: { line?: number | string | null } | null;
	} | null;
	const raw = rule?.end?.line;
	const parsed = Number(raw);
	if (Number.isFinite(parsed) && parsed > 0) return parsed;
	return (
		typeof finding.start_line === "number" && Number.isFinite(finding.start_line)
			? finding.start_line
			: null
	);
}

function getErrorMessage(error: unknown): string {
	const apiError = error as {
		response?: { status?: number; data?: { detail?: string } };
		message?: string;
	};
	const status = Number(apiError?.response?.status || 0);
	if (status === 404) return "缺陷不存在或已被清理";
	return String(
		apiError?.response?.data?.detail ||
			apiError?.message ||
			"缺陷详情加载失败，请稍后重试",
	);
}

function getErrorStatus(error: unknown): number {
	const apiError = error as {
		response?: { status?: number };
	};
	return Number(apiError?.response?.status || 0);
}

function normalizeAgentConfidence(value: number | null | undefined): string {
	if (typeof value !== "number" || !Number.isFinite(value)) return "-";
	if (value >= 0.8) return "高";
	if (value >= 0.5) return "中";
	if (value > 0) return "低";
	return "-";
}

function resolveAgentConfidenceValue(finding: AgentFinding | null): number | null {
	if (!finding) return null;
	if (typeof finding.ai_confidence === "number" && Number.isFinite(finding.ai_confidence)) {
		return finding.ai_confidence;
	}
	if (typeof finding.confidence === "number" && Number.isFinite(finding.confidence)) {
		return finding.confidence;
	}
	return null;
}

function toStaticCodeView(
	finding: OpengrepFinding,
	context: OpengrepFindingContext | null,
): CodeViewItem[] {
	if (context && Array.isArray(context.lines) && context.lines.length > 0) {
		const sortedLines = [...context.lines].sort(
			(a, b) => a.line_number - b.line_number,
		);
		const hitLines = sortedLines
			.filter((line) => Boolean(line.is_hit))
			.map((line) => line.line_number);
		const hitStartLine = hitLines[0] ?? null;
		const hitEndLine = hitLines[hitLines.length - 1] ?? null;
		const code = sortedLines.map((line) => line.content || "").join("\n");
		const lineStart = sortedLines[0]?.line_number ?? context.start_line;
		const lineEnd =
			sortedLines[sortedLines.length - 1]?.line_number ?? context.end_line;
		return [
			{
				id: `static:${finding.id}`,
				title: "命中代码上下文",
				filePath: context.file_path || finding.file_path || null,
					code,
					lineStart,
					lineEnd,
					highlightStartLine:
						hitStartLine ?? context.start_line ?? finding.start_line ?? null,
					highlightEndLine:
						hitEndLine ??
						context.end_line ??
						parseStaticEndLine(finding) ??
						finding.start_line ??
						null,
					focusLine:
						hitStartLine ??
						finding.start_line ??
						context.start_line ??
						lineStart ??
						null,
				},
			];
		}

	const fallbackCode = String(finding.code_snippet || "").trim();
	if (!fallbackCode) return [];
	return [
		{
			id: `static:${finding.id}`,
			title: "命中代码",
			filePath: finding.file_path || null,
			code: fallbackCode,
			lineStart: finding.start_line ?? null,
			lineEnd: parseStaticEndLine(finding),
			highlightStartLine: finding.start_line ?? null,
			highlightEndLine: parseStaticEndLine(finding),
			focusLine: finding.start_line ?? null,
		},
	];
}

function toAgentCodeView(finding: AgentFinding): CodeViewItem[] {
	const context = String(finding.code_context || "").trim();
	const snippet = String(finding.code_snippet || "").trim();
	const code = context || snippet;
	if (!code) return [];

	const lineStart =
		typeof finding.context_start_line === "number" &&
		Number.isFinite(finding.context_start_line)
			? finding.context_start_line
			: finding.line_start;
	const lineEnd =
		typeof finding.context_end_line === "number" &&
		Number.isFinite(finding.context_end_line)
			? finding.context_end_line
			: finding.line_end;

	return [
		{
			id: `agent:${finding.id}`,
			title: context ? "命中代码上下文" : "命中代码",
			filePath: finding.file_path,
			code,
			lineStart: lineStart ?? null,
			lineEnd: lineEnd ?? lineStart ?? null,
			highlightStartLine: finding.line_start ?? lineStart ?? null,
			highlightEndLine: finding.line_end ?? lineEnd ?? lineStart ?? null,
			focusLine: finding.line_start ?? lineStart ?? null,
		},
	];
}

function getSeverityBadgeClass(severity: string): string {
	const normalized = String(severity || "").trim().toUpperCase();
	if (normalized === "CRITICAL" || normalized === "ERROR") {
		return "bg-rose-500/20 text-rose-300 border-rose-500/30";
	}
	if (normalized === "HIGH" || normalized === "WARNING") {
		return "bg-amber-500/20 text-amber-300 border-amber-500/30";
	}
	if (normalized === "MEDIUM" || normalized === "INFO") {
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	}
	if (normalized === "LOW") {
		return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
	}
	return "bg-muted text-muted-foreground border-border";
}

function normalizeFindingToken(value: unknown): string {
	return String(value || "").trim().toLowerCase();
}

function isAgentFalsePositiveFinding(finding: AgentFinding | null): boolean {
	if (!finding) return false;
	return (
		normalizeFindingToken(finding.authenticity) === "false_positive" ||
		normalizeFindingToken(finding.status) === "false_positive"
	);
}

function getAgentFalsePositiveEvidence(finding: AgentFinding | null): string {
	if (!finding) return "未生成详细判定说明";
	const evidence = String(finding.verification_evidence || "").trim();
	if (evidence) return evidence;
	const description = String(finding.description || "").trim();
	if (description) return description;
	return "未生成详细判定说明";
}

export default function FindingDetail() {
	const { source: sourceParam, taskId: rawTaskId, findingId: rawFindingId } = useParams<{
		source: string;
		taskId: string;
		findingId: string;
	}>();
	const navigate = useNavigate();
	const location = useLocation();

	const source = useMemo(() => resolveFindingSource(sourceParam), [sourceParam]);
	const taskId = useMemo(() => decodePathParam(rawTaskId), [rawTaskId]);
	const findingId = useMemo(() => decodePathParam(rawFindingId), [rawFindingId]);
	const staticEngine = useMemo(() => {
		const searchParams = new URLSearchParams(location.search);
		return resolveStaticEngine(searchParams.get("engine"));
	}, [location.search]);
	const returnTo = useMemo(() => {
		const searchParams = new URLSearchParams(location.search);
		return normalizeReturnToPath(searchParams.get("returnTo"));
	}, [location.search]);
	const routeState = useMemo(
		() => (isFindingDetailLocationState(location.state) ? location.state : null),
		[location.state],
	);
	const agentFindingSnapshot = useMemo(() => {
		if (source !== "agent") return null;
		return routeState?.agentFindingSnapshot ?? null;
	}, [routeState, source]);

	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [staticTask, setStaticTask] = useState<OpengrepScanTask | null>(null);
	const [staticFinding, setStaticFinding] = useState<OpengrepFinding | null>(null);
	const [staticContext, setStaticContext] = useState<OpengrepFindingContext | null>(null);
	const [gitleaksTask, setGitleaksTask] = useState<GitleaksScanTask | null>(null);
	const [gitleaksFinding, setGitleaksFinding] = useState<GitleaksFinding | null>(null);
	const [agentFinding, setAgentFinding] = useState<AgentFinding | null>(null);

	useEffect(() => {
		let cancelled = false;

		async function load() {
			if (!source || !taskId || !findingId) {
				setError("缺陷参数无效");
				setLoading(false);
				return;
			}
			setLoading(true);
			setError("");
			setStaticTask(null);
			setStaticFinding(null);
			setStaticContext(null);
			setGitleaksTask(null);
			setGitleaksFinding(null);
			setAgentFinding(null);

			try {
				if (source === "static") {
					if (staticEngine === "gitleaks") {
						const [task, finding] = await Promise.all([
							getGitleaksScanTask(taskId),
							getGitleaksFinding({ taskId, findingId }),
						]);
						if (cancelled) return;
						setGitleaksTask(task);
						setGitleaksFinding(finding);
					} else {
						const [task, finding, context] = await Promise.all([
							getOpengrepScanTask(taskId),
							getOpengrepScanFinding({ taskId, findingId }),
							getOpengrepFindingContext({
								taskId,
								findingId,
								before: 5,
								after: 5,
							}),
						]);
						if (cancelled) return;
						setStaticTask(task);
						setStaticFinding(finding);
						setStaticContext(context);
					}
				} else {
					const canUseSnapshot =
						agentFindingSnapshot &&
						isAgentFalsePositiveFinding(agentFindingSnapshot);
					const retryDelaysMs = canUseSnapshot ? [0, 1200, 2400] : [0];
					let resolved = false;
					for (let attempt = 0; attempt < retryDelaysMs.length; attempt += 1) {
						if (attempt > 0) {
							await new Promise((resolve) =>
								window.setTimeout(resolve, retryDelaysMs[attempt]),
							);
							if (cancelled) return;
						}
						try {
							const finding = await getAgentFinding(taskId, findingId, {
								include_false_positive: true,
							});
							if (cancelled) return;
							setAgentFinding(finding);
							setError("");
							resolved = true;
							break;
						} catch (agentLoadError) {
							const status = getErrorStatus(agentLoadError);
							if (status === 404 && canUseSnapshot) {
								setAgentFinding(agentFindingSnapshot);
								setError("");
								setLoading(false);
								continue;
							}
							throw agentLoadError;
						}
					}
					if (!resolved && canUseSnapshot) {
						if (cancelled) return;
						setAgentFinding(agentFindingSnapshot);
					}
				}
			} catch (loadError) {
				if (!cancelled) {
					setError(getErrorMessage(loadError));
				}
			} finally {
				if (!cancelled) {
					setLoading(false);
				}
			}
		}

		void load();
		return () => {
			cancelled = true;
		};
	}, [agentFindingSnapshot, findingId, source, staticEngine, taskId]);

	const codeViews = useMemo(() => {
		if (source === "static" && staticEngine === "opengrep" && staticFinding) {
			return toStaticCodeView(staticFinding, staticContext);
		}
		if (source === "static" && staticEngine === "gitleaks" && gitleaksFinding) {
			const content = String(gitleaksFinding.match || gitleaksFinding.secret || "").trim();
			if (!content) return [];
			return [
				{
					id: `gitleaks:${gitleaksFinding.id}`,
					title: "命中内容",
					filePath: gitleaksFinding.file_path || null,
					code: content,
					lineStart: gitleaksFinding.start_line ?? null,
					lineEnd: gitleaksFinding.end_line ?? gitleaksFinding.start_line ?? null,
					highlightStartLine: gitleaksFinding.start_line ?? null,
					highlightEndLine: gitleaksFinding.end_line ?? gitleaksFinding.start_line ?? null,
					focusLine: gitleaksFinding.start_line ?? null,
				},
			];
		}
		if (source === "agent" && agentFinding) {
			return toAgentCodeView(agentFinding);
		}
		return [];
	}, [agentFinding, gitleaksFinding, source, staticContext, staticEngine, staticFinding]);

	const codeSections = useMemo(() => buildFindingDetailCodeSections(codeViews), [codeViews]);
	const isAgentFalsePositive = useMemo(
		() => source === "agent" && isAgentFalsePositiveFinding(agentFinding),
		[source, agentFinding],
	);
	const detailPageTitle = isAgentFalsePositive ? "误报判定依据" : "统一缺陷详情";
	const codePanelTitle = isAgentFalsePositive ? "关联代码 / 命中位置" : "命中代码";
	const infoPanelTitle = isAgentFalsePositive ? "判定结果" : "缺陷信息";
	const falsePositiveEvidence = useMemo(
		() => getAgentFalsePositiveEvidence(agentFinding),
		[agentFinding],
	);
	const agentConfidenceLabel = useMemo(() => {
		const normalized = normalizeAgentConfidence(resolveAgentConfidenceValue(agentFinding));
		return normalized === "-" ? null : normalized;
	}, [agentFinding]);

	const handleBack = () => {
		const target = resolveFindingDetailBackTarget({
			returnTo,
			hasHistory: typeof window !== "undefined" && window.history.length > 1,
			state: location.state,
		});
		if (target === -1) {
			navigate(-1);
			return;
		}
		navigate(target);
	};

	const sourceLabel = useMemo(() => {
		if (source === "static") {
			return staticEngine === "gitleaks" ? "静态扫描 · Gitleaks" : "静态扫描 · Opengrep";
		}
		if (source === "agent") return "智能扫描";
		return "-";
	}, [source, staticEngine]);

	return (
		<div className="min-h-screen bg-background p-6 flex flex-col gap-5">
			<div className="flex items-center justify-between gap-3">
				<div className="space-y-1">
					<h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
						{detailPageTitle}
					</h1>
					<p className="text-sm text-muted-foreground">
						来源：{sourceLabel} · 任务ID：{taskId || "-"} · 缺陷ID：{findingId || "-"}
					</p>
				</div>
				<Button variant="outline" className="cyber-btn-outline" onClick={handleBack}>
					<ArrowLeft className="w-4 h-4 mr-2" />
					返回
				</Button>
			</div>

			{loading ? (
				<div className="cyber-card p-8 text-base text-muted-foreground">缺陷详情加载中...</div>
			) : error ? (
				<div className="cyber-card p-8 text-base text-rose-400">{error}</div>
			) : (
				<div className="min-h-0 flex-1 grid grid-cols-1 xl:grid-cols-2 gap-4">
					<div className="cyber-card p-5 min-h-0 flex flex-col gap-4">
						<div className="flex items-center justify-between gap-2">
							<h2 className="text-base font-semibold uppercase tracking-wider text-foreground">
								{codePanelTitle}
							</h2>
							<span className="text-sm text-muted-foreground">{codeSections.length} 个代码块</span>
						</div>

						<div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-1">
							{codeSections.length > 0 ? (
								codeSections.map((item) => (
									<FindingCodeWindow
										key={item.id}
										code={item.code}
										filePath={item.filePath}
										lineStart={item.lineStart}
										lineEnd={item.lineEnd}
										highlightStartLine={item.highlightStartLine}
										highlightEndLine={item.highlightEndLine}
										focusLine={item.focusLine}
										title={item.title || "命中代码上下文"}
										variant="detail"
									/>
								))
							) : (
								<div className="rounded border border-border p-4 text-sm text-muted-foreground">
									{isAgentFalsePositive
										? "该误报未保留可展示代码，仅提供判定结论"
										: "暂无可展示的命中代码"}
								</div>
							)}
						</div>
					</div>

					<div className="cyber-card p-5 min-h-0 flex flex-col gap-5 overflow-y-auto custom-scrollbar">
						<h2 className="text-base font-semibold uppercase tracking-wider text-foreground">
							{infoPanelTitle}
						</h2>

						{source === "static" && staticEngine === "opengrep" && staticFinding ? (
							<>
								<div className="flex flex-wrap items-center gap-2">
									<Badge className={getSeverityBadgeClass(staticFinding.severity)}>
										严重级别：{staticFinding.severity}
									</Badge>
									<Badge className="cyber-badge-muted">状态：{staticFinding.status}</Badge>
									<Badge className="cyber-badge-muted">
										置信度：{staticFinding.confidence || "-"}
									</Badge>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">规则/类型</p>
									<p className="text-base text-foreground break-all">
										{staticFinding.rule_name || "unknown-rule"}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">文件位置</p>
									<p className="text-base text-foreground break-all">
										{staticFinding.file_path || "-"}
										{staticFinding.start_line ? `:${staticFinding.start_line}` : ""}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">任务</p>
									<p className="text-base text-foreground break-all">
										{staticTask?.name || "-"} ({staticTask?.id || "-"})
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">描述</p>
									<p className="text-base text-foreground whitespace-pre-wrap break-words">
										{staticFinding.description || "-"}
									</p>
								</div>
							</>
						) : source === "static" && staticEngine === "gitleaks" && gitleaksFinding ? (
							<>
								<div className="flex flex-wrap items-center gap-2">
									<Badge className="cyber-badge-muted">规则：{gitleaksFinding.rule_id || "-"}</Badge>
									<Badge className="cyber-badge-muted">状态：{gitleaksFinding.status}</Badge>
									<Badge className="cyber-badge-muted">漏洞危害：-</Badge>
									<Badge className="cyber-badge-muted">置信度：-</Badge>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">文件位置</p>
									<p className="text-base text-foreground break-all">
										{gitleaksFinding.file_path || "-"}
										{gitleaksFinding.start_line ? `:${gitleaksFinding.start_line}` : ""}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">任务</p>
									<p className="text-base text-foreground break-all">
										{gitleaksTask?.name || "-"} ({gitleaksTask?.id || "-"})
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">描述</p>
									<p className="text-base text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.description || "-"}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">命中内容</p>
									<p className="text-base text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.match || "-"}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">密钥（脱敏）</p>
									<p className="text-base text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.secret || "-"}
									</p>
								</div>
								<div className="space-y-1.5 text-sm">
									<p className="text-muted-foreground uppercase">提交信息</p>
									<p className="text-base text-foreground whitespace-pre-wrap break-words">
										commit: {gitleaksFinding.commit || "-"}
										{"\n"}
										author: {gitleaksFinding.author || "-"}
										{"\n"}
										email: {gitleaksFinding.email || "-"}
										{"\n"}
										date: {gitleaksFinding.date || "-"}
										{"\n"}
										fingerprint: {gitleaksFinding.fingerprint || "-"}
									</p>
								</div>
							</>
						) : source === "agent" && agentFinding ? (
							<>
								{isAgentFalsePositive ? (
									<>
										<div className="rounded-xl border border-zinc-500/30 bg-zinc-500/10 p-4">
											<p className="text-xs font-mono uppercase tracking-[0.24em] text-zinc-300">
												验证结论
											</p>
											<p className="mt-2 text-base font-medium text-foreground">
												该问题已在验证阶段判定为误报，不计入有效漏洞
											</p>
										</div>
										<div className="flex flex-wrap items-center gap-2">
											<Badge className="cyber-badge-muted">
												状态：{agentFinding.status || "false_positive"}
											</Badge>
											{agentConfidenceLabel ? (
												<Badge className="cyber-badge-muted">
													置信度：{agentConfidenceLabel}
												</Badge>
											) : null}
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">误报类型 / 漏洞类型</p>
											<p className="text-base text-foreground break-all">
												{agentFinding.vulnerability_type || "-"}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">文件位置</p>
											<p className="text-base text-foreground break-all">
												{agentFinding.file_path || "-"}
												{agentFinding.line_start ? `:${agentFinding.line_start}` : ""}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">原标题</p>
											<p className="text-base text-foreground break-words">
												{agentFinding.display_title || agentFinding.title || "-"}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">判定依据</p>
											<p className="text-base text-foreground whitespace-pre-wrap break-words">
												{falsePositiveEvidence}
											</p>
										</div>
										<div className="rounded border border-dashed border-border p-4">
											<p className="mb-1.5 text-sm text-muted-foreground uppercase">说明</p>
											<p className="text-base text-muted-foreground">
												误报仅表示本次验证未确认漏洞成立，不代表该类规则永久失效。
											</p>
										</div>
									</>
								) : (
									<>
										<div className="flex flex-wrap items-center gap-2">
											<Badge className={getSeverityBadgeClass(agentFinding.severity)}>
												严重级别：{agentFinding.severity}
											</Badge>
											<Badge className="cyber-badge-muted">状态：{agentFinding.status}</Badge>
											{agentConfidenceLabel ? (
												<Badge className="cyber-badge-muted">
													置信度：{agentConfidenceLabel}
												</Badge>
											) : null}
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">规则/类型</p>
											<p className="text-base text-foreground break-all">
												{agentFinding.vulnerability_type || "-"}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">文件位置</p>
											<p className="text-base text-foreground break-all">
												{agentFinding.file_path || "-"}
												{agentFinding.line_start ? `:${agentFinding.line_start}` : ""}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">标题</p>
											<p className="text-base text-foreground break-words">
												{agentFinding.display_title || agentFinding.title || "-"}
											</p>
										</div>
										<div className="space-y-1.5 text-sm">
											<p className="text-muted-foreground uppercase">描述</p>
											<p className="text-base text-foreground whitespace-pre-wrap break-words">
												{agentFinding.description || "-"}
											</p>
										</div>
									</>
								)}
							</>
						) : (
							<div className="text-base text-muted-foreground">暂无缺陷信息</div>
						)}

						{!isAgentFalsePositive ? (
							<div className="rounded border border-dashed border-border p-4">
								<p className="text-sm text-muted-foreground uppercase mb-1.5">其他信息（待优化）</p>
								<p className="text-base text-muted-foreground">
									此区域预留给后续扩展（修复建议、证据链、关联规则等）。
								</p>
							</div>
						) : null}
					</div>
				</div>
			)}
		</div>
	);
}
