/**
 * Stats Panel Component
 * Dashboard-style statistics with premium visual design
 * Features: Animated progress, metric gauges, severity indicators
 * Enhanced visual effects with depth and polish
 */

import { memo } from "react";
import {
	Activity,
	Repeat,
	Zap,
	TrendingUp,
} from "lucide-react";
import type { StatsPanelProps } from "../types";

function InlineMetric({
	icon,
	label,
	value,
	suffix = "",
	colorClass = "text-muted-foreground",
}: {
	icon: React.ReactNode;
	label: string;
	value: string | number;
	suffix?: string;
	colorClass?: string;
}) {
	return (
		<div
			className="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-border/60 bg-card/70"
		>
			<div className={`p-1.5 rounded-md bg-muted/50 border border-border/50 ${colorClass}`}>
				{icon}
			</div>
			<div className="flex-1 min-w-0">
				<div className="text-[11px] text-muted-foreground uppercase tracking-wider truncate font-medium">
					{label}
				</div>
				<div className="text-sm text-foreground font-mono font-bold leading-tight">
					{value}
					<span className="text-muted-foreground text-xs ml-0.5">{suffix}</span>
				</div>
			</div>
		</div>
	);
}

export const StatsPanel = memo(function StatsPanel({
	task,
	findings: _findings,
}: StatsPanelProps) {
	if (!task) return null;

	const progressPercent = task.progress_percentage || 0;

	return (
		<div className="rounded-lg border border-border/50 bg-card/80 backdrop-blur-sm p-3">
			<div className="flex flex-col xl:flex-row xl:items-center gap-3">
				<div className="flex-1 min-w-0">
					<div className="flex items-center justify-between mb-2.5">
						<div className="flex items-center gap-2.5">
							<div className="p-1.5 rounded-md bg-primary/15 border border-primary/30">
								<Activity className="w-4 h-4 text-primary" />
							</div>
							<span className="text-sm text-foreground uppercase tracking-wider font-semibold">
								进度
							</span>
						</div>
						<div className="flex items-center gap-1.5">
							<span className="text-base text-primary font-mono font-bold">
								{progressPercent.toFixed(0)}
							</span>
							<span className="text-xs text-muted-foreground">%</span>
						</div>
					</div>
					<div className="relative h-2.5 bg-muted/50 rounded-full overflow-hidden border border-border/30">
						<div
							className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary via-primary to-primary/80 rounded-full transition-all duration-700 ease-out"
							style={{ width: `${progressPercent}%` }}
						/>
						<div
							className="absolute inset-y-0 left-0 bg-gradient-to-r from-transparent via-white/30 to-transparent rounded-full"
							style={{
								width: `${progressPercent}%`,
								animation: "shine 2s ease-in-out infinite",
							}}
						/>
					</div>
				</div>

				<div className="grid grid-cols-1 sm:grid-cols-3 gap-2 xl:min-w-[480px]">
					<InlineMetric
						icon={<Repeat className="w-4 h-4" />}
						label="迭代次数"
						value={task.total_iterations || 0}
						colorClass="text-teal-500"
					/>
					<InlineMetric
						icon={<Zap className="w-4 h-4" />}
						label="工具调用"
						value={task.tool_calls_count || 0}
						colorClass="text-amber-500"
					/>
					<InlineMetric
						icon={<TrendingUp className="w-4 h-4" />}
						label="Token"
						value={((task.tokens_used || 0) / 1000).toFixed(1)}
						suffix="k"
						colorClass="text-violet-500"
					/>
				</div>
			</div>
			<style>{`
        @keyframes shine {
          0% { transform: translateX(-100%); }
          50% { transform: translateX(100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
		</div>
	);
});

export default StatsPanel;
