import test from "node:test";
import assert from "node:assert/strict";

type OpengrepRulesModule = {
  formatRuleCweDisplayLabel?: (cwe?: string) => string;
};

let opengrepRulesModule: OpengrepRulesModule | null = null;

try {
  opengrepRulesModule = (await import(
    "../src/pages/OpengrepRules.tsx"
  )) as OpengrepRulesModule;
} catch {
  opengrepRulesModule = null;
}

test("OpengrepRules 使用统一 formatter 展示规则关联的 CWE 标签", () => {
  assert.equal(typeof opengrepRulesModule?.formatRuleCweDisplayLabel, "function");
  assert.equal(
    opengrepRulesModule?.formatRuleCweDisplayLabel?.("CWE-79"),
    "CWE-79 跨站脚本",
  );
});

test("OpengrepRules 对非数字 CWE 标签保留原始值", () => {
  assert.equal(typeof opengrepRulesModule?.formatRuleCweDisplayLabel, "function");
  assert.equal(
    opengrepRulesModule?.formatRuleCweDisplayLabel?.("CWE-noinfo"),
    "CWE-noinfo",
  );
});
