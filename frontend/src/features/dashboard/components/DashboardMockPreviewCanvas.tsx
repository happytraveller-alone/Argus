import { useMemo, useState } from "react";
import {
	Activity,
	BarChart3,
	Boxes,
	Bug,
	ChevronRight,
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
	DASHBOARD_PREVIEW_TASK_STATUS,
	DASHBOARD_PREVIEW_TREND,
	DASHBOARD_PREVIEW_VIEWS,
	getRecentPreviewTasks,
	getPreviewLeaderboardRows,
	type DashboardPreviewSegment,
	type DashboardPreviewLeaderboardRow,
	type DashboardPreviewViewId,
} from "./dashboardMockPreviewModel";

const TONE_STYLES: Record<
	DashboardPreviewSegment["tone"],
	{ bar: string; chip: string; text: string }
> = {
	critical: {
		bar: "from-rose-500 to-rose-400",
		chip: "bg-rose-500/15 text-rose-100 border-rose-400/30",
		text: "text-rose-200",
	},
	high: {
		bar: "from-orange-400 to-amber-300",
		chip: "bg-orange-500/15 text-orange-50 border-orange-300/30",
		text: "text-orange-100",
	},
	medium: {
		bar: "from-amber-400 to-yellow-300",
		chip: "bg-amber-500/15 text-amber-50 border-amber-300/30",
		text: "text-amber-100",
	},
	low: {
		bar: "from-cyan-400 to-sky-300",
		chip: "bg-cyan-500/15 text-cyan-50 border-cyan-300/30",
		text: "text-cyan-100",
	},
	neutral: {
		bar: "from-slate-500 to-slate-300",
		chip: "bg-slate-500/15 text-slate-100 border-slate-400/30",
		text: "text-slate-100",
	},
};

export const HORIZONTAL_STATS_AXIS_FONT_SIZE = 13;
export const HORIZONTAL_STATS_LABEL_FONT_SIZE = 12;
export const HORIZONTAL_STATS_Y_AXIS_WIDTH = 96;
export const HORIZONTAL_STATS_BAR_SIZE = 9;
export const HORIZONTAL_STATS_ROW_HEIGHT = 34;
export const HORIZONTAL_STATS_BAR_CATEGORY_GAP = 2;
export const HORIZONTAL_STATS_META_ROW_CLASSNAME =
	"mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between";
export const HORIZONTAL_STATS_META_LEGEND_CLASSNAME =
	"flex flex-wrap justify-start gap-2 sm:justify-end";
export const TOP_STATS_GRID_CLASSNAME =
	"grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5";
const SUMMARY_CARD_LABEL_CLASSNAME =
	"text-sm uppercase tracking-[0.12em] text-slate-400";

function formatNumber(value: number) {
	return Math.max(Number(value || 0), 0).toLocaleString("zh-CN");
}

function getToneColor(tone: DashboardPreviewSegment["tone"]) {
	if (tone === "critical") return "#f43f5e";
	if (tone === "high") return "#fb923c";
	if (tone === "medium") return "#fbbf24";
	if (tone === "low") return "#38bdf8";
	return "#94a3b8";
}

