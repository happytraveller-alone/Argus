#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

const DEFAULT_API_BASE_URL = "/api/v1";
const DEFAULT_PLACEHOLDER = "__API_BASE_URL__";
const DEFAULT_HTML_ROOT = "/usr/share/nginx/html";
const DEFAULT_COMMAND = ["nginx", "-g", "daemon off;"];

export function resolveApiBaseUrl(value) {
  const normalized = String(value || "").trim();
  return normalized || DEFAULT_API_BASE_URL;
}

function countOccurrences(content, token) {
  if (!content || !token) {
    return 0;
  }
  return content.split(token).length - 1;
}

function listJavaScriptFiles(rootDir) {
  const files = [];
  const queue = [rootDir];

  while (queue.length > 0) {
    const currentDir = queue.shift();
    if (!currentDir || !fs.existsSync(currentDir)) {
      continue;
    }

    for (const entry of fs.readdirSync(currentDir, { withFileTypes: true })) {
      const entryPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        queue.push(entryPath);
      } else if (entry.isFile() && entry.name.endsWith(".js")) {
        files.push(entryPath);
      }
    }
  }

  return files;
}

export function injectApiBasePlaceholders({
  rootDir = DEFAULT_HTML_ROOT,
  apiUrl = resolveApiBaseUrl(process.env.VITE_API_BASE_URL),
  placeholder = DEFAULT_PLACEHOLDER,
} = {}) {
  let filesChanged = 0;
  let replacements = 0;

  for (const filePath of listJavaScriptFiles(rootDir)) {
    const original = fs.readFileSync(filePath, "utf8");
    const matchCount = countOccurrences(original, placeholder);
    if (matchCount === 0) {
      continue;
    }

    fs.writeFileSync(filePath, original.split(placeholder).join(apiUrl));
    filesChanged += 1;
    replacements += matchCount;
  }

  return {
    filesChanged,
    replacements,
  };
}

function resolveCommand(argv) {
  return argv.length > 0 ? argv : DEFAULT_COMMAND;
}

function forwardSignal(child, signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

export async function main(argv = process.argv.slice(2)) {
  const apiUrl = resolveApiBaseUrl(process.env.VITE_API_BASE_URL);
  console.log(`Injecting API URL: ${apiUrl}`);
  injectApiBasePlaceholders({ apiUrl });

  const [command, ...args] = resolveCommand(argv);
  const child = spawn(command, args, {
    stdio: "inherit",
    env: process.env,
  });

  process.on("SIGINT", () => forwardSignal(child, "SIGINT"));
  process.on("SIGTERM", () => forwardSignal(child, "SIGTERM"));

  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(code ?? 1);
    });
  });

  process.exit(Number(exitCode));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
