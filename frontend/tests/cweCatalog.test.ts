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
  getCweCatalogMetadata?: () => {
    contentVersion: string;
    contentDate: string;
    generatedAt: string;
    reviewedAt?: string;
    entryCount: number;
    source?: string;
    sourceSha256?: string;
    translationSource?: string;
    translationReviewedAt?: string;
  };
  hydrateCweCatalog?: (payload: unknown) => boolean;
  resetCweCatalogForTests?: () => void;
};

let cweCatalogModule: CweCatalogModule | null = null;

try {
  cweCatalogModule = (await import(
    "../src/shared/security/cweCatalog.ts"
  )) as CweCatalogModule;
} catch {
  cweCatalogModule = null;
}

test.afterEach(() => {
  cweCatalogModule?.resetCweCatalogForTests?.();
});

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

test("cweCatalog 可用后端 payload 覆盖静态目录并可重置", () => {
  assert.equal(typeof cweCatalogModule?.hydrateCweCatalog, "function");
  assert.equal(typeof cweCatalogModule?.resetCweCatalogForTests, "function");

  const hydrated = cweCatalogModule?.hydrateCweCatalog?.({
    data: [
      {
        id: "CWE-89",
        numericId: 89,
        nameEnOfficial:
          "Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection')",
        nameEnShort: "SQL Injection",
        nameZh: "后端SQL注入",
      },
    ],
    total: 1,
    sourceVersion: "4.20",
    sourceDate: "2026-04-30",
    sourceSha256: "seed-sha",
    translationSource: "agent_curated_self_reviewed",
    translationReviewedAt: "2026-05-28T10:58:05Z",
  });
  assert.equal(hydrated, true);
  assert.equal(
    cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" })?.label,
    "CWE-89 后端SQL注入",
  );
  assert.equal(cweCatalogModule?.getCweCatalogMetadata?.().source, "backend");
  assert.equal(cweCatalogModule?.getCweCatalogMetadata?.().contentVersion, "4.20");
  assert.equal(cweCatalogModule?.getCweCatalogMetadata?.().entryCount, 1);

  cweCatalogModule?.resetCweCatalogForTests?.();
  assert.equal(
    cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" })?.label,
    "CWE-89 SQL注入",
  );
  assert.equal(cweCatalogModule?.getCweCatalogMetadata?.().source, "static");
});

test("cweCatalog 拒绝格式错误 hydration 且不替换静态 fallback", () => {
  assert.equal(typeof cweCatalogModule?.hydrateCweCatalog, "function");

  const before = cweCatalogModule?.getCweCatalogMetadata?.();
  assert.equal(
    cweCatalogModule?.hydrateCweCatalog?.({
      data: [
        {
          id: "CWE-89",
          numericId: 89,
          nameEnOfficial: "SQL Injection",
          nameEnShort: "SQL Injection",
          nameZh: "",
        },
      ],
      total: 1,
      sourceVersion: "4.20",
    }),
    false,
  );
  assert.deepEqual(cweCatalogModule?.getCweCatalogMetadata?.(), before);
  assert.equal(
    cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" })?.label,
    "CWE-89 SQL注入",
  );

  assert.equal(
    cweCatalogModule?.hydrateCweCatalog?.({
      data: [
        {
          id: "CWE-89",
          numericId: 89,
          nameEnOfficial: "SQL Injection",
          nameEnShort: "SQL Injection",
          nameZh: "后端SQL注入",
        },
      ],
      total: 969,
    }),
    false,
  );
  assert.equal(
    cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" })?.label,
    "CWE-89 SQL注入",
  );

  assert.equal(
    cweCatalogModule?.hydrateCweCatalog?.({
      data: [
        {
          id: "CWE-89",
          numericId: 89,
          nameEnOfficial: "SQL Injection",
          nameEnShort: "SQL Injection",
          nameZh: "后端SQL注入",
        },
        {
          id: "cwe_89",
          numericId: 89,
          nameEnOfficial: "SQL Injection",
          nameEnShort: "SQL Injection",
          nameZh: "重复SQL注入",
        },
      ],
    }),
    false,
  );
  assert.equal(
    cweCatalogModule?.resolveCweDisplay?.({ cwe: "CWE-89" })?.label,
    "CWE-89 SQL注入",
  );
});
