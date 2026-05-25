import test from "node:test";
import assert from "node:assert/strict";

import {
  getStaticAnalysisEngineLabel,
  getStaticAnalysisTaskBasePath,
  getStaticAnalysisTaskQueryParam,
  isStaticAnalysisEngine,
  STATIC_ANALYSIS_ENGINE_IDS,
} from "../src/shared/api/staticAnalysisEngines.ts";

test("static analysis engine descriptors expose Joern as a first-class engine", () => {
  assert.deepEqual(STATIC_ANALYSIS_ENGINE_IDS, ["opengrep", "codeql", "joern"]);
  assert.equal(getStaticAnalysisEngineLabel("joern"), "Joern");
  assert.equal(getStaticAnalysisTaskBasePath("joern"), "/static-tasks/joern/tasks");
  assert.equal(getStaticAnalysisTaskQueryParam("joern"), "joernTaskId");
  assert.equal(isStaticAnalysisEngine("joern"), true);
  assert.equal(isStaticAnalysisEngine("legacy-java"), false);
});
