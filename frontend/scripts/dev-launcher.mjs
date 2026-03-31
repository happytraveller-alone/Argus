#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const DEFAULT_PNPM_VERSION = "9.15.4";
const DEFAULT_REGISTRY = "https://registry.npmmirror.com";
const DEFAULT_STORE_DIR = "/pnpm/store";

export function sha256Hex(input) {
  return createHash("sha256").update(input).digest("hex");
}

function readTrimmedFile(filePath, { readFileSync = fs.readFileSync } = {}) {
  try {
    return String(readFileSync(filePath, "utf8")).trim();
  } catch {
    return "";
  }
}

export function determineInstallState({
  appDir = process.cwd(),
  installMode = process.env.FRONTEND_DEV_INSTALL_MODE || "auto",
  lockFilePath = path.join(appDir, "pnpm-lock.yaml"),
  stampFilePath = path.join(DEFAULT_STORE_DIR, ".VulHunter_frontend_lock.sha256"),
  modulesManifestPath = path.join(appDir, "node_modules", ".modules.yaml"),
  viteBinPath = path.join(appDir, "node_modules", ".bin", "vite"),
  tscBinPath = path.join(appDir, "node_modules", ".bin", "tsc"),
  existsSync = fs.existsSync,
  readFileSync = fs.readFileSync,
} = {}) {
  const hasModulesManifest = existsSync(modulesManifestPath);
  const hasViteBin = existsSync(viteBinPath);
  const hasTscBin = existsSync(tscBinPath);

  let needsInstall = !hasModulesManifest || !hasViteBin || !hasTscBin;
  let reason = needsInstall ? "missing-deps" : "lockfile-unchanged";
  let currentHash = "";
  let previousHash = "";

  if (installMode === "always") {
    needsInstall = true;
    reason = "install-mode-always";
  } else if (installMode === "never") {
    needsInstall = false;
    reason = "install-mode-never";
  } else if (existsSync(lockFilePath)) {
    currentHash = sha256Hex(readFileSync(lockFilePath));
    previousHash = existsSync(stampFilePath)
      ? readTrimmedFile(stampFilePath, { readFileSync })
      : "";

    if (currentHash !== previousHash) {
      needsInstall = true;
      reason = "lockfile-changed";
    }
  }

  return {
    needsInstall,
    reason,
    currentHash,
    previousHash,
    stampFilePath,
  };
}

export function resolveChokidarUsePolling({
  currentValue = process.env.CHOKIDAR_USEPOLLING,
  platform = process.platform,
} = {}) {
  if (currentValue) {
    return currentValue;
  }
  return platform === "darwin" || platform === "win32" ? "true" : "false";
}

function runBestEffort(command, args, options = {}) {
  try {
    spawnSync(command, args, {
      stdio: "ignore",
      ...options,
    });
  } catch {
    return false;
  }
  return true;
}

function configurePnpm(appDir) {
  runBestEffort("corepack", ["enable"], { cwd: appDir });
  runBestEffort("corepack", ["prepare", `pnpm@${process.env.PNPM_VERSION || DEFAULT_PNPM_VERSION}`, "--activate"], {
    cwd: appDir,
  });

  runBestEffort("pnpm", ["config", "set", "registry", process.env.FRONTEND_NPM_REGISTRY || DEFAULT_REGISTRY], {
    cwd: appDir,
  });
  runBestEffort("pnpm", ["config", "set", "store-dir", DEFAULT_STORE_DIR], { cwd: appDir });
  runBestEffort("pnpm", ["config", "set", "network-timeout", "300000"], { cwd: appDir });
  runBestEffort("pnpm", ["config", "set", "fetch-retries", "5"], { cwd: appDir });
}

function writeLockStamp(stampFilePath, currentHash) {
  if (!currentHash) {
    return;
  }
  fs.mkdirSync(path.dirname(stampFilePath), { recursive: true });
  fs.writeFileSync(stampFilePath, `${currentHash}\n`);
}

function installDependencies(appDir, state) {
  console.log("[frontend-dev] installing dependencies...");
  const result = spawnSync("pnpm", ["install", "--no-frozen-lockfile"], {
    cwd: appDir,
    stdio: "inherit",
    env: process.env,
  });

  if (typeof result.status === "number" && result.status !== 0) {
    process.exit(result.status);
  }
  if (result.error) {
    throw result.error;
  }

  let currentHash = state.currentHash;
  const lockFilePath = path.join(appDir, "pnpm-lock.yaml");
  if (!currentHash && fs.existsSync(lockFilePath)) {
    currentHash = sha256Hex(fs.readFileSync(lockFilePath));
  }
  writeLockStamp(state.stampFilePath, currentHash);
}

function buildChildEnv() {
  return {
    ...process.env,
    BROWSER: process.env.BROWSER || "none",
    CHOKIDAR_USEPOLLING: resolveChokidarUsePolling(),
  };
}

async function waitForReady({ url, child }) {
  let readyLogged = false;
  const frontendPublicUrl = process.env.FRONTEND_PUBLIC_URL || "http://localhost:3000";
  const backendPublicUrl = process.env.BACKEND_PUBLIC_URL || "http://localhost:8000";

  while (!child.killed && child.exitCode === null) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        if (!readyLogged) {
          console.log(`[frontend-dev] frontend ready: ${frontendPublicUrl}`);
          console.log(`[frontend-dev] backend docs: ${backendPublicUrl}/docs`);
          readyLogged = true;
        }
        return;
      }
    } catch {
      // Wait for Vite to come up.
    }

    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function forwardSignal(child, signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

export async function main() {
  const appDir = process.env.FRONTEND_WORKDIR
    ? path.resolve(process.env.FRONTEND_WORKDIR)
    : process.cwd();
  configurePnpm(appDir);

  const installState = determineInstallState({ appDir });
  if (installState.needsInstall) {
    installDependencies(appDir, installState);
  } else {
    console.log("[frontend-dev] lockfile unchanged, skip install");
  }

  const port = process.env.FRONTEND_DEV_PORT || "5173";
  const readyUrl = `http://127.0.0.1:${port}/`;
  const child = spawn("pnpm", ["dev", "--host", "0.0.0.0", "--port", String(port)], {
    cwd: appDir,
    stdio: "inherit",
    env: buildChildEnv(),
  });

  const childExit = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(code ?? 1);
    });
  });

  process.on("SIGINT", () => forwardSignal(child, "SIGINT"));
  process.on("SIGTERM", () => forwardSignal(child, "SIGTERM"));

  await Promise.race([waitForReady({ url: readyUrl, child }), childExit]);
  const exitCode = await childExit;

  process.exit(Number(exitCode));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
