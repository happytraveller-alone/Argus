import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const homePagePath = path.resolve(
  process.cwd(),
  "src/pages/AgentAudit/index.tsx",
);

test("agent audit home does not depend on external CDN scripts for startup rendering", () => {
  const source = fs.readFileSync(homePagePath, "utf8");

  assert.doesNotMatch(source, /cdnjs\.cloudflare\.com/i);
  assert.doesNotMatch(source, /cdn\.jsdelivr\.net/i);
  assert.doesNotMatch(source, /loadScript\s*\(/);
});

test("agent audit home no longer depends on nexus-web runtime", () => {
  const source = fs.readFileSync(homePagePath, "utf8");

  assert.doesNotMatch(source, /GitNexus/);
  assert.doesNotMatch(source, /localhost:5174/);
  assert.doesNotMatch(source, /:5174/);
  assert.doesNotMatch(source, /postMessage\s*\(/);
  assert.doesNotMatch(source, /<iframe/i);
});
