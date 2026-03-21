import test from "node:test";
import assert from "node:assert/strict";

import { api } from "../src/shared/api/database.ts";

test("database api no longer exposes getProjectBranches", () => {
  assert.equal("getProjectBranches" in api, false);
});

test("database api no longer exposes legacy audit and instant analysis helpers", () => {
  assert.equal("getAuditTasks" in api, false);
  assert.equal("getAuditTaskById" in api, false);
  assert.equal("createAuditTask" in api, false);
  assert.equal("updateAuditTask" in api, false);
  assert.equal("cancelAuditTask" in api, false);
  assert.equal("getAuditIssues" in api, false);
  assert.equal("createAuditIssue" in api, false);
  assert.equal("updateAuditIssue" in api, false);
  assert.equal("getInstantAnalyses" in api, false);
  assert.equal("createInstantAnalysis" in api, false);
  assert.equal("deleteInstantAnalysis" in api, false);
  assert.equal("deleteAllInstantAnalyses" in api, false);
  assert.equal("exportTaskReportPDF" in api, false);
  assert.equal("exportInstantReportPDF" in api, false);
});
