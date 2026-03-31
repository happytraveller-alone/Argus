import test from "node:test";
import assert from "node:assert/strict";

import {
  extractCreateProjectScanApiErrorMessage,
  normalizeCreateProjectScanProvider,
  resolveCreateProjectScanEffectiveApiKey,
  buildCreateProjectStaticTaskRoute,
  buildHybridStaticBootstrapConfig,
} from "../src/components/scan/create-project-scan/utils.ts";
import {
  extractCreateScanTaskApiErrorMessage,
  stripScanArchiveSuffix,
} from "../src/components/scan/create-scan-task/utils.ts";

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

test("buildHybridStaticBootstrapConfig includes yasa_rule_config_id when custom config is selected", () => {
  assert.deepEqual(
    buildHybridStaticBootstrapConfig({
      opengrepEnabled: true,
      banditEnabled: false,
      gitleaksEnabled: false,
      phpstanEnabled: false,
      yasaEnabled: true,
      yasaLanguage: "auto",
      selectedYasaRuleConfigId: "custom-yasa-1",
    }),
    {
      mode: "embedded",
      opengrep_enabled: true,
      bandit_enabled: false,
      gitleaks_enabled: false,
      phpstan_enabled: false,
      yasa_enabled: true,
      yasa_language: "auto",
      yasa_rule_config_id: "custom-yasa-1",
    },
  );
});

test("buildHybridStaticBootstrapConfig omits yasa_rule_config_id for default selection", () => {
  assert.deepEqual(
    buildHybridStaticBootstrapConfig({
      opengrepEnabled: false,
      banditEnabled: false,
      gitleaksEnabled: false,
      phpstanEnabled: true,
      yasaEnabled: true,
      yasaLanguage: "typescript",
      selectedYasaRuleConfigId: "default",
    }),
    {
      mode: "embedded",
      opengrep_enabled: false,
      bandit_enabled: false,
      gitleaks_enabled: false,
      phpstan_enabled: true,
      yasa_enabled: true,
      yasa_language: "typescript",
      yasa_rule_config_id: null,
    },
  );
});
