import { useEffect, useMemo, useState } from "react";
import {
	Activity,
	BarChart3,
	Boxes,
	Bug,
	ChevronLeft,
	ChevronRight,
	Cpu,
	ListOrdered,
} from "lucide-react";
import {
	Area,
	AreaChart,
	Bar,
	BarChart,
	CartesianGrid,
	LabelList,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { getEstimatedTaskProgressPercent } from "@/features/tasks/services/taskProgress";
import type {
	DashboardDailyActivityItem,
	DashboardEngineBreakdownItem,
	DashboardLanguageLocItem,
	DashboardLanguageRiskItem,
	DashboardProjectRiskDistributionItem,
	DashboardRecentTaskItem,
	DashboardSnapshotResponse,
	DashboardStaticEngineRuleTotalItem,
	DashboardVerifiedVulnerabilityTypeItem,
} from "@/shared/types";

type RangeDays = 7 | 14 | 30;

type DashboardViewId =
	| "trend"
	| "project-risk"
	| "language-risk"
	| "vulnerability-types"
	| "scan-engines"
	| "static-engine-rules"
	| "language-lines";

type Tone = "critical" | "high" | "medium" | "low" | "neutral";

interface DashboardCommandCenterProps {
	snapshot: DashboardSnapshotResponse;
	rangeDays: RangeDays;
	onRangeDaysChange: (value: RangeDays) => void;
}

interface HorizontalRow {
	label: string;
	meta: string;
	total: number;
	critical: number;
	high: number;
	medium: number;
	low: number;
	tone: Tone;
}

interface DashboardViewMeta {
	id: DashboardViewId;
	label: string;
	description: string;
	yAxisLabel: string;
}

const VIEW_ITEMS: DashboardViewMeta[] = [
	{
		id: "trend",
		label: "漏洞态势统计图",
		description: "查看近一段时间新增风险与 AI 验证漏洞的波动。",
		yAxisLabel: "漏洞数量",
	},
	{
		id: "project-risk",
		label: "项目风险统计图",
		description: "按项目聚合已发现漏洞，并以严重度堆叠展示 Top10。",
		yAxisLabel: "项目名称",
	},
	{
		id: "language-risk",
		label: "语言风险统计图",
		description: "按语言统计当前累计漏洞数量，数量从上到下递减。",
		yAxisLabel: "语言类型",
	},
	{
		id: "vulnerability-types",
		label: "漏洞类型统计图",
		description: "展示智能扫描与混合扫描中已验证漏洞类型 Top10。",
		yAxisLabel: "漏洞类型标号",
	},
	{
		id: "scan-engines",
		label: "扫描引擎统计图",
		description: "展示各扫描引擎发现漏洞数量，覆盖静态扫描与智能扫描。",
		yAxisLabel: "引擎名称",
	},
	{
		id: "static-engine-rules",
		label: "静态扫描引擎规则统计图",
		description: "展示各静态扫描引擎当前规则数量。",
		yAxisLabel: "引擎名称",
	},
	{
		id: "language-lines",
		label: "语言代码行数统计图",
		description: "展示当前项目涉及语言代码行数 Top10。",
		yAxisLabel: "语言类型",
	},
];

const TONE_STYLES: Record<
	Tone,
	{ bar: string; chip: string; text: string; fill: string }
> = {
	critical: {
		bar: "bg-rose-500/80",
		chip: "border-rose-500/30 bg-rose-500/10 text-foreground",
		text: "text-rose-700 dark:text-rose-300",
		fill: "#e11d48",
	},
	high: {
		bar: "bg-orange-500/80",
		chip: "border-orange-500/30 bg-orange-500/10 text-foreground",
		text: "text-orange-700 dark:text-orange-300",
		fill: "#fb923c",
	},
	medium: {
		bar: "bg-amber-500/80",
		chip: "border-amber-500/30 bg-amber-500/10 text-foreground",
		text: "text-amber-700 dark:text-amber-300",
		fill: "#fbbf24",
	},
	low: {
		bar: "bg-sky-500/80",
		chip: "border-sky-500/30 bg-sky-500/10 text-foreground",
		text: "text-sky-700 dark:text-sky-300",
		fill: "#0ea5e9",
	},
	neutral: {
		bar: "bg-muted-foreground/60",
		chip: "border-border bg-muted/60 text-foreground",
		text: "text-muted-foreground",
		fill: "#94a3b8",
	},
};

export const HORIZONTAL_STATS_AXIS_FONT_SIZE = 16;
export const HORIZONTAL_STATS_LABEL_FONT_SIZE = 16;
export const HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH = 84;
export const HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH = 120;
export const HORIZONTAL_STATS_BAR_SIZE = 12;
export const HORIZONTAL_STATS_ROW_HEIGHT = 46;
export const HORIZONTAL_STATS_BAR_CATEGORY_GAP = 4;
export const HORIZONTAL_STATS_CHART_MARGIN = {
	top: 8,
	right: 24,
	left: 12,
	bottom: 8,
} as const;
export const HORIZONTAL_STATS_META_ROW_CLASSNAME =
	"mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between";
export const HORIZONTAL_STATS_META_LEGEND_CLASSNAME =
	"flex flex-wrap justify-start gap-2 sm:justify-end";
export const TOP_STATS_GRID_CLASSNAME = "grid grid-cols-2 gap-3 xl:grid-cols-5";
export const DASHBOARD_RECENT_TASKS_PAGE_SIZE = 4;
const DASHBOARD_PANEL_CLASSNAME =
	"rounded-sm border border-border bg-card text-card-foreground shadow-sm";
const DASHBOARD_PANEL_TITLE_CLASSNAME =
	"text-xl font-semibold uppercase tracking-[0.12em] text-foreground";
const DASHBOARD_PANEL_DESCRIPTION_CLASSNAME =
	"max-w-2xl text-sm leading-6 text-muted-foreground";
const DASHBOARD_META_LABEL_CLASSNAME =
	"text-left text-xs uppercase tracking-[0.18em] text-muted-foreground";
const DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME =
	"text-base uppercase tracking-[0.18em] text-muted-foreground";
const DASHBOARD_TOOLTIP_STYLE = {
	backgroundColor: "hsl(var(--card))",
	borderColor: "hsl(var(--border))",
	borderRadius: "4px",
	color: "hsl(var(--foreground))",
};

function estimateAxisLabelUnits(label: string) {
	return Array.from(label).reduce((total, char) => {
		if (/\p{Script=Han}/u.test(char)) {
			return total + 1;
		}
		if (/[A-Z0-9]/.test(char)) {
			return total + 0.72;
		}
		if (/[a-z]/.test(char)) {
			return total + 0.58;
		}
		return total + 0.42;
	}, 0);
}

export function estimateHorizontalStatsYAxisWidth(rows: HorizontalRow[]) {
	const widestLabelUnits = rows.reduce(
		(maxWidth, row) => Math.max(maxWidth, estimateAxisLabelUnits(row.label)),
		0,
	);
	const estimatedWidth = Math.ceil(
		widestLabelUnits * HORIZONTAL_STATS_AXIS_FONT_SIZE + 18,
	);

	return Math.min(
		Math.max(estimatedWidth, HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH),
		HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH,
	);
}

function buildFiveStepTicks(rows: HorizontalRow[]) {
	const upperBound = Math.max(
		5,
		Math.ceil(
			rows.reduce(
				(maxValue, row) => Math.max(maxValue, Number(row.total || 0)),
				0,
			) / 5,
		) * 5,
	);

	const ticks: number[] = [];
	for (let value = 0; value <= upperBound; value += 5) {
		ticks.push(value);
	}
	return ticks;
}

type HorizontalStatsXAxisProps = {
	minTickGap: number;
	tickCount: number | undefined;
	allowDecimals: boolean;
	domain: [number, "dataMax" | "auto"];
	ticks: number[] | undefined;
};

export function getHorizontalStatsXAxisProps(
	viewId: DashboardViewId,
	rows: HorizontalRow[] = [],
): HorizontalStatsXAxisProps {
	if (viewId === "vulnerability-types") {
		return {
			minTickGap: 0,
			tickCount: 6,
			allowDecimals: false,
			domain: [0, "dataMax"],
			ticks: rows.length > 0 ? buildFiveStepTicks(rows) : undefined,
		};
	}

	return {
		minTickGap: 0,
		tickCount: undefined,
		allowDecimals: false,
		domain: [0, "auto"],
		ticks: undefined,
	};
}

function formatNumber(value: number | null | undefined) {
	return Math.max(Number(value || 0), 0).toLocaleString("zh-CN");
}

function truncateDecimal(value: number, digits: number) {
	if (!Number.isFinite(value) || value <= 0) return 0;
	const factor = 10 ** digits;
	return Math.floor(value * factor) / factor;
}

function trimTrailingZeroes(value: number, digits: number) {
	return value.toFixed(digits).replace(/\.?0+$/, "");
}

export function formatTokenValue(value: number | null | undefined) {
	const normalized = Math.max(Number(value || 0), 0);
	const unit = normalized >= 1_000_000 ? "M" : "K";
	const divisor = unit === "M" ? 1_000_000 : 1_000;
	const truncated = truncateDecimal(normalized / divisor, 3);
	return `${trimTrailingZeroes(truncated, 3)}${unit}`;
}

function normalizeViewTone(value: number): Tone {
	if (value >= 20) return "critical";
	if (value >= 12) return "high";
	if (value >= 6) return "medium";
	if (value > 0) return "low";
	return "neutral";
}

function formatTrendDate(value: string) {
	if (!value) return "-";
	if (value.includes("-") && value.length <= 10) return value.slice(5);
	return value;
}

function formatCreatedAt(value: string) {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return value || "-";
	}
	const month = `${date.getMonth() + 1}`.padStart(2, "0");
	const day = `${date.getDate()}`.padStart(2, "0");
	const hour = `${date.getHours()}`.padStart(2, "0");
	const minute = `${date.getMinutes()}`.padStart(2, "0");
	return `${month}-${day} ${hour}:${minute}`;
}

