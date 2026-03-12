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
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import StaticAnalysisFindingsTable from "./static-analysis/StaticAnalysisFindingsTable";
import { useStaticAnalysisData } from "./static-analysis/useStaticAnalysisData";
import {
  buildStaticAnalysisProgressSummary,
  buildStaticAnalysisListState,
  buildUnifiedFindingRows,
  decodeStaticAnalysisPathParam,
  formatStaticAnalysisDuration,
  type ConfidenceFilter,
  type Engine,
  type EngineFilter,
  type StatusFilter,
  toStaticAnalysisSafeMetric,
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
    if (explicit) return explicit;
    if (toolParam === "gitleaks") return "";
    return taskId;
  }, [searchParams, taskId, toolParam]);

  const gitleaksTaskId = useMemo(() => {
    const explicit = searchParams.get("gitleaksTaskId");
    if (explicit) return explicit;
    if (toolParam === "gitleaks") return taskId;
    return "";
  }, [searchParams, taskId, toolParam]);

  const hasEnabledEngine = Boolean(opengrepTaskId || gitleaksTaskId);
  const [engineFilter, setEngineFilter] = useState<EngineFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [confidenceFilter, setConfidenceFilter] =
    useState<ConfidenceFilter>("all");
  const [page, setPage] = useState(1);

  const {
    opengrepTask,
    gitleaksTask,
    opengrepFindings,
    gitleaksFindings,
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
  } = useStaticAnalysisData({
    hasEnabledEngine,
    opengrepTaskId,
    gitleaksTaskId,
  });

  const unifiedRows = useMemo(
    () =>
      buildUnifiedFindingRows({
        opengrepFindings,
        gitleaksFindings,
        opengrepTaskId,
        gitleaksTaskId,
      }),
    [gitleaksFindings, gitleaksTaskId, opengrepFindings, opengrepTaskId],
  );

  const listState = useMemo(
    () =>
      buildStaticAnalysisListState({
        rows: unifiedRows,
        engineFilter,
        statusFilter,
        confidenceFilter,
        page,
      }),
    [confidenceFilter, engineFilter, page, statusFilter, unifiedRows],
  );

  const enabledEngines = useMemo(() => {
    const engines: Engine[] = [];
    if (opengrepTaskId) engines.push("opengrep");
    if (gitleaksTaskId) engines.push("gitleaks");
    return engines;
  }, [gitleaksTaskId, opengrepTaskId]);

  const progressSummary = useMemo(
    () =>
      buildStaticAnalysisProgressSummary({
        opengrepTask,
        gitleaksTask,
      }),
    [gitleaksTask, opengrepTask],
  );
  const progressPercent = progressSummary.progressPercent;

  const totalScanDurationMs =
    toStaticAnalysisSafeMetric(opengrepTask?.scan_duration_ms) +
    toStaticAnalysisSafeMetric(gitleaksTask?.scan_duration_ms);
  const totalFindings =
    toStaticAnalysisSafeMetric(opengrepTask?.total_findings) +
    toStaticAnalysisSafeMetric(gitleaksTask?.total_findings);
  const totalFilesScanned =
    toStaticAnalysisSafeMetric(opengrepTask?.files_scanned) +
    toStaticAnalysisSafeMetric(gitleaksTask?.files_scanned);

  useEffect(() => {
    setPage(1);
  }, [engineFilter, statusFilter, confidenceFilter]);

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

      <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
        <div className="cyber-card p-4 space-y-2">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            进度比例
          </p>
          <p className="text-xl font-bold text-foreground">{progressPercent}%</p>
          <Progress
            value={progressPercent}
            className="h-1.5 bg-muted [&>div]:bg-emerald-500"
          />
        </div>
        <div className="cyber-card p-4 space-y-1">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            扫描时间
          </p>
          <p className="text-xl font-bold text-foreground">
            {formatStaticAnalysisDuration(totalScanDurationMs)}
          </p>
          <p className="text-xs text-muted-foreground">
            合计 {totalScanDurationMs.toLocaleString()} ms
          </p>
        </div>
        <div className="cyber-card p-4 space-y-1">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            扫描漏洞数量
          </p>
          <p className="text-xl font-bold text-foreground">
            {totalFindings.toLocaleString()}
          </p>
          <p className="text-xs text-muted-foreground">多引擎总计</p>
        </div>
        <div className="cyber-card p-4 space-y-1">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            使用引擎数量
          </p>
          <p className="text-xl font-bold text-foreground">
            {enabledEngines.length.toLocaleString()}
          </p>
          <p className="text-xs text-muted-foreground">
            {enabledEngines
              .map((engine) => (engine === "opengrep" ? "Opengrep" : "Gitleaks"))
              .join(" / ") || "-"}
          </p>
        </div>
        <div className="cyber-card p-4 space-y-1">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            涉及文件
          </p>
          <p className="text-xl font-bold text-foreground">
            {totalFilesScanned.toLocaleString()}
          </p>
          <p className="text-xs text-muted-foreground">多引擎总计</p>
        </div>
      </div>

      <div className="cyber-card p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
              引擎筛选
            </label>
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
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
              状态筛选
            </label>
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
            <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
              置信度筛选（仅 Opengrep）
            </label>
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

        <div className="text-xs text-muted-foreground flex items-center justify-between gap-2 flex-wrap">
          <span>
            符合筛选 {listState.totalRows.toLocaleString()} 条，当前第{" "}
            {listState.clampedPage} / {listState.totalPages.toLocaleString()} 页
          </span>
          <span>排序规则：危害降序；同危害按置信度降序；其后按路径+行号升序</span>
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
              {interruptTarget === "opengrep" ? " Opengrep " : " Gitleaks "}
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
