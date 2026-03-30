export type DashboardPreviewViewId =
	| "trend"
	| "project-risk"
	| "language-risk"
	| "vulnerability-types"
	| "scan-engines"
	| "static-engine-rules"
	| "language-lines";

export interface DashboardPreviewView {
	id: DashboardPreviewViewId;
	label: string;
	description: string;
}

export interface DashboardPreviewSegment {
	label: string;
	value: number;
	tone: "critical" | "high" | "medium" | "low" | "neutral";
}

export interface DashboardPreviewLeaderboardRow {
	label: string;
	total: number;
	meta: string;
	segments: DashboardPreviewSegment[];
}

export interface DashboardPreviewTrendPoint {
	date: string;
	totalNewFindings: number;
	staticFindings: number;
	intelligentVerifiedFindings: number;
	hybridVerifiedFindings: number;
}

export interface DashboardPreviewTaskStatus {
	label: string;
	value: number;
	tone: "critical" | "high" | "medium" | "low" | "neutral";
}

export interface DashboardPreviewRecentTask {
	id: string;
	title: string;
	type: "静态扫描" | "智能扫描" | "混合扫描";
	progress: number;
	createdAt: string;
	createdAtLabel: string;
}

const PREVIEW_TOP_N = 10;

export const DASHBOARD_PREVIEW_VIEWS: DashboardPreviewView[] = [
	{
		id: "trend",
		label: "漏洞态势趋势",
		description: "查看近七日当日新增漏洞发现与来源构成的波动",
	},
	{
		id: "project-risk",
		label: "项目风险统计图",
		description: "查看已扫描项目的风险分布，识别高风险项目",
	},
	{
		id: "language-risk",
		label: "语言风险统计图",
		description: "查看不同编程语言的风险分布情况",
	},
	{
		id: "vulnerability-types",
		label: "漏洞类型统计图",
		description: "查看不同类型的漏洞分布情况",
	},
	{
		id: "scan-engines",
		label: "扫描引擎统计图",
		description: "查看各扫描引擎发现的漏洞数量分布情况",
	},
	{
		id: "static-engine-rules",
		label: "扫描规则统计图",
		description: "查看各静态扫描引擎规则数量分布情况",
	},
	{
		id: "language-lines",
		label: "项目语言统计图",
		description: "查看项目涉及语言的代码行数量分布情况",
	},
];

export const DASHBOARD_PREVIEW_TREND: DashboardPreviewTrendPoint[] = [
	{ date: "03-17", totalNewFindings: 18, staticFindings: 9, intelligentVerifiedFindings: 3, hybridVerifiedFindings: 6 },
	{ date: "03-18", totalNewFindings: 26, staticFindings: 14, intelligentVerifiedFindings: 4, hybridVerifiedFindings: 8 },
	{ date: "03-19", totalNewFindings: 21, staticFindings: 11, intelligentVerifiedFindings: 3, hybridVerifiedFindings: 7 },
	{ date: "03-20", totalNewFindings: 34, staticFindings: 18, intelligentVerifiedFindings: 5, hybridVerifiedFindings: 11 },
	{ date: "03-21", totalNewFindings: 29, staticFindings: 15, intelligentVerifiedFindings: 4, hybridVerifiedFindings: 10 },
	{ date: "03-22", totalNewFindings: 41, staticFindings: 20, intelligentVerifiedFindings: 7, hybridVerifiedFindings: 14 },
	{ date: "03-23", totalNewFindings: 37, staticFindings: 18, intelligentVerifiedFindings: 6, hybridVerifiedFindings: 13 },
];

