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

test("scan engine rule stats use dashboard compact summary card tokens", () => {
	const source = readFileSync(opengrepRulesPath, "utf8");
	const statsSection = source.slice(
		source.indexOf("const RULE_STATS_GRID_CLASSNAME"),
		source.indexOf("<div className=\"cyber-card relative z-10 overflow-hidden\">"),
	);

	assert.match(
		source,
		/const RULE_STATS_CARD_CLASSNAME =\s*"rounded-sm border border-border bg-card text-card-foreground shadow-sm flex min-w-0 items-center justify-between gap-3 px-3 py-3"/,
	);
	assert.match(
		source,
		/const RULE_STATS_CARD_LABEL_CLASSNAME =\s*"text-sm uppercase tracking-\[0\.12em\] text-muted-foreground"/,
	);
	assert.match(
		source,
		/const RULE_STATS_CARD_VALUE_CLASSNAME =\s*"text-right text-xl font-semibold tabular-nums text-foreground"/,
	);
	assert.doesNotMatch(statsSection, /cyber-card p-4/);
	assert.doesNotMatch(statsSection, /stat-icon/);
	assert.doesNotMatch(statsSection, /stat-value/);
	assert.match(source, /cyber-card cyber-card-flat relative z-10 overflow-hidden/);
});

test("intelligent engine summary cards mirror dashboard card typography", () => {
	const source = readFileSync(intelligentEnginePath, "utf8");

	assert.match(
		source,
		/const ENGINE_SUMMARY_CARD_CLASSNAME =\s*"rounded-sm border border-border bg-card text-card-foreground shadow-sm flex min-w-0 items-center justify-between gap-3 px-3 py-3"/,
	);
	assert.match(
		source,
		/const ENGINE_SUMMARY_CARD_LABEL_CLASSNAME =\s*"text-sm uppercase tracking-\[0\.12em\] text-muted-foreground"/,
	);
	assert.match(
		source,
		/const ENGINE_SUMMARY_CARD_VALUE_CLASSNAME =\s*"min-w-0 break-all text-right text-xl font-semibold tabular-nums text-foreground"/,
	);
	assert.doesNotMatch(source, /text-2xl/);
	assert.doesNotMatch(source, /h-14 w-14/);
	assert.doesNotMatch(source, /from "lucide-react";[\s\S]*Brain/);
	assert.match(source, /cardClassName="cyber-card-flat"/);
});
