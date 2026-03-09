import test from "node:test";
import assert from "node:assert/strict";

import {
	buildExternalToolRows,
	buildExternalToolDetailSections,
} from "../src/pages/intelligent-scan/externalToolsViewModel.ts";

test("buildExternalToolRows merges MCP before SKILL and keeps unloaded items visible", () => {
	const rows = buildExternalToolRows({
		mcpCatalog: [
			{
				id: "filesystem",
				name: "Filesystem MCP",
				type: "mcp-server",
				enabled: true,
				description: "Read files",
				executionFunctions: ["read_file", "list_directory", "search_files"],
				inputInterface: [],
				outputInterface: [],
				includedSkills: [],
				verificationTools: [],
				source: "builtin",
				runtime_mode: "stdio_only",
				required: true,
				startup_ready: true,
				startup_error: null,
			},
			{
				id: "code_index",
				name: "Code Index MCP",
				type: "mcp-server",
				enabled: true,
				description: "Index code",
				executionFunctions: ["find_files"],
				inputInterface: [],
				outputInterface: [],
				includedSkills: [],
				verificationTools: [],
				source: "builtin",
				runtime_mode: "stdio_only",
				required: true,
				startup_ready: false,
				startup_error: "healthcheck_failed:timeout",
			},
		],
		skillCatalog: [
			{
				id: "smart_scan",
				category: "模型基础增强类",
				summary: "智能扫描入口",
				goal: "扫描高风险区域",
				taskList: ["执行整体扫描", "输出高风险区域", "给出下一步建议"],
				inputChecklist: ["target_path"],
				exampleInput: "{}",
				pitfalls: ["不要直接下结论"],
			},
			{
				id: "verify_vulnerability",
				category: "漏洞验证与 PoC 规划",
				summary: "验证漏洞",
				goal: "输出验证结论",
				taskList: ["制定验证路径"],
				inputChecklist: ["finding"],
				exampleInput: "{}",
				pitfalls: ["不要证据不足就 confirmed"],
			},
		],
		skillAvailability: {
			verify_vulnerability: {
				enabled: false,
				reason: "disabled",
			},
		},
	});

	assert.deepEqual(
		rows.map((item) => ({
			id: item.id,
			type: item.type,
			isLoaded: item.isLoaded,
			capabilities: item.capabilities,
		})),
		[
			{
				id: "filesystem",
				type: "mcp",
				isLoaded: true,
				capabilities: ["read_file", "list_directory", "search_files"],
			},
			{
				id: "code_index",
				type: "mcp",
				isLoaded: false,
				capabilities: ["find_files"],
			},
			{
				id: "smart_scan",
				type: "skill",
				isLoaded: true,
				capabilities: ["执行整体扫描", "输出高风险区域", "给出下一步建议"],
			},
			{
				id: "verify_vulnerability",
				type: "skill",
				isLoaded: false,
				capabilities: ["制定验证路径"],
			},
		],
	);
});

test("buildExternalToolDetailSections returns MCP and SKILL specific sections", () => {
	const mcpSections = buildExternalToolDetailSections({
		type: "mcp",
		name: "Filesystem MCP",
		detailPayload: {
			description: "Read files",
			runtimeMode: "stdio_only",
			source: "builtin",
			startupDiagnostic: "启动正常",
			tools: [
				{
					name: "read_file",
					description: "读取文件",
					inputSchema: { file_path: "string" },
				},
			],
			verifyResult: null,
			verifyError: "",
		},
	});

	const skillSections = buildExternalToolDetailSections({
		type: "skill",
		name: "smart_scan",
		detailPayload: {
			summary: "智能扫描入口",
			goal: "扫描高风险区域",
			taskList: ["执行整体扫描"],
			prompt: "prompt body",
			exampleInput: "{}",
			inputChecklist: ["target_path"],
			pitfalls: ["不要直接下结论"],
		},
	});

	assert.deepEqual(
		mcpSections.map((item) => item.title),
		["基础信息", "可用工具明细", "执行验证"],
	);
	assert.deepEqual(
		skillSections.map((item) => item.title),
		["基础信息", "任务清单", "Prompt 模板", "示例输入", "参数清单", "误用提示"],
	);
});
