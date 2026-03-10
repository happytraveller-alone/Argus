/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
	Activity,
	AlertTriangle,
	Code,
	Clock3,
	Bot,
	Wrench,
	ShieldAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import DeferredSection from "@/components/performance/DeferredSection";
import { Skeleton } from "@/components/ui/skeleton";
import { api, isDemoMode } from "@/shared/config/database";
import type { ProjectStats } from "@/shared/types";
import { getOpengrepRules, type OpengrepRule } from "@/shared/api/opengrep";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";
import { useI18n } from "@/shared/i18n";
import type { I18nKey } from "@/shared/i18n/messages";
import {
	buildProjectScanRunsChartData,
	buildProjectVulnsChartData,
	fetchTaskPoolsWithPagination,
	toTopNByField,
	type ProjectScanRunsChartItem,
	type ProjectVulnsChartItem,
} from "@/features/dashboard/services/projectScanStats";
import { loadDashboardSnapshot } from "@/features/dashboard/services/dashboardSnapshotStore";

const DashboardChartsPanels = lazy(
	() => import("@/features/dashboard/components/DashboardChartsPanels"),
);

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

type RuleLanguageChartItem = {
	language: string;
	total: number;
	highCount: number;
	mediumCount: number;
};

type RuleCweChartItem = {
	cwe: string;
	total: number;
};

function normalizeConfidence(confidence?: string | null) {
	const normalized = confidence?.trim().toUpperCase();
	if (!normalized) return "";
	if (normalized === "MIDIUM" || normalized === "MIDDLE") {
		return "MEDIUM";
	}
	return normalized;
}

function normalizeCweCode(cwe?: string) {
	const raw = cwe?.trim();
	if (!raw) return "";
	const upper = raw.toUpperCase().replace(/_/g, "-");
	const digits = upper.match(/(\d+)/)?.[1];
	if (digits) return `CWE-${digits}`;
	if (upper.startsWith("CWE-")) return upper;
	if (upper.startsWith("CWE")) {
		return upper.replace(/^CWE[-:]?/, "CWE-");
	}
	return `CWE-${upper}`;
}

function getRulesByLanguageData(rules: OpengrepRule[]): RuleLanguageChartItem[] {
	const aggregate = new Map<string, RuleLanguageChartItem>();

	for (const rule of rules) {
		const language = String(rule.language || "unknown").trim() || "unknown";
		if (!aggregate.has(language)) {
			aggregate.set(language, {
				language,
				total: 0,
				highCount: 0,
				mediumCount: 0,
			});
		}
		const entry = aggregate.get(language);
		if (!entry) continue;

		const confidence = normalizeConfidence(rule.confidence);
		if (confidence === "HIGH") {
			entry.highCount += 1;
		} else if (confidence === "MEDIUM") {
			entry.mediumCount += 1;
		}
	}

	return Array.from(aggregate.values())
		.map((item) => ({
			...item,
			total: item.highCount + item.mediumCount,
		}))
		.filter((item) => item.total > 0)
		.sort((a, b) => {
			if (b.total !== a.total) return b.total - a.total;
			return a.language.localeCompare(b.language, "zh-CN");
		});
}

function getRulesByCweData(rules: OpengrepRule[]): RuleCweChartItem[] {
	const aggregate = new Map<string, number>();

	for (const rule of rules) {
		const cweList = Array.isArray(rule.cwe) ? rule.cwe : [];
		const normalizedSet = new Set(
			cweList.map((item) => normalizeCweCode(item)).filter(Boolean),
		);
		for (const cwe of normalizedSet) {
			aggregate.set(cwe, (aggregate.get(cwe) || 0) + 1);
		}
	}

	return Array.from(aggregate.entries())
		.map(([cwe, total]) => ({ cwe, total }))
		.sort((a, b) => {
			if (b.total !== a.total) return b.total - a.total;
			return a.cwe.localeCompare(b.cwe, "zh-CN");
		})
		.slice(0, 20);
}

const SUPPORTED_MODEL_PROVIDERS_COUNT = 13;
const SUPPORTED_EXTERNAL_TOOL_CALLS_COUNT = 40;
const SUPPORTED_VULNERABILITY_TYPES_COUNT = 8;

const parseTimestampMs = (value?: string | null): number | null => {
	if (!value) return null;
	const timestamp = Date.parse(value);
	return Number.isFinite(timestamp) ? timestamp : null;
};

