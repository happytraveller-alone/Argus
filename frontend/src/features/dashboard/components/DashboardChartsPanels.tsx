import { useMemo } from "react";
import { Activity, AlertTriangle, Bug } from "lucide-react";
import {
	Bar,
	BarChart,
	CartesianGrid,
	Legend,
	ResponsiveContainer,
	Tooltip,
	XAxis,
	YAxis,
	RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
    ScatterChart, Scatter, ZAxis, Cell,
    AreaChart, Area,
    Treemap,
} from "recharts";
import type {
	ProjectScanRunsChartItem,
	ProjectVulnsChartItem,
} from "@/features/dashboard/services/projectScanStats";

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

interface DashboardChartsPanelsProps {
	rulesByLanguageData: RuleLanguageChartItem[];
	rulesByCweData: RuleCweChartItem[];
	projectScanRunsData: ProjectScanRunsChartItem[];
	projectVulnsData: ProjectVulnsChartItem[];
	translate: (key: string, fallback?: string) => string;
}

const formatTick = (value: number | string) =>
	Number(value || 0).toLocaleString();

const CHART_MARGIN = { top: 8, right: 14, left: 10, bottom: 8 };
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
	highConfidence: "#fbbf24",
	mediumConfidence: "#38bdf8",
	cweTotal: "#a78bfa",
	tooltipStatic: "#7dd3fc",
	tooltipIntelligent: "#6ee7b7",
	tooltipHybrid: "#c4b5fd",
};

