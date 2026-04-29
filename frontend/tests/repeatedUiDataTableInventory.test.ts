import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const srcDir = path.resolve(process.cwd(), "src");
const allowedNativeTableFiles = new Set([
  path.join(srcDir, "components/ui/table.tsx"),
]);

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      yield* walk(fullPath);
    } else if (/\.(tsx|ts)$/.test(entry)) {
      yield fullPath;
    }
  }
}

test("feature repeated UI no longer uses native table primitives outside DataTable", () => {
  const offenders: string[] = [];
  for (const filePath of walk(srcDir)) {
    if (allowedNativeTableFiles.has(filePath)) continue;
    if (filePath.includes(`${path.sep}components${path.sep}data-table${path.sep}`)) {
      continue;
    }
    const source = readFileSync(filePath, "utf8");
    if (/<table\b|<Table\b|components\/ui\/table/.test(source)) {
      offenders.push(path.relative(srcDir, filePath));
    }
  }

  assert.deepEqual(offenders, []);
});
