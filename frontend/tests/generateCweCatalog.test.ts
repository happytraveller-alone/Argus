import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

type GenerateCweCatalogModule = {
  extractShortEnglishName?: (name: string) => string;
  translateShortNameToChinese?: (name: string, cweId?: string) => string | null;
};

let generateCweCatalogModule: GenerateCweCatalogModule | null = null;

try {
  generateCweCatalogModule = (await import(
    "../scripts/generate-cwe-catalog.mjs"
  )) as GenerateCweCatalogModule;
} catch {
  generateCweCatalogModule = null;
}

test("generate-cwe-catalog 能从官方名称中提取适合展示的英文短名", () => {
  assert.equal(
    typeof generateCweCatalogModule?.extractShortEnglishName,
    "function",
  );

  assert.equal(
    generateCweCatalogModule?.extractShortEnglishName?.(
      "Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection')",
    ),
    "SQL Injection",
  );
  assert.equal(
    generateCweCatalogModule?.extractShortEnglishName?.(
      "Use of Hard-coded Password",
    ),
    "Hard-coded Password",
  );
});

test("generate-cwe-catalog 能为高频 CWE 生成稳定的中文短名", () => {
  assert.equal(
    typeof generateCweCatalogModule?.translateShortNameToChinese,
    "function",
  );

  assert.equal(
    generateCweCatalogModule?.translateShortNameToChinese?.("SQL Injection", "CWE-89"),
    "SQL注入",
  );
  assert.equal(
    generateCweCatalogModule?.translateShortNameToChinese?.(
      "Cross-site Scripting",
      "CWE-79",
    ),
    "跨站脚本",
  );
  assert.equal(
    generateCweCatalogModule?.translateShortNameToChinese?.(
      "Path Traversal",
      "CWE-22",
    ),
    "路径遍历",
  );
});

test("generate-cwe-catalog 生成产物保留 1000+ 的 CWE 条目", () => {
  const testDir = path.dirname(fileURLToPath(import.meta.url));
  const catalogPath = path.resolve(
    testDir,
    "../src/shared/security/cweCatalog.generated.json",
  );
  const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8")) as {
    entries?: Array<{ id?: string; numericId?: number }>;
  };

  assert.ok(Array.isArray(catalog.entries));
  assert.ok(
    catalog.entries?.some(
      (entry) => entry.id === "CWE-1333" && entry.numericId === 1333,
    ),
  );
});
