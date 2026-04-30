import path from "node:path";
import { createRequire } from "node:module";

import type { Plugin } from "vite";

import { createProductionObfuscatorOptions } from "./obfuscatorOptions";

type ObfuscatorModule = {
  obfuscate(code: string, options: Record<string, unknown>): {
    getObfuscatedCode(): string;
  };
};

const require = createRequire(import.meta.url);
const obfuscatorPluginPackagePath = require.resolve(
  "vite-plugin-javascript-obfuscator/package.json",
);
const javascriptObfuscator = require(
  require.resolve("javascript-obfuscator", {
    paths: [path.dirname(obfuscatorPluginPackagePath)],
  }),
) as ObfuscatorModule;

function isApplicationChunk(moduleId: string) {
  return moduleId.length > 0 && !moduleId.includes("/node_modules/");
}

export function createChunkObfuscatorPlugin(): Plugin {
  return {
    name: "vite-chunk-obfuscator",
    apply: "build",
    enforce: "post",
    renderChunk(code, chunk) {
      if (!chunk.fileName.endsWith(".js")) {
        return null;
      }

      if (!chunk.moduleIds.some(isApplicationChunk)) {
        return null;
      }

      const result = javascriptObfuscator.obfuscate(
        code,
        createProductionObfuscatorOptions(),
      );

      return {
        code: result.getObfuscatedCode(),
        map: null,
      };
    },
  };
}
