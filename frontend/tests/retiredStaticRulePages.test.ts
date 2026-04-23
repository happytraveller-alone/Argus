import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("retired non-opengrep static rule pages are removed from the frontend surface", () => {
  const retiredFiles = [
    "src/pages/GitleaksRules.tsx",
    "src/pages/BanditRules.tsx",
    "src/pages/PhpstanRules.tsx",
    "src/pages/PmdRules.tsx",
    "src/pages/pmdRulesLoader.ts",
  ];

  for (const relativePath of retiredFiles) {
    assert.equal(
      fs.existsSync(path.join(frontendDir, relativePath)),
      false,
      `${relativePath} should be removed`,
    );
  }
});
