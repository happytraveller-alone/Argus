import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const systemConfigPath = path.resolve(
  process.cwd(),
  "src/components/system/SystemConfig.tsx",
);
const databaseApiPath = path.resolve(
	process.cwd(),
	"src/shared/api/database.ts",
);

test("SystemConfig fetches models through saved backend config only", () => {
  const source = readFileSync(systemConfigPath, "utf8");
  const databaseSource = readFileSync(databaseApiPath, "utf8");

  assert.match(source, /api\.fetchLLMModels\(\{\}\)/);
  assert.doesNotMatch(source, /api\.fetchLLMModels\(\{[^}]*apiKey/s);
  assert.match(source, /请先保存配置，再一键获取模型/);
  assert.match(source, /disabled=\{\s*fetchingModels \|\|\s*hasChanges/s);
  assert.match(source, /saved-config/);
	assert.match(
		databaseSource,
		/async fetchLLMModels\(params: \{\s*provider\?: string;/,
	);
  assert.match(databaseSource, /\} = \{\}\): Promise<\{/);
});

test("SystemConfig model fetch updates selector source, count cache, and selected model deterministically", () => {
	const source = readFileSync(systemConfigPath, "utf8");

	assert.match(source, /result\.models\s*\n\s*\.map\(\(model\) =>/);
	assert.match(source, /setFetchedModelsByProvider\(\(prev\) => \(\{/);
	assert.match(
		source,
		/Object\.prototype\.hasOwnProperty\.call\(fetchedModelsByProvider, providerId\)/,
	);
	assert.match(source, /availableModelCount: normalizedModels\.length/);
	assert.match(
		source,
		/String\(result\.defaultModel \|\| ""\)\.trim\(\) \|\| normalizedModels\[0\]/,
	);
	assert.match(source, /llmModel: preferredFetchedModel/);
	assert.match(
		source,
		/trigger === "manual" &&\s*result\.success &&\s*normalizedModels\.length > 0/s,
	);
	assert.match(
		source,
		/setModelStatsFetchStateBySignature\(\(prev\) => \(\{\s*\.\.\.prev,\s*\[signature\]: "failed"/s,
	);
	assert.match(source, /\|saved-config\|\$\{statsParsedCustomHeaders\?\.ok/);
});

test("SystemConfig key UI uses compact status text and confirmed destructive clear", () => {
  const source = readFileSync(systemConfigPath, "utf8");

  assert.match(source, /const llmKeyStatusText =/);
  assert.match(source, /需保存密钥/);
  assert.match(source, /已导入密钥/);
  assert.match(source, /已保存密钥/);
  assert.match(source, /aria-label="使用已保存密钥"/);
  assert.match(source, /aria-label="重新输入密钥"/);
  assert.match(source, /aria-label="清除密钥"/);
	assert.match(
		source,
		/window\.confirm\(\s*"确定要清除当前 LLM 密钥状态吗？保存前需要重新输入 API Key。"/,
	);
  assert.doesNotMatch(source, /已保存的密钥将继续用于后端请求/);
});

test("SystemConfig save allows empty model while test remains strict", () => {
  const source = readFileSync(systemConfigPath, "utf8");

  assert.match(source, /if \(!model && source === "test"\)/);
	assert.doesNotMatch(
		source,
		/if \(!model\) \{\s*toast\.error\(\s*`无法\$\{source === "save"/s,
	);
  assert.match(source, /llmModel: validated\.model/);
});
