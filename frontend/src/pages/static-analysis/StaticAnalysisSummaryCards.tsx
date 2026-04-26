import { memo, useMemo } from "react";
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import { getTaskDisplayStatusSummary } from "@/features/tasks/services/taskDisplay";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { OpengrepScanTask } from "@/shared/api/opengrep";
import type { BanditScanTask } from "@/shared/api/bandit";
import type { PhpstanScanTask } from "@/shared/api/phpstan";
import type { PmdScanTask } from "@/shared/api/pmd";

import type { Engine } from "./viewModel";
import {
  buildStaticAnalysisTaskStatusSummary,
  formatStaticAnalysisDuration,
  getStaticAnalysisTotalDisplayDurationMs,
  getStaticAnalysisStatusBadgeClassName,
  isStaticAnalysisPollableStatus,
  toStaticAnalysisSafeMetric,
} from "./viewModel";

interface StaticAnalysisSummaryCardsProps {
  opengrepTask: OpengrepScanTask | null;
  gitleaksTask: GitleaksScanTask | null;
  banditTask: BanditScanTask | null;
  phpstanTask: PhpstanScanTask | null;
  pmdTask: PmdScanTask | null;
  enabledEngines: Engine[];
  loadingInitial?: boolean;
}

const SUMMARY_CARD_CLASSNAME = "cyber-card p-4";
const SUMMARY_CARD_CONTENT_CLASSNAME = "flex min-w-0 items-center justify-between gap-3";
const SUMMARY_LABEL_BADGE_CLASSNAME = "cyber-badge cyber-badge-muted shrink-0 text-[12px]";
const SUMMARY_VALUE_BADGE_CLASSNAME =
  "cyber-badge cyber-badge-info min-w-0 max-w-full truncate normal-case tracking-normal";

