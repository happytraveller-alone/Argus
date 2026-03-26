import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentFindingDetailRoute,
  resolveFindingDetailBackTarget,
} from "../src/shared/utils/findingRoute.ts";

test("buildAgentFindingDetailRoute preserves task detail pagination in returnTo", () => {
  const route = buildAgentFindingDetailRoute({
    taskId: "task-1",
    findingId: "finding-1",
    currentRoute:
      "/agent-audit/task-1?muteToast=1&returnTo=%2Ftasks%2Fintelligent&findingsPage=3&findingsPageSize=7&detailType=finding&detailId=finding-1",
  });

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
