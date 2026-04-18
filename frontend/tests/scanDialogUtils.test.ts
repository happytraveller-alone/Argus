import test from "node:test";
import assert from "node:assert/strict";

import * as createProjectScanUtils from "../src/components/scan/create-project-scan/utils.ts";
import {
  extractCreateScanTaskApiErrorMessage,
  stripScanArchiveSuffix,
} from "../src/components/scan/create-scan-task/utils.ts";

const {
  extractCreateProjectScanApiErrorMessage,
  normalizeCreateProjectScanProvider,
  resolveCreateProjectScanEffectiveApiKey,
  buildCreateProjectStaticTaskRoute,
} = createProjectScanUtils;

test("stripScanArchiveSuffix removes common archive suffixes", () => {
  assert.equal(stripScanArchiveSuffix("demo.tar.gz"), "demo");
  assert.equal(stripScanArchiveSuffix("demo.zip"), "demo");
  assert.equal(stripScanArchiveSuffix("demo.py"), "demo.py");
});

test("extractCreateScanTaskApiErrorMessage prefers backend detail", () => {
  const error = {
    response: {
      data: {
        detail: "后端错误",
      },
    },
  };

  assert.equal(extractCreateScanTaskApiErrorMessage(error), "后端错误");
});

test("normalizeCreateProjectScanProvider and resolveCreateProjectScanEffectiveApiKey normalize provider config", () => {
  assert.equal(normalizeCreateProjectScanProvider("Claude"), "anthropic");
  assert.equal(normalizeCreateProjectScanProvider(""), "openai");

  assert.equal(
    resolveCreateProjectScanEffectiveApiKey("anthropic", {
      llmApiKey: "",
      claudeApiKey: "claude-key",
    }),
    "claude-key",
  );
  assert.equal(
    resolveCreateProjectScanEffectiveApiKey("openai", {
      llmApiKey: "shared-key",
      openaiApiKey: "provider-key",
    }),
    "shared-key",
  );
});

test("buildCreateProjectStaticTaskRoute preserves query params", () => {
  const params = new URLSearchParams();
  params.set("opengrepTaskId", "og-1");
  params.set("gitleaksTaskId", "gl-1");

  assert.equal(
    buildCreateProjectStaticTaskRoute({
      primaryTaskId: "task-1",
      params,
    }),
    "/static-analysis/task-1?opengrepTaskId=og-1&gitleaksTaskId=gl-1",
  );
});

test("buildCreateProjectStaticTaskRoute preserves phpstan-only query params", () => {
  const params = new URLSearchParams();
  params.set("phpstanTaskId", "ps-1");
  params.set("tool", "phpstan");

  assert.equal(
    buildCreateProjectStaticTaskRoute({
      primaryTaskId: "task-phpstan",
      params,
    }),
    "/static-analysis/task-phpstan?phpstanTaskId=ps-1&tool=phpstan",
  );
});

test("extractCreateProjectScanApiErrorMessage falls back to error.message", () => {
  assert.equal(
    extractCreateProjectScanApiErrorMessage(new Error("请求失败")),
    "请求失败",
  );
});
