import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const systemConfigPath = path.resolve(process.cwd(), "src/components/system/SystemConfig.tsx");
const databaseApiPath = path.resolve(process.cwd(), "src/shared/api/database.ts");

test("SystemConfig renders required multi-provider table columns and actions", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.match(source, /\["序号", "模型供应商", "地址", "模型", "状态", "操作"\]/);
	assert.match(source, /openCreateDialog/);
	assert.match(source, /openEditDialog/);
	assert.match(source, /deleteRow/);
	assert.match(source, /moveRow\(row, -1\)/);
	assert.match(source, /moveRow\(row, 1\)/);
	assert.doesNotMatch(source, /runtime-health|运行时健康/);
});

test("SystemConfig edit dialog masks keys and preserves blank saved secrets", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.match(source, /type="password"/);
	assert.match(source, /留空保留已保存密钥，输入则替换/);
	assert.match(source, /hasApiKey: row\.hasApiKey \|\| item\.hasApiKey/);
	assert.match(source, /高级配置/);
	assert.match(source, /llmCustomHeaders/);
	assert.match(source, /agentTimeout/);
});

test("database API accepts row-aware LLM calls", () => {
	const source = readFileSync(databaseApiPath, "utf8");
	assert.match(source, /rowId\?: string;[\s\S]*provider: string;/);
	assert.match(source, /rowId\?: string;[\s\S]*provider\?: string;/);
});
