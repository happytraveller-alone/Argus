import test from "node:test";
import assert from "node:assert/strict";

import { resolveYasaLanguageFromProgrammingLanguages } from "../src/shared/utils/yasaLanguage.ts";

test("yasa language auto resolver skips php-like projects", () => {
  assert.equal(resolveYasaLanguageFromProgrammingLanguages('["php","javascript"]'), null);
  assert.equal(resolveYasaLanguageFromProgrammingLanguages("php8,javascript"), null);
});

test("yasa language auto resolver keeps existing behavior for non-php projects", () => {
  assert.equal(resolveYasaLanguageFromProgrammingLanguages('["javascript"]'), "javascript");
  assert.equal(resolveYasaLanguageFromProgrammingLanguages('["java","python"]'), "java");
});
