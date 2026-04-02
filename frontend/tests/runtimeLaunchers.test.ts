import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dockerfilePath = path.join(frontendDir, "..", "docker", "frontend.Dockerfile");
const devLauncherPath = path.join(frontendDir, "scripts", "dev-launcher.mjs");

function withTempDir(run: (dir: string) => void | Promise<void>) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "frontend-runtime-launchers-"));
  return Promise.resolve(run(dir)).finally(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });
}

async function importModule(modulePath: string) {
  return import(pathToFileURL(modulePath).href);
}

test("Dockerfile keeps Node launcher only for dev and serves static assets directly in prod", () => {
  const dockerfile = fs.readFileSync(dockerfilePath, "utf8");

  assert.match(
    dockerfile,
    /COPY\s+scripts\/dev-launcher\.mjs\s+\/usr\/local\/bin\/frontend-dev-launcher\.mjs/,
  );
  assert.match(dockerfile, /ENTRYPOINT\s+\["node"\]/);
  assert.match(dockerfile, /CMD\s+\["\/usr\/local\/bin\/frontend-dev-launcher\.mjs"\]/);
  assert.doesNotMatch(dockerfile, /dev-entrypoint\.sh/);
  assert.doesNotMatch(dockerfile, /RUN .*apk add --no-cache nodejs/);
  assert.doesNotMatch(dockerfile, /prod-runtime\.mjs/);
  assert.doesNotMatch(dockerfile, /ENTRYPOINT\s+\["node",\s*"\/usr\/local\/bin\/frontend-runtime\.mjs"\]/);
  assert.match(dockerfile, /COPY\s+--from=builder\s+\/app\/dist\s+\/usr\/share\/nginx\/html/);
  assert.match(dockerfile, /CMD\s+\["nginx",\s*"-g",\s*"daemon off;"\]/);
});

test("determineInstallState requests reinstall when the lockfile hash changes", async () => {
  assert.equal(fs.existsSync(devLauncherPath), true, "scripts/dev-launcher.mjs should exist");
  const { determineInstallState } = await importModule(devLauncherPath);

  await withTempDir((dir) => {
    const nodeModulesBinDir = path.join(dir, "node_modules", ".bin");
    const lockFilePath = path.join(dir, "pnpm-lock.yaml");
    const stampFilePath = path.join(dir, ".pnpm-store", ".VulHunter_frontend_lock.sha256");

    fs.mkdirSync(nodeModulesBinDir, { recursive: true });
    fs.mkdirSync(path.dirname(stampFilePath), { recursive: true });
    fs.writeFileSync(path.join(dir, "node_modules", ".modules.yaml"), "hoisted: false\n");
    fs.writeFileSync(path.join(nodeModulesBinDir, "vite"), "");
    fs.writeFileSync(path.join(nodeModulesBinDir, "tsc"), "");
    fs.writeFileSync(lockFilePath, "lockfile-version: 9\npackages:\n  react: 18.3.1\n");
    fs.writeFileSync(stampFilePath, "old-hash");

    const state = determineInstallState({
      appDir: dir,
      stampFilePath,
    });

    assert.equal(state.needsInstall, true);
    assert.equal(state.reason, "lockfile-changed");
    assert.match(state.currentHash, /^[a-f0-9]{64}$/);
  });
});

test("determineInstallState skips reinstall when tools exist and the lockfile hash is unchanged", async () => {
  assert.equal(fs.existsSync(devLauncherPath), true, "scripts/dev-launcher.mjs should exist");
  const { determineInstallState, sha256Hex } = await importModule(devLauncherPath);

  await withTempDir((dir) => {
    const nodeModulesBinDir = path.join(dir, "node_modules", ".bin");
    const lockFilePath = path.join(dir, "pnpm-lock.yaml");
    const stampFilePath = path.join(dir, ".pnpm-store", ".VulHunter_frontend_lock.sha256");

    fs.mkdirSync(nodeModulesBinDir, { recursive: true });
    fs.mkdirSync(path.dirname(stampFilePath), { recursive: true });
    fs.writeFileSync(path.join(dir, "node_modules", ".modules.yaml"), "hoisted: false\n");
    fs.writeFileSync(path.join(nodeModulesBinDir, "vite"), "");
    fs.writeFileSync(path.join(nodeModulesBinDir, "tsc"), "");
    fs.writeFileSync(lockFilePath, "lockfile-version: 9\npackages:\n  react: 18.3.1\n");
    fs.writeFileSync(stampFilePath, sha256Hex(fs.readFileSync(lockFilePath)));

    const state = determineInstallState({
      appDir: dir,
      stampFilePath,
    });

    assert.equal(state.needsInstall, false);
    assert.equal(state.reason, "lockfile-unchanged");
  });
});

test("resolveChokidarUsePolling preserves explicit values and defaults by platform", async () => {
  assert.equal(fs.existsSync(devLauncherPath), true, "scripts/dev-launcher.mjs should exist");
  const { resolveChokidarUsePolling } = await importModule(devLauncherPath);

  assert.equal(resolveChokidarUsePolling({ currentValue: "manual", platform: "linux" }), "manual");
  assert.equal(resolveChokidarUsePolling({ currentValue: "", platform: "linux" }), "false");
  assert.equal(resolveChokidarUsePolling({ currentValue: "", platform: "darwin" }), "true");
  assert.equal(resolveChokidarUsePolling({ currentValue: "", platform: "win32" }), "true");
});
