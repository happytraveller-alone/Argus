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

test("AgentAuditDetail polls on 5-second interval while non-terminal", () => {
	assert.match(source, /const LIVE_REFRESH_INTERVAL_MS = 5000;/);
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

test("AgentAuditDetail keeps required visible controls and table copy", () => {
	const requiredLabels = ["发现问题", "时间日志", "返回"];
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

test("AgentAuditDetail summary tags include project, live runtime, and finding count", () => {
	assert.match(source, /record\.projectName/);
	assert.match(source, /getRuntimeDurationMs\(record, durationNowMs\)/);
	assert.match(source, /parseTimestampMs\(record\.startedAt\)/);
	assert.match(source, /`运行时长 \$\{formatDuration\(runtimeDurationMs\)\}`/);
	assert.match(source, /发现问题 \$\{findings\.length\.toLocaleString\(\)\}/);
});

test("AgentAuditDetail refreshes the runtime duration label every 5 seconds while live", () => {
	assert.match(source, /const \[durationNowMs, setDurationNowMs\]/);
	assert.match(source, /setDurationNowMs\(Date\.now\(\)\)/);
	assert.match(
		source,
		/setInterval\(\(\) => \{\s*setDurationNowMs\(Date\.now\(\)\);\s*\}, LIVE_REFRESH_INTERVAL_MS\)/,
	);
	assert.match(source, /if \(!record \|\| isTerminal\(record\.status\)\) return undefined;/);
});

test("AgentAuditDetail places return button to the right of summary tags", () => {
	assert.match(source, /<ArrowLeft/);
	assert.match(source, /onClick=\{handleBack\}/);
});

test("AgentAuditDetail renders findings with CodeQL-style horizontally scrollable data table", () => {
	assert.match(source, /<DataTable/);
	assert.match(source, /buildFindingColumns\(record, navigate, handleVerdict\)/);
	assert.match(source, /tableClassName="min-w-\[1280px\]"/);
	assert.match(source, /tableContainerClassName="overflow-x-auto rounded-sm"/);
});

test("AgentAuditDetail defaults the findings table to an available 10-row page size", () => {
	assert.match(
		source,
		/pagination:\s*\{\s*pageIndex:\s*0,\s*pageSize:\s*10\s*\}/,
	);
	assert.match(source, /pageSizeOptions:\s*\[10, 20, 50\]/);
	assert.doesNotMatch(
		source,
		/pagination:\s*\{\s*pageIndex:\s*0,\s*pageSize:\s*15\s*\}/,
	);
});

test("AgentAuditDetail keeps terminal durationMs as the stable completed runtime", () => {
	assert.match(source, /durationMs/);
	assert.match(
		source,
		/if \(isTerminal\(record\.status\)\) \{\s*if \(record\.durationMs !== undefined\) return record\.durationMs;/,
	);
});

// ---------------------------------------------------------------------------
// Event log dialog
// ---------------------------------------------------------------------------

test("AgentAuditDetail renders eventLog records in the time log dialog", () => {
	assert.match(source, /eventLog/);
	assert.match(source, /replayEvents/);
	assert.match(source, /activeEvents/);
	assert.match(source, /时间日志/);
	assert.match(source, /ev\.kind/);
	assert.match(source, /ev\.timestamp/);
});

test("AgentAuditDetail merges backend replay, SSE, and cached time-log events cumulatively", () => {
	assert.match(source, /mergeTimelineEvents\(baseEvents, replayEvents, sseEvents\)/);
	assert.match(source, /timelineEventKey/);
	assert.match(source, /readCachedTimelineEvents\(taskId\)/);
	assert.match(source, /writeCachedTimelineEvents\(timelineState\.taskId, timelineState\.events\)/);
	assert.doesNotMatch(source, /sseEvents\.length > 0 \? sseEvents : replayEvents/);
});

test("AgentAuditDetail bounds the cumulative time-log cache", () => {
	assert.match(source, /const TIMELINE_CACHE_LIMIT = 1000;/);
	assert.match(source, /\.slice\(-TIMELINE_CACHE_LIMIT\)/);
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
// agentTable.canonical  (AC8)
// Table column renderers consume buildCanonicalDisplay — assert usage pattern
// ---------------------------------------------------------------------------

test("agentTable.canonical — buildCanonicalDisplay is used in column renderers", () => {
	// 名称 column was intentionally removed; remaining columns still consume buildCanonicalDisplay
	assert.match(source, /buildCanonicalDisplay/);
});

test("agentTable.canonical — 漏洞类型 column uses canonical.typeLabel", () => {
	assert.match(source, /canonical\.typeLabel/);
});

test("agentTable.canonical — 文件位置 column uses canonical.locationLabel", () => {
	assert.match(source, /canonical\.locationLabel/);
});

test("agentTable.canonical — buildCanonicalDisplay receives auditType 智能审计", () => {
	assert.match(source, /"智能审计"/);
});

test("agentTable.canonical — buildCanonicalDisplay receives record.llmModel as engineLabel", () => {
	assert.match(source, /record\?\.llmModel/);
});

test("agentTable.canonical — buildCanonicalDisplay receives record.projectName", () => {
	assert.match(source, /record\?\.projectName/);
});

// ---------------------------------------------------------------------------
// agentSnapshot.projectName  (AC12)
// buildAgentFindingSnapshot passes projectName/llmModel/projectRoot into state
// ---------------------------------------------------------------------------

test("agentSnapshot.projectName — snapshot builder passes projectName into navigation state", () => {
	assert.match(source, /buildAgentFindingSnapshot/);
	assert.match(source, /record\.projectName/);
});

test("agentSnapshot.projectName — snapshot builder passes llmModel into navigation state", () => {
	assert.match(source, /record\.llmModel/);
});

test("agentSnapshot.projectName — snapshot builder passes projectRoot into navigation state", () => {
	assert.match(source, /record\.projectRoot/);
});
