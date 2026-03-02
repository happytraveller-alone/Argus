/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Code } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, isDemoMode } from "@/shared/config/database";
import type { ProjectStats } from "@/shared/types";
import { getOpengrepRules } from "@/shared/api/opengrep";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";

const DEFAULT_STATS: ProjectStats = {
	total_projects: 0,
	active_projects: 0,
	total_tasks: 0,
	completed_tasks: 0,
	interrupted_tasks: 0,
	running_tasks: 0,
	failed_tasks: 0,
	total_issues: 0,
	resolved_issues: 0,
	avg_quality_score: 0,
};

export default function Dashboard() {
	const [stats, setStats] = useState<ProjectStats>(DEFAULT_STATS);
	const [loading, setLoading] = useState(true);
	const [ruleStats, setRuleStats] = useState({ total: 0, enabled: 0 });

	useEffect(() => {
		void loadDashboardData();

		const timer = window.setInterval(() => {
			void loadDashboardData({ silent: true });
		}, 15000);

		return () => {
			window.clearInterval(timer);
		};
	}, []);

	const loadStatsData = async () => {
		const [statsResult, rulesResult] = await Promise.allSettled([
			api.getProjectStats(),
			getOpengrepRules(),
		]);

		if (statsResult.status === "fulfilled") {
			setStats(statsResult.value);
		} else {
			setStats(DEFAULT_STATS);
		}

		if (rulesResult.status === "fulfilled") {
			const allRules = rulesResult.value.filter(
				(rule) => String(rule.severity || "").toUpperCase() === "ERROR",
			);
			const totalRules = allRules.length;
			const enabledRules = allRules.filter((rule) => rule.is_active).length;
			setRuleStats({ total: totalRules, enabled: enabledRules });
		} else {
			setRuleStats({ total: 0, enabled: 0 });
		}
	};

	const loadDashboardData = async (options?: { silent?: boolean }) => {
		try {
			await runWithRefreshMode(loadStatsData, { ...options, setLoading });
		} catch (error) {
			console.error("仪表盘数据加载失败:", error);
			toast.error("数据加载失败");
		}
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<div className="text-center space-y-4">
					<div className="loading-spinner mx-auto" />
					<p className="text-muted-foreground font-mono text-base uppercase tracking-wider">
						加载数据中...
					</p>
				</div>
			</div>
		);
	}

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{isDemoMode && (
				<div className="relative z-10 cyber-card p-4 border-amber-500/30 bg-amber-500/5">
					<div className="flex items-start gap-3">
						<AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5" />
						<div className="text-sm text-foreground/80">
							当前使用<span className="text-amber-400 font-bold">演示模式</span>
							，显示的是模拟数据。
							<Link
								to="/scan-config/engines"
								className="ml-2 text-primary font-bold hover:underline"
							>
								前往扫描引擎 →
							</Link>
						</div>
					</div>
				</div>
			)}

			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">总项目数</p>
							<p className="stat-value">{stats.active_projects || 0}</p>
						</div>
						<div className="stat-icon text-primary">
							<Code className="w-6 h-6" />
						</div>
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">审计任务</p>
							<p className="stat-value">{stats.total_tasks || 0}</p>
							<p className="text-sm mt-1 flex items-center gap-3">
								<span className="text-emerald-400 inline-flex items-center gap-1">
									<span className="w-2 h-2 rounded-full bg-emerald-400" />
									已完成: {stats.completed_tasks || 0}
								</span>
								<span className="text-sky-400 inline-flex items-center gap-1">
									<span className="w-2 h-2 rounded-full bg-sky-400" />
									运行中: {stats.running_tasks || 0}
								</span>
							</p>
						</div>
						<div className="stat-icon text-emerald-400">
							<Activity className="w-6 h-6" />
						</div>
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">审计规则</p>
							<p className="stat-value">{ruleStats.total}</p>
							<p className="text-sm text-sky-400 mt-1 flex items-center gap-1">
								<span className="w-2 h-2 rounded-full bg-sky-400" />
								已启用: {ruleStats.enabled}
							</p>
						</div>
						<div className="stat-icon text-sky-400">
							<AlertTriangle className="w-6 h-6" />
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
