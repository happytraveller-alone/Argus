import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const homePagePath = path.resolve(
  process.cwd(),
  "src/pages/AgentAudit/index.tsx",
);

test("AgentAudit 首页不再保留任何 Nexus iframe 懒加载状态机", () => {
  const source = fs.readFileSync(homePagePath, "utf8");

  assert.doesNotMatch(
    source,
    /const \[isNexusLoaded, setIsNexusLoaded\] = useState\(false\);/,
  );
  assert.doesNotMatch(source, /\{isNexusLoaded \? \(/);
  assert.doesNotMatch(source, /setIsNexusLoaded\(true\)/);
  assert.doesNotMatch(source, /加载 GitNexus/);
  assert.doesNotMatch(source, /http:\/\/\$\{window\.location\.hostname\}:5174/);
  assert.match(source, /一键开始安全审计/);
  assert.match(source, /静态扫描/);
  assert.match(source, /智能扫描/);
  assert.doesNotMatch(source, /findIndex\(\(item\) => item\.key === card\.key\)/);
});
