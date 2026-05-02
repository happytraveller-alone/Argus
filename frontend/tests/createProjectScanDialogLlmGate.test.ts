import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function importOrFail<TModule = Record<string, unknown>>(
	relativePath: string,
): Promise<TModule> {
	try {
		return (await import(relativePath)) as TModule;
	} catch (error) {
		assert.fail(
			`expected helper module ${relativePath} to exist: ${error instanceof Error ? error.message : String(error)}`,
		);
	}
}

test("provider catalog falls back to built-ins and drops unknown current provider", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);

	const options = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "acme-cloud",
	});

	assert.equal(providerCatalog.normalizeLlmProviderId("Claude"), "claude");
	assert.equal(providerCatalog.normalizeLlmProviderId(""), "openai_compatible");
	assert.equal(
		options.some(
			(provider: { id: string }) => provider.id === "openai_compatible",
		),
		true,
	);
	assert.equal(
		options.some((provider: { id: string }) => provider.id === "acme-cloud"),
		false,
	);
	assert.equal(
		providerCatalog.getCreateProjectScanProviderLabel(options[0]),
		"OpenAI 兼容",
	);
});

test("provider switching refreshes default model and only refreshes Base URL before manual override", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const providerOptions = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "openai_compatible",
	});

	const untouchedBaseUrl = llmGate.resolveQuickConfigAfterProviderChange({
		providerOptions,
		currentConfig: {
			provider: "openai_compatible",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "demo-key",
		},
		nextProvider: "anthropic_compatible",
		hasManualBaseUrlOverride: false,
	});

	assert.deepEqual(untouchedBaseUrl, {
		provider: "anthropic_compatible",
		model: "claude-sonnet-4.5",
		baseUrl: "https://api.anthropic.com/v1",
		apiKey: "demo-key",
	});

	const manualBaseUrl = llmGate.resolveQuickConfigAfterProviderChange({
		providerOptions,
		currentConfig: {
			provider: "openai_compatible",
			model: "gpt-5",
			baseUrl: "https://gateway.internal/v1",
			apiKey: "demo-key",
		},
		nextProvider: "anthropic_compatible",
		hasManualBaseUrlOverride: true,
	});

	assert.deepEqual(manualBaseUrl, {
		provider: "anthropic_compatible",
		model: "claude-sonnet-4.5",
		baseUrl: "https://gateway.internal/v1",
		apiKey: "demo-key",
	});
});

test("system provider switch preserves existing values when next defaults are blank", async () => {
	const systemLlmDraft = await importOrFail<any>(
		"../src/components/system/llmProviderSwitch.ts",
	);

	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "https://gateway.internal/v1",
			wasTouched: false,
			nextDefaultValue: "",
		}),
		"https://gateway.internal/v1",
	);
	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "gpt-5-user",
			wasTouched: false,
			nextDefaultValue: "",
		}),
		"gpt-5-user",
	);
});

test("system provider switch still applies next defaults when current field is empty", async () => {
	const systemLlmDraft = await importOrFail<any>(
		"../src/components/system/llmProviderSwitch.ts",
	);

	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "",
			wasTouched: false,
			nextDefaultValue: "https://api.openai.com/v1",
		}),
		"https://api.openai.com/v1",
	);
	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "",
			wasTouched: false,
			nextDefaultValue: "gpt-5",
		}),
		"gpt-5",
	);
});

test("system provider switch preserves non-empty base URLs and respects explicit clear", async () => {
	const systemLlmDraft = await importOrFail<any>(
		"../src/components/system/llmProviderSwitch.ts",
	);

	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "https://gateway.internal/v1",
			wasTouched: false,
			nextDefaultValue: "https://api.openai.com/v1",
			preserveExistingNonEmptyValue: true,
		}),
		"https://gateway.internal/v1",
	);

	assert.equal(
		systemLlmDraft.resolveProviderSwitchFieldValue({
			currentValue: "",
			wasTouched: true,
			nextDefaultValue: "https://api.openai.com/v1",
			preserveExistingNonEmptyValue: true,
			allowExplicitEmptyOverride: true,
		}),
		"",
	);
});

test("LLM gate requires API keys for protocol providers", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const providerOptions = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "openai_compatible",
	});

	assert.deepEqual(
		llmGate.getLlmQuickConfigMissingFields(
			{
				provider: "openai_compatible",
				model: "",
				baseUrl: "",
				apiKey: "",
			},
			providerOptions,
		),
		["llmModel", "llmBaseUrl", "llmApiKey"],
	);

	assert.deepEqual(
		llmGate.getLlmQuickConfigMissingFields(
			{
				provider: "anthropic_compatible",
				model: "claude-sonnet-4.5",
				baseUrl: "https://api.anthropic.com/v1",
				apiKey: "",
			},
			providerOptions,
		),
		["llmApiKey"],
	);
});