const formatDurationMs = (durationMs: number): string => {
	const sanitized = Math.max(0, Math.floor(Number(durationMs) || 0));
	const totalSeconds = Math.floor(sanitized / 1000);
	const days = Math.floor(totalSeconds / 86400);
	const hours = Math.floor((totalSeconds % 86400) / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;

	if (days > 0) {
		return `${days}d ${hours}h ${minutes}m`;
	}
	if (hours > 0) {
		return `${hours}h ${minutes}m ${seconds}s`;
	}
	if (minutes > 0) {
		return `${minutes}m ${seconds}s`;
	}
	return `${seconds}s`;
};

function DashboardChartsFallback() {
	const fallbackPanels = ["rules", "cwe"] as const;
	return (
		<div className="grid grid-cols-1 xl:grid-cols-2 gap-4 relative z-10">
			{fallbackPanels.map((panelId) => (
				<div key={panelId} className="cyber-card p-4 space-y-3">
					<Skeleton className="h-5 w-48" />
					<Skeleton className="h-72 w-full" />
				</div>
			))}
		</div>
	);
}

export default function Dashboard() {
	const { t } = useI18n();
	const [stats, setStats] = useState<ProjectStats>(DEFAULT_STATS);
	const [loading, setLoading] = useState(true);
	const [ruleStats, setRuleStats] = useState({ total: 0, enabled: 0 });
	const [rulesByLanguageData, setRulesByLanguageData] = useState<RuleLanguageChartItem[]>([]);
	const [rulesByCweData, setRulesByCweData] = useState<RuleCweChartItem[]>([]);
	const [projectScanRunsData, setProjectScanRunsData] = useState<
		ProjectScanRunsChartItem[]
	>([]);
	const [projectVulnsData, setProjectVulnsData] = useState<ProjectVulnsChartItem[]>(
		[],
	);
	const [totalScanDurationMs, setTotalScanDurationMs] = useState(0);
	const [scanStatsLoading, setScanStatsLoading] = useState(true);
	const scanStatsRequestSeqRef = useRef(0);
	const translate = useCallback(
		(key: string, fallback?: string) => t(key as I18nKey, fallback),
		[t],
	);

	const loadScanStats = useCallback(async () => {
		const requestSeq = scanStatsRequestSeqRef.current + 1;
		scanStatsRequestSeqRef.current = requestSeq;
		setScanStatsLoading(true);

		try {
			const snapshot = await loadDashboardSnapshot({ topN: 10 });
			if (requestSeq !== scanStatsRequestSeqRef.current) {
				return;
			}

			const snapshotScanRuns = (snapshot.data.scan_runs || []).map((item) => ({
				projectId: item.project_id,
				projectName: item.project_name || "未知项目",
				staticRuns: Math.max(Number(item.static_runs || 0), 0),
				intelligentRuns: Math.max(Number(item.intelligent_runs || 0), 0),
				hybridRuns: Math.max(Number(item.hybrid_runs || 0), 0),
				totalRuns: Math.max(Number(item.total_runs || 0), 0),
			}));
			const snapshotVulns = (snapshot.data.vulns || []).map((item) => ({
				projectId: item.project_id,
				projectName: item.project_name || "未知项目",
				staticVulns: Math.max(Number(item.static_vulns || 0), 0),
				intelligentVulns: Math.max(Number(item.intelligent_vulns || 0), 0),
				hybridVulns: Math.max(Number(item.hybrid_vulns || 0), 0),
				totalVulns: Math.max(Number(item.total_vulns || 0), 0),
			}));
			setTotalScanDurationMs(
				Math.max(Number(snapshot.data.total_scan_duration_ms || 0), 0),
			);
			setProjectScanRunsData(toTopNByField(snapshotScanRuns, "totalRuns", 10));
			setProjectVulnsData(toTopNByField(snapshotVulns, "totalVulns", 10));
			setScanStatsLoading(false);
			return;
		} catch {
			// fallback to legacy client-side aggregation
		}

		try {
			const { projects, agentTasks, opengrepTasks, gitleaksTasks } =
				await fetchTaskPoolsWithPagination();
			if (requestSeq !== scanStatsRequestSeqRef.current) {
				return;
			}

			const opengrepDurationMs = opengrepTasks.reduce(
				(sum, task) => sum + Math.max(Number(task.scan_duration_ms || 0), 0),
				0,
			);
			const gitleaksDurationMs = gitleaksTasks.reduce(
				(sum, task) => sum + Math.max(Number(task.scan_duration_ms || 0), 0),
				0,
			);
			const agentDurationMs = agentTasks.reduce((sum, task) => {
				const startedAt = parseTimestampMs(task.started_at);
				const completedAt = parseTimestampMs(task.completed_at);
				if (startedAt === null || completedAt === null) return sum;
				return sum + Math.max(completedAt - startedAt, 0);
			}, 0);

			setTotalScanDurationMs(
				Math.max(opengrepDurationMs + gitleaksDurationMs + agentDurationMs, 0),
			);

			const scanRuns = buildProjectScanRunsChartData({
				projects,
				agentTasks,
				opengrepTasks,
			});
			const vulns = buildProjectVulnsChartData({
				projects,
				agentTasks,
				opengrepTasks,
			});
			setProjectScanRunsData(toTopNByField(scanRuns, "totalRuns", 10));
			setProjectVulnsData(toTopNByField(vulns, "totalVulns", 10));
			setScanStatsLoading(false);
		} catch {
			if (requestSeq !== scanStatsRequestSeqRef.current) {
				return;
			}
			setProjectScanRunsData([]);
			setProjectVulnsData([]);
			setTotalScanDurationMs(0);
			setScanStatsLoading(false);
		}
	}, []);

	const loadStatsData = useCallback(async () => {
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
			const severeRules = rulesResult.value.filter(
				(rule) => String(rule.severity || "").toUpperCase() === "ERROR",
			);
			const totalRules = severeRules.length;
			const enabledRules = severeRules.filter((rule) => rule.is_active).length;
			setRuleStats({ total: totalRules, enabled: enabledRules });
			setRulesByLanguageData(getRulesByLanguageData(severeRules));
			setRulesByCweData(getRulesByCweData(severeRules));
		} else {
			setRuleStats({ total: 0, enabled: 0 });
			setRulesByLanguageData([]);
			setRulesByCweData([]);
		}
		void loadScanStats();
	}, [loadScanStats]);

	const loadDashboardData = useCallback(async (options?: { silent?: boolean }) => {
		try {
			await runWithRefreshMode(loadStatsData, { ...options, setLoading });
		} catch (error) {
			console.error("仪表盘数据加载失败:", error);
			toast.error("数据加载失败");
		}
	}, [loadStatsData]);

	useEffect(() => {
		void loadDashboardData();

		const timer = window.setInterval(() => {
			void loadDashboardData({ silent: true });
		}, 15000);

		return () => {
			window.clearInterval(timer);
		};
	}, [loadDashboardData]);

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			{loading && (
				<div className="relative z-10 text-xs text-muted-foreground">
					同步最新数据中...
				</div>
			)}

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

			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
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
							<p className="stat-label">扫描任务</p>
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
							<p className="stat-label">扫描规则</p>
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

				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">{t("dashboard.totalScanDuration")}</p>
							<p className="stat-value">{formatDurationMs(totalScanDurationMs)}</p>
							<p className="text-sm text-amber-400 mt-1 flex items-center gap-1">
								<span className="w-2 h-2 rounded-full bg-amber-400" />
								{t("dashboard.totalScanDurationHint")}
							</p>
						</div>
						<div className="stat-icon text-amber-400">
							<Clock3 className="w-6 h-6" />
						</div>
					</div>
				</div>
			</div>

			<div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
								<p className="stat-label">{t("dashboard.supportedModelProviders")}</p>
								<p className="stat-value">{SUPPORTED_MODEL_PROVIDERS_COUNT}</p>
							</div>
						<div className="stat-icon text-sky-400">
							<Bot className="w-6 h-6" />
						</div>
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
								<p className="stat-label">{t("dashboard.supportedExternalToolCalls")}</p>
								<p className="stat-value">{SUPPORTED_EXTERNAL_TOOL_CALLS_COUNT}</p>
							</div>
						<div className="stat-icon text-emerald-400">
							<Wrench className="w-6 h-6" />
						</div>
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
								<p className="stat-label">{t("dashboard.supportedVulnerabilityTypes")}</p>
								<p className="stat-value">{SUPPORTED_VULNERABILITY_TYPES_COUNT}</p>
							</div>
						<div className="stat-icon text-violet-400">
							<ShieldAlert className="w-6 h-6" />
						</div>
					</div>
				</div>
			</div>

			<DeferredSection minHeight={900} priority>
				{scanStatsLoading &&
				projectScanRunsData.length === 0 &&
				projectVulnsData.length === 0 ? (
					<DashboardChartsFallback />
				) : (
					<Suspense fallback={<DashboardChartsFallback />}>
						<DashboardChartsPanels
							rulesByLanguageData={rulesByLanguageData}
							rulesByCweData={rulesByCweData}
							projectScanRunsData={projectScanRunsData}
							projectVulnsData={projectVulnsData}
							translate={translate}
						/>
					</Suspense>
				)}
			</DeferredSection>
		</div>
	);
}
