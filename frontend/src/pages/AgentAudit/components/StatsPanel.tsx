import { memo } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  Bug,
  Clock3,
  Repeat,
  Wrench,
  TrendingUp,
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import type { AgentAuditStatsSummary } from "../detailViewModel";
import { formatDurationMs, formatTokenValue } from "../detailViewModel";

interface StatsPanelProps {
  summary: AgentAuditStatsSummary | null;
}

function MetricCard({
  icon,
  label,
  value,
  subtext,
  progress,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  subtext: ReactNode;
  progress?: number;
}) {
  return (
    <div className="cyber-card flex min-w-[180px] flex-col gap-2 p-4">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <span className="text-primary">{icon}</span>
        <span>{label}</span>
      </div>
      <div className="text-xl font-bold text-foreground">{value}</div>
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

export const StatsPanel = memo(function StatsPanel({ summary }: StatsPanelProps) {
  if (!summary) return null;

  return (
    <div className="overflow-x-auto custom-scrollbar">
      <div className="grid min-w-[1120px] grid-cols-6 gap-3">
        <MetricCard
          icon={<Activity className="h-4 w-4" />}
          label="进度比例"
          value={`${summary.progressPercent.toFixed(0)}%`}
          progress={summary.progressPercent}
          subtext="当前扫描进度"
        />
        <MetricCard
          icon={<Clock3 className="h-4 w-4" />}
          label="扫描时间"
          value={formatDurationMs(summary.durationMs)}
          subtext="任务开始至当前/结束"
        />
        <MetricCard
          icon={<Bug className="h-4 w-4" />}
          label="漏洞数量"
          value={summary.findingsTotal.toLocaleString()}
          subtext={`已验证 ${summary.findingsVerified.toLocaleString()} · 待验证 ${summary.findingsPending.toLocaleString()}`}
        />
        <MetricCard
          icon={<Repeat className="h-4 w-4" />}
          label="迭代次数"
          value={summary.iterations.toLocaleString()}
          subtext="Agent 迭代轮次"
        />
        <MetricCard
          icon={<Wrench className="h-4 w-4" />}
          label="工具扫描"
          value={summary.toolCalls.toLocaleString()}
          subtext="累计工具调用次数"
        />
        <MetricCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Token 消耗"
          value={formatTokenValue(summary.tokensTotal)}
          subtext={
            <div className="flex items-center justify-between gap-3 text-xs">
              Token 消耗
              {/* <span>输入 {summary.tokensInput === null ? "--" : formatTokenValue(summary.tokensInput)}</span>
              <span>输出 {summary.tokensOutput === null ? "--" : formatTokenValue(summary.tokensOutput)}</span> */}
            </div>
          }
        />
      </div>
    </div>
  );
});

export default StatsPanel;