export function formatCumulativeDuration(
	durationMs: number | null | undefined,
) {
	const totalSeconds = Math.max(Math.floor(Number(durationMs || 0) / 1000), 0);
	if (totalSeconds <= 0) return "0秒";

	const days = Math.floor(totalSeconds / 86400);
	const hours = Math.floor((totalSeconds % 86400) / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;

	if (days > 0) return `${days}天 ${hours}时 ${minutes}分 ${seconds}秒`;
	if (hours > 0) return `${hours}时 ${minutes}分 ${seconds}秒`;
	if (minutes > 0) return `${minutes}分 ${seconds}秒`;
	return `${seconds}秒`;
}

function totalFindingsForTrend(item: DashboardDailyActivityItem) {
	return (
		Number(item.agent_findings || 0) +
		Number(item.opengrep_findings || 0) +
		Number(item.gitleaks_findings || 0) +
		Number(item.bandit_findings || 0) +
		Number(item.phpstan_findings || 0) +
		Number(item.yasa_findings || 0)
	);
}

function verifiedFindingsForTrend(item: DashboardDailyActivityItem) {
	return Number(item.agent_findings || 0);
}

function buildTrendRows(items: DashboardDailyActivityItem[]) {
	return items.map((item) => ({
		date: formatTrendDate(item.date),
		total: Math.max(totalFindingsForTrend(item), 0),
		verified: Math.max(verifiedFindingsForTrend(item), 0),
	}));
}

function buildProjectRiskRows(
	items: DashboardProjectRiskDistributionItem[],
): HorizontalRow[] {
	return items.slice(0, 10).map((item) => ({
		label: item.project_name,
		meta: `漏洞总数 ${formatNumber(item.total_findings)}`,
		total: item.total_findings,
		critical: item.critical_count,
		high: item.high_count,
		medium: item.medium_count,
		low: item.low_count,
		tone: normalizeViewTone(item.total_findings),
	}));
}

function buildLanguageRiskRows(
	items: DashboardLanguageRiskItem[],
): HorizontalRow[] {
	return items.slice(0, 10).map((item) => ({
		label: item.language,
		meta: `${formatNumber(item.project_count)} 个项目`,
		total: item.effective_findings,
		critical: 0,
		high: 0,
		medium: 0,
		low: 0,
		tone: normalizeViewTone(item.effective_findings),
	}));
}

function buildVulnerabilityTypeRows(
	items: DashboardVerifiedVulnerabilityTypeItem[],
): HorizontalRow[] {
	return items.slice(0, 10).map((item) => ({
		label: item.type_code,
		meta: item.type_name,
		total: item.verified_count,
		critical: 0,
		high: 0,
		medium: 0,
		low: 0,
		tone: normalizeViewTone(item.verified_count),
	}));
}

function buildEngineRows(
	items: DashboardEngineBreakdownItem[],
): HorizontalRow[] {
	const labelMap: Record<string, string> = {
		llm: "llm",
		opengrep: "opengrep",
		gitleaks: "gitleaks",
		bandit: "bandit",
		phpstan: "phpstan",
		yasa: "yasa",
	};
	const metaMap: Record<string, string> = {
		llm: "智能扫描 + 混合扫描",
		opengrep: "静态扫描",
		gitleaks: "静态扫描",
		bandit: "静态扫描",
		phpstan: "静态扫描",
		yasa: "静态扫描",
	};
	return items
		.slice()
		.sort((a, b) => b.effective_findings - a.effective_findings)
		.map((item) => ({
			label: labelMap[item.engine] ?? item.engine,
			meta: metaMap[item.engine] ?? "扫描引擎",
			total: item.effective_findings,
			critical: 0,
			high: 0,
			medium: 0,
			low: 0,
			tone: normalizeViewTone(item.effective_findings),
		}));
}

function buildStaticRuleRows(
	items: DashboardStaticEngineRuleTotalItem[],
): HorizontalRow[] {
	return items
		.slice()
		.sort((a, b) => b.total_rules - a.total_rules)
		.map((item) => ({
			label: item.engine,
			meta: `规则总数 ${formatNumber(item.total_rules)}`,
			total: item.total_rules,
			critical: 0,
			high: 0,
			medium: 0,
			low: 0,
			tone: normalizeViewTone(item.total_rules),
		}));
}

function buildLanguageLineRows(
	items: DashboardLanguageLocItem[],
): HorizontalRow[] {
	return items.slice(0, 10).map((item) => ({
		label: item.language,
		meta: `代码行 ${formatNumber(item.loc_number)}`,
		total: item.loc_number,
		critical: 0,
		high: 0,
		medium: 0,
		low: 0,
		tone: normalizeViewTone(item.loc_number),
	}));
}

function buildRowsForView(
	view: DashboardViewId,
	snapshot: DashboardSnapshotResponse,
): HorizontalRow[] {
	if (view === "project-risk") {
		return buildProjectRiskRows(snapshot.project_risk_distribution);
	}
	if (view === "language-risk") {
		return buildLanguageRiskRows(snapshot.language_risk);
	}
	if (view === "vulnerability-types") {
		return buildVulnerabilityTypeRows(snapshot.verified_vulnerability_types);
	}
	if (view === "scan-engines") {
		return buildEngineRows(snapshot.engine_breakdown);
	}
	if (view === "static-engine-rules") {
		return buildStaticRuleRows(snapshot.static_engine_rule_totals);
	}
	if (view === "language-lines") {
		return buildLanguageLineRows(snapshot.language_loc_distribution);
	}
	return [];
}

function buildTaskStatusRows(snapshot: DashboardSnapshotResponse) {
	return [
		{
			label: "已完成",
			value: snapshot.task_status_breakdown.completed,
			tone: "low" as Tone,
		},
		{
			label: "运行中",
			value: snapshot.task_status_breakdown.running,
			tone: "neutral" as Tone,
		},
		{
			label: "失败",
			value: snapshot.task_status_breakdown.failed,
			tone: "critical" as Tone,
		},
		{
			label: "已中断",
			value: snapshot.task_status_breakdown.interrupted,
			tone: "high" as Tone,
		},
		{
			label: "已取消",
			value: snapshot.task_status_breakdown.cancelled,
			tone: "medium" as Tone,
		},
	].filter((item) => item.value > 0);
}

export function paginateRecentTasks(
	tasks: DashboardRecentTaskItem[],
	requestedPage: number,
) {
	const totalCount = tasks.length;
	const totalPages = Math.max(
		1,
		Math.ceil(totalCount / DASHBOARD_RECENT_TASKS_PAGE_SIZE),
	);
	const currentPage = Math.min(
		Math.max(Math.floor(Number(requestedPage) || 1), 1),
		totalPages,
	);
	const startIndex = (currentPage - 1) * DASHBOARD_RECENT_TASKS_PAGE_SIZE;

	return {
		items: tasks.slice(
			startIndex,
			startIndex + DASHBOARD_RECENT_TASKS_PAGE_SIZE,
		),
		currentPage,
		totalPages,
		totalCount,
	};
}

function PreviewHeader({ snapshot }: { snapshot: DashboardSnapshotResponse }) {
	const totalTasks =
		snapshot.task_status_breakdown.completed +
		snapshot.task_status_breakdown.running +
		snapshot.task_status_breakdown.failed +
		snapshot.task_status_breakdown.interrupted +
		snapshot.task_status_breakdown.cancelled;
	const cards = [
		{ label: "项目总数", value: formatNumber(snapshot.summary.total_projects) },
		{
			label: "累计发现漏洞总数",
			value: formatNumber(snapshot.summary.current_effective_findings),
		},
		{
			label: "AI验证漏洞总数",
			value: formatNumber(snapshot.summary.current_verified_findings),
		},
		{ label: "累计执行扫描", value: formatNumber(totalTasks) },
		{
			label: "累计消耗词元",
			value: formatTokenValue(snapshot.summary.total_model_tokens),
		},
	];

	return (
		<div className={TOP_STATS_GRID_CLASSNAME}>
			{cards.map((item) => (
				<div
					key={item.label}
					className={`${DASHBOARD_PANEL_CLASSNAME} px-4 py-4`}
				>
					<div className={DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME}>
						{item.label}
					</div>
					<div className="mt-2 text-2xl font-semibold tabular-nums text-foreground">
						{item.value}
					</div>
				</div>
			))}
		</div>
	);
}

function ViewSidebar({
	activeView,
	onChange,
}: {
	activeView: DashboardViewId;
	onChange: (view: DashboardViewId) => void;
}) {
	return (
		<nav
			aria-label="漏洞态势视图切换"
			className={`${DASHBOARD_PANEL_CLASSNAME} p-3`}
		>
			<div className="space-y-2">
				{VIEW_ITEMS.map((view) => {
					const active = view.id === activeView;
					return (
						<button
							key={view.id}
							type="button"
							aria-pressed={active}
							onClick={() => onChange(view.id)}
							className={`group flex w-full items-start gap-3 rounded-sm border px-3 py-3 text-left transition duration-200 ${active
								? "border-primary/30 bg-muted/70 text-foreground shadow-sm"
								: "border-transparent bg-background/60 text-muted-foreground hover:border-border hover:bg-muted/40"
								}`}
						>
							<div
								className={`mt-0.5 rounded-sm p-2 ${active
									? "bg-primary/10 text-primary"
									: "bg-muted/70 text-muted-foreground"
									}`}
							>
								{view.id === "trend" ? (
									<Activity className="h-4 w-4" />
								) : view.id === "project-risk" ? (
									<ListOrdered className="h-4 w-4" />
								) : view.id === "language-risk" ? (
									<Boxes className="h-4 w-4" />
								) : view.id === "scan-engines" ? (
									<Cpu className="h-4 w-4" />
								) : view.id === "static-engine-rules" ||
									view.id === "language-lines" ? (
									<BarChart3 className="h-4 w-4" />
								) : (
									<Bug className="h-4 w-4" />
								)}
							</div>
							<div className="min-w-0 flex-1">
								<div className="flex items-center justify-between gap-3">
									<span className="font-bold tracking-[0.02em]">
										{view.label}
									</span>
									<ChevronRight
										className={`h-4 w-4 transition ${active
											? "translate-x-0 text-primary"
											: "-translate-x-1 text-muted-foreground/70 group-hover:translate-x-0"
											}`}
									/>
								</div>
								<p className="mt-1 text-xs leading-5 text-muted-foreground">
									{view.description}
								</p>
							</div>
						</button>
					);
				})}
			</div>
		</nav>
	);
}

function TaskStatusPanel({
	snapshot,
}: {
	snapshot: DashboardSnapshotResponse;
}) {
	const statusRows = buildTaskStatusRows(snapshot);
	const total = statusRows.reduce((sum, item) => sum + item.value, 0);
	const [recentTasksPage, setRecentTasksPage] = useState(1);
	const recentTasksPagination = useMemo(
		() => paginateRecentTasks(snapshot.recent_tasks, recentTasksPage),
		[snapshot.recent_tasks, recentTasksPage],
	);

	useEffect(() => {
		setRecentTasksPage(1);
	}, [snapshot.recent_tasks]);

	return (
		<section
			data-panel="status"
			className={`${DASHBOARD_PANEL_CLASSNAME} p-5 xl:flex xl:min-h-0 xl:flex-col`}
		>
			<div className="flex items-start justify-between gap-4">
				<div>
					<h2 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>任务状态</h2>
				</div>
			</div>
			<div className="mt-3 space-y-3">
				{statusRows.length === 0 ? (
					<p className="text-sm text-muted-foreground">暂无任务状态数据</p>
				) : (
					statusRows.map((item) => {
						const tone = TONE_STYLES[item.tone];
						const width =
							total > 0 ? Math.max((item.value / total) * 100, 8) : 0;
						return (
							<div key={item.label} className="space-y-2">
								<div className="flex items-center justify-between gap-3 text-sm">
									<span className="text-foreground">{item.label}</span>
									<span className={`font-medium ${tone.text}`}>
										{formatNumber(item.value)}
									</span>
								</div>
								<div className="h-3 rounded-full bg-muted/70">
									<div
										className={`h-3 rounded-full ${tone.bar}`}
										style={{ width: `${width}%` }}
									/>
								</div>
							</div>
						);
					})
				)}
			</div>
			<div className="mt-8 flex items-start justify-between gap-6">
				<div>
					<h2 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>最近任务</h2>
				</div>
			</div>
			<div className="mt-1 border-t border-border/70 pt-5 xl:flex xl:min-h-0 xl:flex-1 xl:flex-col">
				<div className="space-y-3">
					{recentTasksPagination.items.length === 0 ? (
						<p className="rounded-sm border border-dashed border-border bg-muted/20 px-4 py-5 text-sm text-muted-foreground">
							暂无最近任务
						</p>
					) : (
						recentTasksPagination.items.map((task) => (
							<RecentTaskCard key={task.task_id} task={task} />
						))
					)}
				</div>
				{recentTasksPagination.totalPages > 1 ? (
					<div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/70 pt-4">
						<Button
							type="button"
							variant="outline"
							size="sm"
							className="cyber-btn-outline h-8 px-3"
							onClick={() =>
								setRecentTasksPage((page) => Math.max(page - 1, 1))
							}
							disabled={recentTasksPagination.currentPage <= 1}
						>
							<ChevronLeft className="h-4 w-4" />
							上一页
						</Button>
						<Button
							type="button"
							variant="outline"
							size="sm"
							className="cyber-btn-outline h-8 px-3"
							onClick={() =>
								setRecentTasksPage((page) =>
									Math.min(page + 1, recentTasksPagination.totalPages),
								)
							}
							disabled={
								recentTasksPagination.currentPage >=
								recentTasksPagination.totalPages
							}
						>
							下一页
							<ChevronRight className="h-4 w-4" />
						</Button>
					</div>
				) : null}
			</div>
		</section>
	);
}

function RecentTaskCard({ task }: { task: DashboardRecentTaskItem }) {
	const progress = getEstimatedTaskProgressPercent({
		status: task.status,
		createdAt: task.created_at,
	});
	return (
		<div className={`${DASHBOARD_PANEL_CLASSNAME} px-4 py-4`}>
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<p className="truncate text-xs text-muted-foreground">
						{task.title}
					</p>
					{/* <p className="mt-1 text-xs text-muted-foreground">
						{task.task_type} · {formatCreatedAt(task.created_at)}
					</p> */}
				</div>
				<a
					href={task.detail_path || "/tasks/static"}
					className="cyber-btn-outline inline-flex h-8 shrink-0 items-center px-3 text-xs"
				>
					查看详情
				</a>
			</div>
			<div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
				{/* <span>{task.task_type}</span> */}
				<span>执行进度 {progress}%</span>
			</div>
			<div className="mt-2 h-2 rounded-full bg-muted/70">
				<div
					className="h-2 rounded-full bg-primary/80"
					style={{ width: `${progress}%` }}
				/>
			</div>
		</div>
	);
}

function TrendPanel({ snapshot }: { snapshot: DashboardSnapshotResponse }) {
	const trendRows = useMemo(
		() => buildTrendRows(snapshot.daily_activity),
		[snapshot.daily_activity],
	);
	const peakItem = trendRows.reduce(
		(result, item) => (item.total > result.total ? item : result),
		{ date: "-", total: 0, verified: 0 },
	);
	const llmTotal = snapshot.engine_breakdown.find(
		(item) => item.engine === "llm",
	);

	if (trendRows.length === 0) {
		return (
			<div data-panel="trend" className="space-y-4">
				<h3 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>漏洞态势统计图</h3>
				<p className="text-sm text-muted-foreground">暂无趋势数据</p>
			</div>
		);
	}

	return (
		<div data-panel="trend" className="space-y-5">
			<div className="flex flex-col gap-2">
				<h3 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>漏洞态势统计图</h3>
				<p className={DASHBOARD_PANEL_DESCRIPTION_CLASSNAME}>
					查看近一段时间新增风险与 AI 已验证漏洞的波动趋势。
				</p>
			</div>
			<div className="grid gap-3 sm:grid-cols-3">
				{[
					{
						label: "AI发现漏洞",
						value: formatNumber(llmTotal?.effective_findings ?? 0),
						meta: "",
					},
					{
						label: "AI累计已验证漏洞",
						value: formatNumber(snapshot.summary.current_verified_findings),
						meta: "",
					},

				].map((item) => (
					<div
						key={item.label}
						className={`${DASHBOARD_PANEL_CLASSNAME} px-4 py-3`}
					>
						<p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
							{item.label}
						</p>
						<p className="mt-2 text-xl font-semibold text-foreground">
							{item.value}
						</p>
						<p className="mt-1 text-xs text-muted-foreground">{item.meta}</p>
					</div>
				))}
			</div>
			<div className="h-[320px] w-full rounded-sm border border-border bg-background/70 p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className={DASHBOARD_META_LABEL_CLASSNAME}>
						横坐标：日期
						<br />
						纵坐标：漏洞数量
					</div>
					<div className={HORIZONTAL_STATS_META_LEGEND_CLASSNAME}>
						<span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.low.chip}`}
						>
							新增风险
						</span>
						<span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.high.chip}`}
						>
							已验证
						</span>
					</div>
				</div>
				<div className="h-[calc(100%-52px)] w-full">
					<ResponsiveContainer width="100%" height="100%">
						<AreaChart
							data={trendRows}
							margin={{ top: 12, right: 12, left: -10, bottom: 0 }}
						>
							<CartesianGrid
								stroke="rgba(148,163,184,0.18)"
								strokeDasharray="4 4"
							/>
							<XAxis
								dataKey="date"
								tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
								axisLine={false}
								tickLine={false}
							/>
							<YAxis
								tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
								axisLine={false}
								tickLine={false}
							/>
							<Tooltip contentStyle={DASHBOARD_TOOLTIP_STYLE} />
							<Area
								type="monotone"
								dataKey="total"
								name="新增风险"
								stroke={TONE_STYLES.low.fill}
								fill={TONE_STYLES.low.fill}
								fillOpacity={0.12}
								strokeWidth={2.4}
							/>
							<Area
								type="monotone"
								dataKey="verified"
								name="已验证"
								stroke={TONE_STYLES.high.fill}
								fill={TONE_STYLES.high.fill}
								fillOpacity={0.12}
								strokeWidth={2.2}
							/>
						</AreaChart>
					</ResponsiveContainer>
				</div>
			</div>
		</div>
	);
}

