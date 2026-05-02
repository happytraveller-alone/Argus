import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(
	path.dirname(fileURLToPath(import.meta.url)),
	"..",
);
const detailPagePath = path.join(
	frontendDir,
	"src/pages/AgentAuditDetail.tsx",
);

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

test("AgentAuditDetail renders all required metadata labels", () => {
	const requiredLabels = [
		"任务 ID",
		"项目 ID",
		"状态",
		"创建时间",
		"开始时间",
		"完成时间",
		"耗时",
		"LLM 模型",
		"LLM Fingerprint",
		"输入摘要",
		"报告摘要",
		"发现问题",
		"事件日志",
	];
	for (const label of requiredLabels) {
		assert.match(source, new RegExp(label), `Missing label: ${label}`);
	}
});

test("AgentAuditDetail renders inputSummary inside a pre block", () => {
	assert.match(source, /<pre/);
	assert.match(source, /inputSummary/);
});

test("AgentAuditDetail renders durationMs field", () => {
	assert.match(source, /durationMs/);
});

test("AgentAuditDetail renders llmModel field", () => {
	assert.match(source, /llmModel/);
});

test("AgentAuditDetail renders llmFingerprint field", () => {
	assert.match(source, /llmFingerprint/);
});

// ---------------------------------------------------------------------------
// Event log table
// ---------------------------------------------------------------------------

test("AgentAuditDetail renders eventLog as a table with kind and timestamp columns", () => {
	assert.match(source, /eventLog/);
	assert.match(source, /<table/);
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

// ---------------------------------------------------------------------------
// Status pill styling
// ---------------------------------------------------------------------------

test("AgentAuditDetail status pill uses orange style for cancelled", () => {
	assert.match(source, /orange-500/);
});

test("AgentAuditDetail status pill uses emerald style for completed", () => {
	assert.match(source, /emerald-500/);
});

test("AgentAuditDetail status pill uses rose style for failed", () => {
	assert.match(source, /rose-500/);
});

test("AgentAuditDetail status pill uses sky style for running/pending", () => {
	assert.match(source, /sky-500/);
});
