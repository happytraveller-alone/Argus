import { useMemo, useState } from "react";
import {
	Activity,
	BarChart3,
	Boxes,
	Bug,
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
		label: "漏洞态势趋势",
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
		bar: "from-rose-500 to-rose-400",
		chip: "border-rose-400/30 bg-rose-500/15 text-rose-100",
		text: "text-rose-200",
		fill: "#f43f5e",
	},
	high: {
		bar: "from-orange-400 to-amber-300",
		chip: "border-orange-300/30 bg-orange-500/15 text-orange-50",
		text: "text-orange-100",
		fill: "#fb923c",
	},
	medium: {
		bar: "from-amber-400 to-yellow-300",
		chip: "border-amber-300/30 bg-amber-500/15 text-amber-50",
		text: "text-amber-100",
		fill: "#fbbf24",
	},
	low: {
		bar: "from-cyan-400 to-sky-300",
		chip: "border-cyan-300/30 bg-cyan-500/15 text-cyan-50",
		text: "text-cyan-100",
		fill: "#38bdf8",
	},
	neutral: {
		bar: "from-slate-500 to-slate-300",
		chip: "border-slate-400/30 bg-slate-500/15 text-slate-100",
		text: "text-slate-100",
		fill: "#94a3b8",
	},
};

export const HORIZONTAL_STATS_AXIS_FONT_SIZE = 16;
export const HORIZONTAL_STATS_LABEL_FONT_SIZE = 16;
export const HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH = 84;
export const HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH = 120;
export const HORIZONTAL_STATS_BAR_SIZE = 14;
export const HORIZONTAL_STATS_ROW_HEIGHT = 60;
export const HORIZONTAL_STATS_BAR_CATEGORY_GAP = 10;
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
	const estimatedWidth = Math.ceil(widestLabelUnits * HORIZONTAL_STATS_AXIS_FONT_SIZE + 18);

	return Math.min(
		Math.max(estimatedWidth, HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH),
		HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH,
	);
}

