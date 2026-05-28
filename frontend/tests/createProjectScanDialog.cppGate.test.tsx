import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);

const dialogPath = path.join(
	frontendDir,
	"src/components/scan/CreateProjectScanDialog.tsx",
);
const contentPath = path.join(
	frontendDir,
	"src/components/scan/create-project-scan/Content.tsx",
);
const createScanTaskDialogPath = path.join(
	frontendDir,
	"src/components/scan/CreateScanTaskDialog.tsx",
);
const utilPath = path.join(
	frontendDir,
	"src/shared/utils/projectLanguage.ts",
);
const scanEnginesPath = path.join(
	frontendDir,
	"src/shared/constants/scanEngines.ts",
);

const dialogSource = readFileSync(dialogPath, "utf8");
const contentSource = readFileSync(contentPath, "utf8");
const createScanTaskDialogSource = readFileSync(createScanTaskDialogPath, "utf8");
const utilSource = readFileSync(utilPath, "utf8");
const scanEnginesSource = readFileSync(scanEnginesPath, "utf8");

// ---------------------------------------------------------------------------
// Util module wiring
// ---------------------------------------------------------------------------

test("projectLanguage util exports isCppProject and CPP_GATE_COPY", () => {
	assert.match(utilSource, /export function isCppProject\(/);
	assert.match(utilSource, /export const CPP_GATE_COPY/);
	assert.match(utilSource, /CPP_PROJECT_THRESHOLD_DEFAULT = 0\.5/);
});

test("projectLanguage util ships the exact Chinese copy strings", () => {
	assert.match(utilSource, /项目语言检测未完成，完成后才可使用/);
	assert.match(utilSource, /当前功能仅支持 C\/C\+\+ 项目/);
});

test("projectLanguage util enforces fail-closed Principle 3 on info_status", () => {
	assert.match(
		utilSource,
		/if \(project\.info_status !== "completed"\)/,
	);
});

// ---------------------------------------------------------------------------
// SCAN_ENGINE_TAB_META wiring
// ---------------------------------------------------------------------------

test("scanEngines exports SCAN_ENGINE_TAB_META with correct C/C++ flags", () => {
	assert.match(scanEnginesSource, /export const SCAN_ENGINE_TAB_META/);
	assert.match(
		scanEnginesSource,
		/opengrep: \{ value: "opengrep", label: "Opengrep", requiresCppProject: false \}/,
	);
	assert.match(
		scanEnginesSource,
		/codeql: \{ value: "codeql", label: "CodeQL", requiresCppProject: true \}/,
	);
	assert.match(
		scanEnginesSource,
		/joern: \{ value: "joern", label: "Joern", requiresCppProject: true \}/,
	);
});

// ---------------------------------------------------------------------------
// CreateProjectScanDialog wiring
// ---------------------------------------------------------------------------

test("CreateProjectScanDialog computes cppGate from selectedProject", () => {
	assert.match(dialogSource, /isCppProject/);
	assert.match(dialogSource, /const cppGate = useMemo/);
	assert.match(dialogSource, /selectedProject\s*\?\s*isCppProject\(selectedProject\)/);
});

test("CreateProjectScanDialog forwards cppGate to Content", () => {
	assert.match(dialogSource, /cppGate=\{cppGate\}/);
});

test("CreateProjectScanDialog falls back to opengrep when gated engine becomes disabled", () => {
	assert.match(dialogSource, /if \(cppGate\.qualifies\) return;/);
	assert.match(dialogSource, /setCodeqlEnabled\(false\)/);
	assert.match(dialogSource, /setJoernEnabled\(false\)/);
	assert.match(dialogSource, /setOpengrepEnabled\(true\)/);
	assert.match(
		dialogSource,
		/SCAN_ENGINE_TAB_META\[prev\]\.requiresCppProject/,
	);
});

// ---------------------------------------------------------------------------
// Content.tsx tab-level disabled UX
// ---------------------------------------------------------------------------

test("Content threads cppGate into engine tab rendering", () => {
	assert.match(contentSource, /cppGate: CppGateResult/);
	assert.match(contentSource, /const isEngineGated = \(key: StaticTool\)/);
	assert.match(
		contentSource,
		/SCAN_ENGINE_TAB_META\[key\]\.requiresCppProject && !cppGate\.qualifies/,
	);
});

test("Content marks gated engine tabs with aria-disabled and tooltip title", () => {
	assert.match(contentSource, /aria-disabled=\{gated \|\| undefined\}/);
	assert.match(contentSource, /title=\{gateTitle\}/);
	assert.match(contentSource, /opacity-50 cursor-not-allowed/);
});

test("Content blocks selection of gated engines via checkbox", () => {
	assert.match(contentSource, /disabled=\{creating \|\| gated\}/);
	assert.match(contentSource, /if \(gated\) return;\s*item\.setChecked/);
});

test("Content wires blockedReason on StaticEngineConfigDialog from cppGateBlockedReason", () => {
	assert.match(
		contentSource,
		/blockedReason=\{[\s\S]*?SCAN_ENGINE_TAB_META\[configEngine\]\.requiresCppProject[\s\S]*?cppGateBlockedReason[\s\S]*?: null[\s\S]*?\}/,
	);
	assert.doesNotMatch(contentSource, /blockedReason=\{null\}/);
});

// ---------------------------------------------------------------------------
// CreateScanTaskDialog wiring
// ---------------------------------------------------------------------------

test("CreateScanTaskDialog computes cppGate and disabled engine map", () => {
	assert.match(createScanTaskDialogSource, /const cppGate = useMemo/);
	assert.match(createScanTaskDialogSource, /isCppProject/);
	assert.match(createScanTaskDialogSource, /disabledStaticTools/);
	assert.match(createScanTaskDialogSource, /blockedStaticToolMessages/);
});

test("CreateScanTaskDialog forces fallback to opengrep when selection is gated", () => {
	assert.match(
		createScanTaskDialogSource,
		/if \(cppGate\.qualifies\) return;/,
	);
	assert.match(
		createScanTaskDialogSource,
		/return \{ opengrep: true, codeql: false, joern: false \};/,
	);
	assert.match(
		createScanTaskDialogSource,
		/SCAN_ENGINE_TAB_META\[prev\]\.requiresCppProject/,
	);
});

test("CreateScanTaskDialog passes cppGateBlockedReason to StaticEngineConfigDialog", () => {
	assert.match(
		createScanTaskDialogSource,
		/blockedReason=\{[\s\S]*?SCAN_ENGINE_TAB_META\[configEngine\]\.requiresCppProject[\s\S]*?cppGateBlockedReason[\s\S]*?: null[\s\S]*?\}/,
	);
	assert.doesNotMatch(
		createScanTaskDialogSource,
		/blockedReason=\{null\}/,
	);
});
