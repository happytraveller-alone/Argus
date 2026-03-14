import { useMemo } from "react";
import { Activity, AlertTriangle, Bug } from "lucide-react";
import {
	Area,
	AreaChart,
	Bar,
	BarChart,
	CartesianGrid,
	Cell,
	Legend,
	PolarAngleAxis,
	PolarGrid,
	PolarRadiusAxis,
	Radar,
	RadarChart,
	ResponsiveContainer,
	Scatter,
	ScatterChart,
	Treemap,
	Tooltip,
	XAxis,
	YAxis,
	ZAxis,
} from "recharts";
import type {
	DashboardCweDistributionItem,
	DashboardRuleConfidenceItem,
} from "@/shared/types";
import type {
	ProjectScanRunsChartItem,
	ProjectVulnsChartItem,
} from "@/features/dashboard/services/projectScanStats";

type RotatedXAxisTickProps = {
	x?: number;
	y?: number;
	payload?: {
		value?: number | string;
	};
};

type TreemapContentProps = {
	x?: number;
	y?: number;
	width?: number;
	height?: number;
	name?: number | string;
	value?: number | string;
	fill?: string;
};

type ConfidenceChartItem = {
	confidence: DashboardRuleConfidenceItem["confidence"];
	label: string;
	totalRules: number;
	enabledRules: number;
	disabledRules: number;
};

interface DashboardChartsPanelsProps {
	ruleConfidenceData: DashboardRuleConfidenceItem[];
	cweDistributionData: DashboardCweDistributionItem[];
	projectScanRunsData: ProjectScanRunsChartItem[];
	projectVulnsData: ProjectVulnsChartItem[];
	translate: (key: string, fallback?: string) => string;
}

const formatTick = (value: number | string) =>
	Number(value || 0).toLocaleString();

const AXIS_TICK_STYLE = {
	fontSize: 14,
	fill: "hsl(var(--muted-foreground))",
	fontWeight: 500,
};
const AXIS_LINE_STYLE = { stroke: "hsl(var(--border) / 0.65)" };
const AXIS_TICK_LINE_STYLE = { stroke: "hsl(var(--border) / 0.55)" };
const GRID_STROKE = "hsl(var(--border) / 0.35)";
const LEGEND_STYLE = {
	fontSize: 14,
	color: "hsl(var(--muted-foreground))",
};
const TOOLTIP_STYLE = {
	fontSize: 13,
	color: "hsl(var(--foreground))",
	borderColor: "hsl(var(--border) / 0.7)",
	backgroundColor: "hsl(var(--background) / 0.96)",
};
const CHART_COLORS = {
	staticRuns: "#38bdf8",
	intelligentRuns: "#34d399",
	hybridRuns: "#a78bfa",
	totalVulns: "#fbbf24",
	enabledRules: "#38bdf8",
	disabledRules: "#64748b",
	highConfidence: "#f59e0b",
	mediumConfidence: "#38bdf8",
	lowConfidence: "#34d399",
	unspecifiedConfidence: "#94a3b8",
	cwePrimary: "#a78bfa",
	cweSecondary: "#38bdf8",
	agentFindings: "#f472b6",
	opengrepFindings: "#818cf8",
	tooltipStatic: "#7dd3fc",
	tooltipIntelligent: "#6ee7b7",
	tooltipHybrid: "#c4b5fd",
};

const TREEMAP_COLORS = [
	"#a78bfa",
	"#818cf8",
	"#60a5fa",
	"#38bdf8",
	"#34d399",
	"#4ade80",
	"#facc15",
	"#fb923c",
	"#f472b6",
	"#e879f9",
	"#22c55e",
	"#f97316",
];

function RotatedXAxisTick({ x = 0, y = 0, payload }: RotatedXAxisTickProps) {
	return (
		<g transform={`translate(${x},${y})`}>
			<text
				dy={16}
				textAnchor="end"
				fill={AXIS_TICK_STYLE.fill}
				fontSize={AXIS_TICK_STYLE.fontSize}
				fontWeight={AXIS_TICK_STYLE.fontWeight}
				transform="rotate(-35)"
			>
				{String(payload?.value || "")}
			</text>
		</g>
	);
}

