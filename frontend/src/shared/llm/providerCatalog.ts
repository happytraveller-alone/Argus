export type LLMFetchStyle = "openai_compatible" | "anthropic_compatible";

export interface LLMProviderItem {
	id: string;
	name: string;
	description: string;
	defaultModel: string;
	models: string[];
	defaultBaseUrl: string;
	requiresApiKey: boolean;
	supportsModelFetch: boolean;
	fetchStyle: LLMFetchStyle;
	exampleBaseUrls?: string[];
	supportsCustomHeaders?: boolean;
}

const DEFAULT_MODELS: Record<string, string> = {
	openai_compatible: "gpt-5",
	anthropic_compatible: "claude-sonnet-4.5",
};

export const LLM_PROVIDER_API_KEY_FIELD_MAP: Record<string, string> = {
	openai_compatible: "llmApiKey",
	anthropic_compatible: "llmApiKey",
};

export const BUILTIN_LLM_PROVIDERS: LLMProviderItem[] = [
	{
		id: "openai_compatible",
		name: "OpenAI 兼容",
		description: "适用于 OpenAI 兼容站点、中转服务和自建网关。",
		defaultModel: "gpt-5",
		models: ["gpt-5", "gpt-5.1", "gpt-4o", "qwen-max", "deepseek-chat"],
		defaultBaseUrl: "https://api.openai.com/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: [
			"https://api.openai.com/v1",
			"http://localhost:11434/v1",
		],
		supportsCustomHeaders: true,
	},
	{
		id: "anthropic_compatible",
		name: "Anthropic 兼容",
		description: "适用于 Anthropic Messages 兼容接口。",
		defaultModel: "claude-sonnet-4.5",
		models: ["claude-sonnet-4.5", "claude-opus-4.5", "claude-haiku-4.5"],
		defaultBaseUrl: "https://api.anthropic.com/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "anthropic_compatible",
		exampleBaseUrls: ["https://api.anthropic.com/v1"],
		supportsCustomHeaders: true,
	},
];

export function normalizeLlmProviderId(
	provider: string | undefined | null,
): string {
	const normalized = (provider || "").trim().toLowerCase();
	if (!normalized) return "openai_compatible";
	return normalized;
}

function resolveProviderSource(
	providerOptions?: LLMProviderItem[] | null,
): LLMProviderItem[] {
	if (Array.isArray(providerOptions) && providerOptions.length > 0) {
		return providerOptions;
	}
	return BUILTIN_LLM_PROVIDERS;
}

export function buildLlmProviderOptions(options?: {
	backendProviders?: LLMProviderItem[] | null;
	currentProviderId?: string | null;
}): LLMProviderItem[] {
	const backendProviders = Array.isArray(options?.backendProviders)
		? options?.backendProviders
		: [];
	return backendProviders.length > 0 ? backendProviders : BUILTIN_LLM_PROVIDERS;
}

export function getLlmProviderInfo(
	providerOptions: LLMProviderItem[] | null | undefined,
	providerId: string,
): LLMProviderItem | undefined {
	const normalizedProviderId = normalizeLlmProviderId(providerId);
	return resolveProviderSource(providerOptions).find(
		(provider) => provider.id === normalizedProviderId,
	);
}

export function getDefaultModelForProvider(
	providerOptions: LLMProviderItem[] | null | undefined,
	providerId: string,
): string {
	const provider = getLlmProviderInfo(providerOptions, providerId);
	return (
		provider?.defaultModel || DEFAULT_MODELS[normalizeLlmProviderId(providerId)] || ""
	);
}

export function getDefaultBaseUrlForProvider(
	providerOptions: LLMProviderItem[] | null | undefined,
	providerId: string,
): string {
	return getLlmProviderInfo(providerOptions, providerId)?.defaultBaseUrl || "";
}

export function shouldRequireApiKey(
	providerOptionsOrId: LLMProviderItem[] | string | null | undefined,
	providerId?: string,
): boolean {
	const options = Array.isArray(providerOptionsOrId)
		? providerOptionsOrId
		: undefined;
	const targetProviderId =
		typeof providerOptionsOrId === "string"
			? providerOptionsOrId
			: providerId || "";
	const provider = getLlmProviderInfo(options, targetProviderId);
	if (provider) return Boolean(provider.requiresApiKey);
	return true;
}

export function resolveEffectiveLlmApiKey(
	_provider: string,
	llmConfig: Record<string, unknown>,
): string {
	return String(llmConfig.llmApiKey || "").trim();
}

export type LlmCustomHeadersParseResult =
	| {
			ok: true;
			headers: Record<string, string>;
			normalizedText: string;
	  }
	| {
			ok: false;
			message: string;
	  };

export function parseLlmCustomHeadersInput(
	rawValue: string | null | undefined,
): LlmCustomHeadersParseResult {
	const text = String(rawValue || "").trim();
	if (!text) {
		return {
			ok: true,
			headers: {},
			normalizedText: "",
		};
	}

	let parsed: unknown;
	try {
		parsed = JSON.parse(text);
	} catch {
		return {
			ok: false,
			message: "自定义请求头必须是 JSON 对象",
		};
	}

	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
		return {
			ok: false,
			message: "自定义请求头必须是 JSON 对象",
		};
	}

	const headers: Record<string, string> = {};
	for (const [key, value] of Object.entries(parsed)) {
		const headerName = String(key || "").trim();
		if (!headerName) continue;
		if (value && typeof value === "object") {
			return {
				ok: false,
				message: "自定义请求头必须是扁平的 JSON 对象",
			};
		}
		headers[headerName] = value == null ? "" : String(value);
	}

	return {
		ok: true,
		headers,
		normalizedText: Object.keys(headers).length
			? JSON.stringify(headers)
			: "",
	};
}

export function getLlmCustomHeadersParseErrorMessage(
	result: LlmCustomHeadersParseResult,
): string | null {
	return "message" in result ? result.message : null;
}

export function getCreateProjectScanProviderLabel(
	provider: Pick<LLMProviderItem, "id" | "name"> | undefined,
): string {
	if (!provider) return "";
	return provider.name || provider.id;
}