test("LLM gate stays locked until saved and agent preflight passes, then re-locks after edits", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const providerOptions = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "openai_compatible",
	});
	const cleanConfig = {
		provider: "openai_compatible",
		model: "gpt-5",
		baseUrl: "https://api.openai.com/v1",
		apiKey: "demo-key",
	};

	const savedButUntested = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: cleanConfig,
		savedConfig: cleanConfig,
		hasPassedAgentPreflight: false,
	});
	assert.equal(savedButUntested.canTest, true);
	assert.equal(savedButUntested.canCreate, false);

	const savedAndTested = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: cleanConfig,
		savedConfig: cleanConfig,
		hasPassedAgentPreflight: true,
	});
	assert.equal(savedAndTested.canCreate, true);

	const editedAfterSuccess = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: {
			...cleanConfig,
			model: "gpt-5-mini",
		},
		savedConfig: cleanConfig,
		hasPassedAgentPreflight: true,
	});
	assert.equal(editedAfterSuccess.hasUnsavedChanges, true);
	assert.equal(editedAfterSuccess.canTest, true);
	assert.equal(editedAfterSuccess.canCreate, false);
	assert.match(editedAfterSuccess.testBlockMessage, /重新预检将先保存配置/);
	assert.equal(
		llmGate.invalidatePassedAgentPreflight({
			previousConfig: cleanConfig,
			nextConfig: {
				...cleanConfig,
				model: "gpt-5-mini",
			},
			hasPassedAgentPreflight: true,
		}),
		false,
	);
});

test("agent preflight delegates to backend task preflight and does not fall back to local probing", async () => {
	const agentPreflight = await importOrFail<any>(
		"../src/shared/api/agentPreflight.ts",
	);
	const database = await importOrFail<any>("../src/shared/api/database.ts");

	const originalRunAgentTaskPreflight = database.api.runAgentTaskPreflight;
	const originalGetUserConfig = database.api.getUserConfig;
	const originalTestLLMConnection = database.api.testLLMConnection;
	let taskPreflightCalls = 0;
	let legacyGetUserConfigCalls = 0;
	let legacyTestCalls = 0;

	database.api.runAgentTaskPreflight = async () => {
		taskPreflightCalls += 1;
		return {
			ok: false,
			stage: "llm_config",
			reasonCode: "default_config",
			message: "检测到默认配置",
			effectiveConfig: {
				provider: "openai_compatible",
				model: "gpt-5",
				baseUrl: "https://api.openai.com/v1",
				apiKey: "",
			},
			savedConfig: null,
			llmTestMetadata: null,
		};
	};
	database.api.getUserConfig = async () => {
		legacyGetUserConfigCalls += 1;
		throw new Error("legacy getUserConfig should not be called");
	};
	database.api.testLLMConnection = async () => {
		legacyTestCalls += 1;
		throw new Error("legacy testLLMConnection should not be called");
	};

	try {
		const result = await agentPreflight.runAgentPreflightCheck();

		assert.equal(taskPreflightCalls, 1);
		assert.equal(legacyGetUserConfigCalls, 0);
		assert.equal(legacyTestCalls, 0);
		assert.equal(result.reasonCode, "default_config");
		assert.equal(result.savedConfig, null);
		assert.deepEqual(result.effectiveConfig, {
			provider: "openai_compatible",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "",
		});
		assert.equal(result.llmTestMetadata, null);
	} finally {
		database.api.runAgentTaskPreflight = originalRunAgentTaskPreflight;
		database.api.getUserConfig = originalGetUserConfig;
		database.api.testLLMConnection = originalTestLLMConnection;
	}
});

test("scan dialog no longer owns agent preflight while settings page keeps the LLM connection test", async () => {
	const [dialogSource, systemConfigSource] = await Promise.all([
		readFile("src/components/scan/CreateProjectScanDialog.tsx", "utf8"),
		readFile("src/components/system/SystemConfig.tsx", "utf8"),
	]);

	assert.doesNotMatch(dialogSource, /runAgentPreflightCheck/);
	assert.doesNotMatch(dialogSource, /\btestLLMConnection\b/);
	assert.doesNotMatch(dialogSource, /\/system-config\/test-llm/);
	assert.match(systemConfigSource, /\btestLLMConnection\b/);
});

test("LLM gate treats prefilled default config as unsaved until the user saves it", async () => {
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const status = llmGate.getLlmQuickGateStatus({
		providerOptions: [],
		currentConfig: {
			provider: "openai_compatible",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "prefilled-key",
		},
		savedConfig: null,
		hasPassedAgentPreflight: false,
	});

	assert.equal(status.hasUnsavedChanges, true);
	assert.equal(status.canTest, true);
	assert.equal(status.canCreate, false);
	assert.match(status.testBlockMessage, /重新预检将先保存配置/);
});

