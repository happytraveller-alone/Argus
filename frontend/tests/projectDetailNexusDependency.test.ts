import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const projectDetailPath = path.resolve(
  process.cwd(),
  "src/pages/ProjectDetail.tsx",
);

test("ProjectDetail no longer depends on nexus-itemDetail iframe or ZIP postMessage bridge", () => {
  const source = fs.readFileSync(projectDetailPath, "utf8");

  assert.doesNotMatch(source, /5175/);
  assert.doesNotMatch(source, /postMessage\s*\(/);
  assert.doesNotMatch(source, /nexusIframeRef/);
  assert.doesNotMatch(source, /iframeReadyRef/);
  assert.doesNotMatch(source, /archiveSentRef/);
  assert.doesNotMatch(source, /sendArchiveToIframe/);
  assert.doesNotMatch(source, /handleIframeLoad/);
  assert.doesNotMatch(source, /Nexus-itemDetail/);
  assert.doesNotMatch(source, /<iframe/i);
});

test("ProjectDetail keeps local detail sections after Nexus cleanup", () => {
  const source = fs.readFileSync(projectDetailPath, "utf8");

  assert.match(source, /项目简介/);
  assert.match(source, /最近任务/);
  assert.match(source, /ProjectPotentialVulnerabilitiesSection/);
});
