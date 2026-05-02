import test from "node:test";
import assert from "node:assert/strict";

import {
  appendReturnTo,
  sanitizeAgentAuditReturnTo,
  buildProjectCodeBrowserRoute,
  resolveFindingDetailBackTarget,
} from "../src/shared/utils/findingRoute.ts";

test("appendReturnTo preserves sanitized task detail pagination in returnTo", () => {
  const returnTo = sanitizeAgentAuditReturnTo(
    "/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7&detailType=finding&detailId=finding-1",
  );
  const route = appendReturnTo(
    "/finding-detail/agent/task-1/finding-1",
    returnTo,
  );

  const url = new URL(`http://localhost${route}`);
  assert.equal(
    url.searchParams.get("returnTo"),
    "/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7",
  );
});

test("resolveFindingDetailBackTarget prefers explicit returnTo over history back", () => {
  const target = resolveFindingDetailBackTarget({
    returnTo:
      "/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7",
    hasHistory: true,
    state: {
      fromTaskDetail: true,
      preferHistoryBack: true,
    },
  });

  assert.equal(
    target,
    "/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7",
  );
});

test("buildProjectCodeBrowserRoute appends file and line query for deep links", () => {
  const route = buildProjectCodeBrowserRoute({
    projectId: "project-zip",
    filePath: "src/main.ts",
    line: 42,
  });

  const url = new URL(`http://localhost${route}`);
  assert.equal(url.pathname, "/projects/project-zip/code-browser");
  assert.equal(url.searchParams.get("file"), "src/main.ts");
  assert.equal(url.searchParams.get("line"), "42");
});

test("buildProjectCodeBrowserRoute omits invalid line while keeping file query", () => {
  const route = buildProjectCodeBrowserRoute({
    projectId: "project-zip",
    filePath: "src/main.ts",
    line: null,
  });

  const url = new URL(`http://localhost${route}`);
  assert.equal(url.searchParams.get("file"), "src/main.ts");
  assert.equal(url.searchParams.has("line"), false);
});
