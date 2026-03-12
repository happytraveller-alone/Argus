export type LLMFetchStyle =
	| "openai_compatible"
	| "anthropic"
	| "azure_openai"
	| "native_static";

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
	custom: "gpt-5",
	openai: "gpt-5",
	openrouter: "openai/gpt-5-mini",
	azure_openai: "gpt-5",
	anthropic: "claude-sonnet-4.5",
	gemini: "gemini-3-pro",
	deepseek: "deepseek-v3.1-terminus",
	qwen: "qwen3-max-instruct",
	zhipu: "glm-4.6",
	moonshot: "kimi-k2",
	ollama: "llama3.3-70b",
};

export const LLM_PROVIDER_API_KEY_FIELD_MAP: Record<string, string> = {
	custom: "openaiApiKey",
	openai: "openaiApiKey",
	openrouter: "openaiApiKey",
	azure_openai: "openaiApiKey",
	anthropic: "claudeApiKey",
	claude: "claudeApiKey",
	gemini: "geminiApiKey",
	qwen: "qwenApiKey",
	deepseek: "deepseekApiKey",
	zhipu: "zhipuApiKey",
	moonshot: "moonshotApiKey",
	baidu: "baiduApiKey",
	minimax: "minimaxApiKey",
	doubao: "doubaoApiKey",
};

export const BUILTIN_LLM_PROVIDERS: LLMProviderItem[] = [
	{
		id: "custom",
		name: "OpenAI Compatible / 自定义站点",
		description: "适用于 OpenAI 兼容站点、中转服务和自建网关。",
		defaultModel: "gpt-5",
		models: ["gpt-5", "kimi-k2", "deepseek-chat", "qwen-max"],
		defaultBaseUrl: "",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: [
			"https://api.openai.com/v1",
			"https://api.moonshot.cn/v1",
			"http://localhost:11434/v1",
		],
		supportsCustomHeaders: true,
	},
	{
		id: "openai",
		name: "OpenAI",
		description: "OpenAI 官方接口。",
		defaultModel: "gpt-5",
		models: ["gpt-5", "gpt-5.1", "gpt-4o", "gpt-4o-mini"],
		defaultBaseUrl: "https://api.openai.com/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: ["https://api.openai.com/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "openrouter",
		name: "OpenRouter",
		description: "统一多模型路由聚合服务（OpenAI 兼容）。",
		defaultModel: "openai/gpt-5-mini",
		models: [
			"openai/gpt-5-mini",
			"anthropic/claude-3.7-sonnet",
			"google/gemini-2.5-pro",
		],
		defaultBaseUrl: "https://openrouter.ai/api/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: ["https://openrouter.ai/api/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "anthropic",
		name: "Anthropic",
		description: "Claude 系列模型服务。",
		defaultModel: "claude-sonnet-4.5",
		models: [
			"claude-sonnet-4.5",
			"claude-opus-4.5",
			"claude-haiku-4.5",
		],
		defaultBaseUrl: "https://api.anthropic.com/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "anthropic",
		exampleBaseUrls: ["https://api.anthropic.com/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "azure_openai",
		name: "Azure OpenAI",
		description: "Azure 托管 OpenAI 接口。",
		defaultModel: "gpt-5",
		models: ["gpt-5", "gpt-4o", "o4-mini"],
		defaultBaseUrl: "https://{resource}.openai.azure.com/openai/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "azure_openai",
		exampleBaseUrls: ["https://{resource}.openai.azure.com/openai/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "moonshot",
		name: "Moonshot / Kimi",
		description: "Moonshot Kimi 官方接口（OpenAI 兼容）。",
		defaultModel: "kimi-k2",
		models: ["kimi-k2", "kimi-k2-thinking", "moonshot-v1-128k"],
		defaultBaseUrl: "https://api.moonshot.cn/v1",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: ["https://api.moonshot.cn/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "ollama",
		name: "Ollama",
		description: "本地部署 LLM（OpenAI 兼容，无需 API Key）。",
		defaultModel: "llama3.3-70b",
		models: ["llama3.3-70b", "qwen3-8b", "deepseek-r1"],
		defaultBaseUrl: "http://localhost:11434/v1",
		requiresApiKey: false,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: ["http://localhost:11434/v1"],
		supportsCustomHeaders: true,
	},
	{
		id: "gemini",
		name: "Google Gemini",
		description: "Google Gemini 模型服务。",
		defaultModel: "gemini-3-pro",
		models: ["gemini-3-pro", "gemini-2.5-pro", "gemini-2.5-flash"],
		defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		supportsCustomHeaders: true,
	},
	{
		id: "deepseek",
		name: "DeepSeek",
		description: "DeepSeek 推理与对话模型。",
		defaultModel: "deepseek-v3.1-terminus",
		models: ["deepseek-v3.1-terminus", "deepseek-chat", "deepseek-reasoner"],
		defaultBaseUrl: "https://api.deepseek.com",
		requiresApiKey: true,
		supportsModelFetch: true,
		fetchStyle: "openai_compatible",
		supportsCustomHeaders: true,
	},
];

export function normalizeLlmProviderId(
	provider: string | undefined | null,
): string {
	const normalized = (provider || "").trim().toLowerCase();
	if (!normalized) return "openai";
	if (normalized === "claude") return "anthropic";
	if (normalized === "openai_compatible") return "custom";
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

function buildUnknownProvider(providerId: string): LLMProviderItem {
	return {
		id: providerId,
		name: providerId,
		description: "自定义模型提供商",
		defaultModel: "",
		models: [],
		defaultBaseUrl: "",
		requiresApiKey: providerId !== "ollama",
		supportsModelFetch: false,
		fetchStyle: "openai_compatible",
		exampleBaseUrls: [],
		supportsCustomHeaders: true,
	};
}

export function buildLlmProviderOptions(options?: {
	backendProviders?: LLMProviderItem[] | null;
	currentProviderId?: string | null;
}): LLMProviderItem[] {
	const backendProviders = Array.isArray(options?.backendProviders)
		? options?.backendProviders
		: [];
	const currentProviderId = normalizeLlmProviderId(
		options?.currentProviderId || "",
	);
	const baseProviders =
		backendProviders.length > 0 ? backendProviders : BUILTIN_LLM_PROVIDERS;
	if (!currentProviderId) return baseProviders;
	if (baseProviders.some((provider) => provider.id === currentProviderId)) {
		return baseProviders;
	}
	return [...baseProviders, buildUnknownProvider(currentProviderId)];
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
	providerOptions: LLMProviderItem[] | null | undefined,
	providerId: string,
): boolean {
	const provider = getLlmProviderInfo(providerOptions, providerId);
	if (provider) return Boolean(provider.requiresApiKey);
	return normalizeLlmProviderId(providerId) !== "ollama";
}

export function resolveEffectiveLlmApiKey(
	provider: string,
	llmConfig: Record<string, unknown>,
): string {
	const directKey = String(llmConfig.llmApiKey || "").trim();
	if (directKey) return directKey;

	const providerKeyField =
		LLM_PROVIDER_API_KEY_FIELD_MAP[normalizeLlmProviderId(provider)];
	if (!providerKeyField) return "";
	return String(llmConfig[providerKeyField] || "").trim();
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

export function getCreateProjectScanProviderLabel(
	provider: Pick<LLMProviderItem, "id" | "name"> | undefined,
): string {
	if (!provider) return "";
	return normalizeLlmProviderId(provider.id) === "custom"
		? "OpenAI 兼容"
		: provider.name || provider.id;
}