const PROJECT_RISK_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "Alpha Gateway",
		meta: "支付核心 · 最近 24h 新增 5 条",
		segments: [
			{ label: "严重", value: 6, tone: "critical" },
			{ label: "高危", value: 10, tone: "high" },
			{ label: "中危", value: 14, tone: "medium" },
			{ label: "低危", value: 8, tone: "low" },
		],
		total: 38,
	},
	{
		label: "Nebula Console",
		meta: "后台门户 · 智能扫描命中率提升",
		segments: [
			{ label: "严重", value: 4, tone: "critical" },
			{ label: "高危", value: 9, tone: "high" },
			{ label: "中危", value: 11, tone: "medium" },
			{ label: "低危", value: 7, tone: "low" },
		],
		total: 31,
	},
	{
		label: "Orbit API",
		meta: "开放接口 · 混合扫描验证加速",
		segments: [
			{ label: "严重", value: 3, tone: "critical" },
			{ label: "高危", value: 7, tone: "high" },
			{ label: "中危", value: 9, tone: "medium" },
			{ label: "低危", value: 5, tone: "low" },
		],
		total: 24,
	},
	{
		label: "Legacy Portal",
		meta: "PHP 站点 · 低危问题密集",
		segments: [
			{ label: "严重", value: 2, tone: "critical" },
			{ label: "高危", value: 5, tone: "high" },
			{ label: "中危", value: 8, tone: "medium" },
			{ label: "低危", value: 6, tone: "low" },
		],
		total: 21,
	},
	{
		label: "Mercury Admin",
		meta: "运营后台 · 高危接口暴露",
		segments: [
			{ label: "严重", value: 2, tone: "critical" },
			{ label: "高危", value: 4, tone: "high" },
			{ label: "中危", value: 7, tone: "medium" },
			{ label: "低危", value: 5, tone: "low" },
		],
		total: 18,
	},
	{
		label: "Nova Service",
		meta: "微服务集群 · 近期回归发现增加",
		segments: [
			{ label: "严重", value: 1, tone: "critical" },
			{ label: "高危", value: 4, tone: "high" },
			{ label: "中危", value: 6, tone: "medium" },
			{ label: "低危", value: 4, tone: "low" },
		],
		total: 15,
	},
	{
		label: "Atlas DataHub",
		meta: "数据中台 · 中危问题持续堆积",
		segments: [
			{ label: "严重", value: 1, tone: "critical" },
			{ label: "高危", value: 3, tone: "high" },
			{ label: "中危", value: 6, tone: "medium" },
			{ label: "低危", value: 4, tone: "low" },
		],
		total: 14,
	},
	{
		label: "Apollo Mobile API",
		meta: "移动后端 · 认证逻辑风险偏高",
		segments: [
			{ label: "严重", value: 1, tone: "critical" },
			{ label: "高危", value: 3, tone: "high" },
			{ label: "中危", value: 5, tone: "medium" },
			{ label: "低危", value: 3, tone: "low" },
		],
		total: 12,
	},
	{
		label: "Vega Billing",
		meta: "结算服务 · 低危为主",
		segments: [
			{ label: "严重", value: 1, tone: "critical" },
			{ label: "高危", value: 2, tone: "high" },
			{ label: "中危", value: 4, tone: "medium" },
			{ label: "低危", value: 4, tone: "low" },
		],
		total: 11,
	},
	{
		label: "Quasar Web",
		meta: "营销站点 · 混合扫描已清理一轮",
		segments: [
			{ label: "严重", value: 0, tone: "critical" },
			{ label: "高危", value: 2, tone: "high" },
			{ label: "中危", value: 4, tone: "medium" },
			{ label: "低危", value: 4, tone: "low" },
		],
		total: 10,
	},
	{
		label: "Helios CRM",
		meta: "业务系统 · 历史问题回流",
		segments: [
			{ label: "严重", value: 0, tone: "critical" },
			{ label: "高危", value: 2, tone: "high" },
			{ label: "中危", value: 4, tone: "medium" },
			{ label: "低危", value: 3, tone: "low" },
		],
		total: 9,
	},
	{
		label: "Ion Partner OpenAPI",
		meta: "开放接口 · 外部暴露面较广",
		segments: [
			{ label: "严重", value: 0, tone: "critical" },
			{ label: "高危", value: 2, tone: "high" },
			{ label: "中危", value: 3, tone: "medium" },
			{ label: "低危", value: 3, tone: "low" },
		],
		total: 8,
	},
	{
		label: "Terra Search",
		meta: "检索服务 · 低危尾项",
		segments: [
			{ label: "严重", value: 0, tone: "critical" },
			{ label: "高危", value: 1, tone: "high" },
			{ label: "中危", value: 3, tone: "medium" },
			{ label: "低危", value: 3, tone: "low" },
		],
		total: 7,
	},
];

const LANGUAGE_RISK_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "TypeScript",
		meta: "4 个项目 · Web 面向层",
		segments: [{ label: "总数", value: 46, tone: "high" }],
		total: 46,
	},
	{
		label: "Python",
		meta: "3 个项目 · 自动化与服务端",
		segments: [{ label: "总数", value: 31, tone: "medium" }],
		total: 31,
	},
	{
		label: "PHP",
		meta: "2 个项目 · 历史业务系统",
		segments: [{ label: "总数", value: 24, tone: "critical" }],
		total: 24,
	},
	{
		label: "Go",
		meta: "2 个项目 · 网关与工具链",
		segments: [{ label: "总数", value: 18, tone: "low" }],
		total: 18,
	},
	{
		label: "Java",
		meta: "2 个项目 · 核心服务",
		segments: [{ label: "总数", value: 16, tone: "medium" }],
		total: 16,
	},
	{
		label: "C#",
		meta: "2 个项目 · 内部平台",
		segments: [{ label: "总数", value: 14, tone: "low" }],
		total: 14,
	},
	{
		label: "Ruby",
		meta: "1 个项目 · 老旧管理台",
		segments: [{ label: "总数", value: 13, tone: "critical" }],
		total: 13,
	},
	{
		label: "Rust",
		meta: "1 个项目 · 安全组件",
		segments: [{ label: "总数", value: 11, tone: "low" }],
		total: 11,
	},
	{
		label: "JavaScript",
		meta: "2 个项目 · 辅助前端",
		segments: [{ label: "总数", value: 10, tone: "high" }],
		total: 10,
	},
	{
		label: "Kotlin",
		meta: "1 个项目 · Android 支撑",
		segments: [{ label: "总数", value: 8, tone: "medium" }],
		total: 8,
	},
	{
		label: "Swift",
		meta: "1 个项目 · iOS 支撑",
		segments: [{ label: "总数", value: 7, tone: "low" }],
		total: 7,
	},
	{
		label: "Scala",
		meta: "1 个项目 · 数据计算",
		segments: [{ label: "总数", value: 6, tone: "medium" }],
		total: 6,
	},
];

