import test from "node:test";
import assert from "node:assert/strict";

import {
	BUILTIN_LLM_PROVIDERS,
	buildLlmProviderOptions,
	getLlmCustomHeadersParseErrorMessage,
	getCreateProjectScanProviderLabel,
	normalizeLlmProviderId,
	parseLlmCustomHeadersInput,
} from "../src/shared/llm/providerCatalog.ts";

test("normalizeLlmProviderId preserves protocol provider ids", () => {
	assert.equal(normalizeLlmProviderId("claude"), "claude");
	assert.equal(normalizeLlmProviderId("openai_compatible"), "openai_compatible");
	assert.equal(normalizeLlmProviderId("custom"), "custom");
});

test("builtin provider catalog exposes only protocol providers", () => {
	const customProvider = BUILTIN_LLM_PROVIDERS.find(
		(provider) => provider.id === "openai_compatible",
	);
	const anthropicProvider = BUILTIN_LLM_PROVIDERS.find(
		(provider) => provider.id === "anthropic_compatible",
	);

	assert.equal(BUILTIN_LLM_PROVIDERS.length, 2);

	assert.ok(customProvider);
	assert.equal(customProvider.name, "OpenAI 兼容");
	assert.equal(customProvider.supportsCustomHeaders, true);
	assert.ok(customProvider.exampleBaseUrls?.includes("https://api.openai.com/v1"));
	assert.ok(customProvider.exampleBaseUrls?.includes("http://localhost:11434/v1"));

	assert.ok(anthropicProvider);
	assert.equal(anthropicProvider.fetchStyle, "anthropic_compatible");
});

test("buildLlmProviderOptions does not preserve unknown providers", () => {
	const providers = buildLlmProviderOptions({
		backendProviders: BUILTIN_LLM_PROVIDERS,
		currentProviderId: "openai_compatible",
	});

	const matchingProviders = providers.filter((provider) => provider.id === "openai_compatible");
	assert.equal(matchingProviders.length, 1);
	assert.equal(providers.some((provider) => provider.id === "custom"), false);
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

test("getLlmCustomHeadersParseErrorMessage only exposes validation errors", () => {
	assert.equal(
		getLlmCustomHeadersParseErrorMessage(parseLlmCustomHeadersInput("")),
		null,
	);
	assert.equal(
		getLlmCustomHeadersParseErrorMessage(parseLlmCustomHeadersInput('["invalid"]')),
		"自定义请求头必须是 JSON 对象",
	);
});

test("getCreateProjectScanProviderLabel highlights the compatibility entry", () => {
	assert.equal(
		getCreateProjectScanProviderLabel({
			id: "openai_compatible",
			name: "OpenAI 兼容",
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
