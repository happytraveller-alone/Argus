import test from "node:test";
import assert from "node:assert/strict";

import { shouldIgnoreStaleToolEvent } from "../src/pages/AgentAudit/utils.ts";
import type { LogItem } from "../src/pages/AgentAudit/types.ts";

function createToolLog(overrides: Partial<LogItem> = {}): LogItem {
  return {
    id: "tool-log-1",
    time: "00:00:01",
    type: "tool",
    title: "已完成：read_file",
    content: "输出：done",
    tool: {
      name: "read_file",
      status: "completed",
      callId: "call-1",
    },
    detail: {
      sequence: 12,
      metadata: {
        tool_call_id: "call-1",
      },
    },
    ...overrides,
  };
}

test("stale tool_call does not regress an already completed tool log", () => {
  const existingLog = createToolLog();

  assert.equal(
    shouldIgnoreStaleToolEvent({
      existingLog,
      incomingEventType: "tool_call",
      incomingSequence: 11,
      incomingToolCallId: "call-1",
    }),
    true,
  );
});

test("newer tool_result still updates the existing tool log", () => {
  const existingLog = createToolLog({
    tool: {
      name: "read_file",
      status: "running",
      callId: "call-1",
    },
    title: "运行中：read_file",
    detail: {
      sequence: 11,
      metadata: {
        tool_call_id: "call-1",
      },
    },
  });

  assert.equal(
    shouldIgnoreStaleToolEvent({
      existingLog,
      incomingEventType: "tool_result",
      incomingSequence: 12,
      incomingToolCallId: "call-1",
    }),
    false,
  );
});

test("different tool_call_id does not trigger the stale-event guard", () => {
  const existingLog = createToolLog();

  assert.equal(
    shouldIgnoreStaleToolEvent({
      existingLog,
      incomingEventType: "tool_call",
      incomingSequence: 10,
      incomingToolCallId: "call-2",
    }),
    false,
  );
});
