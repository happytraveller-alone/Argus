import { buildSkillToolPrompt, type SkillToolCatalogItem } from "./skillToolsCatalog.ts";
import type { McpCatalogItem } from "./mcpCatalog.ts";

export type SkillAvailabilityMap = Record<
	string,
	{
		enabled?: boolean;
		reason?: string;
	}
>;

export type McpVerifyResult = {
	success: boolean;
	mcp_id: string;
	checks: Array<{
		step: string;
		action: "tools/list" | "tools/call" | "policy/skip" | string;
		success: boolean;
		tool?: string | null;
		runtime_domain?: string | null;
		duration_ms: number;
		error?: string | null;
	}>;
	verification_tools: string[];
	discovered_tools?: Array<{
		name: string;
		description?: string;
		inputSchema?: Record<string, unknown>;
	}>;
	protocol_summary?: {
		list_tools_success?: boolean;
		discovered_count?: number;
		called_count?: number;
		call_success_count?: number;
		call_failed_count?: number;
		arg_failed_count?: number;
		skipped_unsupported_count?: number;
		required_gate?: string[];
		[key: string]: unknown;
	};
	project_context?: {
		project_name?: string;
		fallback_used?: boolean;
	};
};

export type McpToolItem = {
	name: string;
	description: string;
	inputSchema: Record<string, unknown>;
};

export type ExternalToolDetailSection =
	| {
			title: string;
			kind: "properties";
			properties: Array<{ label: string; value: string }>;
	  }
	| {
			title: string;
			kind: "list";
			items: string[];
	  }
	| {
			title: string;
			kind: "code";
			code: string;
	  }
	| {
			title: string;
			kind: "mcp-tools";
			tools: McpToolItem[];
			error?: string;
	  }
	| {
			title: string;
			kind: "mcp-verify";
			result: McpVerifyResult | null;
			error?: string;
	  };

export type ExternalToolRow =
	| {
			id: string;
			type: "mcp";
			name: string;
			capabilities: string[];
			isLoaded: boolean;
			detailPayload: {
				description: string;
				runtimeMode: string;
				source: string;
				startupDiagnostic: string;
				toolListDiagnostic?: string;
				tools: McpToolItem[];
				verifyResult: McpVerifyResult | null;
				verifyError: string;
			};
	  }
	| {
			id: string;
			type: "skill";
			name: string;
			capabilities: string[];
			isLoaded: boolean;
			detailPayload: {
				summary: string;
				goal: string;
				taskList: string[];
				prompt: string;
				exampleInput: string;
				inputChecklist: string[];
				pitfalls: string[];
			};
	  };

export const EXTERNAL_TOOLS_PAGE_SIZE = 6;

export interface ExternalToolListState {
	filteredRows: ExternalToolRow[];
	pageRows: ExternalToolRow[];
	page: number;
	pageSize: number;
	totalRows: number;
	totalPages: number;
	startIndex: number;
	searchQuery: string;
}

export function buildExternalToolRows({
	mcpCatalog,
	skillCatalog,
	skillAvailability,
	mcpToolsById = {},
	mcpToolsErrors = {},
	verifyResults = {},
	verifyErrors = {},
}: {
	mcpCatalog: McpCatalogItem[];
	skillCatalog: SkillToolCatalogItem[];
	skillAvailability: SkillAvailabilityMap;
	mcpToolsById?: Record<string, McpToolItem[]>;
	mcpToolsErrors?: Record<string, string>;
	verifyResults?: Record<string, McpVerifyResult>;
	verifyErrors?: Record<string, string>;
}): ExternalToolRow[] {
	const mcpRows: ExternalToolRow[] = mcpCatalog
		.filter((item) => item.type === "mcp-server")
		.map((item) => ({
			id: item.id,
			type: "mcp",
			name: item.name,
			capabilities: Array.isArray(item.executionFunctions)
				? item.executionFunctions.filter((fn) => fn.trim().length > 0)
				: [],
			isLoaded: Boolean(item.enabled) && item.startup_ready !== false,
			detailPayload: {
				description: item.description,
				runtimeMode: item.runtime_mode || "stdio_only",
				source: item.source,
				startupDiagnostic:
					item.startup_ready === false
						? String(item.startup_error || "启动未就绪")
						: "启动正常",
				toolListDiagnostic: String(mcpToolsErrors[item.id] || ""),
				tools: mcpToolsById[item.id] || [],
				verifyResult: verifyResults[item.id] || null,
				verifyError: String(verifyErrors[item.id] || ""),
			},
		}));

	const skillRows: ExternalToolRow[] = skillCatalog.map((tool) => ({
		id: tool.id,
		type: "skill",
		name: tool.id,
		capabilities: tool.taskList,
		isLoaded: skillAvailability[tool.id]?.enabled !== false,
		detailPayload: {
			summary: tool.summary,
			goal: tool.goal,
			taskList: tool.taskList,
			prompt: buildSkillToolPrompt(tool),
			exampleInput: tool.exampleInput,
			inputChecklist: tool.inputChecklist,
			pitfalls: tool.pitfalls,
		},
	}));

	return [...mcpRows, ...skillRows];
}

