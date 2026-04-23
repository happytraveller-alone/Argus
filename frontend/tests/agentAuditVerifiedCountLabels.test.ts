import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const statsPanelPath = path.join(
	frontendDir,
	"src/pages/AgentAudit/components/StatsPanel.tsx",
);
const detailPanelPath = path.join(
	frontendDir,
	"src/pages/AgentAudit/components/AgentDetailPanel.tsx",
);
const treeNodePath = path.join(
	frontendDir,
	"src/pages/AgentAudit/components/AgentTreeNode.tsx",
);

test("智能审计详情页相关计数字样和 root agent 计数都使用已验证漏洞口径", () => {
	const statsSource = readFileSync(statsPanelPath, "utf8");
	const detailPanelSource = readFileSync(detailPanelPath, "utf8");
	const treeNodeSource = readFileSync(treeNodePath, "utf8");

	assert.match(statsSource, /label="已验证漏洞"/);
	assert.match(detailPanelSource, /agent\.verified_findings_count/);
	assert.match(treeNodeSource, /node\.verified_findings_count/);
});
