/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, Code, Search } from "lucide-react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	Legend,
	ReferenceLine,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { Link, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, isDemoMode } from "@/shared/config/database";
import type {
	ProjectStats,
	StaticScanOverviewItem,
	StaticScanOverviewResponse,
} from "@/shared/types";
import {
	getOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
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

const OVERVIEW_PAGE_SIZE = 6;
const OVERVIEW_MODULE_ID = "static-scan-overview";
const OVERVIEW_MODULE_HASH = `#${OVERVIEW_MODULE_ID}`;
const OVERVIEW_KEYWORD_MAX_LENGTH = 100;

const DEFAULT_OVERVIEW_DATA: StaticScanOverviewResponse = {
	items: [],
	total: 0,
	page: 1,
	page_size: OVERVIEW_PAGE_SIZE,
	total_pages: 1,
};

type RulesChartScope = "all" | "enabled";

type RuleLanguageChartItem = {
	language: string;
	total: number;
	severityError: number;
	severityWarning: number;
	severityInfo: number;
	confidenceHigh: number;
	confidenceMedium: number;
	confidenceLow: number;
	confidenceUnknown: number;
	severityTotal: number;
	confidenceTotal: number;
};

const formatDateTime = (dateText: string) => {
	const date = new Date(dateText);
	if (Number.isNaN(date.getTime())) return dateText;
	return date.toLocaleString("zh-CN", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hour12: false,
	});
};

const normalizeConfidence = (confidence?: string | null) => {
	const normalized = String(confidence || "").trim().toUpperCase();
	if (!normalized) return "UNKNOWN";
	if (normalized === "MIDIUM" || normalized === "MIDDLE") return "MEDIUM";
	if (normalized === "HIGH") return "HIGH";
	if (normalized === "MEDIUM") return "MEDIUM";
	if (normalized === "LOW") return "LOW";
	return "UNKNOWN";
};

const formatAbsTick = (value: number | string) =>
	Math.abs(Number(value || 0)).toLocaleString();

