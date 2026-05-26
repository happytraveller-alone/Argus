import { memo, useMemo } from "react";
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import { getTaskDisplayStatusSummary } from "@/features/tasks/services/taskDisplay";
import type { OpengrepScanTask } from "@/shared/api/opengrep";

import type { Engine } from "./viewModel";
import {
  buildStaticAnalysisTaskStatusSummary,
  formatStaticAnalysisDuration,
  getStaticAnalysisTotalDisplayDurationMs,
  getStaticAnalysisStatusBadgeClassName,
  isStaticAnalysisPollableStatus,
  resolveCodegraphDegradedInfo,
  toStaticAnalysisSafeMetric,
} from "./viewModel";

interface StaticAnalysisSummaryCardsProps {
  opengrepTask: OpengrepScanTask | null;
  codeqlTask: OpengrepScanTask | null;
  joernTask?: OpengrepScanTask | null;
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
  codeqlTask,
  joernTask = null,
  enabledEngines,
  loadingInitial = false,
}: StaticAnalysisSummaryCardsProps) {
  const hasAnyLoadedTask = Boolean(opengrepTask || codeqlTask || joernTask);
  const loadedEnabledEngineCount = useMemo(
    () =>
      enabledEngines.filter((engine) => {
        if (engine === "opengrep") return Boolean(opengrepTask);
        if (engine === "codeql") return Boolean(codeqlTask);
        return Boolean(joernTask);
      }).length,
    [codeqlTask, enabledEngines, joernTask, opengrepTask],
  );
  const isBootstrapping =
    loadingInitial &&
    enabledEngines.length > 0 &&
    (!hasAnyLoadedTask || loadedEnabledEngineCount < enabledEngines.length);
  const shouldTickClock = useMemo(
    () =>
        [opengrepTask, codeqlTask, joernTask].some((task) =>
          isStaticAnalysisPollableStatus(task?.status),
        ),
    [codeqlTask, joernTask, opengrepTask],
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
        codeqlTask,
        joernTask,
      });
    },
    [codeqlTask, isBootstrapping, joernTask, opengrepTask],
  );

  const totalScanDurationMs = useMemo(
    () =>
      getStaticAnalysisTotalDisplayDurationMs({
        opengrepTask,
        codeqlTask,
        joernTask,
        nowMs,
      }),
    [codeqlTask, joernTask, nowMs, opengrepTask],
  );

  const totalFindings = useMemo(
    () =>
      toStaticAnalysisSafeMetric(opengrepTask?.total_findings) +
      toStaticAnalysisSafeMetric(codeqlTask?.total_findings) +
      toStaticAnalysisSafeMetric(joernTask?.total_findings),
    [codeqlTask?.total_findings, joernTask?.total_findings, opengrepTask?.total_findings],
  );

  const timeoutOnlyFailure = useMemo(
    () =>
      statusSummary.aggregateStatus === "failed" &&
      statusSummary.failureReasons.length > 0 &&
      statusSummary.failureReasons.every((reason) => reason.isTimeout),
    [statusSummary.aggregateStatus, statusSummary.failureReasons],
  );

  const codegraphDegraded = useMemo(
    () =>
      resolveCodegraphDegradedInfo({
        opengrepTask,
        codeqlTask,
        joernTask,
      }),
    [codeqlTask, joernTask, opengrepTask],
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

      {codegraphDegraded.unavailable ? (
        <div
          className="flex items-center gap-2"
          data-testid="codegraph-degraded-banner"
        >
          <Badge
            className="bg-amber-500/20 text-amber-300 border-amber-500/30"
            title={
              codegraphDegraded.reason
                ? `codegraph 初始化失败（${codegraphDegraded.reason}），已回退至旧版 6-pattern 探针。`
                : "codegraph 初始化失败，已回退至旧版 6-pattern 探针。"
            }
          >
            降级
          </Badge>
          <span className="text-xs text-muted-foreground">
            codegraph 不可用，已回退至旧版 6-pattern 探针
          </span>
        </div>
      ) : null}

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
