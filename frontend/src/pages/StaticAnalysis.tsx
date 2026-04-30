import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Ban,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
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
  DialogFooter,
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
import { api as databaseApi } from "@/shared/api/database";
import { apiClient } from "@/shared/api/serverClient";
import StaticAnalysisFindingsTable from "./static-analysis/StaticAnalysisFindingsTable";
import {
  createStaticAnalysisInitialTableState,
  resolveStaticAnalysisTableState,
} from "./static-analysis/tableState";
import { useStaticAnalysisData } from "./static-analysis/useStaticAnalysisData";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import {
  buildStaticAnalysisHeaderSummary,
  buildUnifiedFindingRows,
  decodeStaticAnalysisPathParam,
  isStaticAnalysisPollableStatus,
  resolveStaticAnalysisProjectNameFallback,
  type Engine,
} from "./static-analysis/viewModel";

export default function StaticAnalysis() {
  const { taskId: rawTaskId } = useParams<{ taskId: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const searchParams = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const taskId = useMemo(
    () => decodeStaticAnalysisPathParam(rawTaskId),
    [rawTaskId],
  );
  const returnToParam = searchParams.get("returnTo") || "";
  const returnTo =
    returnToParam.startsWith("/") && !returnToParam.startsWith("//")
      ? returnToParam
      : "";
  const currentRoute = `${location.pathname}${location.search}`;
  const { initialState, syncStateToUrl } = useDataTableUrlState(true);

  const opengrepTaskId = useMemo(() => {
    const explicit = searchParams.get("opengrepTaskId");
    if (explicit) return explicit;
    return taskId;
  }, [searchParams, taskId]);

  const usesPathTaskIdFallback = useMemo(() => {
    return !searchParams.get("opengrepTaskId") && Boolean(taskId);
  }, [searchParams, taskId]);

  const hasEnabledEngine = Boolean(opengrepTaskId);
  const [tableState, setTableState] = useState<DataTableQueryState>(() =>
    createStaticAnalysisInitialTableState(initialState),
  );
  const [resolvedProjectName, setResolvedProjectName] = useState<{
    projectId: string;
    name: string;
  } | null>(null);
  const resolvedUrlState = useMemo<DataTableQueryState>(
    () => resolveStaticAnalysisTableState(initialState),
    [initialState],
  );

  const {
    opengrepTask,
    opengrepFindings,
    loadingInitial,
    loadingTask,
    loadingFindings,
    updatingKey,
    interruptTarget,
    setInterruptTarget,
    interrupting,
    refreshAll,
    handleInterrupt,
    handleToggleStatus,
    canInterruptOpengrep,
  } = useStaticAnalysisData({
    hasEnabledEngine,
    opengrepTaskId,
  });

  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<{ analysis: string; model: string } | null>(null);
  const [showAiDialog, setShowAiDialog] = useState(false);

  const handleAiAnalysis = async () => {
    if (!opengrepTaskId) return;
    setAiAnalyzing(true);
    try {
      const response = await apiClient.post(`/static-tasks/tasks/${opengrepTaskId}/ai-analysis`);
      setAiResult(response.data);
      setShowAiDialog(true);
    } catch (error: any) {
      const message =
        error?.response?.data?.error || error?.message || "AI 研判请求失败";
      toast.error(message);
    } finally {
      setAiAnalyzing(false);
    }
  };

  const unifiedRows = useMemo(
    () =>
      buildUnifiedFindingRows({
        opengrepFindings,
        opengrepTaskId,
      }),
    [
      opengrepFindings,
      opengrepTaskId,
    ],
  );

  const enabledEngines = useMemo(() => {
    const engines: Engine[] = [];
    if (opengrepTaskId) engines.push("opengrep");
    return engines;
  }, [opengrepTaskId]);

  const shouldTickClock = useMemo(
    () => [opengrepTask].some((task) => isStaticAnalysisPollableStatus(task?.status)),
    [opengrepTask],
  );
  const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 1000 });
  const opengrepProjectId = String(opengrepTask?.project_id || "").trim();
  const opengrepProjectName = String(opengrepTask?.project_name || "").trim();
  const fallbackProjectName = useMemo(
    () =>
      resolveStaticAnalysisProjectNameFallback({
        taskProjectName: opengrepProjectName,
        resolvedProjectName:
          resolvedProjectName?.projectId === opengrepProjectId
            ? resolvedProjectName.name
            : null,
        projectId: opengrepProjectId,
      }),
    [opengrepProjectId, opengrepProjectName, resolvedProjectName],
  );
  const headerSummary = useMemo(
    () =>
      buildStaticAnalysisHeaderSummary({
        opengrepTask,
        gitleaksTask: null,
        banditTask: null,
        phpstanTask: null,
        pmdTask: null,
        enabledEngines,
        loadingInitial,
        nowMs,
        fallbackProjectName,
      }),
    [enabledEngines, fallbackProjectName, loadingInitial, nowMs, opengrepTask],
  );
  const headerTags = useMemo(
    () => [
      headerSummary.projectName,
      `${Math.round(headerSummary.progressPercent)}%`,
      headerSummary.durationLabel,
      `发现漏洞 ${headerSummary.totalFindings.toLocaleString()}`,
    ],
    [headerSummary],
  );

  useEffect(() => {
    syncStateToUrl(tableState);
  }, [syncStateToUrl, tableState]);

  useEffect(() => {
    setTableState((current) =>
      areDataTableQueryStatesEqual(current, resolvedUrlState) ? current : resolvedUrlState,
    );
  }, [resolvedUrlState]);

  useEffect(() => {
    if (!opengrepProjectId || opengrepProjectName) {
      setResolvedProjectName(null);
      return;
    }

    let cancelled = false;
    setResolvedProjectName((current) =>
      current?.projectId === opengrepProjectId ? current : null,
    );

    void databaseApi.getProjectById(opengrepProjectId).then((project) => {
      if (cancelled) return;
      const name = String(project?.name || "").trim();
      setResolvedProjectName(name ? { projectId: opengrepProjectId, name } : null);
    });

    return () => {
      cancelled = true;
    };
  }, [opengrepProjectId, opengrepProjectName]);

  useEffect(() => {
    if (!usesPathTaskIdFallback) return;
    console.info(
      "[StaticAnalysis] Using path taskId fallback. Prefer explicit engine task ids in query params for stable detail resolution.",
      { pathTaskId: taskId, toolParam: "opengrep" },
    );
  }, [taskId, usesPathTaskIdFallback]);

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
          <AlertCircle className="w-12 h-12 text-rose-400 mx-auto" />
          <p className="text-sm text-muted-foreground">
            静态分析任务参数无效，无法加载详情。
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
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
            静态审计详情
          </h1>
          <div className="flex min-w-0 flex-wrap items-center gap-2" aria-label="静态审计概要标签">
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
          {canInterruptOpengrep ? (
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => setInterruptTarget("opengrep")}
            >
              <Ban className="w-3.5 h-3.5 mr-1.5" />
              中止 Opengrep
            </Button>
          ) : null}
          <Button
            variant="outline"
            className="cyber-btn-outline h-8"
            onClick={() => void handleAiAnalysis()}
            disabled={aiAnalyzing || loadingInitial || isStaticAnalysisPollableStatus(opengrepTask?.status)}
          >
            {aiAnalyzing ? (
              <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            )}
            AI 研判
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
          <Button variant="outline" className="cyber-btn-outline h-8" onClick={handleBack}>
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            返回
          </Button>
        </div>
      </div>

      <StaticAnalysisFindingsTable
          currentRoute={currentRoute}
          loadingInitial={loadingInitial}
          rows={unifiedRows}
          state={tableState}
          onStateChange={setTableState}
          updatingKey={updatingKey}
          onToggleStatus={handleToggleStatus}
        />

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
              即将中止 Opengrep 扫描任务。中止后任务状态将更新为已中断。
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

      <Dialog open={showAiDialog} onOpenChange={setShowAiDialog}>
        <DialogContent className="cyber-dialog border-border max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="font-mono">AI 规则研判分析</DialogTitle>
            {aiResult?.model && (
              <Badge className="cyber-badge cyber-badge-info w-fit mt-1">
                模型: {aiResult.model}
              </Badge>
            )}
          </DialogHeader>
          <div className="flex-1 overflow-y-auto">
            <pre className="whitespace-pre-wrap text-sm font-mono text-foreground leading-relaxed">
              {aiResult?.analysis || ""}
            </pre>
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => {
                if (aiResult?.analysis) {
                  navigator.clipboard.writeText(aiResult.analysis);
                  toast.success("已复制到剪贴板");
                }
              }}
            >
              <Copy className="w-3.5 h-3.5 mr-1.5" />
              复制
            </Button>
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => setShowAiDialog(false)}
            >
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