function CustomTreemapContent({
	x = 0,
	y = 0,
	width = 0,
	height = 0,
	name,
	value,
	fill,
}: TreemapContentProps) {
	if (!width || !height || width < 22 || height < 22) return null;

	return (
		<g>
			<rect
				x={x}
				y={y}
				width={width}
				height={height}
				fill={fill || CHART_COLORS.cwePrimary}
				fillOpacity={0.88}
				rx={4}
			/>
			{width > 56 && height > 34 ? (
				<>
					<text
						x={x + width / 2}
						y={y + height / 2 - 6}
						textAnchor="middle"
						fill="#ffffff"
						fontSize={11}
						fontWeight={700}
					>
						{name}
					</text>
					<text
						x={x + width / 2}
						y={y + height / 2 + 10}
						textAnchor="middle"
						fill="rgba(255,255,255,0.85)"
						fontSize={10}
					>
						{value}
					</text>
				</>
			) : null}
		</g>
	);
}

export default function DashboardChartsPanels({
	ruleConfidenceData,
	cweDistributionData,
	projectScanRunsData,
	projectVulnsData,
	translate,
}: DashboardChartsPanelsProps) {
	const confidenceChartData = useMemo<ConfidenceChartItem[]>(
		() =>
			ruleConfidenceData.map((item) => ({
				confidence: item.confidence,
				label: translate(
					`dashboard.confidence.${item.confidence.toLowerCase()}`,
					item.confidence,
				),
				totalRules: Math.max(Number(item.total_rules || 0), 0),
				enabledRules: Math.max(Number(item.enabled_rules || 0), 0),
				disabledRules: Math.max(
					Math.max(Number(item.total_rules || 0), 0) -
						Math.max(Number(item.enabled_rules || 0), 0),
					0,
				),
			})),
		[ruleConfidenceData, translate],
	);

	const confidenceChartMax = useMemo(() => {
		if (confidenceChartData.length === 0) return 1;
		return Math.max(
			1,
			...confidenceChartData.map((item) => item.totalRules),
		);
	}, [confidenceChartData]);

	const cweBarData = useMemo(
		() =>
			cweDistributionData.map((item) => ({
				cweId: item.cwe_id,
				cweName: item.cwe_name || item.cwe_id,
				totalFindings: Math.max(Number(item.total_findings || 0), 0),
				opengrepFindings: Math.max(Number(item.opengrep_findings || 0), 0),
				agentFindings: Math.max(Number(item.agent_findings || 0), 0),
			})),
		[cweDistributionData],
	);

	const cweChartHeight = useMemo(() => {
		const rowCount = Math.max(1, cweBarData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [cweBarData.length]);

	const projectScanRunsChartMax = useMemo(() => {
		if (projectScanRunsData.length === 0) return 1;
		return Math.max(1, ...projectScanRunsData.map((item) => item.totalRuns));
	}, [projectScanRunsData]);

	const projectVulnsChartMax = useMemo(() => {
		if (projectVulnsData.length === 0) return 1;
		return Math.max(1, ...projectVulnsData.map((item) => item.totalVulns));
	}, [projectVulnsData]);

	const projectScanRunsChartHeight = useMemo(() => {
		const rowCount = Math.max(1, projectScanRunsData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [projectScanRunsData.length]);

	const projectVulnsChartHeight = useMemo(() => {
		const rowCount = Math.max(1, projectVulnsData.length);
		return Math.min(520, Math.max(280, rowCount * 36));
	}, [projectVulnsData.length]);

	const renderProjectVulnsTooltip = (payload: {
		active?: boolean;
		payload?: Array<{ payload?: ProjectVulnsChartItem }>;
	}) => {
		if (
			!payload?.active ||
			!Array.isArray(payload.payload) ||
			payload.payload.length === 0
		) {
			return null;
		}
		const row = payload.payload[0]?.payload;
		if (!row) return null;

		return (
			<div className="rounded border border-border bg-background/95 px-3 py-2 text-xs shadow-xl">
				<p className="font-semibold text-foreground">{row.projectName}</p>
				<p className="mt-1 text-muted-foreground">
					{translate("dashboard.totalVulns")}：{formatTick(row.totalVulns)}
				</p>
				<div className="mt-1 space-y-0.5">
					<p style={{ color: CHART_COLORS.tooltipStatic }}>
						{translate("dashboard.staticScan")}：{formatTick(row.staticVulns)}
					</p>
					<p style={{ color: CHART_COLORS.tooltipIntelligent }}>
						{translate("dashboard.intelligentScan")}：
						{formatTick(row.intelligentVulns)}
					</p>
					<p style={{ color: CHART_COLORS.tooltipHybrid }}>
						{translate("dashboard.hybridScan")}：{formatTick(row.hybridVulns)}
					</p>
				</div>
			</div>
		);
	};

	return (
		<>
			<div className="grid grid-cols-1 xl:grid-cols-2 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Activity className="w-5 h-5 text-emerald-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">
									{translate("dashboard.projectScanRunsChartTitle")}
								</h3>
								<span className="text-sm text-muted-foreground">
									{translate("dashboard.projectCount", "项目数")}：
									{projectScanRunsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.projectScanRunsChartSubtitle",
									"按项目展示静态、智能与混合扫描累计次数（Top 10）",
								)}
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectScanRunsChartHeight }}
					>
						{projectScanRunsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noProjectScanRunsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={projectScanRunsData}
									layout="horizontal"
									margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="category"
										dataKey="projectName"
										tick={<RotatedXAxisTick />}
										interval={0}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="number"
										domain={[0, projectScanRunsChartMax]}
										allowDecimals={false}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip contentStyle={TOOLTIP_STYLE} />
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Bar
										dataKey="staticRuns"
										stackId="runs"
										fill={CHART_COLORS.staticRuns}
										name={translate("dashboard.staticScan")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										dataKey="intelligentRuns"
										stackId="runs"
										fill={CHART_COLORS.intelligentRuns}
										name={translate("dashboard.intelligentScan")}
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										dataKey="hybridRuns"
										stackId="runs"
										fill={CHART_COLORS.hybridRuns}
										name={translate("dashboard.hybridScan")}
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
									{translate("dashboard.projectVulnsChartTitle")}
								</h3>
								<span className="text-sm text-muted-foreground">
									{translate("dashboard.projectCount", "项目数")}：
									{projectVulnsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.projectVulnsChartSubtitle",
									"按项目展示真实漏洞总量（Top 10）",
								)}
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectVulnsChartHeight }}
					>
						{projectVulnsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noProjectVulnsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={projectVulnsData}
									layout="horizontal"
									margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="category"
										dataKey="projectName"
										tick={<RotatedXAxisTick />}
										interval={0}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="number"
										domain={[0, projectVulnsChartMax]}
										allowDecimals={false}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip content={renderProjectVulnsTooltip} />
									<Bar
										dataKey="totalVulns"
										fill={CHART_COLORS.totalVulns}
										name={translate("dashboard.totalVulns")}
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
						<AlertTriangle className="w-5 h-5 text-sky-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">
									{translate(
										"dashboard.ruleConfidenceChartTitle",
										"规则置信度",
									)}
								</h3>
								<span className="text-sm text-muted-foreground">
									{translate("dashboard.confidenceBucketCount", "置信度分桶")}：
									{confidenceChartData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.ruleConfidenceChartSubtitle",
									"仅统计严重(ERROR)规则，对比已启用与未启用数量",
								)}
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: 320 }}
					>
						{confidenceChartData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate(
									"dashboard.noRuleConfidenceData",
									"暂无规则置信度数据",
								)}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={confidenceChartData}
									layout="horizontal"
									margin={{ top: 6, right: 6, left: 4, bottom: 26 }}
									barCategoryGap={20}
									barGap={8}
									barSize={28}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="category"
										dataKey="label"
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										tick={AXIS_TICK_STYLE}
									/>
									<YAxis
										type="number"
										domain={[0, confidenceChartMax]}
										allowDecimals={false}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										tick={AXIS_TICK_STYLE}
									/>
									<Tooltip contentStyle={TOOLTIP_STYLE} />
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Bar
										dataKey="enabledRules"
										stackId="rules"
										fill={CHART_COLORS.enabledRules}
										name={translate("dashboard.enabledRules", "已启用规则")}
										radius={[2, 2, 2, 2]}
									/>
									<Bar
										dataKey="disabledRules"
										stackId="rules"
										fill={CHART_COLORS.disabledRules}
										name={translate("dashboard.disabledRules", "未启用规则")}
										radius={[2, 2, 2, 2]}
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
								<h3 className="section-title">
									{translate(
										"dashboard.cweDistributionChartTitle",
										"CWE 漏洞类型占比",
									)}
								</h3>
								<span className="text-sm text-muted-foreground">
									{translate("dashboard.cweTypeCount", "CWE 类型数")}：
									{cweBarData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.cweDistributionChartSubtitle",
									"仅统计可稳定解析到 CWE 的真实漏洞（Top 12）",
								)}
							</p>
						</div>
					</div>

					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: 320 }}
					>
						{cweBarData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noCweDistributionData", "暂无 CWE 占比数据")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<Treemap
									data={cweBarData.map((item, index) => ({
										...item,
										name: item.cweId,
										size: item.totalFindings,
										fill: TREEMAP_COLORS[index % TREEMAP_COLORS.length],
									}))}
									dataKey="size"
									aspectRatio={4 / 3}
									stroke="rgba(0,0,0,0.2)"
									content={<CustomTreemapContent />}
								>
									<Tooltip
										contentStyle={TOOLTIP_STYLE}
										formatter={(value: number | string, _name, props) => [
											Number(value || 0).toLocaleString(),
											String(props?.payload?.cweName || props?.payload?.name || ""),
										]}
									/>
								</Treemap>
							</ResponsiveContainer>
						)}
					</div>
				</div>
			</div>

			<div className="grid grid-cols-1 xl:grid-cols-4 gap-4 relative z-10">
				{/* <div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Activity className="w-5 h-5 text-emerald-400" />
						<div className="w-full">
							<h3 className="section-title">
								{translate(
									"dashboard.projectScanModesChartTitle",
									"项目扫描类型分布",
								)}
							</h3>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.projectScanModesChartSubtitle",
									"各项目扫描方式对比（雷达图）",
								)}
							</p>
						</div>
					</div>
					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectScanRunsChartHeight }}
					>
						{projectScanRunsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noProjectScanRunsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<RadarChart data={projectScanRunsData}>
									<PolarGrid stroke={GRID_STROKE} />
									<PolarAngleAxis dataKey="projectName" tick={{ fontSize: 11 }} />
									<PolarRadiusAxis tick={{ fontSize: 10 }} />
									<Radar
										name={translate("dashboard.staticScan")}
										dataKey="staticRuns"
										stroke={CHART_COLORS.staticRuns}
										fill={CHART_COLORS.staticRuns}
										fillOpacity={0.25}
									/>
									<Radar
										name={translate("dashboard.intelligentScan")}
										dataKey="intelligentRuns"
										stroke={CHART_COLORS.intelligentRuns}
										fill={CHART_COLORS.intelligentRuns}
										fillOpacity={0.25}
									/>
									<Radar
										name={translate("dashboard.hybridScan")}
										dataKey="hybridRuns"
										stroke={CHART_COLORS.hybridRuns}
										fill={CHART_COLORS.hybridRuns}
										fillOpacity={0.25}
									/>
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Tooltip contentStyle={TOOLTIP_STYLE} />
								</RadarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div> */}

				{/* <div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Bug className="w-5 h-5 text-amber-400" />
						<div className="w-full">
							<h3 className="section-title">
								{translate(
									"dashboard.projectRiskScatterTitle",
									"项目漏洞风险矩阵",
								)}
							</h3>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.projectRiskScatterSubtitle",
									"X=静态漏洞 Y=智能漏洞 大小=混合漏洞",
								)}
							</p>
						</div>
					</div>
					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: projectVulnsChartHeight }}
					>
						{projectVulnsData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noProjectVulnsData")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="number"
										dataKey="staticVulns"
										name={translate("dashboard.staticScan")}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										label={{
											value: translate("dashboard.staticScan"),
											position: "insideBottom",
											offset: -4,
											fontSize: 11,
										}}
									/>
									<YAxis
										type="number"
										dataKey="intelligentVulns"
										name={translate("dashboard.intelligentScan")}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										label={{
											value: translate("dashboard.intelligentScan"),
											angle: -90,
											position: "insideLeft",
											fontSize: 11,
										}}
									/>
									<ZAxis
										type="number"
										dataKey="hybridVulns"
										range={[60, 400]}
										name={translate("dashboard.hybridScan")}
									/>
									<Tooltip
										cursor={{ strokeDasharray: "3 3" }}
										contentStyle={TOOLTIP_STYLE}
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										labelFormatter={(_, payload) =>
											String(payload?.[0]?.payload?.projectName || "")
										}
									/>
									<Scatter
										data={projectVulnsData}
										fill={CHART_COLORS.totalVulns}
										fillOpacity={0.75}
									>
										{projectVulnsData.map((_, index) => (
											<Cell
												key={`scatter-${index}`}
												fill={TREEMAP_COLORS[index % TREEMAP_COLORS.length]}
												fillOpacity={0.75}
											/>
										))}
									</Scatter>
								</ScatterChart>
							</ResponsiveContainer>
						)}
					</div>
				</div> */}

				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<AlertTriangle className="w-5 h-5 text-sky-400" />
						<div className="w-full">
							<h3 className="section-title">
								{translate(
									"dashboard.ruleConfidenceCoverageTitle",
									"规则置信度覆盖情况",
								)}
							</h3>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.ruleConfidenceCoverageSubtitle",
									"各置信度桶的规则覆盖面积",
								)}
							</p>
						</div>
					</div>
					<div className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3" style={{ height: 320 }}>
						{confidenceChartData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noRuleConfidenceData", "暂无规则置信度数据")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<AreaChart
									data={confidenceChartData}
									margin={{ top: 6, right: 6, left: 4, bottom: 20 }}
								>
									<defs>
										<linearGradient id="confidence-coverage" x1="0" y1="0" x2="0" y2="1">
											<stop
												offset="5%"
												stopColor={CHART_COLORS.mediumConfidence}
												stopOpacity={0.48}
											/>
											<stop
												offset="95%"
												stopColor={CHART_COLORS.mediumConfidence}
												stopOpacity={0.06}
											/>
										</linearGradient>
									</defs>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										dataKey="label"
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										tick={AXIS_TICK_STYLE}
									/>
									<YAxis
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
										tick={AXIS_TICK_STYLE}
										tickFormatter={formatTick}
									/>
									<Tooltip contentStyle={TOOLTIP_STYLE} />
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Area
										type="monotone"
										dataKey="totalRules"
										name={translate("dashboard.ruleCount", "规则总量")}
										stroke={CHART_COLORS.mediumConfidence}
										fill="url(#confidence-coverage)"
										strokeWidth={2}
										activeDot={{ r: 5 }}
									/>
								</AreaChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>

				{/* <div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Bug className="w-5 h-5 text-violet-400" />
						<div className="w-full">
							<h3 className="section-title">
								{translate(
									"dashboard.cweTopRankingTitle",
									"CWE 漏洞类型 Top 12",
								)}
							</h3>
							<p className="text-sm text-muted-foreground mt-1">
								{translate(
									"dashboard.cweTopRankingSubtitle",
									"按真实漏洞数量排序，并区分 Opengrep 与 Agent 来源",
								)}
							</p>
						</div>
					</div>
					<div
						className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3"
						style={{ height: cweChartHeight }}
					>
						{cweBarData.length === 0 ? (
							<div className="h-full flex items-center justify-center text-base text-muted-foreground">
								{translate("dashboard.noCweDistributionData", "暂无 CWE 占比数据")}
							</div>
						) : (
							<ResponsiveContainer width="100%" height="100%">
								<BarChart
									data={cweBarData}
									layout="horizontal"
									margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="category"
										dataKey="cweId"
										tick={<RotatedXAxisTick />}
										interval={0}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="number"
										allowDecimals={false}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip
										contentStyle={TOOLTIP_STYLE}
										labelFormatter={(value, payload) =>
											String(payload?.[0]?.payload?.cweName || value)
										}
									/>
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Bar
										dataKey="opengrepFindings"
										stackId="cwe"
										fill={CHART_COLORS.opengrepFindings}
										name="Opengrep"
										radius={[2, 2, 2, 2]}
									/>
									<Bar
										dataKey="agentFindings"
										stackId="cwe"
										fill={CHART_COLORS.agentFindings}
										name="Agent"
										radius={[2, 2, 2, 2]}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div> */}
			</div>
		</>
	);
}
