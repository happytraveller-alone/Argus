import test from "node:test";
import assert from "node:assert/strict";

import * as createProjectScanUtils from "../src/components/scan/create-project-scan/utils.ts";
import {
  extractCreateScanTaskApiErrorMessage,
  stripScanArchiveSuffix,
} from "../src/components/scan/create-scan-task/utils.ts";

const {
  extractCreateProjectScanApiErrorMessage,
  buildCreateProjectScanSystemConfigUpdate,
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
  assert.equal(normalizeCreateProjectScanProvider("Claude"), "claude");
  assert.equal(normalizeCreateProjectScanProvider(""), "openai_compatible");

  assert.equal(
    resolveCreateProjectScanEffectiveApiKey("anthropic_compatible", {
      llmApiKey: "",
      claudeApiKey: "claude-key",
    }),
    "",
  );
  assert.equal(
    resolveCreateProjectScanEffectiveApiKey("openai_compatible", {
      llmApiKey: "shared-key",
      openaiApiKey: "provider-key",
    }),
    "shared-key",
  );
});

test("buildCreateProjectStaticTaskRoute preserves opengrep query params", () => {
  const params = new URLSearchParams();
  params.set("opengrepTaskId", "og-1");

  assert.equal(
    buildCreateProjectStaticTaskRoute({
      primaryTaskId: "task-1",
      params,
    }),
    "/static-analysis/task-1?opengrepTaskId=og-1",
  );
});

test("buildCreateProjectStaticTaskRoute preserves codeql engine route params", () => {
  const params = new URLSearchParams();
  params.set("codeqlTaskId", "cq-1");
  params.set("engine", "codeql");

  assert.equal(
    buildCreateProjectStaticTaskRoute({
      primaryTaskId: "task-codeql",
      params,
    }),
    "/static-analysis/task-codeql?codeqlTaskId=cq-1&engine=codeql",
  );
});

test("extractCreateProjectScanApiErrorMessage falls back to error.message", () => {
  assert.equal(
    extractCreateProjectScanApiErrorMessage(new Error("请求失败")),
    "请求失败",
  );
});

test("extractCreateProjectScanApiErrorMessage prefers axum error payloads", () => {
  assert.equal(
    extractCreateProjectScanApiErrorMessage({
      response: { data: { error: "LLM 配置缺失：`apiKey` 必填。" } },
    }),
    "LLM 配置缺失：`apiKey` 必填。",
  );
});

test("buildCreateProjectScanSystemConfigUpdate preserves otherConfig for system-config PUT", () => {
  assert.deepEqual(
    buildCreateProjectScanSystemConfigUpdate({
      currentConfig: {
        otherConfig: {
          maxAnalyzeFiles: 20,
          llmConcurrency: 1,
          llmGapMs: 0,
        },
      },
      nextLlmConfig: {
        llmProvider: "openai_compatible",
        llmModel: "gpt-5",
        llmBaseUrl: "https://api.openai.com/v1",
        llmApiKey: "sk-test",
      },
    }),
    {
      llmConfig: {
        llmProvider: "openai_compatible",
        llmModel: "gpt-5",
        llmBaseUrl: "https://api.openai.com/v1",
        llmApiKey: "sk-test",
      },
      otherConfig: {
        maxAnalyzeFiles: 20,
        llmConcurrency: 1,
        llmGapMs: 0,
      },
    },
  );
});
