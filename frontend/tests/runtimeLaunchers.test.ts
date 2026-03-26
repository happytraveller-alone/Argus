import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dockerfilePath = path.join(frontendDir, "Dockerfile");
const devLauncherPath = path.join(frontendDir, "scripts", "dev-launcher.mjs");
const prodRuntimePath = path.join(frontendDir, "scripts", "prod-runtime.mjs");

function withTempDir(run: (dir: string) => void | Promise<void>) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "frontend-runtime-launchers-"));
  return Promise.resolve(run(dir)).finally(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });
}

async function importModule(modulePath: string) {
  return import(pathToFileURL(modulePath).href);
}

test("Dockerfile uses Node launchers for dev and prod runtime images", () => {
  const dockerfile = fs.readFileSync(dockerfilePath, "utf8");

  assert.match(
    dockerfile,
    /COPY\s+scripts\/dev-launcher\.mjs\s+\/usr\/local\/bin\/frontend-dev-launcher\.mjs/,
  );
  assert.match(dockerfile, /ENTRYPOINT\s+\["node"\]/);
  assert.match(dockerfile, /CMD\s+\["\/usr\/local\/bin\/frontend-dev-launcher\.mjs"\]/);
  assert.doesNotMatch(dockerfile, /dev-entrypoint\.sh/);
  assert.match(dockerfile, /RUN apk add --no-cache nodejs/);
  assert.match(
    dockerfile,
    /COPY\s+scripts\/prod-runtime\.mjs\s+\/usr\/local\/bin\/frontend-runtime\.mjs/,
  );
  assert.match(dockerfile, /ENTRYPOINT\s+\["node",\s*"\/usr\/local\/bin\/frontend-runtime\.mjs"\]/);
  assert.doesNotMatch(dockerfile, /docker-entrypoint\.sh/);
  assert.doesNotMatch(dockerfile, /ENTRYPOINT\s+\["\/bin\/sh"/);
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

test("injectApiBasePlaceholders rewrites placeholder values in nested JavaScript assets", async () => {
  assert.equal(fs.existsSync(prodRuntimePath), true, "scripts/prod-runtime.mjs should exist");
  const { injectApiBasePlaceholders } = await importModule(prodRuntimePath);

  await withTempDir((dir) => {
    const nestedDir = path.join(dir, "assets");
    const topLevelFile = path.join(dir, "index.js");
    const nestedFile = path.join(nestedDir, "chunk.js");
    const ignoredFile = path.join(dir, "styles.css");

    fs.mkdirSync(nestedDir, { recursive: true });
    fs.writeFileSync(topLevelFile, 'const api = "__API_BASE_URL__";\n');
    fs.writeFileSync(nestedFile, 'fetch("__API_BASE_URL__/projects");\nfetch("__API_BASE_URL__/tasks");\n');
    fs.writeFileSync(ignoredFile, "__API_BASE_URL__ should stay here\n");

    const result = injectApiBasePlaceholders({
      rootDir: dir,
      apiUrl: "https://audit.example.com/api/v1",
    });

    assert.equal(result.filesChanged, 2);
    assert.equal(result.replacements, 3);
    assert.equal(fs.readFileSync(topLevelFile, "utf8"), 'const api = "https://audit.example.com/api/v1";\n');
    assert.equal(
      fs.readFileSync(nestedFile, "utf8"),
      'fetch("https://audit.example.com/api/v1/projects");\nfetch("https://audit.example.com/api/v1/tasks");\n',
    );
    assert.equal(fs.readFileSync(ignoredFile, "utf8"), "__API_BASE_URL__ should stay here\n");
  });
});

test("resolveApiBaseUrl falls back to the nginx proxy default", async () => {
  assert.equal(fs.existsSync(prodRuntimePath), true, "scripts/prod-runtime.mjs should exist");
  const { resolveApiBaseUrl } = await importModule(prodRuntimePath);

  assert.equal(resolveApiBaseUrl(undefined), "/api/v1");
  assert.equal(resolveApiBaseUrl(""), "/api/v1");
  assert.equal(resolveApiBaseUrl("https://audit.example.com/api/v1"), "https://audit.example.com/api/v1");
});