export default function DashboardChartsPanels({
	rulesByLanguageData,
	rulesByCweData,
	projectScanRunsData,
	projectVulnsData,
	translate,
}: DashboardChartsPanelsProps) {
	
	// mock数据，替换时把temp去掉，同时改回小驼峰
	const useMock = true;
	const tempRulesByLanguageData: RuleLanguageChartItem[] = [
		{ language: "Java", total: 128, highCount: 32, mediumCount: 54 },
		{ language: "JavaScript", total: 96, highCount: 21, mediumCount: 40 },
		{ language: "Python", total: 84, highCount: 18, mediumCount: 36 },
		{ language: "Go", total: 57, highCount: 11, mediumCount: 25 },
		{ language: "C#", total: 63, highCount: 14, mediumCount: 27 },
		{ language: "TypeScript", total: 52, highCount: 9, mediumCount: 23 },
		{ language: "PHP", total: 71, highCount: 20, mediumCount: 28 },
		{ language: "C++", total: 46, highCount: 16, mediumCount: 18 },
		{ language: "Java", total: 128, highCount: 32, mediumCount: 54 },
		{ language: "JavaScript", total: 96, highCount: 21, mediumCount: 40 },
		{ language: "Python", total: 84, highCount: 18, mediumCount: 36 },
		{ language: "Go", total: 57, highCount: 11, mediumCount: 25 },
		{ language: "C#", total: 63, highCount: 14, mediumCount: 27 },
		{ language: "TypeScript", total: 52, highCount: 9, mediumCount: 23 },
		{ language: "PHP", total: 71, highCount: 20, mediumCount: 28 },
		{ language: "C++", total: 46, highCount: 16, mediumCount: 18 }
	];
	const tempRulesByCweData: RuleCweChartItem[] = [
		{ cwe: "XSS", total: 74 },
		{ cwe: "SQL Injection", total: 52 },
		{ cwe: "Path Traversal", total: 41 },
		{ cwe: "Auth Bypass", total: 33 },
		{ cwe: "CSRF", total: 29 },
		{ cwe: "Info Exposure", total: 27 },
		{ cwe: "Command Injection", total: 19 },
		{ cwe: "Deserialization", total: 16 },
		{ cwe: "File Upload", total: 14 },
		{ cwe: "XXE", total: 11 },
		{ cwe: "SQL Injection", total: 52 },
		{ cwe: "Path Traversal", total: 41 },
		{ cwe: "Auth Bypass", total: 33 },
		{ cwe: "CSRF", total: 29 },
		{ cwe: "Info Exposure", total: 27 },
		{ cwe: "Command Injection", total: 19 },
		{ cwe: "Deserialization", total: 16 },
		{ cwe: "File Upload", total: 14 },
		{ cwe: "XXE", total: 11 }
	];
	const tempProjectScanRunsData: ProjectScanRunsChartItem[] = [
		{
			projectId: "proj-001",
			projectName: "User Service",
			staticRuns: 12,
			intelligentRuns: 8,
			hybridRuns: 5,
			totalRuns: 25
		},
		{
			projectId: "proj-002",
			projectName: "Payment Gateway",
			staticRuns: 20,
			intelligentRuns: 10,
			hybridRuns: 7,
			totalRuns: 37
		},
		{
			projectId: "proj-003",
			projectName: "Order Management",
			staticRuns: 6,
			intelligentRuns: 15,
			hybridRuns: 4,
			totalRuns: 25
		},
		{
			projectId: "proj-004",
			projectName: "Notification Center",
			staticRuns: 9,
			intelligentRuns: 3,
			hybridRuns: 2,
			totalRuns: 14
		},
		{
			projectId: "proj-005",
			projectName: "Analytics Platform",
			staticRuns: 18,
			intelligentRuns: 12,
			hybridRuns: 10,
			totalRuns: 40
		},
		{
			projectId: "proj-001",
			projectName: "User Service",
			staticRuns: 12,
			intelligentRuns: 8,
			hybridRuns: 5,
			totalRuns: 25
		},
		{
			projectId: "proj-002",
			projectName: "Payment Gateway",
			staticRuns: 20,
			intelligentRuns: 10,
			hybridRuns: 7,
			totalRuns: 37
		},
		{
			projectId: "proj-003",
			projectName: "Order Management",
			staticRuns: 6,
			intelligentRuns: 15,
			hybridRuns: 4,
			totalRuns: 25
		},
		{
			projectId: "proj-004",
			projectName: "Notification Center",
			staticRuns: 9,
			intelligentRuns: 3,
			hybridRuns: 2,
			totalRuns: 14
		},
		{
			projectId: "proj-005",
			projectName: "Analytics Platform",
			staticRuns: 18,
			intelligentRuns: 12,
			hybridRuns: 10,
			totalRuns: 40
		}
	];
	const tempProjectVulnsData: ProjectVulnsChartItem[] = [
		{
			projectId: "proj-001",
			projectName: "User Service",
			staticVulns: 38,
			intelligentVulns: 21,
			hybridVulns: 9,
			totalVulns: 68
		},
		{
			projectId: "proj-002",
			projectName: "Payment Gateway",
			staticVulns: 52,
			intelligentVulns: 26,
			hybridVulns: 13,
			totalVulns: 91
		},
		{
			projectId: "proj-003",
			projectName: "Order Management",
			staticVulns: 29,
			intelligentVulns: 34,
			hybridVulns: 11,
			totalVulns: 74
		},
		{
			projectId: "proj-004",
			projectName: "Notification Center",
			staticVulns: 17,
			intelligentVulns: 8,
			hybridVulns: 4,
			totalVulns: 29
		},
		{
			projectId: "proj-005",
			projectName: "Analytics Platform",
			staticVulns: 61,
			intelligentVulns: 37,
			hybridVulns: 18,
			totalVulns: 116
		},
		{
			projectId: "proj-006",
			projectName: "Search Service",
			staticVulns: 24,
			intelligentVulns: 12,
			hybridVulns: 6,
			totalVulns: 42
		},
		{
			projectId: "proj-007",
			projectName: "File Storage",
			staticVulns: 33,
			intelligentVulns: 19,
			hybridVulns: 10,
			totalVulns: 62
		}
	];
	if(useMock){
		rulesByLanguageData = tempRulesByLanguageData;
		rulesByCweData = tempRulesByCweData;
		projectScanRunsData = tempProjectScanRunsData;
		projectVulnsData = tempProjectVulnsData;
	}


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
		const row = payload.payload[0]?.payload as ProjectVulnsChartItem | undefined;
		if (!row) return null;

		return (
				<div className="rounded border border-border bg-background/95 px-3 py-2 text-xs shadow-xl">
					<p className="font-semibold text-foreground">{row.projectName}</p>
					<p className="text-muted-foreground mt-1">
						{translate("dashboard.totalVulns")}：
						{formatTick(row.totalVulns)}
					</p>
					<div className="mt-1 space-y-0.5">
						<p style={{ color: CHART_COLORS.tooltipStatic }}>
							{translate("dashboard.staticScan")}：
							{formatTick(row.staticVulns)}
						</p>
						<p style={{ color: CHART_COLORS.tooltipIntelligent }}>
							{translate("dashboard.intelligentScan")}：
							{formatTick(row.intelligentVulns)}
						</p>
						<p style={{ color: CHART_COLORS.tooltipHybrid }}>
							{translate("dashboard.hybridScan")}：
							{formatTick(row.hybridVulns)}
						</p>
					</div>
				</div>
		);
	};

	return (
		<>
			{/* <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="section-header mb-3">
						<Activity className="w-5 h-5 text-emerald-400" />
						<div className="w-full">
							<div className="flex items-center justify-between gap-3 flex-wrap">
								<h3 className="section-title">
									{translate("dashboard.projectScanRunsChartTitle")}
								</h3>
								<span className="text-sm text-muted-foreground">
									项目数：{projectScanRunsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate("dashboard.projectScanRunsChartSubtitle")}（Top 10）
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
									layout="vertical"
									margin={CHART_MARGIN}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="number"
										domain={[0, projectScanRunsChartMax]}
										allowDecimals={false}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="category"
										dataKey="projectName"
										width={120}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={TOOLTIP_STYLE}
									/>
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
									项目数：{projectVulnsData.length}
								</span>
							</div>
							<p className="text-sm text-muted-foreground mt-1">
								{translate("dashboard.projectVulnsChartSubtitle")}（Top 10）
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
									layout="vertical"
									margin={CHART_MARGIN}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="number"
										domain={[0, projectVulnsChartMax]}
										allowDecimals={false}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="category"
										dataKey="projectName"
										width={120}
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
									margin={CHART_MARGIN}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="number"
										domain={[0, chartMax]}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="category"
										dataKey="language"
										width={104}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={TOOLTIP_STYLE}
									/>
									<Legend wrapperStyle={LEGEND_STYLE} />
									<Bar
										dataKey="highCount"
										stackId="confidence"
										fill={CHART_COLORS.highConfidence}
										name="高置信度"
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
									<Bar
										stackId="confidence"
										dataKey="mediumCount"
										fill={CHART_COLORS.mediumConfidence}
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
									margin={CHART_MARGIN}
									barCategoryGap={16}
									barGap={6}
									barSize={18}
								>
									<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
									<XAxis
										type="number"
										domain={[0, cweChartMax]}
										tickFormatter={formatTick}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<YAxis
										type="category"
										dataKey="cwe"
										width={104}
										tick={AXIS_TICK_STYLE}
										axisLine={AXIS_LINE_STYLE}
										tickLine={AXIS_TICK_LINE_STYLE}
									/>
									<Tooltip
										formatter={(value: number | string, name: string) => [
											Number(value || 0).toLocaleString(),
											name,
										]}
										contentStyle={TOOLTIP_STYLE}
									/>
									<Bar
										dataKey="total"
										fill={CHART_COLORS.cweTotal}
										name="规则数量"
										radius={[2, 2, 2, 2]}
										minPointSize={6}
									/>
								</BarChart>
							</ResponsiveContainer>
						)}
					</div>
				</div>
			</div> */}
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
															项目数：{projectScanRunsData.length}
													</span>
											</div>
											<p className="text-sm text-muted-foreground mt-1">
													{translate("dashboard.projectScanRunsChartSubtitle")}（Top 10）
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
																	tick={{ ...AXIS_TICK_STYLE, angle: -35, textAnchor: 'end' }}
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
															<Tooltip
																	formatter={(value: number | string, name: string) => [
																			Number(value || 0).toLocaleString(),
																			name,
																	]}
																	contentStyle={TOOLTIP_STYLE}
															/>
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
															项目数：{projectVulnsData.length}
													</span>
											</div>
											<p className="text-sm text-muted-foreground mt-1">
													{translate("dashboard.projectVulnsChartSubtitle")}（Top 10）
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
																	tick={{ ...AXIS_TICK_STYLE, angle: -35, textAnchor: 'end' }}
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
															layout="horizontal"
															margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
															barCategoryGap={16}
															barGap={6}
															barSize={18}
													>
															<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
															<XAxis
																	type="category"
																	dataKey="language"
																	tick={{ ...AXIS_TICK_STYLE, angle: -35, textAnchor: 'end' }}
																	interval={0}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
															/>
															<YAxis
																	type="number"
																	domain={[0, chartMax]}
																	tickFormatter={formatTick}
																	tick={AXIS_TICK_STYLE}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
															/>
															<Tooltip
																	formatter={(value: number | string, name: string) => [
																			Number(value || 0).toLocaleString(),
																			name,
																	]}
																	contentStyle={TOOLTIP_STYLE}
															/>
															<Legend wrapperStyle={LEGEND_STYLE} />
															<Bar
																	dataKey="highCount"
																	stackId="confidence"
																	fill={CHART_COLORS.highConfidence}
																	name="高置信度"
																	radius={[2, 2, 2, 2]}
																	minPointSize={6}
															/>
															<Bar
																	stackId="confidence"
																	dataKey="mediumCount"
																	fill={CHART_COLORS.mediumConfidence}
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
															layout="horizontal"
															margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
															barCategoryGap={16}
															barGap={6}
															barSize={18}
													>
															<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
															<XAxis
																	type="category"
																	dataKey="cwe"
																	tick={{ ...AXIS_TICK_STYLE, angle: -35, textAnchor: 'end' }}
																	interval={0}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
															/>
															<YAxis
																	type="number"
																	domain={[0, cweChartMax]}
																	tickFormatter={formatTick}
																	tick={AXIS_TICK_STYLE}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
															/>
															<Tooltip
																	formatter={(value: number | string, name: string) => [
																			Number(value || 0).toLocaleString(),
																			name,
																	]}
																	contentStyle={TOOLTIP_STYLE}
															/>
															<Bar
																	dataKey="total"
																	fill={CHART_COLORS.cweTotal}
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

			{/* ===== 第二行：多样化图表 ===== */}
			<div className="grid grid-cols-1 xl:grid-cols-4 gap-4 relative z-10">

					{/* 1. 雷达图 - 项目扫描类型分布 */}
					<div className="cyber-card p-4">
							<div className="section-header mb-3">
									<Activity className="w-5 h-5 text-emerald-400" />
									<div className="w-full">
											<h3 className="section-title">项目扫描类型分布</h3>
											<p className="text-sm text-muted-foreground mt-1">各项目扫描方式对比（雷达图）</p>
									</div>
							</div>
							<div className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3" style={{ height: projectScanRunsChartHeight }}>
									{projectScanRunsData.length === 0 ? (
											<div className="h-full flex items-center justify-center text-base text-muted-foreground">暂无数据</div>
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
					</div>

					{/* 2. 气泡图 - 项目漏洞风险矩阵 */}
					<div className="cyber-card p-4">
							<div className="section-header mb-3">
									<Bug className="w-5 h-5 text-amber-400" />
									<div className="w-full">
											<h3 className="section-title">项目漏洞风险矩阵</h3>
											<p className="text-sm text-muted-foreground mt-1">X=静态漏洞 Y=智能漏洞 大小=混合漏洞</p>
									</div>
							</div>
							<div className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3" style={{ height: projectVulnsChartHeight }}>
									{projectVulnsData.length === 0 ? (
											<div className="h-full flex items-center justify-center text-base text-muted-foreground">暂无数据</div>
									) : (
											<ResponsiveContainer width="100%" height="100%">
													<ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
															<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
															<XAxis
																	type="number"
																	dataKey="staticVulns"
																	name="静态漏洞"
																	tick={AXIS_TICK_STYLE}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
																	label={{ value: '静态漏洞', position: 'insideBottom', offset: -4, fontSize: 11 }}
															/>
															<YAxis
																	type="number"
																	dataKey="intelligentVulns"
																	name="智能漏洞"
																	tick={AXIS_TICK_STYLE}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
																	label={{ value: '智能漏洞', angle: -90, position: 'insideLeft', fontSize: 11 }}
															/>
															<ZAxis type="number" dataKey="hybridVulns" range={[60, 400]} name="混合漏洞" />
															<Tooltip
																	cursor={{ strokeDasharray: '3 3' }}
																	contentStyle={TOOLTIP_STYLE}
																	formatter={(value: number | string, name: string) => [
																			Number(value || 0).toLocaleString(),
																			name,
																	]}
															/>
															<Scatter
																	data={projectVulnsData}
																	fill={CHART_COLORS.totalVulns}
																	fillOpacity={0.75}
															>
																	{projectVulnsData.map((entry, index) => (
																			<Cell
																					key={`cell-${index}`}
																					fill={[
																							'#38bdf8', '#34d399', '#a78bfa',
																							'#fb923c', '#f472b6', '#facc15', '#4ade80'
																					][index % 7]}
																					fillOpacity={0.75}
																			/>
																	))}
															</Scatter>
													</ScatterChart>
											</ResponsiveContainer>
									)}
							</div>
					</div>

					{/* 3. 堆叠面积图 - 规则置信度分布 */}
					<div className="cyber-card p-4">
							<div className="section-header mb-3">
									<AlertTriangle className="w-5 h-5 text-sky-400" />
									<div className="w-full">
											<h3 className="section-title">规则置信度趋势</h3>
											<p className="text-sm text-muted-foreground mt-1">各语言高/中置信度规则面积分布</p>
									</div>
							</div>
							<div className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3" style={{ height: rulesChartHeight }}>
									{rulesByLanguageData.length === 0 ? (
											<div className="h-full flex items-center justify-center text-base text-muted-foreground">暂无数据</div>
									) : (
											<ResponsiveContainer width="100%" height="100%">
													<AreaChart
															data={rulesByLanguageData}
															margin={{ top: 6, right: 6, left: 4, bottom: 50 }}
													>
															<defs>
																	<linearGradient id="colorHigh" x1="0" y1="0" x2="0" y2="1">
																			<stop offset="5%" stopColor={CHART_COLORS.highConfidence} stopOpacity={0.5} />
																			<stop offset="95%" stopColor={CHART_COLORS.highConfidence} stopOpacity={0.05} />
																	</linearGradient>
																	<linearGradient id="colorMedium" x1="0" y1="0" x2="0" y2="1">
																			<stop offset="5%" stopColor={CHART_COLORS.mediumConfidence} stopOpacity={0.5} />
																			<stop offset="95%" stopColor={CHART_COLORS.mediumConfidence} stopOpacity={0.05} />
																	</linearGradient>
															</defs>
															<CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
															<XAxis
																	dataKey="language"
																	tick={{ ...AXIS_TICK_STYLE, angle: -35, textAnchor: 'end' }}
																	interval={0}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
															/>
															<YAxis
																	tick={AXIS_TICK_STYLE}
																	axisLine={AXIS_LINE_STYLE}
																	tickLine={AXIS_TICK_LINE_STYLE}
																	tickFormatter={formatTick}
															/>
															<Tooltip contentStyle={TOOLTIP_STYLE} />
															<Legend wrapperStyle={LEGEND_STYLE} />
															<Area
																	type="monotone"
																	dataKey="highCount"
																	stackId="1"
																	stroke={CHART_COLORS.highConfidence}
																	fill="url(#colorHigh)"
																	name="高置信度"
															/>
															<Area
																	type="monotone"
																	dataKey="mediumCount"
																	stackId="1"
																	stroke={CHART_COLORS.mediumConfidence}
																	fill="url(#colorMedium)"
																	name="中置信度"
															/>
													</AreaChart>
											</ResponsiveContainer>
									)}
							</div>
					</div>

					{/* 4. Treemap - CWE 漏洞类型占比 */}
					<div className="cyber-card p-4">
							<div className="section-header mb-3">
									<Bug className="w-5 h-5 text-violet-400" />
									<div className="w-full">
											<h3 className="section-title">CWE 漏洞类型占比</h3>
											<p className="text-sm text-muted-foreground mt-1">面积大小代表规则数量占比</p>
									</div>
							</div>
							<div className="mt-4 border border-border/60 rounded-lg bg-muted/15 p-3" style={{ height: cweChartHeight }}>
									{rulesByCweData.length === 0 ? (
											<div className="h-full flex items-center justify-center text-base text-muted-foreground">暂无数据</div>
									) : (
											<ResponsiveContainer width="100%" height="100%">
													<Treemap
															data={rulesByCweData.map((item, index) => ({
																	...item,
																	name: item.cwe,
																	size: item.total,
																	fill: [
																			'#a78bfa', '#818cf8', '#60a5fa', '#38bdf8',
																			'#34d399', '#4ade80', '#facc15', '#fb923c',
																			'#f472b6', '#e879f9'
																	][index % 10],
															}))}
															dataKey="size"
															aspectRatio={4 / 3}
															stroke="rgba(0,0,0,0.2)"
															content={({ x, y, width, height, name, value, fill }: any) => {
																	if (!width || !height || width < 20 || height < 20) return null;
																	return (
																			<g>
																					<rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={0.8} rx={3} />
																					{width > 40 && height > 28 && (
																							<>
																									<text x={x + width / 2} y={y + height / 2 - 6} textAnchor="middle" fill="#fff" fontSize={11} fontWeight={600}>
																											{name}
																									</text>
																									<text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill="rgba(255,255,255,0.8)" fontSize={10}>
																											{value}
																									</text>
																							</>
																					)}
																			</g>
																	);
															}}
													>
															<Tooltip
																	contentStyle={TOOLTIP_STYLE}
																	formatter={(value: number | string) => [Number(value).toLocaleString(), '规则数量']}
															/>
													</Treemap>
											</ResponsiveContainer>
									)}
							</div>
					</div>
			</div>
		</>
	);
}
