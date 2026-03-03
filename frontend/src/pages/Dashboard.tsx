/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
	Activity,
	AlertTriangle,
	Code,
	Bug,
	Clock3,
	Bot,
	Wrench,
	ShieldAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
	Bar,
	BarChart,
	CartesianGrid,
	Legend,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { api, isDemoMode } from "@/shared/config/database";
import type { ProjectStats } from "@/shared/types";
import { getOpengrepRules, type OpengrepRule } from "@/shared/api/opengrep";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";
import { useI18n } from "@/shared/i18n";
import {
	buildProjectScanRunsChartData,
	buildProjectVulnsChartData,
	fetchTaskPoolsWithPagination,
	toTopNByField,
	type ProjectScanRunsChartItem,
	type ProjectVulnsChartItem,
} from "@/features/dashboard/services/projectScanStats";

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

const formatTick = (value: number | string) => Number(value || 0).toLocaleString();
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

	const chartMax = useMemo(() => {
		if (rulesByLanguageData.length === 0) return 1;
		const maxSide = Math.max(...rulesByLanguageData.map((item) => item.total));
		return Math.max(1, maxSide);
	}, [rulesByLanguageData]);

	const cweChartMax = useMemo(() => {
		if (rulesByCweData.length === 0) return 1;
		const maxSide = Math.max(...rulesByCweData.map((item) => item.total));
		return Math.max(1, maxSide);
	}, [rulesByCweData]);

	const rulesChartHeight = useMemo(() => {
		const rowCount = Math.max(1, rulesByLanguageData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [rulesByLanguageData.length]);

	const cweChartHeight = useMemo(() => {
		const rowCount = Math.max(1, rulesByCweData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [rulesByCweData.length]);

	const projectScanRunsChartMax = useMemo(() => {
		if (projectScanRunsData.length === 0) return 1;
		const maxValue = Math.max(...projectScanRunsData.map((item) => item.totalRuns));
		return Math.max(1, maxValue);
	}, [projectScanRunsData]);

	const projectVulnsChartMax = useMemo(() => {
		if (projectVulnsData.length === 0) return 1;
		const maxValue = Math.max(...projectVulnsData.map((item) => item.totalVulns));
		return Math.max(1, maxValue);
	}, [projectVulnsData]);

	const projectScanRunsChartHeight = useMemo(() => {
		const rowCount = Math.max(1, projectScanRunsData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [projectScanRunsData.length]);

	const projectVulnsChartHeight = useMemo(() => {
		const rowCount = Math.max(1, projectVulnsData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [projectVulnsData.length]);

	const loadStatsData = useCallback(async () => {
		const [statsResult, rulesResult, scanStatsResult] = await Promise.allSettled([
			api.getProjectStats(),
			getOpengrepRules(),
			fetchTaskPoolsWithPagination(),
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

		if (scanStatsResult.status === "fulfilled") {
			const { projects, agentTasks, opengrepTasks, gitleaksTasks } =
				scanStatsResult.value;

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
		} else {
			setProjectScanRunsData([]);
			setProjectVulnsData([]);
			setTotalScanDurationMs(0);
		}
	}, []);

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

	const renderProjectVulnsTooltip = (payload: {
		active?: boolean;
		payload?: Array<{ payload?: ProjectVulnsChartItem }>;
	}) => {
		if (!payload?.active || !Array.isArray(payload.payload) || payload.payload.length === 0) {
			return null;
		}
		const row = payload.payload[0]?.payload as ProjectVulnsChartItem | undefined;
		if (!row) return null;

		return (
			<div className="rounded border border-border bg-background/95 px-3 py-2 text-xs shadow-xl">
				<p className="font-semibold text-foreground">{row.projectName}</p>
				<p className="text-muted-foreground mt-1">
					{t("dashboard.totalVulns")}：{formatTick(row.totalVulns)}
				</p>
				<div className="mt-1 space-y-0.5">
					<p className="text-sky-300">
						{t("dashboard.staticScan")}：{formatTick(row.staticVulns)}
					</p>
					<p className="text-emerald-300">
						{t("dashboard.intelligentScan")}：{formatTick(
							row.intelligentVulns,
						)}
					</p>
					<p className="text-violet-300">
						{t("dashboard.hybridScan")}：{formatTick(row.hybridVulns)}
					</p>
				</div>
			</div>
		);
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
							<p className="text-sm text-sky-400 mt-1 flex items-center gap-1">
								<span className="w-2 h-2 rounded-full bg-sky-400" />
								{t("dashboard.fixedCountHint")}
							</p>
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
							<p className="text-sm text-emerald-400 mt-1 flex items-center gap-1">
								<span className="w-2 h-2 rounded-full bg-emerald-400" />
								{t("dashboard.fixedCountHint")}
							</p>
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
							<p className="text-sm text-violet-400 mt-1 flex items-center gap-1">
								<span className="w-2 h-2 rounded-full bg-violet-400" />
								{t("dashboard.vulnerabilityTypesHint")}
							</p>
						</div>
						<div className="stat-icon text-violet-400">
							<ShieldAlert className="w-6 h-6" />
						</div>
					</div>
				</div>
			</div>

			<div className="grid grid-cols-1 xl:grid-cols-2 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<AlertTriangle className="w-5 h-5 text-sky-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">规则分布横向条形统计图</h3>
								<span className="text-sm text-muted-foreground">
									语言数：{rulesByLanguageData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								仅统计严重且中/高置信度规则
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: rulesChartHeight }}
					>
						{rulesByLanguageData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								暂无符合条件的规则分布数据
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={rulesByLanguageData}
									layout="vertical"
									margin={{ top: 6, right: 6, left: 4, bottom: 6 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
									<XAxis
										type="number"
										domain={[0, chartMax]}
										tickFormatter={formatTick}
										tick={{ fontSize: 13 }}
									/>
									<YAxis
										type="category"
										dataKey="language"
										width={96}
										tick={{ fontSize: 13 }}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={{ fontSize: 13 }}
									/>
									<Legend wrapperStyle={{ fontSize: 13 }} />
									<Bar
										dataKey="highCount"
										stackId="confidence"
										fill="#22c55e"
										name="高置信度"
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										stackId="confidence"
										dataKey="mediumCount"
										fill="#facc15"
										name="中置信度"
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Bug className="w-5 h-5 text-violet-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">规则漏洞类型统计图（CWE分类）</h3>
								<span className="text-sm text-muted-foreground">
									类型数：{rulesByCweData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								统计严重规则关联的 CWE 类型（Top 20）
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: cweChartHeight }}
					>
						{rulesByCweData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								暂无 CWE 分类统计数据
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={rulesByCweData}
									layout="vertical"
									margin={{ top: 6, right: 6, left: 4, bottom: 6 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
									<XAxis
										type="number"
										domain={[0, cweChartMax]}
										tickFormatter={formatTick}
										tick={{ fontSize: 13 }}
									/>
									<YAxis
										type="category"
										dataKey="cwe"
										width={96}
										tick={{ fontSize: 13 }}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={{ fontSize: 13 }}
									/>
									<Bar
										dataKey="total"
										fill="#a78bfa"
										name="规则数量"
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>
			</div>

			<div className="grid grid-cols-1 xl:grid-cols-2 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Activity className="w-5 h-5 text-emerald-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">
									{t("dashboard.projectScanRunsChartTitle")}
								</h3>
								<span className="text-sm text-muted-foreground">
									项目数：{projectScanRunsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{t("dashboard.projectScanRunsChartSubtitle")}（Top 10）
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectScanRunsChartHeight }}
					>
						{projectScanRunsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{t("dashboard.noProjectScanRunsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={projectScanRunsData}
									layout="vertical"
									margin={{ top: 6, right: 6, left: 4, bottom: 6 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
									<XAxis
										type="number"
										domain={[0, projectScanRunsChartMax]}
										tickFormatter={formatTick}
										tick={{ fontSize: 13 }}
									/>
									<YAxis
										type="category"
										dataKey="projectName"
										width={108}
										tick={{ fontSize: 13 }}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={{ fontSize: 13 }}
									/>
									<Legend wrapperStyle={{ fontSize: 13 }} />
									<Bar
										dataKey="staticRuns"
										stackId="runs"
										fill="#38bdf8"
										name={t("dashboard.staticScan")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										dataKey="intelligentRuns"
										stackId="runs"
										fill="#34d399"
										name={t("dashboard.intelligentScan")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										dataKey="hybridRuns"
										stackId="runs"
										fill="#a78bfa"
										name={t("dashboard.hybridScan")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>

				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Bug className="w-5 h-5 text-amber-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">
									{t("dashboard.projectVulnsChartTitle")}
								</h3>
								<span className="text-sm text-muted-foreground">
									项目数：{projectVulnsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{t("dashboard.projectVulnsChartSubtitle")}（Top 10）
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectVulnsChartHeight }}
					>
						{projectVulnsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{t("dashboard.noProjectVulnsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={projectVulnsData}
									layout="vertical"
									margin={{ top: 6, right: 6, left: 4, bottom: 6 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" strokeOpacity={0.2} />
									<XAxis
										type="number"
										domain={[0, projectVulnsChartMax]}
										tickFormatter={formatTick}
										tick={{ fontSize: 13 }}
									/>
									<YAxis
										type="category"
										dataKey="projectName"
										width={108}
										tick={{ fontSize: 13 }}
									/>
									<Tooltip content={renderProjectVulnsTooltip} />
									<Bar
										dataKey="totalVulns"
										fill="#f59e0b"
										name={t("dashboard.totalVulns")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}
