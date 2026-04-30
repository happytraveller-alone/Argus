import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const opengrepRulesPath = path.join(frontendDir, "src/pages/OpengrepRules.tsx");
const intelligentEnginePath = path.join(
	frontendDir,
	"src/pages/ScanConfigIntelligentEngine.tsx",
);

test("scan engine rule stats render as compact inline badges above the table", () => {
	const source = readFileSync(opengrepRulesPath, "utf8");
	const statsSection = source.slice(
		source.indexOf("{/* Search + Stats Badges + Engine Selector */}"),
		source.indexOf('<div className="cyber-card cyber-card-flat relative z-10 overflow-hidden">'),
	);

	assert.match(statsSection, /规则数量/);
	assert.match(statsSection, /支持语言/);
	assert.match(statsSection, /border-cyan-500\/30 bg-cyan-500\/10 text-cyan-300/);
	assert.match(statsSection, /border-emerald-500\/30 bg-emerald-500\/10 text-emerald-300/);
	assert.doesNotMatch(statsSection, /cyber-card p-4/);
	assert.doesNotMatch(statsSection, /stat-icon/);
	assert.doesNotMatch(statsSection, /stat-value/);
	assert.match(source, /cyber-card cyber-card-flat relative z-10 overflow-hidden/);
});

test("intelligent engine page delegates summary rendering to SystemConfig table view", () => {
	const source = readFileSync(intelligentEnginePath, "utf8");

	assert.match(source, /<SystemConfig/);
	assert.match(source, /visibleSections=\{\["llm"\]\}/);
	assert.match(source, /cardClassName="cyber-card-flat"/);
	assert.match(source, /showLlmSummaryCards=\{false\}/);
	assert.match(source, /onLlmSummaryChange=\{setSummaryState\}/);
	assert.doesNotMatch(source, /ENGINE_SUMMARY_CARD_CLASSNAME/);
	assert.doesNotMatch(source, /text-2xl/);
	assert.doesNotMatch(source, /h-14 w-14/);
	assert.doesNotMatch(source, /from "lucide-react";[\s\S]*Brain/);
});
