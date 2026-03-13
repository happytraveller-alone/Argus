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