const VULNERABILITY_TYPE_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "CWE-89",
		meta: "SQL 注入 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 17, tone: "critical" }],
		total: 17,
	},
	{
		label: "CWE-862",
		meta: "越权访问 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 13, tone: "high" }],
		total: 13,
	},
	{
		label: "CWE-78",
		meta: "命令执行 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 11, tone: "medium" }],
		total: 11,
	},
	{
		label: "CWE-200",
		meta: "敏感信息泄露 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 8, tone: "low" }],
		total: 8,
	},
	{
		label: "CWE-79",
		meta: "跨站脚本 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 7, tone: "medium" }],
		total: 7,
	},
	{
		label: "CWE-22",
		meta: "路径遍历 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 6, tone: "high" }],
		total: 6,
	},
	{
		label: "CWE-287",
		meta: "认证绕过 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 6, tone: "critical" }],
		total: 6,
	},
	{
		label: "CWE-352",
		meta: "CSRF · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 5, tone: "medium" }],
		total: 5,
	},
	{
		label: "CWE-434",
		meta: "任意文件上传 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 4, tone: "high" }],
		total: 4,
	},
	{
		label: "CWE-601",
		meta: "开放重定向 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 4, tone: "low" }],
		total: 4,
	},
	{
		label: "CWE-502",
		meta: "不安全反序列化 · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 3, tone: "critical" }],
		total: 3,
	},
	{
		label: "CWE-918",
		meta: "SSRF · 智能 / 混合扫描已验证",
		segments: [{ label: "已验证", value: 3, tone: "high" }],
		total: 3,
	},
];

const SCAN_ENGINE_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "llm",
		meta: "智能扫描 + 混合扫描",
		segments: [{ label: "总数", value: 28, tone: "critical" }],
		total: 28,
	},
	{
		label: "opengrep",
		meta: "静态扫描",
		segments: [{ label: "总数", value: 21, tone: "high" }],
		total: 21,
	},
	{
		label: "gitleaks",
		meta: "静态扫描",
		segments: [{ label: "总数", value: 17, tone: "medium" }],
		total: 17,
	},
	{
		label: "bandit",
		meta: "静态扫描",
		segments: [{ label: "总数", value: 14, tone: "low" }],
		total: 14,
	},
	{
		label: "phpstan",
		meta: "静态扫描",
		segments: [{ label: "总数", value: 11, tone: "medium" }],
		total: 11,
	},
	{
		label: "yasa",
		meta: "静态扫描",
		segments: [{ label: "总数", value: 9, tone: "low" }],
		total: 9,
	},
];

const STATIC_ENGINE_RULE_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "opengrep",
		meta: "规则总数 368",
		segments: [{ label: "规则数", value: 368, tone: "critical" }],
		total: 368,
	},
	{
		label: "gitleaks",
		meta: "规则总数 214",
		segments: [{ label: "规则数", value: 214, tone: "high" }],
		total: 214,
	},
	{
		label: "bandit",
		meta: "规则总数 172",
		segments: [{ label: "规则数", value: 172, tone: "medium" }],
		total: 172,
	},
	{
		label: "phpstan",
		meta: "规则总数 129",
		segments: [{ label: "规则数", value: 129, tone: "low" }],
		total: 129,
	},
	{
		label: "yasa",
		meta: "规则总数 84",
		segments: [{ label: "规则数", value: 84, tone: "medium" }],
		total: 84,
	},
];

