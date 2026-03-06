import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import FindingCodeWindow from "@/pages/AgentAudit/components/FindingCodeWindow";
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
import { normalizeReturnToPath } from "@/shared/utils/findingRoute";

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

function normalizeAgentConfidence(value: number | null | undefined): string {
	if (typeof value !== "number" || !Number.isFinite(value)) return "-";
	if (value >= 0.8) return "高";
	if (value >= 0.5) return "中";
	if (value > 0) return "低";
	return "-";
}

function resolveAgentConfidenceValue(finding: AgentFinding): number | null {
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

	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [staticTask, setStaticTask] = useState<OpengrepScanTask | null>(null);
	const [staticFinding, setStaticFinding] = useState<OpengrepFinding | null>(null);
	const [staticContext, setStaticContext] = useState<OpengrepFindingContext | null>(
		null,
	);
	const [gitleaksTask, setGitleaksTask] = useState<GitleaksScanTask | null>(null);
	const [gitleaksFinding, setGitleaksFinding] = useState<GitleaksFinding | null>(null);
	const [agentFinding, setAgentFinding] = useState<AgentFinding | null>(null);
	const [selectedCodeId, setSelectedCodeId] = useState<string | null>(null);

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
					const finding = await getAgentFinding(taskId, findingId, {
						include_false_positive: true,
					});
					if (cancelled) return;
					setAgentFinding(finding);
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
	}, [findingId, source, staticEngine, taskId]);

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
					highlightEndLine:
						gitleaksFinding.end_line ?? gitleaksFinding.start_line ?? null,
					focusLine: gitleaksFinding.start_line ?? null,
				},
			];
		}
		if (source === "agent" && agentFinding) {
			return toAgentCodeView(agentFinding);
		}
		return [];
	}, [
		agentFinding,
		gitleaksFinding,
		source,
		staticContext,
		staticEngine,
		staticFinding,
	]);

	useEffect(() => {
		setSelectedCodeId(codeViews[0]?.id ?? null);
	}, [codeViews]);

	const selectedCodeView = useMemo(
		() => codeViews.find((item) => item.id === selectedCodeId) ?? codeViews[0] ?? null,
		[codeViews, selectedCodeId],
	);

	const handleBack = () => {
		if (returnTo) {
			navigate(returnTo);
			return;
		}
		navigate(-1);
	};

	const sourceLabel = useMemo(() => {
		if (source === "static") {
			return staticEngine === "gitleaks" ? "静态扫描 · Gitleaks" : "静态扫描 · Opengrep";
		}
		if (source === "agent") return "智能扫描";
		return "-";
	}, [source, staticEngine]);

	return (
		<div className="min-h-screen bg-background p-6 space-y-5">
			<div className="flex items-center justify-between gap-3">
				<div className="space-y-1">
					<h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
						统一缺陷详情
					</h1>
					<p className="text-xs text-muted-foreground">
						来源：{sourceLabel} · 任务ID：{taskId || "-"} · 缺陷ID：{findingId || "-"}
					</p>
				</div>
				<Button
					variant="outline"
					className="cyber-btn-outline"
					onClick={handleBack}
				>
					<ArrowLeft className="w-4 h-4 mr-2" />
					返回
				</Button>
			</div>

			{loading ? (
				<div className="cyber-card p-8 text-sm text-muted-foreground">
					缺陷详情加载中...
				</div>
			) : error ? (
				<div className="cyber-card p-8 text-sm text-rose-400">{error}</div>
			) : (
				<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
					<div className="cyber-card p-4 space-y-3">
						<div className="flex items-center justify-between gap-2">
							<h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
								命中文件
							</h2>
							<span className="text-xs text-muted-foreground">
								{codeViews.length} 个
							</span>
						</div>

						<div className="space-y-2">
							{codeViews.length > 0 ? (
								codeViews.map((item) => (
									<button
										key={item.id}
										type="button"
										onClick={() => setSelectedCodeId(item.id)}
										className={`w-full text-left px-3 py-2 rounded border text-xs transition-colors ${
											selectedCodeView?.id === item.id
												? "border-sky-500/50 bg-sky-500/10 text-sky-200"
												: "border-border bg-card/40 text-muted-foreground hover:text-foreground"
										}`}
									>
										<div className="font-semibold truncate">{item.title}</div>
										<div className="truncate">
											{item.filePath || "未定位文件"}
											{item.focusLine ? `:${item.focusLine}` : ""}
										</div>
									</button>
								))
							) : (
								<div className="rounded border border-border p-3 text-xs text-muted-foreground">
									暂无可展示的命中代码
								</div>
							)}
						</div>

						{selectedCodeView && (
							<FindingCodeWindow
								code={selectedCodeView.code}
								filePath={selectedCodeView.filePath}
								lineStart={selectedCodeView.lineStart}
								lineEnd={selectedCodeView.lineEnd}
								highlightStartLine={selectedCodeView.highlightStartLine}
								highlightEndLine={selectedCodeView.highlightEndLine}
								focusLine={selectedCodeView.focusLine}
								title="命中代码上下文"
							/>
						)}
					</div>

					<div className="cyber-card p-4 space-y-4">
						<h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
							缺陷信息
						</h2>

						{source === "static" && staticEngine === "opengrep" && staticFinding ? (
							<>
								<div className="flex flex-wrap items-center gap-2">
									<Badge className={getSeverityBadgeClass(staticFinding.severity)}>
										严重级别：{staticFinding.severity}
									</Badge>
									<Badge className="cyber-badge-muted">
										状态：{staticFinding.status}
									</Badge>
									<Badge className="cyber-badge-muted">
										置信度：{staticFinding.confidence || "-"}
									</Badge>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">规则/类型</p>
									<p className="text-foreground break-all">
										{staticFinding.rule_name || "unknown-rule"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">文件位置</p>
									<p className="text-foreground break-all">
										{staticFinding.file_path || "-"}
										{staticFinding.start_line ? `:${staticFinding.start_line}` : ""}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">任务</p>
									<p className="text-foreground break-all">
										{staticTask?.name || "-"} ({staticTask?.id || "-"})
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">描述</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
										{staticFinding.description || "-"}
									</p>
								</div>
							</>
						) : source === "static" &&
						  staticEngine === "gitleaks" &&
						  gitleaksFinding ? (
							<>
								<div className="flex flex-wrap items-center gap-2">
									<Badge className="cyber-badge-muted">
										规则：{gitleaksFinding.rule_id || "-"}
									</Badge>
									<Badge className="cyber-badge-muted">
										状态：{gitleaksFinding.status}
									</Badge>
									<Badge className="cyber-badge-muted">漏洞危害：-</Badge>
									<Badge className="cyber-badge-muted">置信度：-</Badge>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">文件位置</p>
									<p className="text-foreground break-all">
										{gitleaksFinding.file_path || "-"}
										{gitleaksFinding.start_line
											? `:${gitleaksFinding.start_line}`
											: ""}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">任务</p>
									<p className="text-foreground break-all">
										{gitleaksTask?.name || "-"} ({gitleaksTask?.id || "-"})
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">描述</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.description || "-"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">命中内容</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.match || "-"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">密钥（脱敏）</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
										{gitleaksFinding.secret || "-"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">提交信息</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
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
								<div className="flex flex-wrap items-center gap-2">
									<Badge className={getSeverityBadgeClass(agentFinding.severity)}>
										严重级别：{agentFinding.severity}
									</Badge>
									<Badge className="cyber-badge-muted">
										状态：{agentFinding.status}
									</Badge>
									<Badge className="cyber-badge-muted">
										置信度：{normalizeAgentConfidence(resolveAgentConfidenceValue(agentFinding))}
									</Badge>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">规则/类型</p>
									<p className="text-foreground break-all">
										{agentFinding.vulnerability_type || "-"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">文件位置</p>
									<p className="text-foreground break-all">
										{agentFinding.file_path || "-"}
										{agentFinding.line_start ? `:${agentFinding.line_start}` : ""}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">标题</p>
									<p className="text-foreground break-words">
										{agentFinding.display_title || agentFinding.title || "-"}
									</p>
								</div>
								<div className="space-y-1 text-xs">
									<p className="text-muted-foreground uppercase">描述</p>
									<p className="text-foreground whitespace-pre-wrap break-words">
										{agentFinding.description || "-"}
									</p>
								</div>
							</>
						) : (
							<div className="text-sm text-muted-foreground">暂无缺陷信息</div>
						)}

						<div className="rounded border border-dashed border-border p-3">
							<p className="text-xs text-muted-foreground uppercase mb-1">
								其他信息（待优化）
							</p>
							<p className="text-xs text-muted-foreground">
								此区域预留给后续扩展（修复建议、证据链、关联规则等）。
							</p>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
