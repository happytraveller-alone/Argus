import test from "node:test";
import assert from "node:assert/strict";

import {
	BUILTIN_LLM_PROVIDERS,
	buildLlmProviderOptions,
	getCreateProjectScanProviderLabel,
	normalizeLlmProviderId,
	parseLlmCustomHeadersInput,
} from "../src/shared/llm/providerCatalog.ts";

test("normalizeLlmProviderId maps compatibility aliases to stable ids", () => {
	assert.equal(normalizeLlmProviderId("claude"), "anthropic");
	assert.equal(normalizeLlmProviderId("openai_compatible"), "custom");
	assert.equal(normalizeLlmProviderId("custom"), "custom");
});

test("builtin provider catalog exposes the OpenAI compatible entry and Kimi preset", () => {
	const customProvider = BUILTIN_LLM_PROVIDERS.find(
		(provider) => provider.id === "custom",
	);
	const moonshotProvider = BUILTIN_LLM_PROVIDERS.find(
		(provider) => provider.id === "moonshot",
	);

	assert.ok(customProvider);
	assert.equal(customProvider.name, "OpenAI Compatible / 自定义站点");
	assert.equal(customProvider.supportsCustomHeaders, true);
	assert.ok(customProvider.exampleBaseUrls?.includes("https://api.openai.com/v1"));
	assert.ok(customProvider.exampleBaseUrls?.includes("https://api.moonshot.cn/v1"));
	assert.ok(customProvider.exampleBaseUrls?.includes("http://localhost:11434/v1"));

	assert.ok(moonshotProvider);
	assert.match(moonshotProvider.description, /Kimi/);
});

test("buildLlmProviderOptions reuses custom for openai_compatible values", () => {
	const providers = buildLlmProviderOptions({
		backendProviders: BUILTIN_LLM_PROVIDERS,
		currentProviderId: "openai_compatible",
	});

	const matchingProviders = providers.filter((provider) => provider.id === "custom");
	assert.equal(matchingProviders.length, 1);
});

test("parseLlmCustomHeadersInput validates JSON object strings", () => {
	assert.deepEqual(parseLlmCustomHeadersInput(""), {
		ok: true,
		headers: {},
		normalizedText: "",
	});

	assert.deepEqual(
		parseLlmCustomHeadersInput(
			'{"HTTP-Referer":"https://app.example.com","X-Trace":"audit"}',
		),
		{
			ok: true,
			headers: {
				"HTTP-Referer": "https://app.example.com",
				"X-Trace": "audit",
			},
			normalizedText:
				'{"HTTP-Referer":"https://app.example.com","X-Trace":"audit"}',
		},
	);

	assert.deepEqual(parseLlmCustomHeadersInput('["invalid"]'), {
		ok: false,
		message: "自定义请求头必须是 JSON 对象",
	});
});

test("getCreateProjectScanProviderLabel highlights the compatibility entry", () => {
	assert.equal(
		getCreateProjectScanProviderLabel({
			id: "custom",
			name: "OpenAI Compatible / 自定义站点",
		}),
		"OpenAI 兼容",
	);
	assert.equal(
		getCreateProjectScanProviderLabel({
			id: "openai",
			name: "OpenAI",
		}),
		"OpenAI",
	);
});
