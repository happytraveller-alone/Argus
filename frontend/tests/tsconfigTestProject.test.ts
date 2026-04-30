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

function loadRawTsconfig(configPath: string) {
  const result = ts.readConfigFile(
    path.join(frontendDir, configPath),
    ts.sys.readFile,
  );

  if (result.error) {
    throw new Error(formatDiagnostics([result.error]));
  }

  return result.config as {
    references?: Array<{ path?: string }>;
  };
}

function loadResolvedTsconfig(configPath: string) {
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

test("root tsconfig references the dedicated test project", () => {
  const rootConfig = loadRawTsconfig("tsconfig.json");

  assert.ok(
    rootConfig.references?.some((reference) => reference.path === "./tsconfig.test.json"),
  );
});

test("test project includes staticAnalysisViewModel.test.ts with node types enabled", () => {
  const testConfig = loadResolvedTsconfig("tsconfig.test.json");
  const program = ts.createProgram({
    rootNames: testConfig.fileNames,
    options: testConfig.options,
    projectReferences: testConfig.projectReferences,
  });
  const diagnostics = filterSupportedDiagnostics(ts.getPreEmitDiagnostics(program));

  assert.equal(testConfig.options.allowImportingTsExtensions, true);
  assert.deepEqual(testConfig.options.types, ["node"]);
  assert.ok(
    testConfig.fileNames.includes(
      path.join(frontendDir, "tests/staticAnalysisViewModel.test.ts"),
    ),
  );
  assert.equal(
    diagnostics.length,
    0,
    formatDiagnostics(diagnostics),
  );
});