function buildFiveStepTicks(rows: HorizontalRow[]) {
	const upperBound = Math.max(
		5,
		Math.ceil(
			rows.reduce((maxValue, row) => Math.max(maxValue, Number(row.total || 0)), 0) / 5,
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

function formatTokenValue(value: number | null | undefined) {
	return formatNumber(value);
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

export function formatCumulativeDuration(durationMs: number | null | undefined) {
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

function buildLanguageRiskRows(items: DashboardLanguageRiskItem[]): HorizontalRow[] {
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

function buildEngineRows(items: DashboardEngineBreakdownItem[]): HorizontalRow[] {
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

function buildLanguageLineRows(items: DashboardLanguageLocItem[]): HorizontalRow[] {
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
		{ label: "已完成", value: snapshot.task_status_breakdown.completed, tone: "low" as Tone },
		{ label: "运行中", value: snapshot.task_status_breakdown.running, tone: "neutral" as Tone },
		{ label: "失败", value: snapshot.task_status_breakdown.failed, tone: "critical" as Tone },
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

function PreviewHeader({ snapshot }: { snapshot: DashboardSnapshotResponse }) {
	const totalTasks =
		snapshot.task_status_breakdown.completed +
		snapshot.task_status_breakdown.running +
		snapshot.task_status_breakdown.failed +
		snapshot.task_status_breakdown.interrupted +
		snapshot.task_status_breakdown.cancelled;
	const cards = [
		{ label: "项目总数", value: formatNumber(snapshot.summary.total_projects) },
		{ label: "累计发现漏洞总数", value: formatNumber(snapshot.summary.current_effective_findings) },
		{ label: "AI累计验证漏洞总数", value: formatNumber(snapshot.summary.current_verified_findings) },
		{ label: "累计执行扫描任务次数", value: formatNumber(totalTasks) },
		{ label: "累计消耗模型token", value: formatTokenValue(snapshot.summary.total_model_tokens) },
	];

	return (
		<div className={TOP_STATS_GRID_CLASSNAME}>
			{cards.map((item) => (
				<div
					key={item.label}
					className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 backdrop-blur-sm"
				>
					<div className="text-[16px] uppercase tracking-[0.28em] text-slate-400">
						{item.label}
					</div>
					<div className="mt-2 text-3xl font-semibold text-white">{item.value}</div>
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
			className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-3 shadow-[0_18px_48px_rgba(15,23,42,0.45)]"
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
							className={`group flex w-full items-start gap-3 rounded-2xl border px-3 py-3 text-left transition duration-200 ${
								active
									? "border-cyan-300/30 bg-cyan-400/12 text-white shadow-[0_10px_30px_rgba(34,211,238,0.18)]"
									: "border-transparent bg-slate-900/70 text-slate-300 hover:border-slate-700 hover:bg-slate-900"
							}`}
						>
							<div
								className={`mt-0.5 rounded-xl p-2 ${
									active ? "bg-cyan-400/20 text-cyan-100" : "bg-slate-800 text-slate-400"
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
								) : view.id === "static-engine-rules" || view.id === "language-lines" ? (
									<BarChart3 className="h-4 w-4" />
								) : (
									<Bug className="h-4 w-4" />
								)}
							</div>
							<div className="min-w-0 flex-1">
								<div className="flex items-center justify-between gap-3">
									<span className="font-medium tracking-[0.02em]">{view.label}</span>
									<ChevronRight
										className={`h-4 w-4 transition ${
											active
												? "translate-x-0 text-cyan-200"
												: "-translate-x-1 text-slate-600 group-hover:translate-x-0"
										}`}
									/>
								</div>
								<p className="mt-1 text-xs leading-5 text-slate-400">
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
	return (
		<section
			data-panel="status"
			className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.45)]"
		>
			<div className="flex items-start justify-between gap-4">
				<div>
					<h2 className="mt-3 text-2xl font-semibold text-white">任务状态</h2>
				</div>
			</div>
			<div className="mt-3 space-y-3">
				{statusRows.length === 0 ? (
					<p className="text-sm text-slate-400">暂无任务状态数据</p>
				) : (
					statusRows.map((item) => {
						const tone = TONE_STYLES[item.tone];
						const width = total > 0 ? Math.max((item.value / total) * 100, 8) : 0;
						return (
							<div key={item.label} className="space-y-2">
								<div className="flex items-center justify-between gap-3 text-sm">
									<span className="text-slate-200">{item.label}</span>
									<span className={`font-medium ${tone.text}`}>
										{formatNumber(item.value)}
									</span>
								</div>
								<div className="h-3 rounded-full bg-slate-900">
									<div
										className={`h-3 rounded-full bg-gradient-to-r ${tone.bar}`}
										style={{ width: `${width}%` }}
									/>
								</div>
							</div>
						);
					})
				)}
			</div>
			<div className="mt-1 border-t border-white/10 pt-5">
				<div className="space-y-3">
					{snapshot.recent_tasks.slice(0, 5).map((task) => (
						<RecentTaskCard key={task.task_id} task={task} />
					))}
				</div>
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
		<div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<p className="truncate text-sm font-medium text-slate-100">{task.title}</p>
					<p className="mt-1 text-xs text-slate-400">
						{task.task_type} · {formatCreatedAt(task.created_at)}
					</p>
				</div>
				<a
					href={task.detail_path || "/tasks/static"}
					className="shrink-0 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/15"
				>
					查看详情
				</a>
			</div>
			<div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-400">
				<span>{task.task_type}</span>
				<span>执行进度 {progress}%</span>
			</div>
			<div className="mt-2 h-2 rounded-full bg-slate-900">
				<div
					className="h-2 rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-emerald-300"
					style={{ width: `${progress}%` }}
				/>
			</div>
		</div>
	);
}

function TrendPanel({
	snapshot,
}: {
	snapshot: DashboardSnapshotResponse;
}) {
	const trendRows = useMemo(() => buildTrendRows(snapshot.daily_activity), [snapshot.daily_activity]);
	const peakItem = trendRows.reduce(
		(result, item) => (item.total > result.total ? item : result),
		{ date: "-", total: 0, verified: 0 },
	);
	const llmTotal = snapshot.engine_breakdown.find((item) => item.engine === "llm");

	if (trendRows.length === 0) {
		return (
			<div data-panel="trend" className="space-y-4">
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">漏洞态势趋势</h3>
				<p className="text-sm text-slate-400">暂无趋势数据</p>
			</div>
		);
	}

	return (
		<div data-panel="trend" className="space-y-5">
			<div className="flex flex-col gap-2">
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">
					漏洞态势趋势
				</h3>
				<p className="max-w-2xl text-sm leading-6 text-slate-400">
					查看近一段时间新增风险与 AI 已验证漏洞的波动趋势。
				</p>
			</div>
			<div className="grid gap-3 sm:grid-cols-3">
				{[
					{
						label: "区间峰值",
						value: formatNumber(peakItem.total),
						meta: peakItem.date,
					},
					{
						label: "AI 已验证漏洞",
						value: formatNumber(snapshot.summary.current_verified_findings),
						meta: "累计验证",
					},
					{
						label: "LLM 贡献",
						value: formatNumber(llmTotal?.effective_findings ?? 0),
						meta: "智能扫描 + 混合扫描",
					},
				].map((item) => (
					<div
						key={item.label}
						className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3"
					>
						<p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
							{item.label}
						</p>
						<p className="mt-2 text-2xl font-semibold text-white">{item.value}</p>
						<p className="mt-1 text-xs text-slate-400">{item.meta}</p>
					</div>
				))}
			</div>
			<div className="h-[320px] w-full rounded-[24px] border border-cyan-400/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.4),rgba(2,6,23,0.8))] p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className="text-left text-[14px] uppercase tracking-[0.28em] text-slate-500">
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
						<AreaChart data={trendRows} margin={{ top: 12, right: 12, left: -10, bottom: 0 }}>
							<defs>
								<linearGradient id="dashboardTotal" x1="0" x2="0" y1="0" y2="1">
									<stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
									<stop offset="100%" stopColor="#22d3ee" stopOpacity={0.02} />
								</linearGradient>
								<linearGradient id="dashboardVerified" x1="0" x2="0" y1="0" y2="1">
									<stop offset="0%" stopColor="#f97316" stopOpacity={0.38} />
									<stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
								</linearGradient>
							</defs>
							<CartesianGrid stroke="rgba(100,116,139,0.15)" strokeDasharray="4 4" />
							<XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
							<YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
							<Tooltip
								contentStyle={{
									backgroundColor: "rgba(2, 6, 23, 0.92)",
									borderColor: "rgba(56, 189, 248, 0.18)",
									borderRadius: "16px",
									color: "#e2e8f0",
								}}
							/>
							<Area
								type="monotone"
								dataKey="total"
								name="新增风险"
								stroke="#22d3ee"
								fill="url(#dashboardTotal)"
								strokeWidth={2.4}
							/>
							<Area
								type="monotone"
								dataKey="verified"
								name="已验证"
								stroke="#f97316"
								fill="url(#dashboardVerified)"
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
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">{title}</h3>
				<p className="text-sm text-slate-400">暂无统计数据</p>
			</div>
		);
	}

	const chartHeight = Math.max(rows.length * HORIZONTAL_STATS_ROW_HEIGHT, 260);
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
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">{title}</h3>
				<p className="max-w-2xl text-sm leading-6 text-slate-400">{description}</p>
			</div>
			<div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className="text-left text-[14px] uppercase tracking-[0.28em] text-slate-500">
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
								stroke="rgba(100,116,139,0.15)"
								strokeDasharray="4 4"
								horizontal={false}
							/>
								<XAxis
									type="number"
									tick={{ fill: "#94a3b8", fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE }}
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
								tick={{ fill: "#e2e8f0", fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE }}
								axisLine={false}
								tickLine={false}
							/>
							<Tooltip
								cursor={{ fill: "rgba(15, 23, 42, 0.45)" }}
								contentStyle={{
									backgroundColor: "rgba(2, 6, 23, 0.94)",
									borderColor: "rgba(56, 189, 248, 0.18)",
									borderRadius: "16px",
									color: "#e2e8f0",
								}}
								formatter={(value: number) => [formatNumber(Number(value)), "数量"]}
								labelFormatter={(label: string, payload: Array<{ payload?: HorizontalRow }>) =>
									`${label}${payload[0]?.payload?.meta ? ` · ${payload[0].payload.meta}` : ""}`
								}
							/>
							{stacked ? (
								<>
									<Bar dataKey="critical" stackId="risk" name="严重" fill={TONE_STYLES.critical.fill} barSize={HORIZONTAL_STATS_BAR_SIZE} />
									<Bar dataKey="high" stackId="risk" name="高危" fill={TONE_STYLES.high.fill} barSize={HORIZONTAL_STATS_BAR_SIZE} />
									<Bar dataKey="medium" stackId="risk" name="中危" fill={TONE_STYLES.medium.fill} barSize={HORIZONTAL_STATS_BAR_SIZE} />
									<Bar dataKey="low" stackId="risk" name="低危" fill={TONE_STYLES.low.fill} radius={[0, 10, 10, 0]} barSize={HORIZONTAL_STATS_BAR_SIZE}>
										<LabelList
											dataKey="total"
											position="right"
											fill="#f8fafc"
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
										fill="#f8fafc"
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
	const rows = useMemo(() => buildRowsForView(activeView, snapshot), [activeView, snapshot]);

	return (
		<div className="bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),transparent_22%),linear-gradient(180deg,#020617_0%,#020817_52%,#030712_100%)] px-1 py-1 text-slate-100">
			<div className="space-y-6">
				<PreviewHeader snapshot={snapshot} />
				<div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)_360px]">
					<ViewSidebar activeView={activeView} onChange={setActiveView} />
					<section className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.45)]">
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
