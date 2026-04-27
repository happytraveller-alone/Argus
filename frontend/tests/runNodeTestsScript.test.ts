import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildNodeTestCommand,
  listDefaultTestFiles,
  normalizeTestArgs,
} from "../scripts/run-node-tests.mjs";

function withTempDir(run: (dir: string) => void) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "run-node-tests-"));
  try {
    run(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("listDefaultTestFiles returns sorted .test.ts and .test.tsx files", () => {
  withTempDir((dir) => {
    fs.writeFileSync(path.join(dir, "b.test.ts"), "");
    fs.writeFileSync(path.join(dir, "a.test.tsx"), "");
    fs.writeFileSync(path.join(dir, "ignore.spec.ts"), "");
    fs.writeFileSync(path.join(dir, "ignore.tsx"), "");

    assert.deepEqual(listDefaultTestFiles({ testsDirPath: dir }), [
      "tests/a.test.tsx",
      "tests/b.test.ts",
    ]);
  });
});

test("normalizeTestArgs strips pnpm separator and resolves bare test filenames", () => {
  withTempDir((dir) => {
    fs.writeFileSync(path.join(dir, "sample.test.tsx"), "");

    assert.deepEqual(normalizeTestArgs(["--", "sample.test.tsx"], { testsDirPath: dir }), [
      "tests/sample.test.tsx",
    ]);
  });
});

test("normalizeTestArgs expands a bare token to matching test filenames", () => {
  withTempDir((dir) => {
    fs.writeFileSync(path.join(dir, "agentAlpha.test.ts"), "");
    fs.writeFileSync(path.join(dir, "projectBeta.test.ts"), "");
    fs.writeFileSync(path.join(dir, "agentZeta.test.tsx"), "");

    assert.deepEqual(normalizeTestArgs(["agent"], { testsDirPath: dir }), [
      "tests/agentAlpha.test.ts",
      "tests/agentZeta.test.tsx",
    ]);
  });
});


test("buildNodeTestCommand uses node --import tsx --test", () => {
  const command = buildNodeTestCommand(["tests/example.test.ts"]);

  assert.equal(command.bin, process.execPath);
  assert.deepEqual(command.args, [
    "--import",
    "tsx",
    "--test",
    "tests/example.test.ts",
  ]);
});
