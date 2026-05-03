import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
	AlertCircle,
	ArrowLeft,
	Ban,
	Loader2,
	RefreshCw,
} from "lucide-react";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	areDataTableQueryStatesEqual,
	type DataTableQueryState,
	useDataTableUrlState,
} from "@/components/data-table";
import { LlmReasoningPanel } from "@/components/scan/LlmReasoningPanel";
import { StepProgressIndicator } from "@/components/scan/StepProgressIndicator";
import { useSseStream } from "@/hooks/useSseStream";
import { getApiBaseUrl } from "@/shared/api/apiBase";
import { api as databaseApi } from "@/shared/api/database";
import CodeqlExplorationPanel from "./static-analysis/CodeqlExplorationPanel";
import StaticAnalysisFindingsTable from "./static-analysis/StaticAnalysisFindingsTable";
import {
	createStaticAnalysisInitialTableState,
	resolveStaticAnalysisTableState,
} from "./static-analysis/tableState";
import { useStaticAnalysisData } from "./static-analysis/useStaticAnalysisData";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import {
	buildStaticAnalysisHeaderSummary,
	buildStaticAnalysisTaskStatusSummary,
	buildUnifiedFindingRows,
	countCodeqlReasoningRounds,
	formatStaticAnalysisDuration,
	getStaticAnalysisTaskDisplayDurationMs,
	isStaticAnalysisPollableStatus,
	resolveStaticAnalysisProjectNameFallback,
} from "./static-analysis/viewModel";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);

