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

test("SystemConfig fetches models from complete draft config without save-first guard", () => {
  const source = readFileSync(systemConfigPath, "utf8");
  const databaseSource = readFileSync(databaseApiPath, "utf8");

  assert.match(source, /api\.fetchLLMModels\(\{[\s\S]*provider: providerId,[\s\S]*baseUrl,[\s\S]*customHeaders: parsedCustomHeaders\.normalizedText \|\| undefined,[\s\S]*\.\.\.\(draftApiKey \? \{ apiKey: draftApiKey \} : \{\}\),[\s\S]*\}\)/);
  assert.doesNotMatch(source, /api\.fetchLLMModels\(\{\}\)/);
  assert.doesNotMatch(source, /请先保存配置，再一键获取模型/);
  assert.doesNotMatch(source, /fetchingModels \|\|\s*hasChanges \|\|/);
  assert.match(source, /resolveModelFetchCredentialSource/);
  assert.match(source, /"draft-config"/);
  assert.match(source, /"saved-config"/);
	assert.match(
		databaseSource,
		/async fetchLLMModels\(params: \{\s*provider\?: string;/,
	);
  assert.match(databaseSource, /apiKey\?: string;/);
  assert.match(databaseSource, /baseUrl\?: string;/);
});

test("SystemConfig model fetch caches by non-secret request signature and updates selector deterministically", () => {
	const source = readFileSync(systemConfigPath, "utf8");

	assert.match(source, /function buildRedactedHeaderRevision\(normalizedHeaders: string\)/);
	assert.match(source, /return `headers:\$\{\(hash >>> 0\)\.toString\(36\)\}`/);
	assert.match(source, /function buildModelFetchSignature/);
	assert.match(source, /credentialSource: resolveModelFetchCredentialSource\(config\)/);
	assert.doesNotMatch(source, /`\$\{providerId\}\|\$\{baseUrl\}\|saved-config\|\$\{parsedCustomHeaders\.normalizedText\}`/);
	assert.match(source, /setFetchedModelsByProvider\(\(prev\) => \(\{[\s\S]*\[signature\]: normalizedModels/s);
	assert.match(source, /Object\.prototype\.hasOwnProperty\.call\(fetchedModelsByProvider, signature\)/);
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
});

test("SystemConfig key UI is password-only and keeps compact saved/reset/clear actions", () => {
  const source = readFileSync(systemConfigPath, "utf8");

  assert.doesNotMatch(source, /Eye,|EyeOff,|showApiKey|显示 API Key|隐藏 API Key/);
  assert.match(source, /<Input\s*\n\s*type="password"/);
  assert.doesNotMatch(source, /type=\{[^}]*"text"/);
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
