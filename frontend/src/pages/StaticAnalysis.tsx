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
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import StaticAnalysisFindingsTable from "./static-analysis/StaticAnalysisFindingsTable";
import StaticAnalysisSummaryCards from "./static-analysis/StaticAnalysisSummaryCards";
import { useStaticAnalysisData } from "./static-analysis/useStaticAnalysisData";
import {
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
  decodeStaticAnalysisPathParam,
  type ConfidenceFilter,
  type Engine,
  type EngineFilter,
  type SeverityFilter,
  type StatusFilter,
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
  const toolParam = searchParams.get("tool");
  const returnToParam = searchParams.get("returnTo") || "";
  const returnTo =
    returnToParam.startsWith("/") && !returnToParam.startsWith("//")
      ? returnToParam
      : "";
  const currentRoute = `${location.pathname}${location.search}`;

  const opengrepTaskId = useMemo(() => {
    const explicit = searchParams.get("opengrepTaskId");
    const hasOtherExplicitEngineTaskId = Boolean(
      searchParams.get("gitleaksTaskId") || searchParams.get("banditTaskId"),
    );
    if (explicit) return explicit;
    if (hasOtherExplicitEngineTaskId) return "";
    if (toolParam === "gitleaks" || toolParam === "bandit") return "";
    return taskId;
  }, [searchParams, taskId, toolParam]);

  const gitleaksTaskId = useMemo(() => {
    const explicit = searchParams.get("gitleaksTaskId");
    if (explicit) return explicit;
    if (toolParam === "gitleaks") return taskId;
    return "";
  }, [searchParams, taskId, toolParam]);

  const banditTaskId = useMemo(() => {
    const explicit = searchParams.get("banditTaskId");
    if (explicit) return explicit;
    if (toolParam === "bandit") return taskId;
    return "";
  }, [searchParams, taskId, toolParam]);

  const hasEnabledEngine = Boolean(opengrepTaskId || gitleaksTaskId || banditTaskId);
  const [engineFilter, setEngineFilter] = useState<EngineFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [confidenceFilter, setConfidenceFilter] =
    useState<ConfidenceFilter>("all");
  const [page, setPage] = useState(1);

  const {
    opengrepTask,
    gitleaksTask,
    banditTask,
    opengrepFindings,
    gitleaksFindings,
    banditFindings,
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
    canInterruptGitleaks,
    canInterruptBandit,
  } = useStaticAnalysisData({
    hasEnabledEngine,
    opengrepTaskId,
    gitleaksTaskId,
    banditTaskId,
  });

  const unifiedRows = useMemo(
    () =>
      buildUnifiedFindingRows({
        opengrepFindings,
        gitleaksFindings,
        banditFindings,
        opengrepTaskId,
        gitleaksTaskId,
        banditTaskId,
      }),
    [
      banditFindings,
      banditTaskId,
      gitleaksFindings,
      gitleaksTaskId,
      opengrepFindings,
      opengrepTaskId,
    ],
  );

  const listState = useMemo(
    () =>
      buildStaticAnalysisListState({
        rows: unifiedRows,
        engineFilter,
        statusFilter,
        severityFilter,
        confidenceFilter,
        page,
      }),
    [confidenceFilter, engineFilter, page, severityFilter, statusFilter, unifiedRows],
  );

  const enabledEngines = useMemo(() => {
    const engines: Engine[] = [];
    if (opengrepTaskId) engines.push("opengrep");
    if (gitleaksTaskId) engines.push("gitleaks");
    if (banditTaskId) engines.push("bandit");
    return engines;
  }, [banditTaskId, gitleaksTaskId, opengrepTaskId]);
  const pageResetKey = `${engineFilter}:${statusFilter}:${severityFilter}:${confidenceFilter}`;

  useEffect(() => {
    if (!pageResetKey) return;
    setPage(1);
  }, [pageResetKey]);

  useEffect(() => {
    if (page !== listState.clampedPage) {
      setPage(listState.clampedPage);
    }
  }, [listState.clampedPage, page]);

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
        <div>
          <h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
            静态分析详情
          </h1>
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
          {canInterruptGitleaks ? (
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => setInterruptTarget("gitleaks")}
            >
              <Ban className="w-3.5 h-3.5 mr-1.5" />
              中止 Gitleaks
            </Button>
          ) : null}
          {canInterruptBandit ? (
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => setInterruptTarget("bandit")}
            >
              <Ban className="w-3.5 h-3.5 mr-1.5" />
              中止 Bandit
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

      <StaticAnalysisSummaryCards
        opengrepTask={opengrepTask}
        gitleaksTask={gitleaksTask}
        banditTask={banditTask}
        enabledEngines={enabledEngines}
      />

      <div className="cyber-card p-4 space-y-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <div className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">
              引擎筛选
            </div>
            <Select
              value={engineFilter}
              onValueChange={(value) => setEngineFilter(value as EngineFilter)}
            >
              <SelectTrigger className="cyber-input">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="opengrep">Opengrep</SelectItem>
                <SelectItem value="gitleaks">Gitleaks</SelectItem>
                <SelectItem value="bandit">Bandit</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">
              状态筛选
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => setStatusFilter(value as StatusFilter)}
            >
              <SelectTrigger className="cyber-input">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="open">未处理</SelectItem>
                <SelectItem value="verified">已验证</SelectItem>
                <SelectItem value="false_positive">误报</SelectItem>
                <SelectItem value="fixed">已修复</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">
              漏洞危害
            </div>
            <Select
              value={severityFilter}
              onValueChange={(value) => setSeverityFilter(value as SeverityFilter)}
            >
              <SelectTrigger className="cyber-input">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="CRITICAL">严重</SelectItem>
                <SelectItem value="HIGH">高危</SelectItem>
                <SelectItem value="MEDIUM">中危</SelectItem>
                <SelectItem value="LOW">低危</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="mb-1 block text-xs font-semibold uppercase text-muted-foreground">
              置信度筛选
            </div>
            <Select
              value={confidenceFilter}
              onValueChange={(value) => setConfidenceFilter(value as ConfidenceFilter)}
            >
              <SelectTrigger className="cyber-input">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="HIGH">高</SelectItem>
                <SelectItem value="MEDIUM">中</SelectItem>
                <SelectItem value="LOW">低</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <StaticAnalysisFindingsTable
          currentRoute={currentRoute}
          loadingInitial={loadingInitial}
          pagedRows={listState.pagedRows}
          pageStart={listState.pageStart}
          totalRows={listState.totalRows}
          totalPages={listState.totalPages}
          clampedPage={listState.clampedPage}
          updatingKey={updatingKey}
          onToggleStatus={handleToggleStatus}
          onPageChange={setPage}
        />
      </div>

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
              即将中止
              {interruptTarget === "opengrep"
                ? " Opengrep "
                : interruptTarget === "gitleaks"
                  ? " Gitleaks "
                  : " Bandit "}
              扫描任务。中止后任务状态将更新为已中断。
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