export const StaticAnalysisSummaryCards = memo(function StaticAnalysisSummaryCards({
  opengrepTask,
  gitleaksTask,
  banditTask,
  phpstanTask,
  pmdTask,
  enabledEngines,
  loadingInitial = false,
}: StaticAnalysisSummaryCardsProps) {
  const hasAnyLoadedTask = Boolean(opengrepTask || gitleaksTask || banditTask || phpstanTask || pmdTask);
  const loadedEnabledEngineCount = useMemo(
    () =>
      enabledEngines.filter((engine) => {
        if (engine === "opengrep") return Boolean(opengrepTask);
        if (engine === "gitleaks") return Boolean(gitleaksTask);
        if (engine === "bandit") return Boolean(banditTask);
        if (engine === "phpstan") return Boolean(phpstanTask);
        if (engine === "pmd") return Boolean(pmdTask);
        return false;
      }).length,
    [
      banditTask,
      enabledEngines,
      gitleaksTask,
      opengrepTask,
      phpstanTask,
      pmdTask,
    ],
  );
  const isBootstrapping =
    loadingInitial &&
    enabledEngines.length > 0 &&
    (!hasAnyLoadedTask || loadedEnabledEngineCount < enabledEngines.length);
  const shouldTickClock = useMemo(
    () =>
        [opengrepTask, gitleaksTask, banditTask, phpstanTask, pmdTask].some((task) =>
          isStaticAnalysisPollableStatus(task?.status),
        ),
    [banditTask, gitleaksTask, opengrepTask, phpstanTask, pmdTask],
  );
  const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 1000 });

  const statusSummary = useMemo(
    () => {
      if (isBootstrapping) {
        const pendingSummary = getTaskDisplayStatusSummary("pending");
        return {
          aggregateStatus: "pending" as const,
          aggregateLabel: pendingSummary.statusLabel,
          progressHint: pendingSummary.progressHint,
          engineStatuses: [],
          failureReasons: [],
        };
      }

      return buildStaticAnalysisTaskStatusSummary({
        opengrepTask,
        gitleaksTask,
        banditTask,
        phpstanTask,
        pmdTask,
      });
    },
    [banditTask, gitleaksTask, isBootstrapping, opengrepTask, phpstanTask, pmdTask],
  );

  const totalScanDurationMs = useMemo(
    () =>
      getStaticAnalysisTotalDisplayDurationMs({
        opengrepTask,
        gitleaksTask,
        banditTask,
        phpstanTask,
        pmdTask,
        nowMs,
      }),
    [banditTask, gitleaksTask, nowMs, opengrepTask, phpstanTask, pmdTask],
  );

  const totalFindings = useMemo(
    () =>
      toStaticAnalysisSafeMetric(opengrepTask?.total_findings) +
      toStaticAnalysisSafeMetric(gitleaksTask?.total_findings) +
      toStaticAnalysisSafeMetric(banditTask?.total_findings) +
      toStaticAnalysisSafeMetric(phpstanTask?.total_findings) +
      toStaticAnalysisSafeMetric(pmdTask?.total_findings) +
      0,
    [banditTask?.total_findings, gitleaksTask?.total_findings, opengrepTask?.total_findings, phpstanTask?.total_findings, pmdTask?.total_findings],
  );

  const timeoutOnlyFailure = useMemo(
    () =>
      statusSummary.aggregateStatus === "failed" &&
      statusSummary.failureReasons.length > 0 &&
      statusSummary.failureReasons.every((reason) => reason.isTimeout),
    [statusSummary.aggregateStatus, statusSummary.failureReasons],
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className={SUMMARY_CARD_CLASSNAME}>
          <div className={SUMMARY_CARD_CONTENT_CLASSNAME}>
            <Badge className={SUMMARY_LABEL_BADGE_CLASSNAME}>
              进度比例
            </Badge>
            <Badge
              className={`cyber-badge ${getStaticAnalysisStatusBadgeClassName(statusSummary.aggregateStatus)} min-w-0 max-w-full truncate normal-case tracking-normal`}
            >
              {statusSummary.aggregateLabel}
            </Badge>
          </div>
        </div>
        <div className={SUMMARY_CARD_CLASSNAME}>
          <div className={SUMMARY_CARD_CONTENT_CLASSNAME}>
            <Badge className={SUMMARY_LABEL_BADGE_CLASSNAME}>
              时间
            </Badge>
            <Badge className={SUMMARY_VALUE_BADGE_CLASSNAME}>
              {formatStaticAnalysisDuration(totalScanDurationMs)}
            </Badge>
          </div>
        </div>
        <div className={SUMMARY_CARD_CLASSNAME}>
          <div className={SUMMARY_CARD_CONTENT_CLASSNAME}>
            <Badge className={SUMMARY_LABEL_BADGE_CLASSNAME}>
              发现漏洞
            </Badge>
            <Badge className={`${SUMMARY_VALUE_BADGE_CLASSNAME} tabular-nums`}>
              {totalFindings.toLocaleString()}
            </Badge>
          </div>
        </div>
      </div>

      {statusSummary.failureReasons.length > 0 ? (
        <div
          className={`cyber-card border p-4 ${statusSummary.aggregateStatus === "failed"
            ? "border-rose-500/30 bg-rose-500/5"
            : "border-amber-500/30 bg-amber-500/5"
            }`}
        >
          <div className="flex items-start gap-3">
            <AlertTriangle
              className={`mt-0.5 h-4 w-4 shrink-0 ${statusSummary.aggregateStatus === "failed"
                ? "text-rose-300"
                : "text-amber-300"
                }`}
            />
            <div className="space-y-2">
              <p className="text-sm font-semibold text-foreground">
                {statusSummary.aggregateStatus === "failed"
                  ? timeoutOnlyFailure
                    ? "扫描已结束，但存在超时引擎"
                    : "扫描已结束，但存在异常引擎"
                  : "扫描已结束，任务被中断"}
              </p>
              <div className="space-y-2">
                {statusSummary.failureReasons.map((reason) => (
                  <div key={`${reason.engine}-${reason.message}`} className="space-y-1">
                    <Badge
                      variant="outline"
                      className={`${statusSummary.aggregateStatus === "failed"
                        ? "border-rose-400/40 text-rose-200"
                        : "border-amber-400/40 text-amber-200"
                        }`}
                    >
                      {reason.engineLabel}
                    </Badge>
                    <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                      {reason.message}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
});

export default StaticAnalysisSummaryCards;