export function buildExternalToolListState({
	rows,
	searchQuery,
	page,
	pageSize = EXTERNAL_TOOLS_PAGE_SIZE,
}: {
	rows: ExternalToolRow[];
	searchQuery: string;
	page: number;
	pageSize?: number;
}): ExternalToolListState {
	const normalizedQuery = String(searchQuery || "").trim().toLowerCase();
	const safePageSize = Math.max(1, Math.floor(pageSize) || EXTERNAL_TOOLS_PAGE_SIZE);
	const filteredRows = normalizedQuery
		? rows.filter((row) => {
				const searchable = [row.name, ...row.capabilities].join(" ").toLowerCase();
				return searchable.includes(normalizedQuery);
		  })
		: rows;
	const totalRows = filteredRows.length;
	const totalPages = Math.max(1, Math.ceil(totalRows / safePageSize));
	const normalizedPage =
		totalRows === 0 ? 1 : Math.min(Math.max(1, Math.floor(page) || 1), totalPages);
	const startIndex = totalRows === 0 ? 0 : (normalizedPage - 1) * safePageSize;

	return {
		filteredRows,
		pageRows: filteredRows.slice(startIndex, startIndex + safePageSize),
		page: normalizedPage,
		pageSize: safePageSize,
		totalRows,
		totalPages,
		startIndex,
		searchQuery: String(searchQuery || ""),
	};
}

export function buildExternalToolDetailSections(
	row: ExternalToolRow,
): ExternalToolDetailSection[] {
	if (row.type === "mcp") {
		return [
			{
				title: "基础信息",
				kind: "properties",
				properties: [
					{ label: "名称", value: row.name },
					{ label: "描述", value: row.detailPayload.description || "-" },
					{ label: "运行模式", value: row.detailPayload.runtimeMode || "-" },
					{ label: "来源", value: row.detailPayload.source || "-" },
					{ label: "启动诊断", value: row.detailPayload.startupDiagnostic || "-" },
					{
						label: "工具列表诊断",
						value: row.detailPayload.toolListDiagnostic || "工具列表正常",
					},
				],
			},
			{
				title: "可用工具明细",
				kind: "mcp-tools",
				tools: row.detailPayload.tools,
				error: row.detailPayload.toolListDiagnostic,
			},
			{
				title: "执行验证",
				kind: "mcp-verify",
				result: row.detailPayload.verifyResult,
				error: row.detailPayload.verifyError,
			},
		];
	}

	return [
		{
			title: "基础信息",
			kind: "properties",
			properties: [
				{ label: "名称", value: row.name },
				{ label: "摘要", value: row.detailPayload.summary || "-" },
				{ label: "使用目标", value: row.detailPayload.goal || "-" },
			],
		},
		{
			title: "任务清单",
			kind: "list",
			items: row.detailPayload.taskList,
		},
		{
			title: "Prompt 模板",
			kind: "code",
			code: row.detailPayload.prompt,
		},
		{
			title: "示例输入",
			kind: "code",
			code: row.detailPayload.exampleInput,
		},
		{
			title: "参数清单",
			kind: "list",
			items: row.detailPayload.inputChecklist,
		},
		{
			title: "误用提示",
			kind: "list",
			items: row.detailPayload.pitfalls,
		},
	];
}
