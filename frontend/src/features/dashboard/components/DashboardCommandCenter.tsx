import { useMemo } from "react";
import {
	Activity,
	AlertTriangle,
	Bug,
	Clock3,
	Radar,
	ShieldAlert,
	Target,
} from "lucide-react";
import {
	Area,
	AreaChart,
	CartesianGrid,
	Cell,
	Pie,
	PieChart,
	RadialBar,
	RadialBarChart,
	Scatter,
	ScatterChart,
	Tooltip,
	Treemap,
	XAxis,
	YAxis,
	ZAxis,
} from "recharts";
import {
	ChartContainer,
	ChartTooltip,
	ChartTooltipContent,
} from "@/components/ui/chart";
import type {
	DashboardCweDistributionItem,
	DashboardDailyActivityItem,
	DashboardLanguageRiskItem,
	DashboardSnapshotResponse,
} from "@/shared/types";

type RangeDays = 7 | 14 | 30;

interface DashboardCommandCenterProps {
	snapshot: DashboardSnapshotResponse;
	rangeDays: RangeDays;
	onRangeDaysChange: (value: RangeDays) => void;
}

const RANGE_OPTIONS: RangeDays[] = [7, 14, 30];

const ENGINE_LABELS: Record<string, string> = {
	agent: "Agent 审计",
	opengrep: "Opengrep",
	gitleaks: "Gitleaks",
	bandit: "Bandit",
	phpstan: "PHPStan",
};

const ENGINE_COLORS: Record<string, string> = {
	agent: "#f97316",
	opengrep: "#38bdf8",
	gitleaks: "#14b8a6",
	bandit: "#f43f5e",
	phpstan: "#a855f7",
};

const STATUS_COLORS: Record<string, string> = {
	completed: "#34d399",
	running: "#38bdf8",
	failed: "#fb7185",
	interrupted: "#f97316",
	cancelled: "#94a3b8",
	pending: "#facc15",
};

const HEATMAP_TONES = [
	"bg-slate-900/40 text-slate-200",
	"bg-cyan-950/80 text-cyan-100",
	"bg-cyan-800/80 text-cyan-50",
	"bg-emerald-600/80 text-emerald-50",
	"bg-amber-500/85 text-amber-950",
	"bg-rose-500/90 text-rose-50",
];

function formatNumber(value: number | null | undefined) {
	return Math.max(Number(value || 0), 0).toLocaleString();
}

function formatPercent(value: number | null | undefined) {
	return `${(Math.max(Number(value || 0), 0) * 100).toFixed(1)}%`;
}

function formatDurationShort(durationMs: number | null | undefined) {
	const totalSeconds = Math.max(Math.floor(Number(durationMs || 0) / 1000), 0);
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = totalSeconds % 60;
	if (minutes <= 0) return `${seconds}s`;
	return `${minutes}m ${seconds}s`;
}