function PreviewHeader() {
	return (
		<div className={TOP_STATS_GRID_CLASSNAME}>
			{[
				{ label: "项目总数", value: "18" },
				{ label: "累计发现漏洞总数", value: "49" },
				{ label: "AI验证漏洞总数", value: "22" },
				{ label: "累计执行扫描", value: "126" },
				{ label: "累计消耗词元", value: "1.482M" },
			].map((item) => (
				<div
					key={item.label}
					className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-sm"
				>
					<div className={SUMMARY_CARD_LABEL_CLASSNAME}>{item.label}</div>
					<div className="text-right text-3xl font-semibold text-white">
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
	activeView: DashboardPreviewViewId;
	onChange: (view: DashboardPreviewViewId) => void;
}) {
	return (
		<nav
			aria-label="漏洞态势视图切换"
			className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-3 shadow-[0_18px_48px_rgba(15,23,42,0.45)]"
		>
			<div className="space-y-2">
				{DASHBOARD_PREVIEW_VIEWS.map((view) => {
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
								className={`mt-0.5 rounded-xl p-2 ${active ? "bg-cyan-400/20 text-cyan-100" : "bg-slate-800 text-slate-400"}`}
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
									<span className="font-medium tracking-[0.02em]">
										{view.label}
									</span>
									<ChevronRight
										className={`h-4 w-4 transition ${active ? "translate-x-0 text-cyan-200" : "-translate-x-1 text-slate-600 group-hover:translate-x-0"}`}
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

function TaskStatusPanel() {
	const total = DASHBOARD_PREVIEW_TASK_STATUS.reduce(
		(sum, item) => sum + item.value,
		0,
	);
	const recentTasks = getRecentPreviewTasks();
	return (
		<section className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.45)]">
			<div className="flex items-start justify-between gap-4">
				<div>
					<p className="text-[11px] uppercase tracking-[0.32em] text-slate-500">
						任务状态
					</p>
					<h2 className="mt-3 text-2xl font-semibold text-white">任务状态</h2>
				</div>
			</div>
			<div className="mt-3 space-y-3">
				{DASHBOARD_PREVIEW_TASK_STATUS.map((item) => {
					const width = total > 0 ? Math.max((item.value / total) * 100, 8) : 0;
					const tone = TONE_STYLES[item.tone];
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
				})}
			</div>
			<div className="mt-1 border-t border-white/10 pt-5">
				<div className="space-y-1">
					{recentTasks.map((task) => (
						<div
							key={task.id}
							className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4"
						>
							<div className="flex items-start justify-between gap-3">
								<div className="min-w-0">
									<p className="truncate text-sm font-medium text-slate-100">
										{task.title}
									</p>
								</div>
								<button
									type="button"
									className="shrink-0 rounded-full border border-cyan-300/20 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-100 transition hover:border-cyan-300/35 hover:bg-cyan-400/15"
								>
									查看详情
								</button>
							</div>
							<div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-400">
								<span>执行进度 {task.progress}%</span>
							</div>
							<div className="mt-2 h-2 rounded-full bg-slate-900">
								<div
									className="h-2 rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-emerald-300"
									style={{ width: `${task.progress}%` }}
								/>
							</div>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}

function TrendPanel() {
	const trendRows = useMemo(
		() =>
			DASHBOARD_PREVIEW_TREND.map((item) => {
				const total = Math.max(Number(item.totalNewFindings || 0), 0);
				const staticFindings = Math.max(Number(item.staticFindings || 0), 0);
				const intelligentVerifiedFindings = Math.max(
					Number(item.intelligentVerifiedFindings || 0),
					0,
				);
				return {
					...item,
					staticShare: total > 0 ? staticFindings / total : 0,
					intelligentShare: total > 0 ? intelligentVerifiedFindings / total : 0,
				};
			}),
		[],
	);

	return (
		<div data-panel="trend" className="space-y-5">
			<div className="flex flex-col gap-2">
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">
					漏洞态势趋势
				</h3>
				<p className="max-w-2xl text-sm leading-6 text-slate-400">
					查看近七日当日新增漏洞发现与静态、智能、混合来源构成的波动趋势。
				</p>
			</div>
			<div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
				{[
					{ label: "当日累计新增漏洞发现", value: "41", meta: "03-22 峰值" },
					{ label: "当日静态审计漏洞发现", value: "18", meta: "03-23 最新" },
					{ label: "当日智能审计漏洞发现", value: "19", meta: "03-23 最新" },
				].map((item) => (
					<div
						key={item.label}
						className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
					>
						<p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
							{item.label}
						</p>
						<p className="mt-2 text-2xl font-semibold text-white">
							{item.value}
						</p>
						<p className="mt-1 text-xs text-slate-400">{item.meta}</p>
					</div>
				))}
			</div>
			<div className="h-[320px] w-full rounded-[24px] border border-cyan-400/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.4),rgba(2,6,23,0.8))] p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className="text-left text-[14px] uppercase tracking-[0.28em] text-slate-500">
						横坐标：日期 纵坐标：漏洞数量
					</div>
					<div className={HORIZONTAL_STATS_META_LEGEND_CLASSNAME}>
						<span
							className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${TONE_STYLES.low.chip}`}
						>
							当日累计新增漏洞发现
						</span>
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
								stroke="rgba(100,116,139,0.15)"
								strokeDasharray="4 4"
							/>
							<XAxis
								dataKey="date"
								tick={{ fill: "#94a3b8", fontSize: 12 }}
								axisLine={false}
								tickLine={false}
							/>
							<YAxis
								tick={{ fill: "#94a3b8", fontSize: 12 }}
								axisLine={false}
								tickLine={false}
							/>
							<Tooltip
								contentStyle={{
									backgroundColor: "rgba(2, 6, 23, 0.92)",
									borderColor: "rgba(56, 189, 248, 0.18)",
									borderRadius: "16px",
									color: "#e2e8f0",
								}}
							/>
							<Bar
								dataKey="staticShare"
								stackId="share"
								fill="#fbbf24"
								fillOpacity={0.32}
								barSize={18}
							>
								<LabelList
									dataKey="staticFindings"
									position="insideTop"
									formatter={(value: number) =>
										value > 0 ? formatNumber(value) : ""
									}
								/>
							</Bar>
							<Bar
								dataKey="intelligentShare"
								stackId="share"
								fill="#fb923c"
								fillOpacity={0.34}
							>
								<LabelList
									dataKey="intelligentVerifiedFindings"
									position="insideTop"
									formatter={(value: number) =>
										value > 0 ? formatNumber(value) : ""
									}
								/>
							</Bar>
							<Line
								type="monotone"
								dataKey="totalNewFindings"
								name="当日累计新增漏洞发现"
								stroke="#38bdf8"
								strokeWidth={2.4}
								dot={{ r: 3 }}
							/>
							<Line
								type="monotone"
								dataKey="staticFindings"
								name="当日静态审计漏洞发现"
								stroke="#fbbf24"
								strokeWidth={2}
								dot={false}
							/>
							<Line
								type="monotone"
								dataKey="intelligentVerifiedFindings"
								name="当日智能审计漏洞发现"
								stroke="#fb923c"
								strokeWidth={2}
								dot={false}
							/>
						</ComposedChart>
					</ResponsiveContainer>
				</div>
			</div>
			<div className="grid gap-3 lg:grid-cols-3">
				{[
					{
						title: "项目高点",
						value: "Alpha Gateway",
						meta: "严重 + 高危累计最高",
					},
					{
						title: "语言高点",
						value: "TypeScript",
						meta: "累计漏洞总数 46",
					},
					{
						title: "类型高点",
						value: "CWE-89",
						meta: "SQL 注入 · 智能 / 混合已验证 17",
					},
				].map((item) => (
					<div
						key={item.title}
						className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4"
					>
						<p className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
							{item.title}
						</p>
						<p className="mt-2 text-lg font-semibold text-white">
							{item.value}
						</p>
						<p className="mt-1 text-sm text-slate-400">{item.meta}</p>
					</div>
				))}
			</div>
		</div>
	);
}

function buildHorizontalBarRows(rows: DashboardPreviewLeaderboardRow[]) {
	return rows.map((row) => ({
		label: row.label,
		meta: row.meta,
		total: row.total,
		critical:
			row.segments.find((segment) => segment.tone === "critical")?.value ?? 0,
		high: row.segments.find((segment) => segment.tone === "high")?.value ?? 0,
		medium:
			row.segments.find((segment) => segment.tone === "medium")?.value ?? 0,
		low: row.segments.find((segment) => segment.tone === "low")?.value ?? 0,
		neutral:
			row.segments.find((segment) => segment.tone === "neutral")?.value ?? 0,
	}));
}

function getHorizontalLegendItems(
	rows: DashboardPreviewLeaderboardRow[],
	stacked: boolean,
) {
	return stacked
		? [
				{ label: "严重", tone: "critical" as const },
				{ label: "高危", tone: "high" as const },
				{ label: "中危", tone: "medium" as const },
				{ label: "低危", tone: "low" as const },
			]
		: [
				{
					label: rows[0]?.segments[0]?.label ?? "总数",
					tone: rows[0]?.segments[0]?.tone ?? ("low" as const),
				},
			];
}

function HorizontalStatsChart({
	title,
	description,
	rows,
	yAxisLabel,
	stacked = false,
}: {
	title: string;
	description: string;
	rows: DashboardPreviewLeaderboardRow[];
	yAxisLabel: string;
	stacked?: boolean;
}) {
	const chartRows = useMemo(() => buildHorizontalBarRows(rows), [rows]);
	const legendItems = useMemo(
		() => getHorizontalLegendItems(rows, stacked),
		[rows, stacked],
	);
	const chartHeight = Math.max(rows.length * HORIZONTAL_STATS_ROW_HEIGHT, 180);

	return (
		<div className="space-y-5">
			<div className="flex flex-col gap-2">
				<h3 className="text-2xl font-semibold tracking-[0.04em] text-white">
					{title}
				</h3>
				<p className="max-w-2xl text-sm leading-6 text-slate-400">
					{description}
				</p>
			</div>
			<div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
				<div className={HORIZONTAL_STATS_META_ROW_CLASSNAME}>
					<div className="text-left text-[14px] uppercase tracking-[0.28em] text-slate-500">
						横坐标：漏洞数量 纵坐标：{yAxisLabel}
					</div>
					<div className={HORIZONTAL_STATS_META_LEGEND_CLASSNAME}>
						{legendItems.map((item) => {
							const tone = TONE_STYLES[item.tone];
							return (
								<span
									key={item.label}
									className={`rounded-full border px-3 py-1 text-xs tracking-[0.18em] ${tone.chip}`}
								>
									{item.label}
								</span>
							);
						})}
					</div>
				</div>
				<div style={{ height: chartHeight }} className="w-full">
					<ResponsiveContainer width="100%" height="100%">
						<BarChart
							data={chartRows}
							layout="vertical"
							margin={{ top: 8, right: 24, left: 36, bottom: 8 }}
							barCategoryGap={HORIZONTAL_STATS_BAR_CATEGORY_GAP}
						>
							<CartesianGrid
								stroke="rgba(100,116,139,0.15)"
								strokeDasharray="4 4"
								horizontal={false}
							/>
							<XAxis
								type="number"
								tick={{
									fill: "#94a3b8",
									fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE,
								}}
								axisLine={false}
								tickLine={false}
							/>
							<YAxis
								type="category"
								dataKey="label"
								width={HORIZONTAL_STATS_Y_AXIS_WIDTH}
								tick={{
									fill: "#e2e8f0",
									fontSize: HORIZONTAL_STATS_AXIS_FONT_SIZE,
								}}
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
								formatter={(value: number, name: string) => [
									formatNumber(Number(value)),
									name,
								]}
								labelFormatter={(
									label: string,
									payload: Array<{ payload?: { meta?: string } }>,
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
										fill={getToneColor("critical")}
										radius={[0, 0, 0, 0]}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="high"
										stackId="risk"
										name="高危"
										fill={getToneColor("high")}
										radius={[0, 0, 0, 0]}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="medium"
										stackId="risk"
										name="中危"
										fill={getToneColor("medium")}
										radius={[0, 0, 0, 0]}
										barSize={HORIZONTAL_STATS_BAR_SIZE}
									/>
									<Bar
										dataKey="low"
										stackId="risk"
										name="低危"
										fill={getToneColor("low")}
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
								</>
							) : (
								<Bar
									dataKey="total"
									name="漏洞数量"
									fill={getToneColor(rows[0]?.segments[0]?.tone ?? "low")}
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

export default function DashboardMockPreviewCanvas() {
	const [activeView, setActiveView] = useState<DashboardPreviewViewId>("trend");
	const activeMeta = useMemo(
		() =>
			DASHBOARD_PREVIEW_VIEWS.find((view) => view.id === activeView) ??
			DASHBOARD_PREVIEW_VIEWS[0],
		[activeView],
	);
	const rows = useMemo(
		() => getPreviewLeaderboardRows(activeView),
		[activeView],
	);

	return (
		<div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.12),transparent_22%),linear-gradient(180deg,#020617_0%,#020817_52%,#030712_100%)] px-4 py-6 text-slate-100 md:px-6 xl:px-8">
			<div className="mx-auto max-w-[1600px] space-y-6">
				<PreviewHeader />
				<TaskStatusPanel />
				<div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
					<ViewSidebar activeView={activeView} onChange={setActiveView} />
					<section className="rounded-[28px] border border-slate-800/90 bg-slate-950/88 p-5 shadow-[0_18px_48px_rgba(15,23,42,0.45)]">
						{activeView === "trend" ? (
							<TrendPanel />
						) : (
							<HorizontalStatsChart
								title={activeMeta.label}
								description={activeMeta.description}
								rows={rows}
								yAxisLabel={
									activeView === "project-risk"
										? "项目名称"
										: activeView === "language-risk" ||
												activeView === "language-lines"
											? "语言类型"
											: activeView === "vulnerability-types"
												? "漏洞类型标号"
												: "类别名称"
								}
								stacked={activeView === "project-risk"}
							/>
						)}
					</section>
				</div>
			</div>
		</div>
	);
}
