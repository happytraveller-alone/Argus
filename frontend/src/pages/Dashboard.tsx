/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
	Activity,
	AlertTriangle,
	Bot,
	Clock3,
	Code,
	ShieldAlert,
	Wrench,
} from "lucide-react";
import { toast } from "sonner";
import DeferredSection from "@/components/performance/DeferredSection";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/shared/api/database";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import type {
	DashboardCweDistributionItem,
	DashboardRuleConfidenceItem,
	DashboardRuleConfidenceByLanguageItem,
	ProjectStats,
} from "@/shared/types";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";
import { useI18n } from "@/shared/i18n";
import type { I18nKey } from "@/shared/i18n/messages";
import {
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

const SUPPORTED_MODEL_PROVIDERS_COUNT = 13;
const SUPPORTED_EXTERNAL_TOOL_CALLS_COUNT = 40;
const SUPPORTED_VULNERABILITY_TYPES_COUNT = 8;

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
	const fallbackPanels = ["overview", "confidence"] as const;
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
	const [ruleConfidenceData, setRuleConfidenceData] = useState<
		DashboardRuleConfidenceItem[]
	>([]);
	const [ruleConfidenceByLanguageData, setRuleConfidenceByLanguageData] = useState<
		DashboardRuleConfidenceByLanguageItem[]
	>([]);
	const [cweDistributionData, setCweDistributionData] = useState<
		DashboardCweDistributionItem[]
	>([]);
	const [projectScanRunsData, setProjectScanRunsData] = useState<
		ProjectScanRunsChartItem[]
	>([]);
	const [projectVulnsData, setProjectVulnsData] = useState<ProjectVulnsChartItem[]>(
		[],
	);
	const [totalScanDurationMs, setTotalScanDurationMs] = useState(0);
	const [scanStatsLoading, setScanStatsLoading] = useState(true);
	const snapshotRequestSeqRef = useRef(0);
	const translate = useCallback(
		(key: string, fallback?: string) => t(key as I18nKey, fallback),
		[t],
	);

	const loadSnapshotData = useCallback(async () => {
		const requestSeq = snapshotRequestSeqRef.current + 1;
		snapshotRequestSeqRef.current = requestSeq;
		setScanStatsLoading(true);

		try {
			const snapshot = await loadDashboardSnapshot({ topN: 10, force: true });
			if (requestSeq !== snapshotRequestSeqRef.current) {
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
			const snapshotRuleConfidence = (snapshot.data.rule_confidence || []).map(
				(item) => ({
					confidence: item.confidence,
					total_rules: Math.max(Number(item.total_rules || 0), 0),
					enabled_rules: Math.max(Number(item.enabled_rules || 0), 0),
				}),
			);
			const snapshotRuleConfidenceByLanguage = (
				snapshot.data.rule_confidence_by_language || []
			).map((item) => ({
				language: item.language || "unknown",
				high_count: Math.max(Number(item.high_count || 0), 0),
				medium_count: Math.max(Number(item.medium_count || 0), 0),
			}));
			const snapshotCweDistribution = (snapshot.data.cwe_distribution || []).map(
				(item) => {
					const cweDisplay = resolveCweDisplay({
						cwe: item.cwe_id,
						fallbackLabel: item.cwe_name || item.cwe_id || "CWE-UNKNOWN",
					});
					return {
						cwe_id: item.cwe_id || cweDisplay.cweId || "CWE-UNKNOWN",
						cwe_name: cweDisplay.label,
						total_findings: Math.max(Number(item.total_findings || 0), 0),
						opengrep_findings: Math.max(Number(item.opengrep_findings || 0), 0),
						agent_findings: Math.max(Number(item.agent_findings || 0), 0),
						bandit_findings: Math.max(Number(item.bandit_findings || 0), 0),
					};
				},
			);

			setTotalScanDurationMs(
				Math.max(Number(snapshot.data.total_scan_duration_ms || 0), 0),
			);
			setProjectScanRunsData(toTopNByField(snapshotScanRuns, "totalRuns", 10));
			setProjectVulnsData(toTopNByField(snapshotVulns, "totalVulns", 10));
			setRuleConfidenceData(snapshotRuleConfidence);
			setRuleConfidenceByLanguageData(snapshotRuleConfidenceByLanguage);
			setCweDistributionData(snapshotCweDistribution);
			setRuleStats({
				total: snapshotRuleConfidence.reduce(
					(sum, item) => sum + Math.max(Number(item.total_rules || 0), 0),
					0,
				),
				enabled: snapshotRuleConfidence.reduce(
					(sum, item) => sum + Math.max(Number(item.enabled_rules || 0), 0),
					0,
				),
			});
			setScanStatsLoading(false);
		} catch (error) {
			if (requestSeq !== snapshotRequestSeqRef.current) {
				return;
			}
			console.error("加载 dashboard snapshot 失败:", error);
			setProjectScanRunsData([]);
			setProjectVulnsData([]);
			setRuleConfidenceData([]);
			setRuleConfidenceByLanguageData([]);
			setCweDistributionData([]);
			setRuleStats({ total: 0, enabled: 0 });
			setTotalScanDurationMs(0);
			setScanStatsLoading(false);
			throw error;
		}
	}, []);

	const loadDashboardData = useCallback(async (options?: { silent?: boolean }) => {
		try {
			await runWithRefreshMode(async () => {
				const [statsResult, snapshotResult] = await Promise.allSettled([
					api.getProjectStats(),
					loadSnapshotData(),
				]);

				if (statsResult.status === "fulfilled") {
					setStats(statsResult.value);
				} else {
					setStats(DEFAULT_STATS);
				}

				if (snapshotResult.status === "rejected") {
					throw snapshotResult.reason;
				}
			}, { ...options, setLoading });
		} catch (error) {
			console.error("仪表盘数据加载失败:", error);
			toast.error("数据加载失败");
		}
	}, [loadSnapshotData]);

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
							<p className="stat-label">
								{t("dashboard.supportedModelProviders")}
							</p>
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
							<p className="stat-label">
								{t("dashboard.supportedExternalToolCalls")}
							</p>
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
							<p className="stat-label">
								{t("dashboard.supportedVulnerabilityTypes")}
							</p>
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
				projectVulnsData.length === 0 &&
				ruleConfidenceData.length === 0 &&
				ruleConfidenceByLanguageData.length === 0 &&
				cweDistributionData.length === 0 ? (
					<DashboardChartsFallback />
				) : (
						<Suspense fallback={<DashboardChartsFallback />}>
							<DashboardChartsPanels
								ruleConfidenceByLanguageData={ruleConfidenceByLanguageData}
								cweDistributionData={cweDistributionData}
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
