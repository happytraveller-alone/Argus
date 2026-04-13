#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const API_KEY_ENV_NAMES = ["OPENAI_API_KEY", "OPENAI_API_KEY_PATH"];

export function resolveRepoRoot({ scriptPath = fileURLToPath(import.meta.url) } = {}) {
  return path.resolve(path.dirname(scriptPath), "..");
}

export function resolveCodexPaths({ repoRoot }) {
  const sharedCodexDir = path.join(repoRoot, ".codex");
  const runtimeCodexHome = path.join(repoRoot, ".codex.local");

  return {
    repoRoot,
    sharedCodexDir,
    sharedConfigPath: path.join(sharedCodexDir, "config.toml"),
    runtimeCodexHome,
    runtimeConfigPath: path.join(runtimeCodexHome, "config.toml"),
    runtimeAuthPath: path.join(runtimeCodexHome, "auth.json"),
  };
}

export function hasApiKeyEnv({ env = process.env } = {}) {
  return API_KEY_ENV_NAMES.some((name) => String(env[name] || "").trim() !== "");
}

function readFileIfExists(filePath) {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

export function syncSharedConfig({ sharedConfigPath, runtimeConfigPath }) {
  const sharedConfig = readFileIfExists(sharedConfigPath);
  if (sharedConfig === null) {
    throw new Error(`Shared Codex config is missing: ${sharedConfigPath}`);
  }

  fs.mkdirSync(path.dirname(runtimeConfigPath), { recursive: true });

  const runtimeConfig = readFileIfExists(runtimeConfigPath);
  if (runtimeConfig !== sharedConfig) {
    fs.copyFileSync(sharedConfigPath, runtimeConfigPath);
    return { updated: true };
  }

  return { updated: false };
}

export function buildBootstrapMessage({ repoRoot, runtimeCodexHome, runtimeAuthPath }) {
  return [
    "[codex-project] Missing repo-local Codex credentials.",
    `[codex-project] Repo root: ${repoRoot}`,
    `[codex-project] Expected auth file: ${runtimeAuthPath}`,
    "[codex-project] Bootstrap once with one of the following:",
    `[codex-project]   CODEX_HOME=${runtimeCodexHome} codex login`,
    `[codex-project]   cp ~/.codex/auth.json ${runtimeAuthPath}`,
    "[codex-project] Or provide an API key via OPENAI_API_KEY / OPENAI_API_KEY_PATH.",
  ].join("\n");
}

export function ensureRepoLocalCodexHome({
  repoRoot = resolveRepoRoot(),
  env = process.env,
} = {}) {
  const paths = resolveCodexPaths({ repoRoot });
  fs.mkdirSync(paths.runtimeCodexHome, { recursive: true });
  const { updated } = syncSharedConfig({
    sharedConfigPath: paths.sharedConfigPath,
    runtimeConfigPath: paths.runtimeConfigPath,
  });

  const hasLocalAuth = fs.existsSync(paths.runtimeAuthPath);
  const hasApiKey = hasApiKeyEnv({ env });
  const requiresBootstrap = !(hasLocalAuth || hasApiKey);

  return {
    ...paths,
    syncedConfig: updated,
    hasLocalAuth,
    hasApiKey,
    requiresBootstrap,
    bootstrapMessage: requiresBootstrap
      ? buildBootstrapMessage({
          repoRoot,
          runtimeCodexHome: paths.runtimeCodexHome,
          runtimeAuthPath: paths.runtimeAuthPath,
        })
      : "",
  };
}

export function resolveLaunchCwd({ repoRoot, cwd = process.cwd() } = {}) {
  const relative = path.relative(repoRoot, cwd);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return cwd;
  }
  return repoRoot;
}

function spawnCodex({ argv, env, cwd }) {
  return new Promise((resolve, reject) => {
    const child = spawn("codex", argv, {
      cwd,
      env,
      stdio: "inherit",
    });

    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(typeof code === "number" ? code : 1);
    });
  });
}

export async function main({ argv = process.argv.slice(2), env = process.env } = {}) {
  const repoRoot = resolveRepoRoot();
  const state = ensureRepoLocalCodexHome({ repoRoot, env });

  if (state.requiresBootstrap) {
    process.stderr.write(`${state.bootstrapMessage}\n`);
    return 1;
  }

  return spawnCodex({
    argv,
    cwd: resolveLaunchCwd({ repoRoot }),
    env: {
      ...env,
      CODEX_HOME: state.runtimeCodexHome,
    },
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
    .then((exitCode) => {
      process.exit(Number(exitCode));
    })
    .catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      process.stderr.write(`${message}\n`);
      process.exit(1);
    });
}