function HorizontalStatsChart({
	title,
	description,
	rows,
	viewId,
	yAxisLabel,
	stacked = false,
}: {
	title: string;
	description: string;
	rows: HorizontalRow[];
	viewId: DashboardViewId;
	yAxisLabel: string;
	stacked?: boolean;
}) {
	if (rows.length === 0) {
		return (
			<div className="space-y-4">
				<h3 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>{title}</h3>
				<p className="text-sm text-muted-foreground">暂无统计数据</p>
			</div>
		);
	}

	const chartHeight = Math.max(rows.length * HORIZONTAL_STATS_ROW_HEIGHT, 220);
	const yAxisWidth = estimateHorizontalStatsYAxisWidth(rows);
	const xAxisProps = getHorizontalStatsXAxisProps(viewId, rows);
	const primaryTone = rows[0]?.tone ?? "low";
	const legendItems = stacked
		? [
			{ label: "严重", tone: "critical" as Tone },
			{ label: "高危", tone: "high" as Tone },
			{ label: "中危", tone: "medium" as Tone },
			{ label: "低危", tone: "low" as Tone },
		]
		: [{ label: "总数", tone: primaryTone }];

	return (
		<div className="space-y-5">
			<div className="flex flex-col gap-2">
				<h3 className={DASHBOARD_PANEL_TITLE_CLASSNAME}>{title}</h3>
				<p className={DASHBOARD_PANEL_DESCRIPTION_CLASSNAME}>{description}</p>
			</div>
			<div className="rounded-sm border border-border bg-background/70 p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className={DASHBOARD_META_LABEL_CLASSNAME}>
						横坐标：数量
						<br />
						纵坐标：{yAxisLabel}
					</div>
					<div className={HORIZONTAL_STATS_META_LEGEND_CLASSNAME}>
						{legendItems.map((item) => (
							<span
								key={item.label}
								className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES[item.tone].chip}`}
							>
								{item.label}
							</span>
						))}
					</div>
				</div>
				<div style={{ height: chartHeight }} className="w-full">
					<ResponsiveContainer width="100%" height="100%">
						<BarChart
							data={rows}
							layout="vertical"
							margin={HORIZONTAL_STATS_CHART_MARGIN}
							barCategoryGap={HORIZONTAL_STATS_BAR_CATEGORY_GAP}
						>
							<CartesianGrid
								stroke="rgba(148,163,184,0.18)"
								strokeDasharray="4 4"
								horizontal={false}
							/>
							<XAxis
								type="number"
								tick={{
									fill: "hsl(var(--muted-foreground))",
									fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE,
								}}
								axisLine={false}
								tickLine={false}
								minTickGap={xAxisProps.minTickGap}
								tickCount={xAxisProps.tickCount}
								allowDecimals={xAxisProps.allowDecimals}
								domain={xAxisProps.domain}
								ticks={xAxisProps.ticks}
							/>
							<YAxis
								type="category"
								dataKey="label"
								width={yAxisWidth}
								tick={{
									fill: "hsl(var(--foreground))",
									fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE,
								}}
								axisLine={false}
								tickLine={false}
							/>
							<Tooltip
								cursor={{ fill: "rgba(148, 163, 184, 0.12)" }}
								contentStyle={DASHBOARD_TOOLTIP_STYLE}
								formatter={(value: number) => [
									formatNumber(Number(value)),
									"数量",
								]}
								labelFormatter={(
									label: string,
									payload: Array<{ payload?: HorizontalRow }>,
								) =>
									`${label}${payload[0]?.payload?.meta ? ` · ${payload[0].payload.meta}` : ""}`
								}
							/>
							{stacked ? (
								<>
									<Bar
										dataKey="critical"
										stackId="risk"
										name="严重"
										fill={TONE_STYLES.critical.fill}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="high"
										stackId="risk"
										name="高危"
										fill={TONE_STYLES.high.fill}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="medium"
										stackId="risk"
										name="中危"
										fill={TONE_STYLES.medium.fill}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="low"
										stackId="risk"
										name="低危"
										fill={TONE_STYLES.low.fill}
										radius={[0, 10, 10, 0]}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									>
										<LabelList
											dataKey="total"
											position="right"
											fill="hsl(var(--foreground))"
											fontSize={HORIZONTAL_STATS_LABEL_FONT_SIZE}
											formatter={(value: number) => formatNumber(Number(value))}
										/>
									</Bar>
								</>
							) : (
								<Bar
									dataKey="total"
									name="数量"
									fill={TONE_STYLES[primaryTone].fill}
									radius={[0, 10, 10, 0]}
									barSize={HORIZONTAL_STATS_BAR_SIZE}
								>
									<LabelList
										dataKey="total"
										position="right"
										fill="hsl(var(--foreground))"
										fontSize={HORIZONTAL_STATS_LABEL_FONT_SIZE}
										formatter={(value: number) => formatNumber(Number(value))}
									/>
								</Bar>
							)}
						</BarChart>
					</ResponsiveContainer>
				</div>
			</div>
		</div>
	);
}

export default function DashboardCommandCenter({
	snapshot,
}: DashboardCommandCenterProps) {
	const [activeView, setActiveView] = useState<DashboardViewId>("trend");
	const activeMeta = useMemo(
		() => VIEW_ITEMS.find((item) => item.id === activeView) ?? VIEW_ITEMS[0],
		[activeView],
	);
	const rows = useMemo(
		() => buildRowsForView(activeView, snapshot),
		[activeView, snapshot],
	);

	return (
		<div className="px-1 py-1 text-foreground xl:flex xl:h-full xl:min-h-0 xl:flex-col xl:overflow-hidden">
			<div className="space-y-6 xl:flex xl:min-h-0 xl:flex-1 xl:flex-col xl:space-y-4">
				<PreviewHeader snapshot={snapshot} />
				<div className="grid gap-6 xl:min-h-0 xl:flex-1 xl:grid-cols-[260px_minmax(0,1fr)_340px] xl:gap-4">
					<ViewSidebar activeView={activeView} onChange={setActiveView} />
					<section className={`${DASHBOARD_PANEL_CLASSNAME} p-5 xl:min-h-0`}>
						{activeView === "trend" ? (
							<TrendPanel snapshot={snapshot} />
						) : (
							<HorizontalStatsChart
								title={activeMeta.label}
								description={activeMeta.description}
								rows={rows}
								viewId={activeView}
								yAxisLabel={activeMeta.yAxisLabel}
								stacked={activeView === "project-risk"}
							/>
						)}
					</section>
					<TaskStatusPanel snapshot={snapshot} />
				</div>
			</div>
		</div>
	);
}
