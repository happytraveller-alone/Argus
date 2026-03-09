import test from "node:test";
import assert from "node:assert/strict";

import {
  buildFindingDetailCodeSections,
  type FindingDetailCodeView,
} from "../src/pages/finding-detail/viewModel.ts";

test("buildFindingDetailCodeSections 保留所有代码块并按输入顺序展开", () => {
  const sections = buildFindingDetailCodeSections([
    {
      id: "first",
      title: "首段",
      filePath: "src/a.ts",
      code: "const a = 1;",
      lineStart: 10,
      lineEnd: 10,
      highlightStartLine: 10,
      highlightEndLine: 10,
      focusLine: 10,
    },
    {
      id: "second",
      title: "次段",
      filePath: "src/b.ts",
      code: "const b = 2;",
      lineStart: 20,
      lineEnd: 20,
      highlightStartLine: 20,
      highlightEndLine: 20,
      focusLine: 20,
    },
  ] satisfies FindingDetailCodeView[]);

  assert.equal(sections.length, 2);
  assert.deepEqual(
    sections.map((item) => ({ id: item.id, title: item.title, focusLine: item.focusLine })),
    [
      { id: "first", title: "首段", focusLine: 10 },
      { id: "second", title: "次段", focusLine: 20 },
    ],
  );
});

test("buildFindingDetailCodeSections 在无代码块时返回空数组", () => {
  assert.deepEqual(buildFindingDetailCodeSections([]), []);
});