const LANGUAGE_LINE_ROWS: DashboardPreviewLeaderboardRow[] = [
	{
		label: "TypeScript",
		meta: "代码行 182,400",
		segments: [{ label: "代码行", value: 182400, tone: "high" }],
		total: 182400,
	},
	{
		label: "Java",
		meta: "代码行 156,800",
		segments: [{ label: "代码行", value: 156800, tone: "medium" }],
		total: 156800,
	},
	{
		label: "Go",
		meta: "代码行 131,500",
		segments: [{ label: "代码行", value: 131500, tone: "low" }],
		total: 131500,
	},
	{
		label: "Python",
		meta: "代码行 124,600",
		segments: [{ label: "代码行", value: 124600, tone: "medium" }],
		total: 124600,
	},
	{
		label: "PHP",
		meta: "代码行 109,300",
		segments: [{ label: "代码行", value: 109300, tone: "critical" }],
		total: 109300,
	},
	{
		label: "C#",
		meta: "代码行 96,200",
		segments: [{ label: "代码行", value: 96200, tone: "low" }],
		total: 96200,
	},
	{
		label: "JavaScript",
		meta: "代码行 85,400",
		segments: [{ label: "代码行", value: 85400, tone: "high" }],
		total: 85400,
	},
	{
		label: "Kotlin",
		meta: "代码行 73,900",
		segments: [{ label: "代码行", value: 73900, tone: "medium" }],
		total: 73900,
	},
	{
		label: "Rust",
		meta: "代码行 64,700",
		segments: [{ label: "代码行", value: 64700, tone: "low" }],
		total: 64700,
	},
	{
		label: "Swift",
		meta: "代码行 52,800",
		segments: [{ label: "代码行", value: 52800, tone: "low" }],
		total: 52800,
	},
	{
		label: "Ruby",
		meta: "代码行 41,500",
		segments: [{ label: "代码行", value: 41500, tone: "critical" }],
		total: 41500,
	},
	{
		label: "Scala",
		meta: "代码行 36,900",
		segments: [{ label: "代码行", value: 36900, tone: "medium" }],
		total: 36900,
	},
];

export const DASHBOARD_PREVIEW_TASK_STATUS: DashboardPreviewTaskStatus[] = [
	{ label: "运行中", value: 12, tone: "high" },
	{ label: "已完成", value: 128, tone: "low" },
	{ label: "失败", value: 5, tone: "critical" },
	{ label: "已中断", value: 3, tone: "neutral" },
];

const DASHBOARD_PREVIEW_RECENT_TASKS: DashboardPreviewRecentTask[] = [
	{
		id: "task-206",
		title: "混合扫描 · Alpha Gateway",
		type: "混合扫描",
		progress: 92,
		createdAt: "2026-03-23T16:42:00+08:00",
		createdAtLabel: "03-23 16:42",
	},
	{
		id: "task-205",
		title: "智能扫描 · Nebula Console",
		type: "智能扫描",
		progress: 81,
		createdAt: "2026-03-23T16:18:00+08:00",
		createdAtLabel: "03-23 16:18",
	},
	{
		id: "task-204",
		title: "静态扫描 · Orbit API",
		type: "静态扫描",
		progress: 68,
		createdAt: "2026-03-23T15:56:00+08:00",
		createdAtLabel: "03-23 15:56",
	},
	{
		id: "task-203",
		title: "智能扫描 · Mercury Admin",
		type: "智能扫描",
		progress: 54,
		createdAt: "2026-03-23T15:11:00+08:00",
		createdAtLabel: "03-23 15:11",
	},
	{
		id: "task-202",
		title: "静态扫描 · Vega Billing",
		type: "静态扫描",
		progress: 37,
		createdAt: "2026-03-23T14:28:00+08:00",
		createdAtLabel: "03-23 14:28",
	},
	{
		id: "task-201",
		title: "静态扫描 · Helios CRM",
		type: "静态扫描",
		progress: 19,
		createdAt: "2026-03-23T13:42:00+08:00",
		createdAtLabel: "03-23 13:42",
	},
];

export function getPreviewLeaderboardRows(
	viewId: DashboardPreviewViewId,
): DashboardPreviewLeaderboardRow[] {
	if (viewId === "project-risk") return PROJECT_RISK_ROWS.slice(0, PREVIEW_TOP_N);
	if (viewId === "language-risk") return LANGUAGE_RISK_ROWS.slice(0, PREVIEW_TOP_N);
	if (viewId === "vulnerability-types") {
		return VULNERABILITY_TYPE_ROWS.slice(0, PREVIEW_TOP_N);
	}
	if (viewId === "scan-engines") return SCAN_ENGINE_ROWS.slice(0, PREVIEW_TOP_N);
	if (viewId === "static-engine-rules") {
		return STATIC_ENGINE_RULE_ROWS.slice(0, PREVIEW_TOP_N);
	}
	if (viewId === "language-lines") {
		return LANGUAGE_LINE_ROWS.slice(0, PREVIEW_TOP_N);
	}
	return [];
}

export function getRecentPreviewTasks(limit = 5): DashboardPreviewRecentTask[] {
	return [...DASHBOARD_PREVIEW_RECENT_TASKS]
		.sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
		.slice(0, limit);
}