test("create dialog exposes static engine selection without quick-fix preflight controls", async () => {
	const [dialogSource, contentSource] = await Promise.all([
		readFile("src/components/scan/CreateProjectScanDialog.tsx", "utf8"),
		readFile("src/components/scan/create-project-scan/Content.tsx", "utf8"),
	]);

	assert.match(dialogSource, /createStaticTasksForProject/);
	assert.match(contentSource, /Opengrep/);
	assert.match(contentSource, /CodeQL/);
	assert.doesNotMatch(contentSource, /handleQuickFixSave/);
	assert.doesNotMatch(contentSource, /onClick=\{handleQuickFixSave\}/);
	assert.doesNotMatch(contentSource, />\s*保存配置\s*</);
	assert.doesNotMatch(contentSource, /保存并预检中/);
	assert.doesNotMatch(contentSource, /\"重新预检\"/);
});

test("create dialog does not carry manual intelligent-audit preflight paths", async () => {
	const dialogSource = await readFile(
		"src/components/scan/CreateProjectScanDialog.tsx",
		"utf8",
	);

	assert.doesNotMatch(dialogSource, /handleQuickFixTest/);
	assert.doesNotMatch(dialogSource, /runAgentPreflightCheck/);
	assert.doesNotMatch(dialogSource, /createAgentTaskForProject/);
	assert.doesNotMatch(dialogSource, /handleCreateAgentTaskForProject/);
});

test("LLM gate treats redacted placeholders as inert and requires an explicit saved/imported source", async () => {
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const redactedOnlyConfig = {
		provider: "openai_compatible",
		model: "gpt-5",
		baseUrl: "https://api.openai.com/v1",
		apiKey: "***configured***",
	};
	const redactedOnlyStatus = llmGate.getLlmQuickGateStatus({
		providerOptions: [],
		currentConfig: redactedOnlyConfig,
		savedConfig: redactedOnlyConfig,
		hasPassedAgentPreflight: true,
	});

	assert.equal(redactedOnlyStatus.canCreate, false);
	assert.deepEqual(redactedOnlyStatus.missingFields, ["llmApiKey"]);

	const savedSecretConfig = {
		...redactedOnlyConfig,
		apiKey: "",
		hasSavedApiKey: true,
		apiKeySource: "imported",
	};
	const savedSecretStatus = llmGate.getLlmQuickGateStatus({
		providerOptions: [],
		currentConfig: savedSecretConfig,
		savedConfig: savedSecretConfig,
		hasPassedAgentPreflight: true,
	});

	assert.equal(savedSecretStatus.hasUnsavedChanges, false);
	assert.equal(savedSecretStatus.canTest, true);
	assert.equal(savedSecretStatus.canCreate, true);
});

test("LLM gate accepts only preflight metadata carrying fingerprints", async () => {
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	assert.equal(llmGate.hasVerifiedLlmTestMetadata(null), false);
	assert.equal(llmGate.hasVerifiedLlmTestMetadata({}), false);
	assert.equal(llmGate.hasVerifiedLlmTestMetadata({ fingerprint: "" }), false);
	assert.equal(
		llmGate.hasVerifiedLlmTestMetadata({ fingerprint: "sha256:abc" }),
		true,
	);
});

test("project pagination slices three cards per page and clamps invalid pages", async () => {
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const projects = Array.from({ length: 7 }, (_, index) => ({
		id: `project-${index + 1}`,
		name: `Project ${index + 1}`,
	}));

	const firstPage = llmGate.paginateProjectCards(projects, 1);
	assert.equal(firstPage.currentPage, 1);
	assert.equal(firstPage.totalPages, 3);
	assert.deepEqual(
		firstPage.items.map((project: { id: string }) => project.id),
		["project-1", "project-2", "project-3"],
	);

	const lastPage = llmGate.paginateProjectCards(projects, 999);
	assert.equal(lastPage.currentPage, 3);
	assert.deepEqual(
		lastPage.items.map((project: { id: string }) => project.id),
		["project-7"],
	);

	assert.equal(
		llmGate.resolveProjectPageAfterSearchChange({
			currentPage: 2,
			previousSearchTerm: "repo",
			nextSearchTerm: "zip",
		}),
		1,
	);
	assert.equal(
		llmGate.resolveProjectPageAfterSearchChange({
			currentPage: 2,
			previousSearchTerm: " repo ",
			nextSearchTerm: "repo",
		}),
		2,
	);
});
