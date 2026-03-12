import test from "node:test";
import assert from "node:assert/strict";

import { buildFindingDetailCodeSections } from "../src/pages/finding-detail/viewModel.ts";
import { buildFindingDetailPath } from "../src/shared/utils/findingRoute.ts";

test("buildFindingDetailCodeSections 裁剪命中代码并插入省略占位", () => {
  const code = Array.from({ length: 21 }, (_, index) => `line ${20 + index}`).join("\n");
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-1",
      title: "命中代码",
      filePath: "src/demo.ts",
      code,
      lineStart: 20,
      lineEnd: 40,
      highlightStartLine: 30,
      highlightEndLine: 31,
      focusLine: 30,
    },
  ]);

  assert.ok(section);
  assert.ok(section.displayLines);
  assert.equal(section.displayLines?.[0]?.lineNumber, null);
  assert.equal(section.displayLines?.[0]?.content, "// ....");
  assert.deepEqual(
    section.displayLines?.slice(1, -1).map((line) => line.lineNumber),
    [27, 28, 29, 30, 31, 32, 33, 34],
  );
  assert.equal(section.displayLines?.at(-1)?.lineNumber, null);
  assert.equal(section.displayLines?.at(-1)?.content, "// ....");
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 30)?.isHighlighted,
    true,
  );
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 30)?.isFocus,
    true,
  );
  assert.equal(
    section.displayLines?.find((line) => line.lineNumber === 31)?.isHighlighted,
    true,
  );
});

test("buildFindingDetailCodeSections 对没有可靠行号的片段保持原样", () => {
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-2",
      title: "命中代码",
      filePath: "src/raw.txt",
      code: "raw one\nraw two",
      lineStart: null,
      lineEnd: null,
      highlightStartLine: null,
      highlightEndLine: null,
      focusLine: null,
    },
  ]);

  assert.ok(section);
  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, "raw one\nraw two");
});

test("buildFindingDetailCodeSections 对短片段保持原样", () => {
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-3",
      title: "命中代码",
      filePath: "src/short.ts",
      code: "a\nb\nc\nd\ne",
      lineStart: 10,
      lineEnd: 14,
      highlightStartLine: 12,
      highlightEndLine: 12,
      focusLine: 12,
    },
  ]);

  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, "a\nb\nc\nd\ne");
});

test("buildFindingDetailCodeSections 对单行命中长片段保持原样", () => {
  const code = Array.from({ length: 18 }, (_, index) => `line ${index + 1}`).join("\n");
  const [section] = buildFindingDetailCodeSections([
    {
      id: "section-4",
      title: "命中代码",
      filePath: "src/long-single.ts",
      code,
      lineStart: 1,
      lineEnd: 18,
      highlightStartLine: 9,
      highlightEndLine: 9,
      focusLine: 9,
    },
  ]);

  assert.equal(section.displayLines, undefined);
  assert.equal(section.code, code);
});

test("buildFindingDetailPath 为 bandit 详情保留 engine 查询参数", () => {
  const route = buildFindingDetailPath({
    source: "static",
    taskId: "task-bandit",
    findingId: "finding-bandit",
    engine: "bandit",
  });

  assert.equal(
    route,
    "/finding-detail/static/task-bandit/finding-bandit?engine=bandit",
  );
});
