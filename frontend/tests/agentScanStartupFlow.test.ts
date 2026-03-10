import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function read(relativePath: string) {
	return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

test("scan creation dialogs no longer block on frontend LLM preflight", () => {
	const cases = [
		"src/components/scan/CreateProjectScanDialog.tsx",
		"src/components/scan/CreateScanTaskDialog.tsx",
	] as const;

	for (const file of cases) {
		const content = read(file);
		assert.doesNotMatch(content, /runAgentPreflightCheck\s*\(/, `${file} should not call runAgentPreflightCheck()`);
		assert.doesNotMatch(content, /正在检查智能扫描配置（LLM）\.\.\./, `${file} should not show blocking LLM preflight toast`);
	}
});

test("scan creation dialogs still navigate to task detail after task creation", () => {
	const cases = [
		"src/components/scan/CreateProjectScanDialog.tsx",
		"src/components/scan/CreateScanTaskDialog.tsx",
	] as const;

	for (const file of cases) {
		const content = read(file);
		assert.match(content, /navigate\(`\/agent-audit\/\$\{agentTask\.id\}`\)/, `${file} should navigate to /agent-audit/:taskId`);
	}
});
