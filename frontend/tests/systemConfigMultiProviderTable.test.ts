import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const systemConfigPath = path.resolve(process.cwd(), "src/components/system/SystemConfig.tsx");
const databaseApiPath = path.resolve(process.cwd(), "src/shared/api/database.ts");

test("SystemConfig renders required multi-provider table columns and actions", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	for (const column of ["序号", "模型供应商", "地址", "模型", "状态", "操作"]) {
		assert.match(source, new RegExp(column));
	}
	assert.match(source, /openCreateDialog/);
	assert.match(source, /openEditDialog/);
	assert.match(source, /deleteRow/);
	assert.match(source, /moveRow\(row, -1\)/);
	assert.match(source, /moveRow\(row, 1\)/);
	assert.doesNotMatch(source, /runtime-health|运行时健康/);
});

test("SystemConfig uses updated grid columns and enlarged fonts", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.match(source, /<Table className="table-fixed text-base"/);
	assert.match(source, /TableHead className="w-16/);
	assert.match(source, /showInlineSaveButtons/);
});

test("SystemConfig renders LLM summary badges with available and abnormal counts", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.match(source, /可用/);
	assert.match(source, /异常/);
	assert.match(source, /border-emerald-500\/40 text-emerald-300/);
	assert.match(source, /border-rose-500\/40 text-rose-300/);
	assert.match(source, /新增配置/);
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

test("SystemConfig uses global saved-config batch validation while preserving row diagnostics", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	const databaseSource = readFileSync(databaseApiPath, "utf8");
	assert.match(source, /runSaveThenBatchValidateAction/);
	assert.match(source, /batchTestLLMConnections/);
	assert.match(source, /await reloadConfig\(\)/);
	assert.match(source, /保存并验证/);
	assert.match(source, /批量验证中/);
	assert.match(source, /handleSaveAndTestRow/);
	assert.match(source, /testLLMConnection/);
	assert.match(databaseSource, /batchTestLLMConnections/);
	assert.match(databaseSource, /\/system-config\/test-llm\/batch/);
});

test("SystemConfig delete action is text-only without Trash2 icon", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.doesNotMatch(source, /\bTrash2\b/);
	assert.match(source, />删除<\/Button>/);
});

test("SystemConfig status text covers persisted batch validation states and timestamps", () => {
	const source = readFileSync(systemConfigPath, "utf8");
	assert.match(source, /missing_fields/);
	assert.match(source, /字段不完整/);
	assert.match(source, /checkedAt/);
	assert.match(source, /上次验证/);
	assert.match(source, /禁用/);
});
