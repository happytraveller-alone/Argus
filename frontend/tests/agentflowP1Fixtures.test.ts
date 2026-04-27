import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentAuditTaskFindingCountersPatch,
  summarizeAgentAuditFindings,
} from "../src/pages/AgentAudit/detailViewModel.ts";
import { buildAgentFindingDetailModel } from "../src/pages/finding-detail/viewModel.ts";
import {
  failurePathAgentTaskFixture,
  happyPathAgentFindingFixture,
  happyPathAgentTaskFixture,
  nativeArtifactsOnlyOutputFixture,
  staticOriginCandidateFixture,
} from "./fixtures/agentflowP1Fixtures.ts";

function hasStaticOrigin(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  const source = record.source && typeof record.source === "object"
    ? record.source as Record<string, unknown>
    : {};
  return [record.source_origin, source.kind, source.engine].some((candidate) =>
    String(candidate || "").toLowerCase().includes("static"),
  );
}

test("AgentFlow P1 fixtures expose a native happy-path finding to frontend counters", () => {
  assert.equal(happyPathAgentTaskFixture.tool_evidence_protocol, "native_v1");

  const summary = summarizeAgentAuditFindings([happyPathAgentFindingFixture]);
  assert.equal(summary.findingsCount, 1);
  assert.equal(summary.verifiedCount, 1);
  assert.deepEqual(summary.effectiveSeverityCounts, {
    critical: 0,
    high: 1,
    medium: 0,
    low: 0,
    info: 0,
  });

  const patch = buildAgentAuditTaskFindingCountersPatch({
    task: happyPathAgentTaskFixture,
    findings: [happyPathAgentFindingFixture],
  });
  assert.equal(patch.findings_count, 1);
  assert.equal(patch.verified_high_count, 1);
  assert.equal(patch.defect_summary.status_counts.verified, 1);
});

test("AgentFlow P1 happy-path finding renders as an agent detail, not a static finding", () => {
  const model = buildAgentFindingDetailModel({
    finding: happyPathAgentFindingFixture,
    taskId: happyPathAgentTaskFixture.id,
    findingId: happyPathAgentFindingFixture.id,
    projectId: happyPathAgentTaskFixture.project_id,
    projectSourceType: "zip",
    projectName: "agentflow-demo",
  });

  assert.equal(model.pageTitle, "统一漏洞详情");
  assert.equal(model.overviewItems[0]?.value, "订单查询接口可被拼接 SQL 输入影响");
  assert.match(model.narrativeSections[0]?.content || "", /业务调用链验证/);
  assert.equal(model.codeSections[0]?.filePath, "src/orders/repository.ts");
  assert.equal(model.codeSections[0]?.fullFileAvailable, true);
});

test("AgentFlow P1 failure fixture keeps Chinese diagnostics and no findings", () => {
  assert.equal(failurePathAgentTaskFixture.status, "failed");
  assert.equal(failurePathAgentTaskFixture.findings_count, 0);
  assert.match(failurePathAgentTaskFixture.error_message || "", /智能审计运行失败/);
});

test("AgentFlow P1 static-origin fixture is rejected by the frontend fixture guard", () => {
  assert.equal(hasStaticOrigin(staticOriginCandidateFixture), true);
});

test("AgentFlow P1 native artifacts are not promoted into direct findings", () => {
  assert.equal(nativeArtifactsOnlyOutputFixture.findings.length, 0);
  assert.equal(nativeArtifactsOnlyOutputFixture.native_artifacts.length, 2);
  assert.match(nativeArtifactsOnlyOutputFixture.native_artifacts[0]?.content || "", /不得直接导入为漏洞/);
});