function formatDateTime(value: string | null | undefined) {
	if (!value) return "暂无";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "暂无";
	return date.toLocaleString("zh-CN", {
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
}

function normalizeTrendSeries(items: DashboardDailyActivityItem[]) {
	return items.map((item) => ({
		date: item.date,
		completedScans: Math.max(Number(item.completed_scans || 0), 0),
		agent: Math.max(Number(item.agent_findings || 0), 0),
		opengrep: Math.max(Number(item.opengrep_findings || 0), 0),
		gitleaks: Math.max(Number(item.gitleaks_findings || 0), 0),
		bandit: Math.max(Number(item.bandit_findings || 0), 0),
		phpstan: Math.max(Number(item.phpstan_findings || 0), 0),
	}));
}

function computeMiniTrendValues(items: DashboardDailyActivityItem[], key: "completed_scans" | "agent_findings" | "opengrep_findings" | "gitleaks_findings" | "bandit_findings" | "phpstan_findings") {
	return items.map((item) => Math.max(Number(item[key] || 0), 0));
}

function DashboardSection({
	title,
	description,
	icon,
	children,
	panel,
	className,
}: {
	title: string;
	description?: string;
	icon: React.ReactNode;
	children: React.ReactNode;
	panel: string;
	className?: string;
}) {
	return (
		<section
			data-panel={panel}
			className={`cyber-card rounded-3xl border border-border/60 bg-slate-950/70 p-5 shadow-2xl shadow-cyan-950/20 ${className || ""}`}
		>
			<div className="mb-4 flex items-start justify-between gap-4">
				<div>
					<p className="text-xs uppercase tracking-[0.28em] text-cyan-300/70">
						{title}
					</p>
					{description ? (
						<p className="mt-2 text-sm text-slate-400">{description}</p>
					) : null}
				</div>
				<div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-3 text-cyan-200">
					{icon}
				</div>
			</div>
			{children}
		</section>
	);
}

function SummaryStrip({
	snapshot,
}: {
	snapshot: DashboardSnapshotResponse;
}) {
	const summary = snapshot.summary;
	const cards = [
		{
			label: "项目总数",
			value: formatNumber(summary.total_projects),
			// subtitle: `窗口内已扫描 ${formatNumber(summary.window_scanned_projects)} 个项目`,
			accent: "text-cyan-200",
			values: computeMiniTrendValues(snapshot.daily_activity, "completed_scans"),
		},
		{
			label: "当前有效风险",
			value: formatNumber(summary.current_effective_findings),
			// subtitle: `窗口新增 ${formatNumber(summary.window_new_effective_findings)} 项`,
			accent: "text-amber-200",
			values: snapshot.daily_activity.map((item) => {
				const total =
					Number(item.agent_findings || 0) +
					Number(item.opengrep_findings || 0) +
					Number(item.gitleaks_findings || 0) +
					Number(item.bandit_findings || 0) +
					Number(item.phpstan_findings || 0);
				return Math.max(total, 0);
			}),
		},
		{
			label: "已验证风险",
			value: formatNumber(summary.current_verified_findings),
			// subtitle: `窗口已验证 ${formatNumber(summary.window_verified_findings)} 项`,
			accent: "text-emerald-200",
			values: computeMiniTrendValues(snapshot.daily_activity, "agent_findings"),
		},
		{
			label: "误报率",
			value: formatPercent(summary.false_positive_rate),
			// subtitle: `窗口误报率 ${formatPercent(summary.window_false_positive_rate)}`,
			accent: "text-rose-200",
			values: computeMiniTrendValues(snapshot.daily_activity, "opengrep_findings"),
		},
		{
			label: "扫描成功率",
			value: formatPercent(summary.scan_success_rate),
			// subtitle: `窗口成功率 ${formatPercent(summary.window_scan_success_rate)}`,
			accent: "text-sky-200",
			values: computeMiniTrendValues(snapshot.daily_activity, "gitleaks_findings"),
		},
		{
			label: "平均扫描耗时",
			value: formatDurationShort(summary.avg_scan_duration_ms),
			// subtitle: `窗口平均 ${formatDurationShort(summary.window_avg_scan_duration_ms)}`,
			accent: "text-violet-200",
			values: computeMiniTrendValues(snapshot.daily_activity, "phpstan_findings"),
		},
	];

	return (
		<div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
			{cards.map((card) => (
				<div
					key={card.label}
					className="rounded-3xl border border-border/60 bg-slate-950/80 p-4 shadow-lg shadow-cyan-950/10"
				>
					<p className="text-[11px] uppercase tracking-[0.28em] text-slate-400">
						{card.label}
					</p>
					<p className={`mt-3 text-3xl font-semibold ${card.accent}`}>
						{card.value}
					</p>
					{/* <SummaryMiniTrend values={card.values} /> */}
				</div>
			))}
		</div>
	);
}

function VerificationFunnel({
	raw,
	effective,
	verified,
	falsePositive,
}: {
	raw: number;
	effective: number;
	verified: number;
	falsePositive: number;
}) {
	const maxValue = Math.max(raw, effective, verified, 1);
	const items = [
		{ label: "原始发现", value: raw, color: "bg-cyan-500/70" },
		{ label: "有效风险", value: effective, color: "bg-amber-500/80" },
		{ label: "已验证", value: verified, color: "bg-emerald-500/80" },
	];

	return (
		<div className="space-y-3">
			{items.map((item, index) => (
				<div key={item.label}>
					<div className="mb-1 flex items-center justify-between text-sm text-slate-300">
						<span>{item.label}</span>
						<span>{formatNumber(item.value)}</span>
					</div>
					<div className="rounded-full bg-slate-900/70 px-1 py-1">
						<div
							className={`${item.color} mx-auto h-9 rounded-full transition-all`}
							style={{
								width: `${Math.max((item.value / maxValue) * (100 - index * 12), 24)}%`,
							}}
						/>
					</div>
				</div>
			))}
			<div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
				误报数：{formatNumber(falsePositive)}
			</div>
		</div>
	);
}

function TaskStatusRing({
	breakdown,
}: {
	breakdown: DashboardSnapshotResponse["task_status_breakdown"];
}) {
	const data = [
		{ name: "completed", label: "已完成", value: breakdown.completed },
		{ name: "running", label: "运行中", value: breakdown.running },
		{ name: "failed", label: "失败", value: breakdown.failed },
		{ name: "interrupted", label: "中断", value: breakdown.interrupted },
		{ name: "cancelled", label: "取消", value: breakdown.cancelled },
		{ name: "pending", label: "等待中", value: breakdown.pending },
	].filter((item) => item.value > 0);

	if (data.length === 0) {
		return <p className="text-sm text-slate-400">暂无任务状态数据</p>;
	}

	return (
		<div className="space-y-3">
			<ChartContainer
				className="h-56 w-full"
				config={{
					completed: { label: "已完成", color: STATUS_COLORS.completed },
					running: { label: "运行中", color: STATUS_COLORS.running },
					failed: { label: "失败", color: STATUS_COLORS.failed },
					interrupted: { label: "中断", color: STATUS_COLORS.interrupted },
					cancelled: { label: "取消", color: STATUS_COLORS.cancelled },
					pending: { label: "等待中", color: STATUS_COLORS.pending },
				}}
			>
				<PieChart>
					<Pie
						data={data}
						dataKey="value"
						nameKey="name"
						cx="50%"
						cy="50%"
						innerRadius={54}
						outerRadius={82}
						paddingAngle={3}
					>
						{data.map((item) => (
							<Cell key={item.name} fill={STATUS_COLORS[item.name]} />
						))}
					</Pie>
					<ChartTooltip content={<ChartTooltipContent labelKey="label" />} />
				</PieChart>
			</ChartContainer>
			<div className="grid grid-cols-2 gap-2 text-sm text-slate-300">
				{data.map((item) => (
					<div key={item.name} className="flex items-center gap-2 rounded-2xl border border-border/60 bg-slate-900/60 px-3 py-2">
						<span
							className="h-2.5 w-2.5 rounded-full"
							style={{ backgroundColor: STATUS_COLORS[item.name] }}
						/>
						<span>{item.label}</span>
						<span className="ml-auto font-medium text-white">{formatNumber(item.value)}</span>
					</div>
				))}
			</div>
		</div>
	);
}

function RiskHeatmap({ items }: { items: DashboardLanguageRiskItem[] }) {
	if (items.length === 0) {
		return <p className="text-sm text-slate-400">暂无语言风险数据</p>;
	}

	const maxValue = Math.max(...items.map((item) => item.findings_per_kloc), 0);

	return (
		<div className="grid gap-3 md:grid-cols-2">
			{items.map((item) => {
				const intensity =
					maxValue <= 0 ? 0 : Math.min(Math.floor((item.findings_per_kloc / maxValue) * 5), 5);
				return (
					<div
						key={item.language}
						className={`rounded-3xl border border-border/60 px-4 py-4 ${HEATMAP_TONES[intensity]}`}
					>
						<div className="flex items-start justify-between gap-3">
							<div>
								<p className="text-base font-semibold">{item.language}</p>
								<p className="mt-1 text-xs opacity-80">
									{formatNumber(item.project_count)} 个项目 · {formatNumber(item.loc_number)} LOC
								</p>
							</div>
							<div className="text-right">
								<p className="text-2xl font-semibold">{item.findings_per_kloc.toFixed(2)}</p>
								<p className="text-xs uppercase tracking-[0.24em] opacity-75">per KLOC</p>
							</div>
						</div>
						<div className="mt-4 grid grid-cols-2 gap-2 text-xs">
							<div className="rounded-2xl bg-black/15 px-3 py-2">
								<p className="opacity-80">有效风险</p>
								<p className="mt-1 text-lg font-semibold">{formatNumber(item.effective_findings)}</p>
							</div>
							<div className="rounded-2xl bg-black/15 px-3 py-2">
								<p className="opacity-80">已验证</p>
								<p className="mt-1 text-lg font-semibold">{formatNumber(item.verified_findings)}</p>
							</div>
							<div className="rounded-2xl bg-black/15 px-3 py-2">
								<p className="opacity-80">误报</p>
								<p className="mt-1 text-lg font-semibold">{formatNumber(item.false_positive_count)}</p>
							</div>
							<div className="rounded-2xl bg-black/15 px-3 py-2">
								<p className="opacity-80">高/中置信规则</p>
								<p className="mt-1 text-lg font-semibold">
									{formatNumber(item.rules_high)} / {formatNumber(item.rules_medium)}
								</p>
							</div>
						</div>
					</div>
				);
			})}
		</div>
	);
}

function AttackSurfaceTreemap({ items }: { items: DashboardCweDistributionItem[] }) {
	const data = items.map((item) => ({
		name: item.cwe_id,
		label: item.cwe_name,
		size: item.total_findings,
	}));

	if (data.length === 0) {
		return <p className="text-sm text-slate-400">暂无 CWE 攻击面数据</p>;
	}

	return (
		<div className="space-y-4">
			<ChartContainer
				className="h-72 w-full"
				config={{
					total: { label: "发现总数", color: "#8b5cf6" },
				}}
			>
				<Treemap
					data={data}
					dataKey="size"
					stroke="rgba(15,23,42,0.35)"
					fill="#8b5cf6"
				/>
			</ChartContainer>
			<div className="grid gap-2 text-sm text-slate-300">
				{items.map((item) => (
					<div
						key={item.cwe_id}
						className="flex items-center justify-between rounded-2xl border border-border/60 bg-slate-900/60 px-3 py-2"
					>
						<div>
							<p className="font-medium text-white">{item.cwe_id}</p>
							<p className="text-xs text-slate-400">{item.cwe_name}</p>
						</div>
						<p className="text-base font-semibold text-violet-100">
							{formatNumber(item.total_findings)}
						</p>
					</div>
				))}
			</div>
		</div>
	);
}

export default function DashboardCommandCenter({
	snapshot,
	rangeDays,
	onRangeDaysChange,
}: DashboardCommandCenterProps) {
	const trendData = useMemo(
		() => normalizeTrendSeries(snapshot.daily_activity || []),
		[snapshot.daily_activity],
	);
	const trendHasData = trendData.length > 0;

	const hotspotScatter = useMemo(
		() =>
			(snapshot.project_hotspots || []).map((item) => ({
				name: item.project_name,
				effectiveFindings: Math.max(Number(item.effective_findings || 0), 0),
				scanRunsWindow: Math.max(Number(item.scan_runs_window || 0), 0),
				riskScore: Math.max(Number(item.risk_score || 0), 0),
				verifiedFindings: Math.max(Number(item.verified_findings || 0), 0),
				dominantLanguage: item.dominant_language || "unknown",
				falsePositiveRate: Math.max(Number(item.false_positive_rate || 0), 0),
				topEngine: ENGINE_LABELS[item.top_engine] || item.top_engine || "未知引擎",
			})),
		[snapshot.project_hotspots],
	);

	return (
		<div className="space-y-6">
			<header className="rounded-[2rem] border border-border/70 bg-slate-950/85 px-6 py-6 shadow-2xl shadow-cyan-950/20">
				<div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
					<div>
						<h1 className="mt-3 text-3xl font-semibold text-slate-50">
							漏洞扫描统计
						</h1>
					</div>
					<div className="flex flex-wrap items-center gap-2">
						{RANGE_OPTIONS.map((option) => (
							<button
								key={option}
								type="button"
								onClick={() => onRangeDaysChange(option)}
								className={
									rangeDays === option
										? "rounded-full border border-cyan-400/60 bg-cyan-500/20 px-4 py-2 text-sm font-medium text-cyan-100"
										: "rounded-full border border-border/70 bg-slate-900/80 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-cyan-400/40 hover:text-cyan-100"
								}
							>
								{option} 天
							</button>
						))}
					</div>
				</div>
			</header>

			<SummaryStrip snapshot={snapshot} />

			<div className="grid gap-1 xl:grid-cols-12">
				<DashboardSection
					className="xl:col-span-7"
					panel="trend"
					title="漏洞态势趋势"
					description={`过去 ${rangeDays} 天内各扫描引擎的有效风险发现和扫描活跃度。`}
					icon={<Activity className="h-5 w-5" />}
				>
					{trendHasData ? (
						<ChartContainer
							className="h-80 w-full"
							config={{
								agent: { label: "Agent", color: ENGINE_COLORS.agent },
								opengrep: { label: "Opengrep", color: ENGINE_COLORS.opengrep },
								gitleaks: { label: "Gitleaks", color: ENGINE_COLORS.gitleaks },
								bandit: { label: "Bandit", color: ENGINE_COLORS.bandit },
								phpstan: { label: "PHPStan", color: ENGINE_COLORS.phpstan },
							}}
						>
							<AreaChart data={trendData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
								<CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
								<XAxis dataKey="date" />
								<YAxis />
								<ChartTooltip content={<ChartTooltipContent />} />
								<Area type="monotone" dataKey="agent" stackId="findings" stroke={ENGINE_COLORS.agent} fill={ENGINE_COLORS.agent} fillOpacity={0.3} />
								<Area type="monotone" dataKey="opengrep" stackId="findings" stroke={ENGINE_COLORS.opengrep} fill={ENGINE_COLORS.opengrep} fillOpacity={0.28} />
								<Area type="monotone" dataKey="gitleaks" stackId="findings" stroke={ENGINE_COLORS.gitleaks} fill={ENGINE_COLORS.gitleaks} fillOpacity={0.28} />
								<Area type="monotone" dataKey="bandit" stackId="findings" stroke={ENGINE_COLORS.bandit} fill={ENGINE_COLORS.bandit} fillOpacity={0.26} />
								<Area type="monotone" dataKey="phpstan" stackId="findings" stroke={ENGINE_COLORS.phpstan} fill={ENGINE_COLORS.phpstan} fillOpacity={0.26} />
							</AreaChart>
						</ChartContainer>
					) : (
						<p className="text-sm text-slate-400">暂无趋势数据</p>
					)}
				</DashboardSection>
				<DashboardSection
						panel="funnel"
						title="验证漏斗"
						description={`窗口内原始发现、有效风险和已验证结果的收敛情况。`}
						icon={<Target className="h-5 w-120" />}
					>
						<VerificationFunnel
							raw={snapshot.verification_funnel.raw_findings}
							effective={snapshot.verification_funnel.effective_findings}
							verified={snapshot.verification_funnel.verified_findings}
							falsePositive={snapshot.verification_funnel.false_positive_count}
						/>
				</DashboardSection>
				<DashboardSection
					className="xl:col-span-7"
					panel="hotspots"
					title="风险热点项目"
					description="按风险加权排序的项目视图，横轴为窗口扫描次数，纵轴为有效风险数，气泡大小为已验证数。"
					icon={<Radar className="h-5 w-5" />}
				>
					{hotspotScatter.length > 0 ? (
						<ChartContainer
							className="h-80 w-full"
							config={{
								riskScore: { label: "风险分数", color: "#22d3ee" },
							}}
						>
							<ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
								<CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
								<XAxis type="number" dataKey="scanRunsWindow" name="窗口扫描次数" />
								<YAxis type="number" dataKey="effectiveFindings" name="有效风险数" />
								<ZAxis type="number" dataKey="verifiedFindings" range={[120, 620]} />
								<Tooltip
									cursor={{ strokeDasharray: "4 4" }}
									content={({ active, payload }) => {
										if (!active || !payload?.length) return null;
										const row = payload[0]?.payload as (typeof hotspotScatter)[number] | undefined;
										if (!row) return null;
										return (
											<div className="rounded-2xl border border-border/70 bg-slate-950/95 px-3 py-2 text-xs text-slate-100 shadow-xl">
												<p className="font-semibold text-cyan-100">{row.name}</p>
												<p className="mt-1">风险分数：{row.riskScore.toFixed(1)}</p>
												<p>有效风险：{formatNumber(row.effectiveFindings)}</p>
												<p>已验证：{formatNumber(row.verifiedFindings)}</p>
												<p>误报率：{formatPercent(row.falsePositiveRate)}</p>
												<p>主语言：{row.dominantLanguage}</p>
												<p>主引擎：{row.topEngine}</p>
											</div>
										);
									}}
								/>
								<Scatter data={hotspotScatter} fill="#22d3ee" />
							</ScatterChart>
						</ChartContainer>
					) : (
						<p className="text-sm text-slate-400">暂无热点项目</p>
					)}
				</DashboardSection>	
				

					<DashboardSection
						panel="status"
						title="任务状态"
						description="全量任务分布，便于快速识别失败、中断和运行中队列。"
						icon={<AlertTriangle className="h-5 w-5" />}
					>
						<TaskStatusRing breakdown={snapshot.task_status_breakdown} />
					</DashboardSection>
				{/* <div className="grid gap-4 xl:col-span-4">
					
				</div> */}
			</div>

			<div className="grid gap-4 xl:grid-cols-12">
				

				<DashboardSection
					className="xl:col-span-5"
					panel="engines"
					title="引擎贡献"
					description={`过去 ${rangeDays} 天内各引擎的扫描成功率、有效发现和平均耗时。`}
					icon={<Bug className="h-5 w-5" />}
				>
					{snapshot.engine_breakdown.length > 0 ? (
						<div className="space-y-4">
							<ChartContainer
								className="h-72 w-full"
								config={snapshot.engine_breakdown.reduce<Record<string, { label: string; color: string }>>(
									(accumulator, item) => {
										accumulator[item.engine] = {
											label: ENGINE_LABELS[item.engine] || item.engine,
											color: ENGINE_COLORS[item.engine] || "#38bdf8",
										};
										return accumulator;
									},
									{},
								)}
							>
								<RadialBarChart
									innerRadius="24%"
									outerRadius="92%"
									barSize={12}
									data={snapshot.engine_breakdown.map((item) => ({
										...item,
										fill: ENGINE_COLORS[item.engine] || "#38bdf8",
									}))}
									startAngle={180}
									endAngle={-180}
								>
									<ChartTooltip content={<ChartTooltipContent />} />
									<RadialBar dataKey="effective_findings" background />
								</RadialBarChart>
							</ChartContainer>
							<div className="space-y-2">
								{snapshot.engine_breakdown.map((item) => (
									<div
										key={item.engine}
										className="rounded-2xl border border-border/60 bg-slate-900/60 px-4 py-3"
									>
										<div className="flex items-center justify-between gap-3">
											<div className="flex items-center gap-2">
												<span
													className="h-2.5 w-2.5 rounded-full"
													style={{
														backgroundColor: ENGINE_COLORS[item.engine] || "#38bdf8",
													}}
												/>
												<p className="font-medium text-white">
													{ENGINE_LABELS[item.engine] || item.engine}
												</p>
											</div>
											<p className="text-sm text-slate-400">
												成功率 {formatPercent(item.success_rate)}
											</p>
										</div>
										<div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-300">
											<div>完成扫描：{formatNumber(item.completed_scans)}</div>
											<div>有效风险：{formatNumber(item.effective_findings)}</div>
											<div>已验证：{formatNumber(item.verified_findings)}</div>
											<div>误报：{formatNumber(item.false_positive_count)}</div>
											<div className="col-span-2">
												平均耗时：{formatDurationShort(item.avg_scan_duration_ms)}
											</div>
										</div>
									</div>
								))}
							</div>
						</div>
					) : (
						<p className="text-sm text-slate-400">暂无引擎贡献数据</p>
					)}
				</DashboardSection>
			</div>

			<div className="grid gap-4 xl:grid-cols-12">
				<DashboardSection
					className="xl:col-span-5"
					panel="language-risk"
					title="语言风险热力"
					description="按语言聚合有效风险密度、已验证结果和误报质量。"
					icon={<ShieldAlert className="h-5 w-5" />}
				>
					<RiskHeatmap items={snapshot.language_risk || []} />
				</DashboardSection>

				<DashboardSection
					className="xl:col-span-7"
					panel="cwe"
					title="CWE 攻击面"
					description="具备 CWE 语义的引擎发现分布，用于观察攻击面聚集。"
					icon={<Target className="h-5 w-5" />}
				>
					<AttackSurfaceTreemap items={snapshot.cwe_distribution || []} />
				</DashboardSection>
			</div>

			<DashboardSection
				panel="actions"
				title="行动清单"
				description=""
				icon={<Clock3 className="h-5 w-5" />}
			>
				{(snapshot.project_hotspots || []).length > 0 ? (
					<div className="grid gap-3 lg:grid-cols-2">
						{snapshot.project_hotspots.map((item, index) => (
							<div
								key={item.project_id}
								className="rounded-3xl border border-border/60 bg-slate-900/70 p-4"
							>
								<div className="flex items-start justify-between gap-3">
									<div>
										<p className="text-xs uppercase tracking-[0.28em] text-cyan-300/70">
											#{index + 1} 风险项目
										</p>
										<p className="mt-2 text-xl font-semibold text-slate-50">
											{item.project_name}
										</p>
										<p className="mt-2 text-sm text-slate-400">
											主语言 {item.dominant_language} · 主引擎{" "}
											{ENGINE_LABELS[item.top_engine] || item.top_engine}
										</p>
									</div>
									<div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-right">
										<p className="text-xs uppercase tracking-[0.22em] text-amber-200/70">
											风险分数
										</p>
										<p className="mt-1 text-2xl font-semibold text-amber-100">
											{item.risk_score.toFixed(1)}
										</p>
									</div>
								</div>
								<div className="mt-4 grid grid-cols-2 gap-2 text-sm text-slate-300">
									<div className="rounded-2xl bg-slate-950/70 px-3 py-2">
										<p className="text-slate-500">有效风险</p>
										<p className="mt-1 text-lg font-medium text-white">
											{formatNumber(item.effective_findings)}
										</p>
									</div>
									<div className="rounded-2xl bg-slate-950/70 px-3 py-2">
										<p className="text-slate-500">已验证</p>
										<p className="mt-1 text-lg font-medium text-white">
											{formatNumber(item.verified_findings)}
										</p>
									</div>
									<div className="rounded-2xl bg-slate-950/70 px-3 py-2">
										<p className="text-slate-500">误报率</p>
										<p className="mt-1 text-lg font-medium text-white">
											{formatPercent(item.false_positive_rate)}
										</p>
									</div>
									<div className="rounded-2xl bg-slate-950/70 px-3 py-2">
										<p className="text-slate-500">最近扫描</p>
										<p className="mt-1 text-lg font-medium text-white">
											{formatDateTime(item.last_scan_at)}
										</p>
									</div>
								</div>
							</div>
						))}
					</div>
				) : (
					<p className="text-sm text-slate-400">暂无热点项目</p>
				)}
			</DashboardSection>
		</div>
	);
}
