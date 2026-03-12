import type { PreflightMissingField } from "@/shared/api/agentPreflight";
import {
	getDefaultBaseUrlForProvider,
	getDefaultModelForProvider,
	normalizeLlmProviderId,
	shouldRequireApiKey,
	type LLMProviderItem,
} from "@/shared/llm/providerCatalog";

export interface LlmQuickConfig {
	provider: string;
	model: string;
	baseUrl: string;
	apiKey: string;
}

interface LlmQuickGateStatusInput {
	providerOptions: LLMProviderItem[];
	currentConfig: LlmQuickConfig;
	savedConfig: LlmQuickConfig | null;
	hasSuccessfulManualTest: boolean;
}

function normalizeQuickConfig(config: LlmQuickConfig | null | undefined): LlmQuickConfig | null {
	if (!config) return null;
	return {
		provider: normalizeLlmProviderId(config.provider),
		model: String(config.model || "").trim(),
		baseUrl: String(config.baseUrl || "").trim(),
		apiKey: String(config.apiKey || "").trim(),
	};
}

export function areSameLlmQuickConfig(
	left: LlmQuickConfig | null | undefined,
	right: LlmQuickConfig | null | undefined,
): boolean {
	const normalizedLeft = normalizeQuickConfig(left);
	const normalizedRight = normalizeQuickConfig(right);
	if (!normalizedLeft && !normalizedRight) return true;
	if (!normalizedLeft || !normalizedRight) return false;
	return (
		normalizedLeft.provider === normalizedRight.provider &&
		normalizedLeft.model === normalizedRight.model &&
		normalizedLeft.baseUrl === normalizedRight.baseUrl &&
		normalizedLeft.apiKey === normalizedRight.apiKey
	);
}

export function getLlmQuickConfigMissingFields(
	config: LlmQuickConfig,
	providerOptions: LLMProviderItem[],
): PreflightMissingField[] {
	const normalizedConfig = normalizeQuickConfig(config);
	if (!normalizedConfig) return ["llmModel", "llmBaseUrl", "llmApiKey"];
	const missingFields: PreflightMissingField[] = [];
	if (!normalizedConfig.model) missingFields.push("llmModel");
	if (!normalizedConfig.baseUrl) missingFields.push("llmBaseUrl");
	if (
		shouldRequireApiKey(providerOptions, normalizedConfig.provider) &&
		!normalizedConfig.apiKey
	) {
		missingFields.push("llmApiKey");
	}
	return missingFields;
}

export function resolveQuickConfigAfterProviderChange(options: {
	providerOptions: LLMProviderItem[];
	currentConfig: LlmQuickConfig;
	nextProvider: string;
	hasManualBaseUrlOverride: boolean;
}): LlmQuickConfig {
	const normalizedCurrent = normalizeQuickConfig(options.currentConfig) || {
		provider: "openai",
		model: "",
		baseUrl: "",
		apiKey: "",
	};
	const normalizedProvider = normalizeLlmProviderId(options.nextProvider);
	const defaultModel = getDefaultModelForProvider(
		options.providerOptions,
		normalizedProvider,
	);
	const defaultBaseUrl = getDefaultBaseUrlForProvider(
		options.providerOptions,
		normalizedProvider,
	);
	return {
		provider: normalizedProvider,
		model: defaultModel || normalizedCurrent.model,
		baseUrl:
			options.hasManualBaseUrlOverride && normalizedCurrent.baseUrl
				? normalizedCurrent.baseUrl
				: defaultBaseUrl || normalizedCurrent.baseUrl,
		apiKey: normalizedCurrent.apiKey,
	};
}

export function invalidateSuccessfulManualTest(options: {
	previousConfig: LlmQuickConfig | null | undefined;
	nextConfig: LlmQuickConfig | null | undefined;
	hasSuccessfulManualTest: boolean;
}): boolean {
	if (!options.hasSuccessfulManualTest) return false;
	return areSameLlmQuickConfig(options.previousConfig, options.nextConfig);
}

export function getLlmQuickGateStatus({
	providerOptions,
	currentConfig,
	savedConfig,
	hasSuccessfulManualTest,
}: LlmQuickGateStatusInput) {
	const missingFields = getLlmQuickConfigMissingFields(currentConfig, providerOptions);
	const hasUnsavedChanges = !areSameLlmQuickConfig(currentConfig, savedConfig);
	const canTest = missingFields.length === 0;
	const testBlockMessage = "";

	return {
		missingFields,
		hasUnsavedChanges,
		canSave: missingFields.length === 0,
		canTest,
		canCreate: missingFields.length === 0 && !hasUnsavedChanges && hasSuccessfulManualTest,
		testBlockMessage,
	};
}

export const CREATE_PROJECT_SCAN_PAGE_SIZE = 3;

export function paginateProjectCards<T>(
	items: T[],
	requestedPage: number,
	pageSize = CREATE_PROJECT_SCAN_PAGE_SIZE,
) {
	const safePageSize = Math.max(1, pageSize);
	const totalPages = Math.max(1, Math.ceil(items.length / safePageSize));
	const currentPage = Math.min(Math.max(1, requestedPage), totalPages);
	const startIndex = (currentPage - 1) * safePageSize;
	return {
		items: items.slice(startIndex, startIndex + safePageSize),
		currentPage,
		totalPages,
		pageSize: safePageSize,
	};
}

export function resolveProjectPageAfterSearchChange(options: {
	currentPage: number;
	previousSearchTerm: string;
	nextSearchTerm: string;
}): number {
	const previousSearchTerm = String(options.previousSearchTerm || "").trim();
	const nextSearchTerm = String(options.nextSearchTerm || "").trim();
	return previousSearchTerm === nextSearchTerm ? options.currentPage : 1;
}
