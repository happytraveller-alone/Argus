import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const detailPagePath = path.join(frontendDir, "src/pages/AgentAuditDetail.tsx");

const source = readFileSync(detailPagePath, "utf8");

// ---------------------------------------------------------------------------
// Route / navigation
// ---------------------------------------------------------------------------

test("AgentAuditDetail reads taskId from useParams", () => {
	assert.match(source, /useParams/);
	assert.match(source, /taskId/);
});

// ---------------------------------------------------------------------------
// Polling behaviour
// ---------------------------------------------------------------------------

test("AgentAuditDetail polls on 3-second interval while non-terminal", () => {
	assert.match(source, /3000/);
	assert.match(source, /setInterval/);
});

test("AgentAuditDetail stops polling on terminal status via clearInterval", () => {
	assert.match(source, /isTerminal/);
	assert.match(source, /clearInterval/);
});

test("AgentAuditDetail treats completed, failed, cancelled as terminal", () => {
	assert.match(source, /"completed"/);
	assert.match(source, /"failed"/);
	assert.match(source, /"cancelled"/);
	assert.match(source, /TERMINAL_STATUSES/);
});

// ---------------------------------------------------------------------------
// Cancel button
// ---------------------------------------------------------------------------

test("AgentAuditDetail renders cancel button only while pending or running", () => {
	assert.match(source, /取消任务/);
	assert.match(source, /canCancel/);
	assert.match(
		source,
		/record\.status === "pending"\s*\|\|\s*record\.status === "running"/,
	);
});

test("AgentAuditDetail calls cancelIntelligentTask on cancel", () => {
	assert.match(source, /cancelIntelligentTask/);
	assert.match(source, /handleCancel/);
});

// ---------------------------------------------------------------------------
// Zero-findings proof
// ---------------------------------------------------------------------------

test("AgentAuditDetail shows lifecycle proof hint for 0 findings (not error)", () => {
	assert.match(source, /0 findings \(lifecycle proof captured\)/);
});

// ---------------------------------------------------------------------------
// Failure section
// ---------------------------------------------------------------------------

test("AgentAuditDetail renders failure info section only when status is failed", () => {
	assert.match(source, /record\.status === "failed"/);
	assert.match(source, /失败信息/);
});

test("AgentAuditDetail shows failureStage label", () => {
	assert.match(source, /failureStage/);
	assert.match(source, /失败阶段/);
});

test("AgentAuditDetail shows failureReason label", () => {
	assert.match(source, /failureReason/);
	assert.match(source, /失败原因/);
});

// ---------------------------------------------------------------------------
// Required proof fields visible in UI
// ---------------------------------------------------------------------------

test("AgentAuditDetail removes standalone basic/status/reasoning/summary modules", () => {
	const removedLabels = [
		"基本信息",
		"运行状态",
		"LLM 推理思考",
		"输入摘要",
		"报告摘要",
	];
	for (const label of removedLabels) {
		assert.doesNotMatch(
			source,
			new RegExp(label),
			`Unexpected label: ${label}`,
		);
	}
	assert.doesNotMatch(source, /LlmReasoningPanel/);
});

test("AgentAuditDetail keeps required visible sections", () => {
	const requiredLabels = ["发现问题", "事件日志", "返回"];
	for (const label of requiredLabels) {
		assert.match(source, new RegExp(label), `Missing label: ${label}`);
	}
});

test("AgentAuditDetail header matches CodeQL detail title and summary tag pattern", () => {
	assert.match(source, />\s*智能审计\s*</);
	assert.match(
		source,
		/<legend className="sr-only">智能审计概要标签<\/legend>/,
	);
	assert.match(source, /headerTags\.map/);
});

test("AgentAuditDetail summary tags include project, progress, elapsed time, and finding count", () => {
	assert.match(source, /record\.projectName/);
	assert.match(source, /progressPercent/);
	assert.match(source, /formatDuration\(record\.durationMs\)/);
	assert.match(source, /发现问题 \$\{findings\.length\.toLocaleString\(\)\}/);
});

test("AgentAuditDetail places return button to the right of summary tags", () => {
	assert.match(source, /<ArrowLeft/);
	assert.match(source, /onClick=\{handleBack\}/);
});

test("AgentAuditDetail renders findings with CodeQL-style horizontally scrollable data table", () => {
	assert.match(source, /<DataTable/);
	assert.match(source, /findingColumns/);
	assert.match(source, /tableClassName="min-w-\[1280px\]"/);
	assert.match(source, /tableContainerClassName="overflow-x-auto rounded-sm"/);
});

test("AgentAuditDetail renders durationMs in header tag", () => {
	assert.match(source, /durationMs/);
});

// ---------------------------------------------------------------------------
// Event log table
// ---------------------------------------------------------------------------

test("AgentAuditDetail renders eventLog with kind and timestamp columns", () => {
	assert.match(source, /eventLog/);
	assert.match(source, /<th scope="col">类型<\/th>/);
	assert.match(source, /entry\.kind/);
	assert.match(source, /entry\.timestamp/);
});

// ---------------------------------------------------------------------------
// Loading / error states
// ---------------------------------------------------------------------------

test("AgentAuditDetail handles loading state without crash", () => {
	assert.match(source, /加载中/);
	assert.match(source, /loading/);
});

test("AgentAuditDetail handles fetch error state with retry button", () => {
	assert.match(source, /fetchError/);
	assert.match(source, /重试/);
});
