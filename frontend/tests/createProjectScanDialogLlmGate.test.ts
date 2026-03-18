import test from "node:test";
import assert from "node:assert/strict";

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

test("provider catalog falls back to built-ins and preserves unknown current provider", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);

	const options = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "acme-cloud",
	});

	assert.equal(providerCatalog.normalizeLlmProviderId("Claude"), "anthropic");
	assert.equal(providerCatalog.normalizeLlmProviderId(""), "openai");
	assert.equal(
		options.some((provider: { id: string }) => provider.id === "openai"),
		true,
	);
	assert.equal(options.at(-1)?.id, "acme-cloud");
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
		currentProviderId: "openai",
	});

	const untouchedBaseUrl = llmGate.resolveQuickConfigAfterProviderChange({
		providerOptions,
		currentConfig: {
			provider: "openai",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "demo-key",
		},
		nextProvider: "ollama",
		hasManualBaseUrlOverride: false,
	});

	assert.deepEqual(untouchedBaseUrl, {
		provider: "ollama",
		model: "llama3.3-70b",
		baseUrl: "http://localhost:11434/v1",
		apiKey: "demo-key",
	});

	const manualBaseUrl = llmGate.resolveQuickConfigAfterProviderChange({
		providerOptions,
		currentConfig: {
			provider: "openai",
			model: "gpt-5",
			baseUrl: "https://gateway.internal/v1",
			apiKey: "demo-key",
		},
		nextProvider: "ollama",
		hasManualBaseUrlOverride: true,
	});

	assert.deepEqual(manualBaseUrl, {
		provider: "ollama",
		model: "llama3.3-70b",
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

test("LLM gate marks only required missing fields and exempts ollama API keys", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const providerOptions = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "openai",
	});

	assert.deepEqual(
		llmGate.getLlmQuickConfigMissingFields(
			{
				provider: "openai",
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
				provider: "ollama",
				model: "llama3.1",
				baseUrl: "http://localhost:11434/v1",
				apiKey: "",
			},
			providerOptions,
		),
		[],
	);
});

test("LLM gate stays locked until saved and manually tested, then re-locks after edits", async () => {
	const providerCatalog = await importOrFail<any>(
		"../src/shared/llm/providerCatalog.ts",
	);
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const providerOptions = providerCatalog.buildLlmProviderOptions({
		backendProviders: [],
		currentProviderId: "openai",
	});
	const cleanConfig = {
		provider: "openai",
		model: "gpt-5",
		baseUrl: "https://api.openai.com/v1",
		apiKey: "demo-key",
	};

	const savedButUntested = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: cleanConfig,
		savedConfig: cleanConfig,
		hasSuccessfulManualTest: false,
	});
	assert.equal(savedButUntested.canTest, true);
	assert.equal(savedButUntested.canCreate, false);

	const savedAndTested = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: cleanConfig,
		savedConfig: cleanConfig,
		hasSuccessfulManualTest: true,
	});
	assert.equal(savedAndTested.canCreate, true);

	const editedAfterSuccess = llmGate.getLlmQuickGateStatus({
		providerOptions,
		currentConfig: {
			...cleanConfig,
			model: "gpt-5-mini",
		},
		savedConfig: cleanConfig,
		hasSuccessfulManualTest: true,
	});
	assert.equal(editedAfterSuccess.hasUnsavedChanges, true);
	assert.equal(editedAfterSuccess.canTest, false);
	assert.equal(editedAfterSuccess.canCreate, false);
	assert.match(editedAfterSuccess.testBlockMessage, /先保存/);
	assert.equal(
		llmGate.invalidateSuccessfulManualTest({
			previousConfig: cleanConfig,
			nextConfig: {
				...cleanConfig,
				model: "gpt-5-mini",
			},
			hasSuccessfulManualTest: true,
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
				provider: "openai",
				model: "gpt-5",
				baseUrl: "https://api.openai.com/v1",
				apiKey: "",
			},
			savedConfig: null,
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
			provider: "openai",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "",
		});
	} finally {
		database.api.runAgentTaskPreflight = originalRunAgentTaskPreflight;
		database.api.getUserConfig = originalGetUserConfig;
		database.api.testLLMConnection = originalTestLLMConnection;
	}
});

test("LLM gate treats prefilled default config as unsaved until the user saves it", async () => {
	const llmGate = await importOrFail<any>(
		"../src/components/scan/create-project-scan/llmGate.ts",
	);

	const status = llmGate.getLlmQuickGateStatus({
		providerOptions: [],
		currentConfig: {
			provider: "openai",
			model: "gpt-5",
			baseUrl: "https://api.openai.com/v1",
			apiKey: "prefilled-key",
		},
		savedConfig: null,
		hasSuccessfulManualTest: false,
	});

	assert.equal(status.hasUnsavedChanges, true);
	assert.equal(status.canTest, false);
	assert.equal(status.canCreate, false);
	assert.match(status.testBlockMessage, /先保存/);
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
