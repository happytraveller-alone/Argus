import { memo } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  Bug,
  Clock3,
  FolderOpen,
  Repeat,
  Wrench,
  TrendingUp,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { formatDurationMs, formatTokenValue } from "../detailViewModel";
import type { StatsPanelProps } from "../types";

function MetricCard({
  icon,
  label,
  value,
  subtext,
  progress,
  valueClassName,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  subtext: ReactNode;
  progress?: number;
  valueClassName?: string;
}) {
  return (
    <div className="cyber-card flex min-w-[180px] flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <span className="text-primary">{icon}</span>
        <span>{label}</span>
      </div>
      <div className={valueClassName || "text-xl font-bold text-foreground"}>{value}</div>
      {typeof progress === "number" ? (
        <Progress
          value={Math.max(Math.min(progress, 100), 0)}
          className="h-1.5 bg-muted [&>div]:bg-emerald-500"
        />
      ) : null}
      <div className="text-xs text-muted-foreground">{subtext}</div>
    </div>
  );
}

export const StatsPanel = memo(function StatsPanel({ summary, projectName }: StatsPanelProps) {
  if (!summary) return null;

  return (
    <div className="overflow-x-auto custom-scrollbar">
      <div className="grid min-w-[1300px] grid-cols-7 gap-3">
        <MetricCard
          icon={<FolderOpen className="h-4 w-4" />}
          label="当前项目"
          value={String(projectName || "-")}
          // valueClassName="line-clamp-2 min-h-[3.5rem] break-all text-lg font-bold leading-snug text-foreground"
          subtext=""
        />
        <MetricCard
          icon={<Activity className="h-4 w-4" />}
          label="进度比例"
          value={`${summary.progressPercent.toFixed(0)}%`}
          // progress={summary.progressPercent}
          subtext=""
        />
        <MetricCard
          icon={<Clock3 className="h-4 w-4" />}
          label="扫描时间"
          value={formatDurationMs(summary.durationMs)}
          subtext=""
        />
        <MetricCard
          icon={<Bug className="h-4 w-4" />}
          label="漏洞数量"
          value={summary.totalFindings.toLocaleString()}
          subtext=""
        />
        {/* <MetricCard
          icon={<Repeat className="h-4 w-4" />}
          label="迭代次数"
          value={summary.iterations.toLocaleString()}
          subtext=""
        />
        <MetricCard
          icon={<Wrench className="h-4 w-4" />}
          label="工具扫描"
          value={summary.toolCalls.toLocaleString()}
          subtext=""
        /> */}
        <MetricCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Token 消耗"
          value={formatTokenValue(summary.tokensTotal)}
          subtext=""
        />
      </div>
    </div>
  );
});

export default StatsPanel;
