import { useMemo, useState } from "react";
import {
	Activity,
	BarChart3,
	Boxes,
	Bug,
	ChevronRight,
	Info,
	ListOrdered,
} from "lucide-react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	ComposedChart,
	LabelList,
	Line,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
} from "recharts";
import {
	Tooltip as UiTooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { DataTable, type AppColumnDef } from "@/components/data-table";
import type {
	DashboardDailyActivityItem,
	DashboardLanguageLocItem,
	DashboardLanguageRiskItem,
	DashboardProjectRiskDistributionItem,
	DashboardRecentTaskItem,
	DashboardSnapshotResponse,
	DashboardTaskStatusScanTypeBreakdown,
	DashboardVerifiedVulnerabilityTypeItem,
} from "@/shared/types";

type RangeDays = 7 | 14 | 30;

type DashboardViewId =
	| "trend"
	| "project-risk"
	| "language-risk"
	| "vulnerability-types"
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

interface DashboardMetricRow {
	label: string;
	value: string;
}

interface AuditTypeTaskStatusSection {
	key: "intelligent" | "static";
	label: "智能审计" | "静态审计";
	total: number;
	completed: number;
	running: number;
	anomaly: number;
	recentTasks: DashboardRecentTaskItem[];
	tasksRoute: string;
}

const DASHBOARD_METRIC_COLUMNS: AppColumnDef<DashboardMetricRow, unknown>[] = [
	{ accessorKey: "label", header: "指标", meta: { label: "指标" } },
	{ accessorKey: "value", header: "数值", meta: { label: "数值" } },
];

const DASHBOARD_VIEW_COLUMNS: AppColumnDef<DashboardViewMeta, unknown>[] = [
	{ accessorKey: "label", header: "视图", meta: { label: "视图" } },
	{ accessorKey: "description", header: "说明", meta: { label: "说明" } },
];

const DASHBOARD_STATUS_SECTION_COLUMNS: AppColumnDef<AuditTypeTaskStatusSection, unknown>[] = [
	{ accessorKey: "label", header: "审计类型", meta: { label: "审计类型" } },
	{ accessorKey: "total", header: "总执行", meta: { label: "总执行" } },
];

const DASHBOARD_RECENT_TASK_COLUMNS: AppColumnDef<DashboardRecentTaskItem, unknown>[] = [
	{ accessorKey: "title", header: "任务", meta: { label: "任务" } },
	{ accessorKey: "status", header: "状态", meta: { label: "状态" } },
];

type TaskStatusTooltipItem = {
	label: string;
	value: number;
};

type TrendRow = {
	date: string;
	totalNewFindings: number;
	staticFindings: number;
	intelligentVerifiedFindings: number;
	staticShare: number;
	intelligentShare: number;
	staticLabel: number;
	intelligentLabel: number;
};

const VIEW_ITEMS: DashboardViewMeta[] = [
	{
		id: "trend",
		label: "漏洞态势统计图",
		description: "查看近一段时间当日新增漏洞发现与来源构成的波动。",
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
		description: "展示智能审计中已验证漏洞类型 Top10。",
		yAxisLabel: "漏洞类型标号",
	},
	{
		id: "language-lines",
		label: "项目语言统计图",
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

export const HORIZONTAL_STATS_AXIS_FONT_SIZE = 13;
export const HORIZONTAL_STATS_LABEL_FONT_SIZE = 12;
export const HORIZONTAL_STATS_Y_AXIS_MIN_WIDTH = 68;
export const HORIZONTAL_STATS_Y_AXIS_MAX_WIDTH = 96;
export const HORIZONTAL_STATS_BAR_SIZE = 9;
export const HORIZONTAL_STATS_ROW_HEIGHT = 34;
export const HORIZONTAL_STATS_BAR_CATEGORY_GAP = 2;
export const HORIZONTAL_STATS_CHART_MARGIN = {
	top: 4,
	right: 16,
	left: 4,
	bottom: 4,
} as const;
export const HORIZONTAL_STATS_META_ROW_CLASSNAME =
	"mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between";
export const HORIZONTAL_STATS_META_LEGEND_CLASSNAME =
	"flex flex-wrap justify-start gap-2 sm:justify-end";
export const TOP_STATS_GRID_CLASSNAME =
	"grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5";
export const DASHBOARD_MAIN_GRID_CLASSNAME =
	"grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,24rem)] xl:min-h-0 xl:flex-1";
export const DASHBOARD_RECENT_TASKS_LIMIT = 3;
const DASHBOARD_PANEL_CLASSNAME =
	"rounded-sm border border-border bg-card text-card-foreground shadow-sm";
const DASHBOARD_PANEL_TITLE_CLASSNAME =
	"text-xl font-semibold uppercase tracking-[0.12em] text-foreground";
const DASHBOARD_PANEL_DESCRIPTION_CLASSNAME =
	"max-w-2xl text-sm leading-6 text-muted-foreground";
const DASHBOARD_META_LABEL_CLASSNAME =
	"text-left text-xs uppercase tracking-[0.18em] text-muted-foreground";
const DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME =
	"text-sm uppercase tracking-[0.12em] text-muted-foreground";
const RECENT_TASK_CARD_CLASSNAME =
	"min-w-[16rem] rounded-sm border border-border bg-card px-4 py-4 text-card-foreground shadow-sm transition hover:border-border/80 hover:bg-muted/30 focus-visible:border-foreground/50 focus-visible:bg-muted/40 focus-visible:outline focus-visible:outline-1 focus-visible:outline-foreground/55 focus-visible:outline-offset-2";
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

export function formatHorizontalStatsTooltipValue(
	viewId: DashboardViewId,
	value: number,
	name: string,
): [string, string] {
	const formattedValue = formatNumber(Number(value));

	if (viewId === "project-risk") {
		return [formattedValue, `${name}漏洞数量`];
	}

	return [formattedValue, name];
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

function toShare(value: number, total: number) {
	if (total <= 0) return 0;
	return value / total;
}

export function buildTrendRows(
	items: DashboardDailyActivityItem[],
): TrendRow[] {
	return items.map((item) => {
		const totalNewFindings = Math.max(Number(item.total_new_findings || 0), 0);
		const staticFindings = Math.max(Number(item.static_findings || 0), 0);
		const intelligentVerifiedFindings = Math.max(
			Number(item.intelligent_verified_findings || 0),
			0,
		);

		return {
			date: formatTrendDate(item.date),
			totalNewFindings,
			staticFindings,
			intelligentVerifiedFindings,
			staticShare: toShare(staticFindings, totalNewFindings),
			intelligentShare: toShare(intelligentVerifiedFindings, totalNewFindings),
			staticLabel: staticFindings,
			intelligentLabel: intelligentVerifiedFindings,
		};
	});
}

function renderTrendLabel(value: number | string) {
	return Number(value || 0) > 0 ? formatNumber(Number(value || 0)) : "";
}

function renderTrendTooltip(payload: {
	active?: boolean;
	label?: string;
	payload?: Array<{ payload?: TrendRow }>;
}) {
	if (
		!payload.active ||
		!Array.isArray(payload.payload) ||
		payload.payload.length === 0
	) {
		return null;
	}
	const row = payload.payload[0]?.payload;
	if (!row) return null;

	return (
		<div
			className="rounded border border-border bg-card px-3 py-2 text-xs shadow-xl"
			style={DASHBOARD_TOOLTIP_STYLE}
		>
			<p className="font-semibold text-foreground">{row.date}</p>
			<div className="mt-2 space-y-1 text-muted-foreground">
				{/* <p>当日累计新增漏洞发现：{formatNumber(row.totalNewFindings)}</p> */}
				<p>当日静态审计漏洞发现：{formatNumber(row.staticFindings)}</p>
				<p>
					当日智能审计漏洞发现：{formatNumber(row.intelligentVerifiedFindings)}
				</p>
			</div>
		</div>
	);
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
	if (view === "language-lines") {
		return buildLanguageLineRows(snapshot.language_loc_distribution);
	}
	return [];
}

export function buildTaskStatusTooltipItems(
	breakdown: DashboardTaskStatusScanTypeBreakdown,
): TaskStatusTooltipItem[] {
	return [
		{ label: "静态审计", value: breakdown.static },
		{ label: "智能审计", value: breakdown.intelligent },
	];
}

export function getRecentTaskProjectTitle(
	task: DashboardRecentTaskItem,
): string {
	const title = String(task.title || "").trim();
	if (!title) {
		return "-";
	}

	const segments = title.split("·");
	if (segments.length < 2) {
		return title;
	}

	return segments[segments.length - 1]?.trim() || title;
}

export function normalizeRecentTaskTypeLabel(
	taskType: string | null | undefined,
): string {
	const normalized = String(taskType || "").trim();
	if (normalized.includes("混合")) {
		return "智能审计";
	}
	return normalized || "静态审计";
}

export function normalizeRecentTaskStatusLabel(
	status: string | null | undefined,
): "完成" | "进行" | "中断" | "异常" {
	const normalized = String(status || "").trim().toLowerCase();
	if (normalized === "completed" || normalized === "success") {
		return "完成";
	}
	if (
		normalized === "running" ||
		normalized === "pending" ||
		normalized === "queued" ||
		normalized === "created"
	) {
		return "进行";
	}
	if (normalized === "interrupted" || normalized === "cancelled") {
		return "中断";
	}
	return "异常";
}

export function getRecentTaskTypeBadgeClassName(
	taskType: string | null | undefined,
): string {
	return normalizeRecentTaskTypeLabel(taskType) === "智能审计"
		? "cyber-badge-primary"
		: "cyber-badge-info";
}

export function getRecentTaskProgressBadgeClassName(
	status: string | null | undefined,
): string {
	const progress = normalizeRecentTaskStatusLabel(status);
	if (progress === "完成") return "cyber-badge-success";
	if (progress === "进行") return "cyber-badge-info";
	if (progress === "中断") return "cyber-badge-warning";
	return "cyber-badge-danger";
}

export function getRecentTaskCards(tasks: DashboardRecentTaskItem[]) {
	return tasks.slice(0, DASHBOARD_RECENT_TASKS_LIMIT);
}

function getRecentTasksForSection(
	snapshot: DashboardSnapshotResponse,
	key: "intelligent" | "static",
): DashboardRecentTaskItem[] {
	const byType = snapshot.recent_tasks_by_scan_type?.[key];
	if (Array.isArray(byType)) return byType;
	const label = key === "intelligent" ? "智能审计" : "静态审计";
	return snapshot.recent_tasks.filter(
		(task) => normalizeRecentTaskTypeLabel(task.task_type) === label,
	);
}

export function buildAuditTypeTaskStatusSections(
	snapshot: DashboardSnapshotResponse,
): AuditTypeTaskStatusSection[] {
	const byType = snapshot.task_status_by_scan_type;
	return ([
		{ key: "intelligent" as const, label: "智能审计" as const, tasksRoute: "/tasks/intelligent" },
		{ key: "static" as const, label: "静态审计" as const, tasksRoute: "/tasks/static" },
	]).map((section) => {
		const key = section.key;
		const completed = byType.completed[key];
		const running = byType.pending[key] + byType.running[key];
		const anomaly = byType.failed[key] + byType.interrupted[key] + byType.cancelled[key];
		return {
			...section,
			completed,
			running,
			anomaly,
			total: completed + running + anomaly,
			recentTasks: getRecentTasksForSection(snapshot, key),
		};
	});
}

function AuditTypeBreakdownTooltipContent({
	section,
}: {
	section: AuditTypeTaskStatusSection;
}) {
	return (
		<div className="space-y-3">
			<div>
				<p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
					{section.label}
				</p>
				<p className="mt-1 font-semibold text-foreground">任务状态细分</p>
			</div>
			<div className="space-y-2">
				{[
					["已完成", section.completed],
					["进行中", section.running],
					["异常", section.anomaly],
				].map(([label, value]) => (
					<div key={label} className="flex items-center justify-between gap-6 text-sm">
						<span className="text-muted-foreground">{label}</span>
						<span className="font-semibold tabular-nums text-foreground">
							{formatNumber(Number(value))}
						</span>
					</div>
				))}
			</div>
		</div>
	);
}

function PreviewHeader({ snapshot }: { snapshot: DashboardSnapshotResponse }) {
	const totalTasks =
		snapshot.task_status_breakdown.pending +
		snapshot.task_status_breakdown.completed +
		snapshot.task_status_breakdown.running +
		snapshot.task_status_breakdown.failed +
		snapshot.task_status_breakdown.interrupted +
		snapshot.task_status_breakdown.cancelled;
	const cards: DashboardMetricRow[] = [
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
		<DataTable
			data={cards}
			columns={DASHBOARD_METRIC_COLUMNS}
			toolbar={false}
			pagination={false}
			className="border-0 bg-transparent shadow-none"
			renderMode={({ rows }) => (
				<div className={TOP_STATS_GRID_CLASSNAME}>
					{rows.map((item) => (
						<div
							key={item.label}
							className={`${DASHBOARD_PANEL_CLASSNAME} flex items-center justify-between gap-3 px-3 py-3`}
						>
							<div className={DASHBOARD_SUMMARY_CARD_LABEL_CLASSNAME}>
								{item.label}
							</div>
							<div className="text-right text-xl font-semibold tabular-nums text-foreground">
								{item.value}
							</div>
						</div>
					))}
				</div>
			)}
		/>
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
		<DataTable
			data={VIEW_ITEMS}
			columns={DASHBOARD_VIEW_COLUMNS}
			toolbar={false}
			pagination={false}
			className="border-0 bg-transparent shadow-none"
			renderMode={({ rows }) => (
				<nav
					aria-label="漏洞态势视图切换"
					className={`${DASHBOARD_PANEL_CLASSNAME} p-3`}
				>
					<div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
						{rows.map((view) => {
							const active = view.id === activeView;
							return (
								<button
									key={view.id}
									type="button"
									aria-pressed={active}
									onClick={() => onChange(view.id)}
									className={`group flex w-full items-start gap-3 rounded-sm border px-3 py-3 text-left transition duration-200 ${
										active
											? "border-primary/30 bg-muted/70 text-foreground shadow-sm"
											: "border-transparent bg-background/60 text-muted-foreground hover:border-border hover:bg-muted/40"
									}`}
								>
									<div
										className={`mt-0.5 rounded-sm p-2 ${
											active
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
										) : view.id === "language-lines" ? (
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
												className={`h-4 w-4 transition ${
													active
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
			)}
		/>
	);
}

function TaskStatusPanel({
	snapshot,
}: {
	snapshot: DashboardSnapshotResponse;
}) {
	const sections = buildAuditTypeTaskStatusSections(snapshot);

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
			<DataTable
				data={sections}
				columns={DASHBOARD_STATUS_SECTION_COLUMNS}
				toolbar={false}
				pagination={false}
				className="mt-4 border-0 bg-transparent shadow-none"
				renderMode={({ rows }) => (
					<div className="grid min-h-0 flex-1 grid-rows-2 gap-0 divide-y divide-border/70">
						{rows.map((section) => {
							const recentTasks = getRecentTaskCards(section.recentTasks);
							const hasMore = section.recentTasks.length > DASHBOARD_RECENT_TASKS_LIMIT;
							return (
								<div key={section.key} data-audit-type-section={section.key} className="min-h-0 py-4 first:pt-0 last:pb-0">
									<div className="mb-3 flex items-center justify-between gap-3">
										<div className="flex items-center gap-2">
											<h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-foreground">
												{section.label}
											</h3>
											<UiTooltip>
												<TooltipTrigger asChild>
													<button
														type="button"
														aria-label={`查看${section.label}任务状态细分`}
														className="rounded-full border border-border/70 p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
													>
														<Info className="h-3.5 w-3.5" />
													</button>
												</TooltipTrigger>
												<TooltipContent
													side="top"
													align="start"
													sideOffset={6}
													className="w-[15rem] max-w-[calc(100vw-2rem)] border border-border bg-card px-3 py-3 text-sm text-foreground shadow-xl"
												>
													<AuditTypeBreakdownTooltipContent section={section} />
												</TooltipContent>
											</UiTooltip>
										</div>
										<div className="text-right text-xl font-semibold tabular-nums text-foreground">
											{formatNumber(section.total)}
										</div>
									</div>
									<DataTable
										data={recentTasks}
										columns={DASHBOARD_RECENT_TASK_COLUMNS}
										toolbar={false}
										pagination={false}
										className="border-0 bg-transparent shadow-none"
										renderMode={({ rows: taskRows }) =>
											taskRows.length === 0 ? (
												<p className="rounded-sm border border-dashed border-border bg-muted/20 px-4 py-5 text-sm text-muted-foreground">
													暂无最近任务
												</p>
											) : (
												<div className="grid gap-2">
													{taskRows.map((task) => (
														<RecentTaskCard key={task.task_id} task={task} />
													))}
													{hasMore ? (
														<a href={section.tasksRoute} className="rounded-sm border border-dashed border-border px-3 py-2 text-center text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
															...
														</a>
													) : null}
												</div>
											)
										}
									/>
								</div>
							);
						})}
					</div>
				)}
			/>
		</section>
	);
}

function RecentTaskCard({ task }: { task: DashboardRecentTaskItem }) {
	const projectTitle = getRecentTaskProjectTitle(task);
	const statusLabel = normalizeRecentTaskStatusLabel(task.status);
	const typeLabel = normalizeRecentTaskTypeLabel(task.task_type);
	const typeBadgeClassName = getRecentTaskTypeBadgeClassName(task.task_type);
	const progressBadgeClassName = getRecentTaskProgressBadgeClassName(task.status);
	return (
		<a
			href={task.detail_path || "/tasks/static"}
			aria-label={`查看 ${projectTitle} 详情`}
			title={`查看 ${projectTitle} 详情`}
			className={RECENT_TASK_CARD_CLASSNAME}
		>
			<div className="flex items-center justify-between gap-3">
				<div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
					<Badge className="cyber-badge cyber-badge-muted min-w-0 max-w-full flex-1 truncate normal-case tracking-normal">
						{projectTitle}
					</Badge>
					<Badge className={`cyber-badge shrink-0 ${typeBadgeClassName}`}>
						{typeLabel}
					</Badge>
					<Badge className={`cyber-badge shrink-0 ${progressBadgeClassName}`}>
						{statusLabel}
					</Badge>
				</div>
				<ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
			</div>
		</a>
	);
}

function TrendPanel({ snapshot }: { snapshot: DashboardSnapshotResponse }) {
	const trendRows = useMemo(
		() => buildTrendRows(snapshot.daily_activity),
		[snapshot.daily_activity],
	);
	const latestItem = trendRows[trendRows.length - 1];

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
					查看近一段时间当日新增漏洞发现与静态、智能来源构成的波动趋势。
				</p>
			</div>
			<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
				{[
					// {
					// 	label: "当日累计新增漏洞发现",
					// 	value: formatNumber(peakItem.totalNewFindings),
					// 	meta: peakItem.date === "-" ? "" : `峰值 ${peakItem.date}`,
					// },
					{
						label: "当日静态审计漏洞发现",
						value: formatNumber(latestItem?.staticFindings ?? 0),
						meta: latestItem ? `${latestItem.date} 最新` : "",
					},
					{
						label: "当日智能审计漏洞发现",
						value: formatNumber(latestItem?.intelligentVerifiedFindings ?? 0),
						meta: latestItem ? `${latestItem.date} 最新` : "",
					},
				].map((item) => (
					<div
						key={item.label}
						className={`${DASHBOARD_PANEL_CLASSNAME} px-2 py-3`}
					>
						<p className="text-xs uppercase tracking-[0.20em] text-muted-foreground">
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
						{/* <span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.low.chip}`}
						>
							当日累计新增漏洞发现
						</span> */}
						<span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.medium.chip}`}
						>
							当日静态审计漏洞发现
						</span>
						<span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.high.chip}`}
						>
							当日智能审计漏洞发现
						</span>
					</div>
				</div>
				<div className="h-[calc(100%-52px)] w-full">
					<ResponsiveContainer width="100%" height="100%">
						<ComposedChart
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
							<Tooltip content={renderTrendTooltip} />
							<Bar
								dataKey="staticShare"
								stackId="share"
								name="当日静态审计漏洞发现"
								fill={TONE_STYLES.medium.fill}
								fillOpacity={0.28}
								barSize={18}
							>
								<LabelList
									dataKey="staticLabel"
									position="insideTop"
									formatter={renderTrendLabel}
								/>
							</Bar>
							<Bar
								dataKey="intelligentShare"
								stackId="share"
								name="当日智能审计漏洞发现"
								fill={TONE_STYLES.high.fill}
								fillOpacity={0.32}
							>
								<LabelList
									dataKey="intelligentLabel"
									position="insideTop"
									formatter={renderTrendLabel}
								/>
							</Bar>
							{/* <Line
								type="monotone"
								dataKey="totalNewFindings"
								name="当日累计新增漏洞发现"
								stroke={TONE_STYLES.low.fill}
								strokeWidth={2.4}
								dot={{ r: 3 }}
							/> */}
							<Line
								type="monotone"
								dataKey="staticFindings"
								name="当日静态审计漏洞发现"
								stroke={TONE_STYLES.medium.fill}
								strokeWidth={2}
								dot={false}
							/>
							<Line
								type="monotone"
								dataKey="intelligentVerifiedFindings"
								name="当日智能审计漏洞发现"
								stroke={TONE_STYLES.high.fill}
								strokeWidth={2.2}
								dot={false}
							/>
						</ComposedChart>
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

	const chartHeight = Math.max(rows.length * HORIZONTAL_STATS_ROW_HEIGHT, 180);
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
			<div className="rounded-sm border border-border bg-background/70 p-3">
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
								formatter={(value: number, name: string) =>
									formatHorizontalStatsTooltipValue(viewId, value, name)
								}
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
		<div className="px-1 pb-1 text-foreground xl:flex xl:h-full xl:min-h-0 xl:flex-col xl:overflow-hidden">
			<div className="space-y-6 xl:flex xl:min-h-0 xl:flex-1 xl:flex-col xl:space-y-4">
				<PreviewHeader snapshot={snapshot} />
				<ViewSidebar activeView={activeView} onChange={setActiveView} />
				<div className={DASHBOARD_MAIN_GRID_CLASSNAME}>
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
