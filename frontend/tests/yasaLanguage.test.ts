import test from "node:test";
import assert from "node:assert/strict";

import {
  getYasaBlockedProjectMessage,
  isYasaBlockedProjectLanguage,
  resolveYasaLanguageFromProgrammingLanguages,
} from "../src/shared/utils/yasaLanguage.ts";

test("isYasaBlockedProjectLanguage blocks projects without whitelist languages", () => {
  assert.equal(isYasaBlockedProjectLanguage('["cpp","java"]'), false);
  assert.equal(isYasaBlockedProjectLanguage("c++,python"), false);
  assert.equal(isYasaBlockedProjectLanguage(["cc", "golang"]), false);
  assert.equal(isYasaBlockedProjectLanguage('["typescript","swift"]'), false);
  assert.equal(isYasaBlockedProjectLanguage('["javascript"]'), true);
  assert.equal(isYasaBlockedProjectLanguage('["java","python"]'), false);
});

test("resolveYasaLanguageFromProgrammingLanguages returns null for blocked projects", () => {
  assert.equal(resolveYasaLanguageFromProgrammingLanguages('["javascript"]'), null);
});

test("getYasaBlockedProjectMessage returns fixed user-facing copy", () => {
  assert.equal(
    getYasaBlockedProjectMessage(),
    "YASA 引擎仅支持 Java / Go / TypeScript / Python 项目",
  );
});
