import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function read(relativePath: string) {
	return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

test("high-impact frontend copy uses 扫描 terminology", () => {
	const cases = [
		{
			file: "src/app/routes.tsx",
			mustInclude: ["扫描规则"],
			mustExclude: ["审计规则"],
		},
		{
			file: "src/pages/Dashboard.tsx",
			mustInclude: ["扫描规则"],
			mustExclude: ["审计规则"],
		},
		{
			file: "src/components/scan/CreateScanTaskDialog.tsx",
			mustInclude: [
				"开始代码扫描",
				"启动智能扫描",
				"智能扫描任务已创建",
			],
			mustExclude: ["开始代码审计", "启动智能审计", "智能审计任务已创建"],
		},
		{
			file: "src/components/scan/CreateProjectScanDialog.tsx",
			mustInclude: ["创建扫描", "静态扫描", "智能扫描"],
			mustExclude: ["创建审计", "静态审计", "智能审计"],
		},
		{
			file: "src/pages/ProjectDetail.tsx",
			mustInclude: ["扫描任务已创建", "静态扫描", "智能扫描", "启动扫描"],
			mustExclude: ["审计任务已创建", "静态审计", "智能审计", "启动审计"],
		},
		{
			file: "src/pages/intelligent-scan/SkillToolsPanel.tsx",
			mustInclude: ["外部工具列表", "是否加载", "可执行功能"],
			mustExclude: ["智能审计 MCP 目录", "智能审计 SKILL 目录"],
		},
		{
			file: "src/shared/i18n/messages.ts",
			mustInclude: ["扫描规则", '"Scan Tasks"'],
			mustExclude: ["审计规则", '"Audit Tasks"'],
		},
	] as const;

	for (const entry of cases) {
		const content = read(entry.file);
		for (const phrase of entry.mustInclude) {
			assert.match(
				content,
				new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
				`${entry.file} should include ${phrase}`,
			);
		}
		for (const phrase of entry.mustExclude) {
			assert.doesNotMatch(
				content,
				new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
				`${entry.file} should not include ${phrase}`,
			);
		}
	}
});
