import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const taskDetailPagePath = path.resolve(
  process.cwd(),
  "src/pages/AgentAudit/TaskDetailPage.tsx",
);

test("AgentAudit 详情页首页卡片直接保留静态扫描和智能扫描，不再依赖重复定义后去重", () => {
  const source = fs.readFileSync(taskDetailPagePath, "utf8");
  const homeScanCardsBlock = source.match(
    /const homeScanCards: HomeScanCard\[] = useMemo\(\s*\(\) => \[(.*?)\],\s*\[\],\s*\);/s,
  )?.[1];

  assert.ok(homeScanCardsBlock);
  assert.equal(homeScanCardsBlock.match(/key:\s*"static"/g)?.length ?? 0, 1);
  assert.equal(homeScanCardsBlock.match(/key:\s*"agent"/g)?.length ?? 0, 1);
  assert.doesNotMatch(homeScanCardsBlock, /findIndex\(\(item\) => item\.key === card\.key\)/);
});
