import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("static analysis detail page is opengrep-only and no longer imports retired engines", () => {
  const pageSource = fs.readFileSync(
    path.join(frontendDir, "src/pages/StaticAnalysis.tsx"),
    "utf8",
  );
  const hookSource = fs.readFileSync(
    path.join(frontendDir, "src/pages/static-analysis/useStaticAnalysisData.ts"),
    "utf8",
  );

  assert.doesNotMatch(pageSource, /gitleaksTaskId|banditTaskId|phpstanTaskId|pmdTaskId/);
  assert.doesNotMatch(
    hookSource,
    /getGitleaksFindings|getBanditFindings|getPhpstanFindings|getPmdFindings/,
  );
  assert.doesNotMatch(
    hookSource,
    /getGitleaksScanTask|getBanditScanTask|getPhpstanScanTask|getPmdScanTask/,
  );
  assert.doesNotMatch(
    hookSource,
    /interruptGitleaksScanTask|interruptBanditScanTask|interruptPhpstanScanTask|interruptPmdScanTask/,
  );
  assert.doesNotMatch(
    hookSource,
    /updateGitleaksFindingStatus|updateBanditFindingStatus|updatePhpstanFindingStatus|updatePmdFindingStatus/,
  );
});
