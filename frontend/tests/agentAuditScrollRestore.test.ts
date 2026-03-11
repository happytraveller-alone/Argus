import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { computeContainerAnchorScrollTop } from "../src/pages/AgentAudit/utils.ts";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("滚动恢复只计算容器内 scrollTop，不依赖 scrollIntoView", () => {
  assert.equal(
    computeContainerAnchorScrollTop({
      containerScrollTop: 320,
      containerClientHeight: 240,
      containerTop: 100,
      anchorTop: 460,
      anchorHeight: 40,
    }),
    580,
  );
});

test("锚点已在容器可视区内时保持现有 scrollTop", () => {
  assert.equal(
    computeContainerAnchorScrollTop({
      containerScrollTop: 320,
      containerClientHeight: 240,
      containerTop: 100,
      anchorTop: 190,
      anchorHeight: 48,
    }),
    320,
  );
});

test("无效尺寸输入时返回当前容器 scrollTop", () => {
  assert.equal(
    computeContainerAnchorScrollTop({
      containerScrollTop: 180,
      containerClientHeight: 0,
      containerTop: 100,
      anchorTop: 320,
      anchorHeight: 20,
    }),
    180,
  );
});

test("finding 锚点恢复使用 RealtimeFindingsPanel 内部的实际滚动容器", () => {
  const pageSource = fs.readFileSync(
    path.join(frontendRoot, "src/pages/AgentAudit/index.tsx"),
    "utf8",
  );
  const panelSource = fs.readFileSync(
    path.join(frontendRoot, "src/pages/AgentAudit/components/RealtimeFindingsPanel.tsx"),
    "utf8",
  );

  assert.match(pageSource, /scrollContainerRef=\{findingsContainerRef\}/);
  assert.doesNotMatch(pageSource, /<div ref=\{findingsContainerRef\} className="h-full">/);
  assert.match(panelSource, /scrollContainerRef\?: RefObject<HTMLDivElement \| null>/);
  assert.match(panelSource, /<div ref=\{props\.scrollContainerRef\} className="h-full overflow-auto custom-scrollbar">/);
});