export default function Dashboard() {
	const location = useLocation();
	const initialOverviewParams = useMemo(() => {
		const params = new URLSearchParams(location.search);
		const rawPage = Number(params.get("overviewPage"));
		const page =
			Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;
		const keyword = String(params.get("overviewKeyword") || "")
			.trim()
			.slice(0, OVERVIEW_KEYWORD_MAX_LENGTH);
		return { page, keyword };
	}, [location.search]);

	const [stats, setStats] = useState<ProjectStats>(DEFAULT_STATS);
	const [loading, setLoading] = useState(true);
	const [ruleStats, setRuleStats] = useState({ total: 0, enabled: 0 });
	const [rules, setRules] = useState<OpengrepRule[]>([]);
	const [rulesChartScope, setRulesChartScope] =
		useState<RulesChartScope>("all");
	const [rulesLanguageKeyword, setRulesLanguageKeyword] = useState("");

	const [overviewData, setOverviewData] =
		useState<StaticScanOverviewResponse>(DEFAULT_OVERVIEW_DATA);
	const [overviewPage, setOverviewPage] = useState(initialOverviewParams.page);
	const [overviewPageSize] = useState(OVERVIEW_PAGE_SIZE);
	const [overviewLoading, setOverviewLoading] = useState(false);
	const [overviewKeyword, setOverviewKeyword] = useState(
		initialOverviewParams.keyword,
	);

	const overviewPageRef = useRef(initialOverviewParams.page);
	const overviewKeywordRef = useRef(initialOverviewParams.keyword);
	const overviewKeywordReadyRef = useRef(false);

	useEffect(() => {
		overviewPageRef.current = overviewPage;
	}, [overviewPage]);

	useEffect(() => {
		overviewKeywordRef.current = overviewKeyword
			.trim()
			.slice(0, OVERVIEW_KEYWORD_MAX_LENGTH);
	}, [overviewKeyword]);

	useEffect(() => {
		if (loading || location.hash !== OVERVIEW_MODULE_HASH) return;
		const timer = window.setTimeout(() => {
			document
				.getElementById(OVERVIEW_MODULE_ID)
				?.scrollIntoView({ behavior: "smooth", block: "start" });
		}, 60);
		return () => window.clearTimeout(timer);
	}, [loading, location.hash]);

	useEffect(() => {
		loadDashboardData();

		const timer = window.setInterval(() => {
			loadDashboardData({ silent: true });
		}, 15000);

		return () => {
			window.clearInterval(timer);
		};
	}, []);

	useEffect(() => {
		if (!overviewKeywordReadyRef.current) {
			overviewKeywordReadyRef.current = true;
			return;
		}
		const timer = window.setTimeout(() => {
			setOverviewPage(1);
			overviewPageRef.current = 1;
			void loadOverviewData(1);
		}, 300);
		return () => window.clearTimeout(timer);
	}, [overviewKeyword]);

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
			const allRules = rulesResult.value;
			const totalRules = allRules.length;
			const enabledRules = allRules.filter((rule) => rule.is_active).length;
			setRuleStats({ total: totalRules, enabled: enabledRules });
			setRules(allRules);
		} else {
			setRuleStats({ total: 0, enabled: 0 });
			setRules([]);
		}
	};

	const loadOverviewData = async (
		page: number,
		options?: { silent?: boolean },
	) => {
		try {
			const result = await runWithRefreshMode(
				() =>
					api.getStaticScanOverview({
						page,
						page_size: overviewPageSize,
						keyword: overviewKeywordRef.current || undefined,
					}),
				{ ...options, setLoading: setOverviewLoading },
			);
			const totalPages = Math.max(1, result.total_pages || 1);
			if (result.total > 0 && page > totalPages) {
				const fallbackPage = totalPages;
				overviewPageRef.current = fallbackPage;
				setOverviewPage(fallbackPage);
				const fallbackResult = await api.getStaticScanOverview({
					page: fallbackPage,
					page_size: overviewPageSize,
					keyword: overviewKeywordRef.current || undefined,
				});
				setOverviewData(fallbackResult);
				return;
			}
			setOverviewData(result);
		} catch (error) {
			console.error("静态扫描概览加载失败:", error);
			setOverviewData((prev) => ({
				...DEFAULT_OVERVIEW_DATA,
				page,
				page_size: prev.page_size || OVERVIEW_PAGE_SIZE,
			}));
			if (!options?.silent) {
				toast.error("静态扫描概览加载失败");
			}
		}
	};

	const loadDashboardData = async (options?: { silent?: boolean }) => {
		try {
			await runWithRefreshMode(loadStatsData, { ...options, setLoading });
			await loadOverviewData(overviewPageRef.current, options);
		} catch (error) {
			console.error("仪表盘数据加载失败:", error);
			toast.error("数据加载失败");
		}
	};

	const filteredRulesByScope = useMemo(() => {
		return rulesChartScope === "enabled"
			? rules.filter((rule) => rule.is_active)
			: rules;
	}, [rules, rulesChartScope]);

	const rulesByLanguageData = useMemo<RuleLanguageChartItem[]>(() => {
		const aggregate = new Map<string, RuleLanguageChartItem>();

		for (const rule of filteredRulesByScope) {
			const language = String(rule.language || "unknown").trim() || "unknown";
			if (!aggregate.has(language)) {
				aggregate.set(language, {
					language,
					total: 0,
					severityError: 0,
					severityWarning: 0,
					severityInfo: 0,
					confidenceHigh: 0,
					confidenceMedium: 0,
					confidenceLow: 0,
					confidenceUnknown: 0,
					severityTotal: 0,
					confidenceTotal: 0,
				});
			}
			const entry = aggregate.get(language);
			if (!entry) continue;

			const severity = String(rule.severity || "").toUpperCase();
			if (severity === "ERROR") {
				entry.severityError += 1;
			} else if (severity === "WARNING") {
				entry.severityWarning += 1;
			} else {
				entry.severityInfo += 1;
			}

			const confidence = normalizeConfidence(rule.confidence);
			if (confidence === "HIGH") {
				entry.confidenceHigh += 1;
			} else if (confidence === "MEDIUM") {
				entry.confidenceMedium += 1;
			} else if (confidence === "LOW") {
				entry.confidenceLow += 1;
			} else {
				entry.confidenceUnknown += 1;
			}

			entry.severityTotal =
				entry.severityError + entry.severityWarning + entry.severityInfo;
			entry.confidenceTotal =
				entry.confidenceHigh +
				entry.confidenceMedium +
				entry.confidenceLow +
				entry.confidenceUnknown;
			entry.total = entry.severityTotal;
		}

		const languageKeyword = rulesLanguageKeyword.trim().toLowerCase();
		return Array.from(aggregate.values())
			.filter((item) =>
				languageKeyword
					? item.language.toLowerCase().includes(languageKeyword)
					: true,
			)
			.map((item) => ({
				...item,
				severityError: -item.severityError,
				severityWarning: -item.severityWarning,
				severityInfo: -item.severityInfo,
			}))
			.sort((a, b) => {
				if (b.total !== a.total) return b.total - a.total;
				return a.language.localeCompare(b.language, "zh-CN");
			});
	}, [filteredRulesByScope, rulesLanguageKeyword]);

	const chartMax = useMemo(() => {
		if (rulesByLanguageData.length === 0) return 1;
		const maxSide = Math.max(
			...rulesByLanguageData.map((item) =>
				Math.max(item.severityTotal, item.confidenceTotal),
			),
		);
		return Math.max(1, maxSide);
	}, [rulesByLanguageData]);

	const rulesChartHeight = useMemo(() => {
		const rowCount = Math.max(1, rulesByLanguageData.length);
		return Math.min(760, Math.max(420, rowCount * 52));
	}, [rulesByLanguageData.length]);

	const totalOverviewPages = Math.max(1, overviewData.total_pages || 1);

	const handleOverviewPageChange = async (nextPage: number) => {
		if (
			nextPage < 1 ||
			nextPage > totalOverviewPages ||
			nextPage === overviewPage
		) {
			return;
		}
		setOverviewPage(nextPage);
		overviewPageRef.current = nextPage;
		await loadOverviewData(nextPage);
	};

	const overviewReturnTo = useMemo(() => {
		const params = new URLSearchParams();
		params.set("overviewPage", String(Math.max(1, overviewPage)));
		const safeKeyword = overviewKeyword
			.trim()
			.slice(0, OVERVIEW_KEYWORD_MAX_LENGTH);
		if (safeKeyword) {
			params.set("overviewKeyword", safeKeyword);
		}
		const query = params.toString();
		return `/dashboard${query ? `?${query}` : ""}${OVERVIEW_MODULE_HASH}`;
	}, [overviewPage, overviewKeyword]);

	const getOverviewDetailRoute = (item: StaticScanOverviewItem) => {
		const params = new URLSearchParams();
		if (item.last_scan_tool === "opengrep") {
			params.set("opengrepTaskId", item.last_scan_task_id);
			if (item.paired_gitleaks_task_id) {
				params.set("gitleaksTaskId", item.paired_gitleaks_task_id);
			}
			params.set("returnTo", overviewReturnTo);
			return `/static-analysis/${item.last_scan_task_id}?${params.toString()}`;
		}

		params.set("tool", "gitleaks");
		params.set("gitleaksTaskId", item.last_scan_task_id);
		params.set("returnTo", overviewReturnTo);
		return `/static-analysis/${item.last_scan_task_id}?${params.toString()}`;
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
								to="/admin"
								className="ml-2 text-primary font-bold hover:underline"
							>
								前往配置 →
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

			<div className="cyber-card p-4 relative z-10">
				<div className="section-header mb-3">
					<AlertTriangle className="w-5 h-5 text-sky-400" />
					<div className="w-full">
						<div className="flex items-center justify-between gap-3 flex-wrap">
							<h3 className="section-title">规则分布蝴蝶图</h3>
							<span className="text-sm text-muted-foreground">
								语言数：{rulesByLanguageData.length}
							</span>
						</div>
						<p className="text-sm text-muted-foreground mt-1">
							按语言展示严重程度（左）与置信度（右）
						</p>
					</div>
				</div>

				<div className="mt-3 flex flex-wrap items-center gap-2">
					<Button
						type="button"
						size="sm"
						variant={rulesChartScope === "all" ? "default" : "outline"}
						className={
							rulesChartScope === "all" ? "cyber-btn-primary h-8" : "cyber-btn-outline h-8"
						}
						onClick={() => setRulesChartScope("all")}
					>
						全部规则
					</Button>
					<Button
						type="button"
						size="sm"
						variant={rulesChartScope === "enabled" ? "default" : "outline"}
						className={
							rulesChartScope === "enabled"
								? "cyber-btn-primary h-8"
								: "cyber-btn-outline h-8"
						}
						onClick={() => setRulesChartScope("enabled")}
					>
						仅启用规则
					</Button>
					<div className="relative ml-auto w-full sm:w-[280px]">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
						<Input
							value={rulesLanguageKeyword}
							onChange={(e) => setRulesLanguageKeyword(e.target.value)}
							placeholder="搜索语言..."
							className="h-8 pl-9 font-mono text-xs"
						/>
					</div>
				</div>

				<div
					className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
					style={{ height: rulesChartHeight }}
				>
					{rulesByLanguageData.length === 0 ? (
						<div className="h-full flex items-center justify-center text-base text-muted-foreground">
							暂无可展示的规则分布数据
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
									domain={[-chartMax, chartMax]}
									tickFormatter={formatAbsTick}
									tick={{ fontSize: 13 }}
								/>
								<YAxis
									type="category"
									dataKey="language"
									width={96}
									tick={{ fontSize: 13 }}
								/>
								<ReferenceLine x={0} stroke="hsl(var(--border))" />
								<Tooltip
									formatter={(value: number | string, name: string) => [
										Math.abs(Number(value || 0)).toLocaleString(),
										name,
									]}
									contentStyle={{ fontSize: 13 }}
								/>
								<Legend wrapperStyle={{ fontSize: 13 }} />
								<Bar
									dataKey="severityError"
									stackId="severity"
									fill="#f43f5e"
									name="严重(ERROR)"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="severityWarning"
									stackId="severity"
									fill="#f59e0b"
									name="提示(WARNING)"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="severityInfo"
									stackId="severity"
									fill="#0ea5e9"
									name="信息(INFO)"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="confidenceHigh"
									stackId="confidence"
									fill="#22c55e"
									name="高置信度"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="confidenceMedium"
									stackId="confidence"
									fill="#facc15"
									name="中置信度"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="confidenceLow"
									stackId="confidence"
									fill="#60a5fa"
									name="低置信度"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
								<Bar
									dataKey="confidenceUnknown"
									stackId="confidence"
									fill="#94a3b8"
									name="未设置置信度"
									radius={[2, 2, 2, 2]}
									minPointSize={6}
								/>
							</BarChart>
						</ResponsiveContainer>
					)}
				</div>
			</div>

			<div id={OVERVIEW_MODULE_ID} className="cyber-card p-4 relative z-10">
				<div className="section-header mb-3">
					<Activity className="w-5 h-5 text-amber-400" />
					<div className="w-full">
						<div className="flex items-center justify-between gap-3 flex-wrap">
							<h3 className="section-title">项目静态扫描概览</h3>
							<span className="text-sm text-muted-foreground">
								共 {overviewData.total} 个项目
							</span>
						</div>
						<p className="text-sm text-muted-foreground mt-1">
							项目最近一次成功静态扫描统计（gitleaks并入提示）
						</p>
					</div>
				</div>

				<div className="mt-3">
					<div className="relative w-full sm:w-[320px]">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
						<Input
							value={overviewKeyword}
							onChange={(e) =>
								setOverviewKeyword(
									e.target.value.slice(0, OVERVIEW_KEYWORD_MAX_LENGTH),
								)
							}
							placeholder="搜索项目名称..."
							className="h-10 pl-9 font-mono text-base"
						/>
					</div>
				</div>

				<div className="mt-4 space-y-2">
					{overviewLoading && overviewData.items.length === 0 ? (
						<div className="py-6 text-center text-base text-muted-foreground">
							加载扫描概览中...
						</div>
					) : overviewData.items.length === 0 ? (
						<div className="py-6 text-center text-base text-muted-foreground">
							暂无成功静态扫描记录
						</div>
					) : (
						overviewData.items.map((item) => (
							<Link
								key={`${item.project_id}-${item.last_scan_task_id}`}
								to={getOverviewDetailRoute(item)}
								className="block p-3 rounded-lg border transition-all bg-muted/20 border-border hover:border-primary/30"
							>
								<div className="flex flex-wrap items-center gap-x-3 gap-y-2">
									<p className="text-lg font-semibold text-foreground">
										{item.project_name}
									</p>
									<span className="text-base text-muted-foreground/80">
										最近成功扫描：{formatDateTime(item.last_scan_at)}
									</span>
									<span className="text-base text-muted-foreground ml-auto">
										总计：{item.total_findings}
									</span>
								</div>
								<div className="mt-2 flex items-center flex-wrap gap-4 text-base">
									<span className="text-rose-400 font-semibold">
										严重：{item.severe_count}
									</span>
									<span className="text-amber-400 font-semibold">
										提示：{item.hint_count}
									</span>
									<span className="text-sky-400 font-semibold">
										信息：{item.info_count}
									</span>
								</div>
							</Link>
						))
					)}
				</div>

				{overviewData.total > 0 && (
					<div className="mt-4 flex items-center justify-between">
						<div className="text-sm text-muted-foreground">
							第 {overviewPage} / {totalOverviewPages} 页（每页 {overviewPageSize} 条）
						</div>
						<div className="flex items-center gap-2">
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-outline h-8 px-3"
								onClick={() => {
									void handleOverviewPageChange(overviewPage - 1);
								}}
								disabled={overviewPage <= 1 || overviewLoading}
							>
								上一页
							</Button>
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-outline h-8 px-3"
								onClick={() => {
									void handleOverviewPageChange(overviewPage + 1);
								}}
								disabled={overviewPage >= totalOverviewPages || overviewLoading}
							>
								下一页
							</Button>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
