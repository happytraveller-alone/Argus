import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function formatDiagnostics(diagnostics: readonly ts.Diagnostic[]) {
  return ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: (fileName) =>
      ts.sys.useCaseSensitiveFileNames ? fileName : fileName.toLowerCase(),
    getCurrentDirectory: () => frontendDir,
    getNewLine: () => ts.sys.newLine,
  });
}

function filterSupportedDiagnostics(diagnostics: readonly ts.Diagnostic[]) {
  return diagnostics.filter((diagnostic) => diagnostic.code !== 5103);
}

function loadParsedTsconfig(configPath: string) {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    path.join(frontendDir, configPath),
    {},
    {
      ...ts.sys,
      onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
        throw new Error(formatDiagnostics([diagnostic]));
      },
    },
  );

  assert.ok(parsed, `Unable to load ${configPath}`);
  return parsed;
}

test("frontend test tsconfig type-checks cleanly", () => {
  const parsed = loadParsedTsconfig("tsconfig.test.json");
  const program = ts.createProgram({
    rootNames: parsed.fileNames,
    options: parsed.options,
    projectReferences: parsed.projectReferences,
  });
  const diagnostics = filterSupportedDiagnostics(ts.getPreEmitDiagnostics(program));

  assert.equal(
    diagnostics.length,
    0,
    formatDiagnostics(diagnostics) || "tsc exited with a non-zero status",
  );
});
