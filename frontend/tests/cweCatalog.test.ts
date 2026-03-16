import test from "node:test";
import assert from "node:assert/strict";

type CweCatalogModule = {
  normalizeCweId?: (value: unknown) => string | null;
  resolveCweDisplay?: (input: {
    cwe?: unknown;
    fallbackLabel?: string | null;
  }) => {
    cweId: string | null;
    label: string;
    tooltip: string | null;
    nameZh: string | null;
    nameEn: string | null;
    matched: boolean;
  };
};

let cweCatalogModule: CweCatalogModule | null = null;

try {
  cweCatalogModule = (await import(
    "../src/shared/security/cweCatalog.ts"
  )) as CweCatalogModule;
} catch {
  cweCatalogModule = null;
}

test("cweCatalog 提供统一的 CWE 编号归一化能力", () => {
  assert.equal(typeof cweCatalogModule?.normalizeCweId, "function");

  assert.equal(cweCatalogModule?.normalizeCweId?.("89"), "CWE-89");
  assert.equal(cweCatalogModule?.normalizeCweId?.("cwe_79"), "CWE-79");
  assert.equal(cweCatalogModule?.normalizeCweId?.("CWE:22"), "CWE-22");
  assert.equal(cweCatalogModule?.normalizeCweId?.("not-a-cwe"), null);
});

test("cweCatalog 为已知 CWE 返回 编号+中文 和英文 tooltip", () => {
  assert.equal(typeof cweCatalogModule?.resolveCweDisplay, "function");

  const display = cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" });
  assert.ok(display);
  assert.equal(display?.cweId, "CWE-89");
  assert.equal(display?.label, "CWE-89 SQL注入");
  assert.equal(display?.nameZh, "SQL注入");
  assert.match(String(display?.tooltip || ""), /SQL Injection/i);
  assert.equal(display?.matched, true);
});

test("cweCatalog 对未知 CWE 安全回退到原始编号或后备文案", () => {
  assert.equal(typeof cweCatalogModule?.resolveCweDisplay, "function");

  const unknownCwe = cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-9999" });
  assert.ok(unknownCwe);
  assert.equal(unknownCwe?.label, "CWE-9999");
  assert.equal(unknownCwe?.matched, false);

  const fallbackOnly = cweCatalogModule?.resolveCweDisplay?.({
    cwe: null,
    fallbackLabel: "SQL Injection",
  });
  assert.ok(fallbackOnly);
  assert.equal(fallbackOnly?.label, "SQL Injection");
});

test("cweCatalog 在目录未命中但存在后备文案时保留可读名称", () => {
  assert.equal(typeof cweCatalogModule?.resolveCweDisplay, "function");

  const fallbackDisplay = cweCatalogModule?.resolveCweDisplay?.({
    cwe: "CWE-9999",
    fallbackLabel: "Custom Vulnerability Name",
  });

  assert.ok(fallbackDisplay);
  assert.equal(
    fallbackDisplay?.label,
    "CWE-9999 Custom Vulnerability Name",
  );
  assert.equal(fallbackDisplay?.matched, false);
});
