import { memo, useMemo } from "react";

import { Progress } from "@/components/ui/progress";
import { useTaskClock } from "@/features/tasks/hooks/useTaskClock";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { OpengrepScanTask } from "@/shared/api/opengrep";
import type { BanditScanTask } from "@/shared/api/bandit";

import type { Engine } from "./viewModel";
import {
  buildStaticAnalysisProgressSummary,
  formatStaticAnalysisDuration,
  getStaticAnalysisTotalDisplayDurationMs,
  isStaticAnalysisPollableStatus,
  toStaticAnalysisSafeMetric,
} from "./viewModel";

interface StaticAnalysisSummaryCardsProps {
  opengrepTask: OpengrepScanTask | null;
  gitleaksTask: GitleaksScanTask | null;
  banditTask: BanditScanTask | null;
  enabledEngines: Engine[];
}

export const StaticAnalysisSummaryCards = memo(function StaticAnalysisSummaryCards({
  opengrepTask,
  gitleaksTask,
  banditTask,
  enabledEngines,
}: StaticAnalysisSummaryCardsProps) {
  const shouldTickClock = useMemo(
    () =>
      [opengrepTask, gitleaksTask, banditTask].some((task) =>
        isStaticAnalysisPollableStatus(task?.status),
      ),
    [banditTask, gitleaksTask, opengrepTask],
  );
  const nowMs = useTaskClock({ enabled: shouldTickClock, intervalMs: 1000 });

  const progressPercent = useMemo(
    () =>
      buildStaticAnalysisProgressSummary({
        opengrepTask,
        gitleaksTask,
        banditTask,
        nowMs,
      }).progressPercent,
    [banditTask, gitleaksTask, nowMs, opengrepTask],
  );

  const totalScanDurationMs = useMemo(
    () =>
      getStaticAnalysisTotalDisplayDurationMs({
        opengrepTask,
        gitleaksTask,
        banditTask,
        nowMs,
      }),
    [banditTask, gitleaksTask, nowMs, opengrepTask],
  );

  const totalFindings = useMemo(
    () =>
      toStaticAnalysisSafeMetric(opengrepTask?.total_findings) +
      toStaticAnalysisSafeMetric(gitleaksTask?.total_findings) +
      toStaticAnalysisSafeMetric(banditTask?.total_findings),
    [banditTask?.total_findings, gitleaksTask?.total_findings, opengrepTask?.total_findings],
  );

  const totalFilesScanned = useMemo(
    () =>
      toStaticAnalysisSafeMetric(opengrepTask?.files_scanned) +
      toStaticAnalysisSafeMetric(gitleaksTask?.files_scanned) +
      toStaticAnalysisSafeMetric(banditTask?.files_scanned),
    [banditTask?.files_scanned, gitleaksTask?.files_scanned, opengrepTask?.files_scanned],
  );

  return (
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
      </div>
      <div className="cyber-card p-4 space-y-1">
        <p className="text-xs font-semibold uppercase text-muted-foreground">
          扫描漏洞数量
        </p>
        <p className="text-xl font-bold text-foreground">
          {totalFindings.toLocaleString()}
        </p>
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
            .map((engine) =>
              engine === "opengrep"
                ? "Opengrep"
                : engine === "gitleaks"
                  ? "Gitleaks"
                  : "Bandit",
            )
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
      </div>
    </div>
  );
});

export default StaticAnalysisSummaryCards;