export default function CodeqlScanDetail() {
	const { taskId: rawTaskId } = useParams<{ taskId: string }>();
	const location = useLocation();
	const navigate = useNavigate();

	const searchParams = useMemo(
		() => new URLSearchParams(location.search),
		[location.search],
	);

	const taskId = rawTaskId ?? "";
	const codeqlTaskId = useMemo(() => {
		const explicit = searchParams.get("codeqlTaskId");
		return explicit || taskId;
	}, [searchParams, taskId]);

	const returnToParam = searchParams.get("returnTo") || "";
	const returnTo =
		returnToParam.startsWith("/") && !returnToParam.startsWith("//")
			? returnToParam
			: "";
	const currentRoute = `${location.pathname}${location.search}`;
	const { initialState, syncStateToUrl } = useDataTableUrlState(true);

	const hasEnabledEngine = Boolean(codeqlTaskId);

	const {
		codeqlTask,
		codeqlProgress,
		codeqlExplorationEvents,
		codeqlFindings,
		loadingInitial,
		loadingTask,
		loadingFindings,
		updatingKey,
		interruptTarget,
		setInterruptTarget,
		interrupting,
		resettingCodeqlPlan,
		refreshAll,
		handleInterrupt,
		handleResetCodeqlBuildPlan,
		handleToggleStatus,
		canInterruptCodeql,
		canResetCodeqlBuildPlan,
	} = useStaticAnalysisData({
		hasEnabledEngine,
		opengrepTaskId: "",
		codeqlTaskId,
	});

	const resolvedUrlState = useMemo(
		() =>
			resolveStaticAnalysisTableState(initialState),
		[initialState],
	);
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createStaticAnalysisInitialTableState(initialState),
	);

	const unifiedRows = useMemo(
		() =>
			buildUnifiedFindingRows({
				opengrepFindings: [],
				opengrepTaskId: "",
				codeqlFindings,
				codeqlTaskId,
			}),
		[codeqlFindings, codeqlTaskId],
	);

	const taskTerminal = codeqlTask ? TERMINAL_STATUSES.has(codeqlTask.status) : false;

	const sseUrl = codeqlTaskId
		? `${getApiBaseUrl()}/static-tasks/codeql/tasks/${codeqlTaskId}/stream`
		: "";

	const { events: sseEvents, isConnected, isComplete } = useSseStream(sseUrl, {
		enabled: Boolean(codeqlTaskId) && !taskTerminal,
	});

	const isStreaming = isConnected && !isComplete;

	const shouldTickClock = useMemo(
		() => isStaticAnalysisPollableStatus(codeqlTask?.status),
		[codeqlTask],
	);
	const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 1000 });

	const [resolvedProjectName, setResolvedProjectName] = useState<{
		projectId: string;
		name: string;
	} | null>(null);

	const staticProjectId = String(codeqlTask?.project_id || "").trim();
	const staticProjectName = String(codeqlTask?.project_name || "").trim();
	const fallbackProjectName = useMemo(
		() =>
			resolveStaticAnalysisProjectNameFallback({
				taskProjectName: staticProjectName,
				resolvedProjectName:
					resolvedProjectName?.projectId === staticProjectId
						? resolvedProjectName.name
						: null,
				projectId: staticProjectId,
			}),
		[resolvedProjectName, staticProjectId, staticProjectName],
	);

	const headerSummary = useMemo(
		() =>
			buildStaticAnalysisHeaderSummary({
				opengrepTask: null,
				codeqlTask,
				enabledEngines: ["codeql"],
				loadingInitial,
				nowMs,
				fallbackProjectName,
			}),
		[codeqlTask, fallbackProjectName, loadingInitial, nowMs],
	);

	const reasoningCount = useMemo(
		() => countCodeqlReasoningRounds(codeqlExplorationEvents),
		[codeqlExplorationEvents],
	);

	const llmModel = codeqlProgress?.llm_model || null;

	const durationMs = useMemo(
		() => getStaticAnalysisTaskDisplayDurationMs(codeqlTask, nowMs),
		[codeqlTask, nowMs],
	);

	const headerTags = useMemo(
		() => [
			headerSummary.projectName,
			`${Math.round(headerSummary.progressPercent)}%`,
			formatStaticAnalysisDuration(durationMs),
			`发现漏洞 ${headerSummary.totalFindings.toLocaleString()}`,
			...(llmModel ? [`模型 ${llmModel}`] : []),
			`推理 ${reasoningCount}次`,
		],
		[headerSummary, durationMs, llmModel, reasoningCount],
	);

	const failureReasons = useMemo(
		() =>
			buildStaticAnalysisTaskStatusSummary({
				opengrepTask: null,
				codeqlTask,
			}).failureReasons,
		[codeqlTask],
	);
	const codeqlFailureReason = useMemo(
		() => failureReasons.find((reason) => reason.engine === "codeql") ?? null,
		[failureReasons],
	);

	useEffect(() => {
		syncStateToUrl(tableState);
	}, [syncStateToUrl, tableState]);

	useEffect(() => {
		setTableState((current) =>
			areDataTableQueryStatesEqual(current, resolvedUrlState)
				? current
				: resolvedUrlState,
		);
	}, [resolvedUrlState]);

	useEffect(() => {
		if (!staticProjectId || staticProjectName) {
			setResolvedProjectName(null);
			return;
		}

		let cancelled = false;
		setResolvedProjectName((current) =>
			current?.projectId === staticProjectId ? current : null,
		);

		void databaseApi.getProjectById(staticProjectId).then((project) => {
			if (cancelled) return;
			const name = String(project?.name || "").trim();
			setResolvedProjectName(name ? { projectId: staticProjectId, name } : null);
		});

		return () => {
			cancelled = true;
		};
	}, [staticProjectId, staticProjectName]);

	const handleBack = () => {
		if (returnTo) {
			navigate(returnTo);
			return;
		}
		navigate(-1);
	};

	if (!hasEnabledEngine) {
		return (
			<div className="min-h-screen bg-background p-6">
				<div className="cyber-card p-8 text-center space-y-4">
					<p className="text-sm text-muted-foreground">
						CodeQL 任务参数无效，无法加载详情。
					</p>
					<Button variant="outline" className="cyber-btn-outline" onClick={handleBack}>
						<ArrowLeft className="w-4 h-4 mr-2" />
						返回
					</Button>
				</div>
			</div>
		);
	}

	return (
		<div className="space-y-5 p-6 bg-background min-h-screen">
			{/* Header */}
			<div className="flex items-center justify-between gap-3 flex-wrap">
				<div className="flex min-w-0 flex-wrap items-center gap-3">
					<h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
						CodeQL 审计详情
					</h1>
					<div className="flex min-w-0 flex-wrap items-center gap-2" aria-label="CodeQL审计概要标签">
						{headerTags.map((tag, index) => (
							<Badge
								key={`${index}:${tag}`}
								className="cyber-badge cyber-badge-info max-w-[18rem] truncate normal-case tracking-normal"
								title={tag}
							>
								{tag}
							</Badge>
						))}
					</div>
				</div>
				<div className="flex items-center gap-2">
					{canInterruptCodeql ? (
						<Button
							variant="outline"
							className="cyber-btn-outline h-8"
							onClick={() => setInterruptTarget("codeql")}
						>
							<Ban className="w-3.5 h-3.5 mr-1.5" />
							中止 CodeQL
						</Button>
					) : null}
					<Button
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={() => void refreshAll(false)}
						disabled={loadingInitial || loadingTask || loadingFindings}
					>
						<RefreshCw
							className={`w-3.5 h-3.5 mr-1.5 ${loadingInitial ? "animate-spin" : ""}`}
						/>
						刷新
					</Button>
					<Button variant="outline" className="cyber-btn-outline h-8" onClick={handleBack}>
						<ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
						返回
					</Button>
				</div>
			</div>

			{codeqlFailureReason ? (
				<div className="cyber-card flex items-start gap-3 border border-rose-500/30 bg-rose-500/10 p-4">
					<AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
					<div className="min-w-0 flex-1 space-y-1">
						<h2 className="text-sm font-semibold text-rose-200">
							CodeQL 任务失败
						</h2>
						<pre className="whitespace-pre-wrap break-words text-xs leading-5 text-rose-100/90">
							{codeqlFailureReason.message}
						</pre>
						{canResetCodeqlBuildPlan ? (
							<p className="pt-1 text-[11px] text-rose-200/70">
								可在右侧"CodeQL 编译探索"面板点击"重置并重新探索"重新触发构建方案探索。
							</p>
						) : null}
					</div>
				</div>
			) : null}

			{/* 60/40 split layout */}
			<div className="grid min-h-0 gap-5 lg:h-[calc(100vh-11rem)] lg:grid-cols-[minmax(0,6fr)_minmax(0,4fr)]">
				{/* Left panel: 60% - Findings table */}
				<div className="min-h-[28rem] min-w-0 overflow-y-auto rounded-md pr-1 lg:h-full">
					<StaticAnalysisFindingsTable
						currentRoute={currentRoute}
						loadingInitial={loadingInitial}
						rows={unifiedRows}
						state={tableState}
						showEngineColumn={false}
						onStateChange={setTableState}
						updatingKey={updatingKey}
						onToggleStatus={handleToggleStatus}
					/>
				</div>

				{/* Right panel: 40% - Exploration + LLM reasoning */}
				<div className="min-h-[28rem] min-w-0 overflow-y-auto pr-1 lg:h-full">
					<CodeqlExplorationPanel
						events={codeqlExplorationEvents}
						canReset={canResetCodeqlBuildPlan}
						resetting={resettingCodeqlPlan}
						onReset={handleResetCodeqlBuildPlan}
					/>

					{sseEvents.length > 0 && (
						<section className="mt-5 rounded border border-border bg-card/40 p-4">
							<h2 className="mb-2 text-sm font-semibold text-foreground">执行进度</h2>
							<StepProgressIndicator events={sseEvents} />
						</section>
					)}

					{(sseEvents.length > 0 || isStreaming) && (
						<section className="mt-5 rounded border border-purple-500/20 bg-card/40 p-4">
							<h2 className="mb-2 text-sm font-semibold text-foreground">LLM 推理过程</h2>
							<LlmReasoningPanel events={sseEvents} isStreaming={isStreaming} />
						</section>
					)}
				</div>
			</div>

			{/* Interrupt confirmation dialog */}
			<AlertDialog
				open={Boolean(interruptTarget)}
				onOpenChange={(open) => {
					if (!open) setInterruptTarget(null);
				}}
			>
				<AlertDialogContent className="cyber-dialog border-border">
					<AlertDialogHeader>
						<AlertDialogTitle>确认中止任务？</AlertDialogTitle>
						<AlertDialogDescription>
							即将中止 CodeQL 扫描任务。中止后任务状态将更新为已中断。
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel disabled={interrupting}>取消</AlertDialogCancel>
						<AlertDialogAction
							disabled={interrupting}
							onClick={(event) => {
								event.preventDefault();
								void handleInterrupt();
							}}
							className="bg-rose-600 hover:bg-rose-500"
						>
							{interrupting ? (
								<span className="inline-flex items-center gap-1.5">
									<Loader2 className="w-3.5 h-3.5 animate-spin" />
									处理中...
								</span>
							) : (
								"确认中止"
							)}
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
