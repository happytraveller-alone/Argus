/**
 * Stats Panel Component
 * Dashboard-style statistics with premium visual design
 * Features: Animated progress, metric gauges, severity indicators
 * Enhanced visual effects with depth and polish
 */

import { memo } from "react";
import {
	Activity,
	FileCode,
	Repeat,
	Zap,
	AlertTriangle,
	TrendingUp,
} from "lucide-react";
import type { StatsPanelProps } from "../types";

// Enhanced Metric card component with premium styling
function MetricCard({
	icon,
	label,
	value,
	suffix = "",
	colorClass = "text-muted-foreground",
	bgClass = "",
}: {
	icon: React.ReactNode;
	label: string;
	value: string | number;
	suffix?: string;
	colorClass?: string;
	bgClass?: string;
}) {
	return (
		<div
			className={`
      group relative flex items-center gap-3 p-3.5 rounded-lg
      min-w-[170px]
      bg-card/80 border border-border/50 backdrop-blur-sm
      hover:bg-card hover:border-border/80 hover:shadow-md
      transition-all duration-300
      ${bgClass}
    `}
		>
			{/* Subtle gradient overlay on hover */}
			<div className="absolute inset-0 rounded-lg bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

			<div
				className={`relative z-10 p-2 rounded-md bg-muted/50 border border-border/50 ${colorClass} transition-transform duration-300 group-hover:scale-105`}
			>
				{icon}
			</div>
			<div className="flex-1 min-w-0 relative z-10">
				<div className="text-xs text-muted-foreground uppercase tracking-wider truncate font-medium mb-0.5">
					{label}
				</div>
				<div className="text-lg text-foreground font-mono font-bold leading-tight">
					{value}
					<span className="text-muted-foreground text-sm ml-0.5">{suffix}</span>
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
		<div className="space-y-3">
			{/* Progress Section with enhanced styling */}
			<div className="p-4 rounded-lg border border-border/50 bg-card/80 backdrop-blur-sm relative overflow-hidden">
				{/* Background gradient */}
				<div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none" />

				<div className="relative z-10">
					<div className="flex items-center justify-between mb-3">
						<div className="flex items-center gap-2.5">
							<div className="p-1.5 rounded-md bg-primary/15 border border-primary/30">
								<Activity className="w-4 h-4 text-primary" />
							</div>
							<span className="text-sm text-foreground uppercase tracking-wider font-semibold">
								进度
							</span>
						</div>
						<div className="flex items-center gap-2">
							<span className="text-lg text-primary font-mono font-bold">
								{progressPercent.toFixed(0)}
							</span>
							<span className="text-sm text-muted-foreground">%</span>
						</div>
					</div>

					{/* Enhanced Progress bar */}
					<div className="relative h-3 bg-muted/50 rounded-full overflow-hidden border border-border/30">
						<div
							className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary via-primary to-primary/80 rounded-full transition-all duration-700 ease-out"
							style={{ width: `${progressPercent}%` }}
						/>
						{/* Animated shine effect */}
						<div
							className="absolute inset-y-0 left-0 bg-gradient-to-r from-transparent via-white/30 to-transparent rounded-full"
							style={{
								width: `${progressPercent}%`,
								animation: "shine 2s ease-in-out infinite",
							}}
						/>
						{/* Glow effect */}
						<div
							className="absolute inset-y-0 left-0 rounded-full blur-sm opacity-50"
							style={{
								width: `${progressPercent}%`,
								background: "linear-gradient(to right, #FF6B2C, #FF6B2C)",
							}}
						/>
					</div>

					{/* File progress with enhanced styling */}
					<div className="flex items-center justify-between mt-4 text-sm">
						<div className="flex items-center gap-2 text-muted-foreground">
							<FileCode className="w-4 h-4" />
							<span className="font-medium">已扫描文件</span>
						</div>
						<span className="text-foreground font-mono font-bold">
							{task.analyzed_files}
							<span className="text-muted-foreground font-normal">
								{" "}
								/ {task.total_files}
							</span>
						</span>
					</div>
					{/* Files with findings */}
					{task.files_with_findings > 0 && (
						<div className="flex items-center justify-between mt-2 text-sm">
							<div className="flex items-center gap-2 text-muted-foreground">
								<AlertTriangle className="w-4 h-4 text-rose-500" />
								<span className="font-medium">命中缺陷文件</span>
							</div>
							<span className="text-rose-500 font-mono font-bold">
								{task.files_with_findings}
							</span>
						</div>
					)}
				</div>
			</div>

			{/* Metrics Grid with enhanced styling */}
			<div className="flex gap-2.5 overflow-x-auto pb-1">
				<MetricCard
					icon={<Repeat className="w-4 h-4" />}
					label="迭代次数"
					value={task.total_iterations || 0}
					colorClass="text-teal-500"
				/>
				<MetricCard
					icon={<Zap className="w-4 h-4" />}
					label="工具调用"
					value={task.tool_calls_count || 0}
					colorClass="text-amber-500"
				/>
				<MetricCard
					icon={<TrendingUp className="w-4 h-4" />}
					label="Token"
					value={((task.tokens_used || 0) / 1000).toFixed(1)}
					suffix="k"
					colorClass="text-violet-500"
				/>
			</div>

			{/* Inline animation */}
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
