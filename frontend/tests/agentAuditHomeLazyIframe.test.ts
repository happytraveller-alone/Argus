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
  assert.doesNotMatch(source, /一键开始安全审计/);
  assert.match(source, /grid-cols-1/);
  assert.match(source, /md:grid-cols-2/);
  assert.match(source, /backdrop-blur-xl/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /max-w-none/);
  assert.doesNotMatch(source, /drop-shadow/);
  assert.doesNotMatch(source, /rgba\(14,165,233,0\.28\)/);
  assert.match(source, /静态审计/);
  assert.match(source, /智能审计/);
  assert.match(source, /source=home-static/);
  assert.match(source, /source=home-agent/);
  assert.doesNotMatch(source, /findIndex\(\(item\) => item\.key === card\.key\)/);
});
