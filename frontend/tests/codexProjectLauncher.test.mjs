import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendDir, "..");
const launcherModulePath = path.join(repoRoot, "scripts", "codex-project.mjs");

function withTempDir(run) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "codex-project-launcher-"));
  return Promise.resolve(run(dir)).finally(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });
}

async function importLauncherModule() {
  return import(pathToFileURL(launcherModulePath).href);
}

test("ensureRepoLocalCodexHome copies the shared config into .codex.local", async () => {
  assert.equal(fs.existsSync(launcherModulePath), true, "scripts/codex-project.mjs should exist");
  const { ensureRepoLocalCodexHome } = await importLauncherModule();

  await withTempDir((dir) => {
    const sharedDir = path.join(dir, ".codex");
    fs.mkdirSync(sharedDir, { recursive: true });
    fs.writeFileSync(path.join(sharedDir, "config.toml"), 'model = "gpt-5.4"\n');

    const result = ensureRepoLocalCodexHome({ repoRoot: dir, env: {} });

    assert.equal(result.runtimeCodexHome, path.join(dir, ".codex.local"));
    assert.equal(
      fs.readFileSync(path.join(dir, ".codex.local", "config.toml"), "utf8"),
      'model = "gpt-5.4"\n',
    );
    assert.equal(result.requiresBootstrap, true);
  });
});

test("ensureRepoLocalCodexHome rewrites runtime config when the shared config changes", async () => {
  assert.equal(fs.existsSync(launcherModulePath), true, "scripts/codex-project.mjs should exist");
  const { ensureRepoLocalCodexHome } = await importLauncherModule();

  await withTempDir((dir) => {
    const sharedDir = path.join(dir, ".codex");
    const runtimeDir = path.join(dir, ".codex.local");
    fs.mkdirSync(sharedDir, { recursive: true });
    fs.mkdirSync(runtimeDir, { recursive: true });
    fs.writeFileSync(path.join(sharedDir, "config.toml"), 'model = "gpt-5.4"\n');
    fs.writeFileSync(path.join(runtimeDir, "config.toml"), 'model = "stale"\n');

    ensureRepoLocalCodexHome({ repoRoot: dir, env: { OPENAI_API_KEY: "test-key" } });

    assert.equal(
      fs.readFileSync(path.join(runtimeDir, "config.toml"), "utf8"),
      'model = "gpt-5.4"\n',
    );
  });
});

test("ensureRepoLocalCodexHome reports bootstrap instructions when auth is missing", async () => {
  assert.equal(fs.existsSync(launcherModulePath), true, "scripts/codex-project.mjs should exist");
  const { ensureRepoLocalCodexHome } = await importLauncherModule();

  await withTempDir((dir) => {
    const sharedDir = path.join(dir, ".codex");
    fs.mkdirSync(sharedDir, { recursive: true });
    fs.writeFileSync(path.join(sharedDir, "config.toml"), 'model = "gpt-5.4"\n');

    const result = ensureRepoLocalCodexHome({ repoRoot: dir, env: {} });

    assert.equal(result.requiresBootstrap, true);
    assert.match(result.bootstrapMessage, /CODEX_HOME=.*\.codex\.local codex login/);
    assert.match(result.bootstrapMessage, /auth\.json/);
  });
});
