import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("StaticAnalysis hides CodeQL exploration on OpenGrep-only detail pages", async () => {
  const source = await readFile(
    new URL("../src/pages/StaticAnalysis.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /isCodeqlOnlyDetail/);
  assert.match(source, /<CodeqlExplorationPanel/);
  assert.doesNotMatch(
    source,
    /isCodeqlOnlyDetail[\s\S]*?\?\s*\([\s\S]*?<CodeqlExplorationPanel[\s\S]*?\)\s*:\s*\([\s\S]*?<CodeqlExplorationPanel/,
  );
});
