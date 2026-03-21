import test from "node:test";
import assert from "node:assert/strict";

import * as localization from "../src/pages/AgentAudit/localization.ts";

test("normalizeEventLogPhaseLabel maps backend phases to the five allowed labels", () => {
	assert.equal(
		typeof localization.normalizeEventLogPhaseLabel,
		"function",
	);

	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "preparation" }),
		"初始化",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "planning" }),
		"初始化",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "indexing" }),
		"初始化",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "orchestration" }),
		"编排",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "recon" }),
		"侦查",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "reconnaissance" }),
		"侦查",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "business_logic_recon" }),
		"侦查",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "analysis" }),
		"分析",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "verification" }),
		"分析",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({ rawPhase: "reporting" }),
		"分析",
	);
});

test("normalizeEventLogPhaseLabel only returns 完成 for true completed terminal logs", () => {
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "task_complete",
			taskStatus: "completed",
		}),
		"完成",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "complete",
			taskStatus: "completed",
		}),
		"完成",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			rawPhase: "verification",
			taskStatus: "running",
		}),
		"分析",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "task_cancel",
			taskStatus: "cancelled",
		}) ?? null,
		null,
	);
});

test("normalizeEventLogPhaseLabel falls back to 初始化 for startup info and blank for unknown logs", () => {
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "info",
			message: "任务开始执行: Demo",
		}),
		"初始化",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "progress",
			message: "索引进度: 3/10",
		}),
		"初始化",
	);
	assert.equal(
		localization.normalizeEventLogPhaseLabel?.({
			eventType: "info",
			message: "普通提示",
		}) ?? null,
		null,
	);
});
