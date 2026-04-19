#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const DEFAULT_NPM_CACHE = "/tmp/npm-cache-omx";

function usage() {
  return `
Usage: node scripts/fix-wsl-omx.mjs [options]

Options:
  --version <version|latest>  Upgrade global oh-my-codex before patching
  --skip-cleanup             Skip omx cleanup
  --skip-setup               Skip omx setup --force --verbose
  --skip-doctor              Skip omx doctor
  --dry-run                  Print planned actions without changing anything
  -h, --help                 Show this help
`.trim();
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const options = {
    version: null,
    skipCleanup: false,
    skipSetup: false,
    skipDoctor: false,
    dryRun: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case "--version":
        options.version = argv[i + 1] || "";
        i += 1;
        break;
      case "--skip-cleanup":
        options.skipCleanup = true;
        break;
      case "--skip-setup":
        options.skipSetup = true;
        break;
      case "--skip-doctor":
        options.skipDoctor = true;
        break;
      case "--dry-run":
        options.dryRun = true;
        break;
      case "-h":
      case "--help":
        process.stdout.write(`${usage()}\n`);
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}\n\n${usage()}`);
    }
  }

  if (options.version !== null && options.version.trim() === "") {
    fail(`--version requires a value\n\n${usage()}`);
  }

  return options;
}

function ensureWsl() {
  if (!process.env.WSL_DISTRO_NAME && !process.env.WSL_INTEROP) {
    fail("This script is intended to run inside WSL.");
  }
}

function run(command, args, { cwd = REPO_ROOT, env = process.env, dryRun = false, capture = false } = {}) {
  const rendered = [command, ...args].join(" ");
  process.stdout.write(`[fix-wsl-omx] ${rendered}\n`);
  if (dryRun) {
    return { stdout: "", stderr: "", status: 0 };
  }
  const result = spawnSync(command, args, {
    cwd,
    env,
    encoding: "utf8",
    stdio: capture ? ["inherit", "pipe", "pipe"] : "inherit",
  });
  if (result.error) {
    fail(`[fix-wsl-omx] failed to launch ${command}: ${result.error.message}`);
  }
  if ((result.status ?? 1) !== 0) {
    if (capture) {
      const stderr = (result.stderr || result.stdout || "").trim();
      fail(`[fix-wsl-omx] command failed (${result.status}): ${rendered}\n${stderr}`);
    }
    process.exit(result.status ?? 1);
  }
  return result;
}

function npmEnv() {
  return {
    ...process.env,
    NPM_CONFIG_CACHE: DEFAULT_NPM_CACHE,
  };
}

function resolveGlobalPackageRoot() {
  const result = run("npm", ["root", "-g"], {
    env: npmEnv(),
    capture: true,
  });
  return path.join(result.stdout.trim(), "oh-my-codex");
}

function resolveUpgradeVersion(requestedVersion) {
  if (!requestedVersion) {
    return null;
  }
  if (requestedVersion !== "latest") {
    return requestedVersion;
  }
  const result = run("npm", ["view", "oh-my-codex", "version"], {
    env: npmEnv(),
    capture: true,
  });
  return result.stdout.trim();
}

function patchFile(filePath, transform, { dryRun = false, backupSuffix } = {}) {
  const original = fs.readFileSync(filePath, "utf8");
  const next = transform(original);
  if (next === original) {
    process.stdout.write(`[fix-wsl-omx] unchanged ${filePath}\n`);
    return false;
  }
  const backupPath = `${filePath}.bak-${backupSuffix}`;
  process.stdout.write(`[fix-wsl-omx] patching ${filePath}\n`);
  process.stdout.write(`[fix-wsl-omx] backup -> ${backupPath}\n`);
  if (!dryRun) {
    fs.copyFileSync(filePath, backupPath);
    fs.writeFileSync(filePath, next);
  }
  return true;
}

function patchCodexHooks(content) {
  const marker = 'const escapedNodeExec = process.execPath.replace(/"/g, \'\\\\"\');';
  if (content.includes(marker)) {
    return content;
  }
  const target = '    const command = `node "${hookScript}"`;\n';
  const replacement = [
    '    const escapedNodeExec = process.execPath.replace(/"/g, \'\\\\"\');',
    '    const escapedHookScript = hookScript.replace(/"/g, \'\\\\"\');',
    '    const command = `"${escapedNodeExec}" "${escapedHookScript}"`;',
    "",
  ].join("\n");
  if (!content.includes(target)) {
    fail("[fix-wsl-omx] codex-hooks.js layout changed; patch target not found");
  }
  return content.replace(target, replacement);
}

function patchGenerator(content) {
  let next = content;

  if (!next.includes('const nodeExecPath = escapeTomlString(process.execPath);')) {
    const needle = '    const notifyHookPath = join(pkgRoot, "dist", "scripts", "notify-hook.js");\n';
    if (!next.includes(needle)) {
      fail("[fix-wsl-omx] generator.js notifyHookPath block not found");
    }
    next = next.replace(
      needle,
      `${needle}    const nodeExecPath = escapeTomlString(process.execPath);\n`,
    );
  }

  next = next.replace(
    '        `notify = ["node", "${escapedPath}"]`,',
    '        `notify = ["${nodeExecPath}", "${escapedPath}"]`,',
  );

  if (!next.includes("function getOmxTablesBlock(pkgRoot, includeTui = true) {\n    const nodeExecPath = escapeTomlString(process.execPath);\n")) {
    const blockNeedle = "function getOmxTablesBlock(pkgRoot, includeTui = true) {\n";
    if (!next.includes(blockNeedle)) {
      fail("[fix-wsl-omx] generator.js getOmxTablesBlock block not found");
    }
    next = next.replace(
      blockNeedle,
      `${blockNeedle}    const nodeExecPath = escapeTomlString(process.execPath);\n`,
    );
  }

  next = next.replaceAll("'command = \"node\"',", '`command = "${nodeExecPath}"`,');
  return next;
}

function main() {
  ensureWsl();
  const options = parseArgs(process.argv.slice(2));
  const backupSuffix = timestamp();

  if (!options.dryRun) {
    fs.mkdirSync(DEFAULT_NPM_CACHE, { recursive: true });
  }

  const upgradeVersion = resolveUpgradeVersion(options.version);
  if (upgradeVersion) {
    run("npm", ["install", "-g", `oh-my-codex@${upgradeVersion}`], {
      env: npmEnv(),
      dryRun: options.dryRun,
    });
  }

  const packageRoot = resolveGlobalPackageRoot();
  const codexHooksPath = path.join(packageRoot, "dist", "config", "codex-hooks.js");
  const generatorPath = path.join(packageRoot, "dist", "config", "generator.js");

  if (!options.dryRun) {
    if (!fs.existsSync(codexHooksPath) || !fs.existsSync(generatorPath)) {
      fail(`[fix-wsl-omx] could not locate installed oh-my-codex under ${packageRoot}`);
    }
  }

  patchFile(codexHooksPath, patchCodexHooks, {
    dryRun: options.dryRun,
    backupSuffix,
  });
  patchFile(generatorPath, patchGenerator, {
    dryRun: options.dryRun,
    backupSuffix,
  });

  if (!options.skipSetup) {
    run("omx", ["setup", "--force", "--verbose"], {
      cwd: REPO_ROOT,
      dryRun: options.dryRun,
    });
  }

  if (!options.skipCleanup) {
    run("omx", ["cleanup"], {
      cwd: REPO_ROOT,
      dryRun: options.dryRun,
    });
  }

  if (!options.skipDoctor) {
    run("omx", ["doctor"], {
      cwd: REPO_ROOT,
      dryRun: options.dryRun,
    });
  }

  process.stdout.write("[fix-wsl-omx] done\n");
}

main();
