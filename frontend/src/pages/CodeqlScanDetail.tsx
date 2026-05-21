import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, Ban, CheckCircle2, Circle, Loader2, RefreshCw, Terminal } from "lucide-react";
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
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	areDataTableQueryStatesEqual,
	type DataTableQueryState,
	useDataTableUrlState,
} from "@/components/data-table";
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
	formatStaticAnalysisDuration,
	getStaticAnalysisTaskDisplayDurationMs,
	isStaticAnalysisPollableStatus,
	type CodeqlExplorationProgressEventLike,
} from "./static-analysis/viewModel";

type CodeqlScanStage = "pending" | "exploration" | "building" | "scanning" | "completed" | "failed";

function resolveCodeqlScanStage(
	status: string | undefined,
	events: CodeqlExplorationProgressEventLike[],
): CodeqlScanStage {
	const s = String(status || "").trim().toLowerCase();
	if (s === "completed") return "completed";
	if (s === "failed" || s === "interrupted" || s === "cancelled" || s === "aborted") return "failed";
	if (s === "pending") return "pending";
	const hasBuildPlanAccepted = events.some(
		(e) => e.stage === "build_plan_accepted" || e.event_type === "build_plan_accepted",
	);
	if (hasBuildPlanAccepted) return "scanning";
	const hasExplorationEvent = events.some((e) => {
		const kind = String(e.stage || e.event_type || "");
		return kind.includes("compile_sandbox") || kind.includes("llm_round") || kind.includes("sandbox_command");
	});
	if (hasExplorationEvent) return "exploration";
	if (s === "running") return "exploration";
	return "pending";
}

function CodeqlScanStages({ stage }: { stage: CodeqlScanStage }) {
	const steps = [
		{ key: "exploration", label: "编译探索" },
		{ key: "building", label: "CodeQL 构建" },
		{ key: "scanning", label: "规则扫描" },
	];
	const ORDER: Record<string, number> = { pending: -1, exploration: 0, building: 1, scanning: 2, completed: 3, failed: 3 };
	const currentIndex = ORDER[stage] ?? -1;

	return (
		<div className="flex items-center gap-0">
			{steps.map((step, i) => {
				const stepIndex = i;
				const isDone = currentIndex > stepIndex || stage === "completed";
				const isActive = currentIndex === stepIndex && stage !== "completed" && stage !== "failed" && stage !== "pending";
				const isFailed = stage === "failed" && currentIndex === stepIndex;
				return (
					<div key={step.key} className="flex items-center">
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
								{step.label}
							</span>
						</div>
						{i < steps.length - 1 && (
							<div className={`mx-2 mb-4 h-px w-8 ${isDone ? "bg-emerald-500/40" : "bg-border"}`} />
						)}
					</div>
				);
			})}
		</div>
	);
}

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
		() => resolveStaticAnalysisTableState(initialState),
		[initialState],
	);
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createStaticAnalysisInitialTableState(initialState),
	);
	const [showExploration, setShowExploration] = useState(false);

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

	const shouldTickClock = useMemo(
		() => isStaticAnalysisPollableStatus(codeqlTask?.status),
		[codeqlTask],
	);
	const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 1000 });

	const staticProjectName = String(codeqlTask?.project_name || "").trim();
	const fallbackProjectName = useMemo(
		() => String(staticProjectName || "").trim() || "-",
		[staticProjectName],
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
		],
		[headerSummary, durationMs],
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

	const scanStage = useMemo(
		() => resolveCodeqlScanStage(codeqlTask?.status, codeqlExplorationEvents),
		[codeqlTask?.status, codeqlExplorationEvents],
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
					<Button
						variant="outline"
						className="cyber-btn-outline"
						onClick={handleBack}
					>
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
					<div
						className="flex min-w-0 flex-wrap items-center gap-2"
						aria-label="CodeQL审计概要标签"
					>
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
						size="sm"
						variant="outline"
						className="cyber-btn-ghost h-8 px-3"
						onClick={() => setShowExploration(true)}
					>
						<Terminal className="w-3.5 h-3.5 mr-1.5" />
						编译探索
					</Button>
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
					<Button
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={handleBack}
					>
						<ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
						返回
					</Button>
				</div>
			</div>

			{/* Progress stage indicator — always visible */}
			<div className="flex items-center gap-4 rounded border border-border bg-card/40 px-4 py-3">
				<span className="text-xs text-muted-foreground shrink-0">扫描阶段</span>
				<CodeqlScanStages stage={scanStage} />
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
								可点击"编译探索"按钮打开面板，点击"重置并重新探索"重新触发构建方案探索。
							</p>
						) : null}
					</div>
				</div>
			) : null}

			<div className="min-h-[28rem] overflow-x-auto">
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

			{/* Exploration Dialog */}
			<Dialog open={showExploration} onOpenChange={setShowExploration}>
				<DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
					<DialogHeader>
						<DialogTitle>CodeQL 编译探索</DialogTitle>
					</DialogHeader>
					<div className="flex-1 overflow-y-auto">
						<CodeqlExplorationPanel
							events={codeqlExplorationEvents}
							canReset={canResetCodeqlBuildPlan}
							resetting={resettingCodeqlPlan}
							onReset={handleResetCodeqlBuildPlan}
						/>
					</div>
				</DialogContent>
			</Dialog>

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
