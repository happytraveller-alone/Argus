import type { PreflightMissingField } from "@/shared/api/agentPreflight";
import {
	getDefaultBaseUrlForProvider,
	getDefaultModelForProvider,
	normalizeLlmProviderId,
	shouldRequireApiKey,
	type LLMProviderItem,
} from "@/shared/llm/providerCatalog";

export const REDACTED_API_KEY = "***configured***";

export type LlmSecretSource = "saved" | "imported" | "entered" | "none";

export interface LlmQuickConfig {
	provider: string;
	model: string;
	baseUrl: string;
	apiKey: string;
	apiKeySource?: LlmSecretSource;
	hasSavedApiKey?: boolean;
}

interface LlmQuickGateStatusInput {
	providerOptions: LLMProviderItem[];
	currentConfig: LlmQuickConfig;
	savedConfig: LlmQuickConfig | null;
	hasPassedAgentPreflight: boolean;
}

export function isRedactedApiKeyPlaceholder(
	value: string | null | undefined,
): boolean {
	return String(value || "").trim() === REDACTED_API_KEY;
}

export function normalizeSecretSource(
	value: unknown,
	hasSavedApiKey?: boolean,
): LlmSecretSource {
	const normalized = String(value || "")
		.trim()
		.toLowerCase();
	if (
		normalized === "imported" ||
		normalized === "saved" ||
		normalized === "entered"
	) {
		return normalized;
	}
	return hasSavedApiKey ? "saved" : "none";
}

export function usesSavedOrImportedSecret(
	config: LlmQuickConfig | null | undefined,
): boolean {
	if (!config) return false;
	const source = normalizeSecretSource(
		config.apiKeySource,
		config.hasSavedApiKey,
	);
	return Boolean(
		config.hasSavedApiKey && (source === "saved" || source === "imported"),
	);
}

function normalizeQuickConfig(
	config: LlmQuickConfig | null | undefined,
): LlmQuickConfig | null {
	if (!config) return null;
	const rawApiKey = String(config.apiKey || "").trim();
	const hasSavedApiKey = Boolean(config.hasSavedApiKey);
	const apiKeySource = normalizeSecretSource(
		config.apiKeySource,
		hasSavedApiKey,
	);
	return {
		provider: normalizeLlmProviderId(config.provider),
		model: String(config.model || "").trim(),
		baseUrl: String(config.baseUrl || "").trim(),
		apiKey: isRedactedApiKeyPlaceholder(rawApiKey) ? "" : rawApiKey,
		apiKeySource,
		hasSavedApiKey,
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
		normalizedLeft.apiKey === normalizedRight.apiKey &&
		normalizedLeft.apiKeySource === normalizedRight.apiKeySource &&
		normalizedLeft.hasSavedApiKey === normalizedRight.hasSavedApiKey
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
	if (shouldRequireApiKey(providerOptions, normalizedConfig.provider)) {
		const hasExecutableEnteredKey = Boolean(normalizedConfig.apiKey);
		const hasSelectedServerSideKey =
			usesSavedOrImportedSecret(normalizedConfig);
		if (!hasExecutableEnteredKey && !hasSelectedServerSideKey) {
			missingFields.push("llmApiKey");
		}
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
		provider: "openai_compatible",
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
		...(normalizedCurrent.apiKeySource !== "none"
			? { apiKeySource: normalizedCurrent.apiKeySource }
			: {}),
		...(normalizedCurrent.hasSavedApiKey
			? { hasSavedApiKey: normalizedCurrent.hasSavedApiKey }
			: {}),
	};
}

export function invalidatePassedAgentPreflight(options: {
	previousConfig: LlmQuickConfig | null | undefined;
	nextConfig: LlmQuickConfig | null | undefined;
	hasPassedAgentPreflight: boolean;
}): boolean {
	if (!options.hasPassedAgentPreflight) return false;
	return areSameLlmQuickConfig(options.previousConfig, options.nextConfig);
}

export function hasVerifiedLlmTestMetadata(
	metadata: Record<string, unknown> | null | undefined,
): boolean {
	return (
		typeof metadata?.fingerprint === "string" &&
		metadata.fingerprint.trim() !== ""
	);
}

export function getLlmQuickGateStatus({
	providerOptions,
	currentConfig,
	savedConfig,
	hasPassedAgentPreflight,
}: LlmQuickGateStatusInput) {
	const missingFields = getLlmQuickConfigMissingFields(
		currentConfig,
		providerOptions,
	);
	const hasUnsavedChanges = !areSameLlmQuickConfig(currentConfig, savedConfig);
	const hasRequiredFields = missingFields.length === 0;
	const normalizedConfig = normalizeQuickConfig(currentConfig);
	const hasSelectedServerSideKey = usesSavedOrImportedSecret(normalizedConfig);
	const hasEnteredKey = Boolean(normalizedConfig?.apiKey);
	const canTest =
		hasRequiredFields &&
		!hasUnsavedChanges &&
		(hasEnteredKey ||
			hasSelectedServerSideKey ||
			!shouldRequireApiKey(providerOptions, normalizedConfig?.provider || ""));
	const testBlockMessage = hasRequiredFields
		? hasUnsavedChanges
			? "当前 LLM 配置有未保存改动，请先保存，再重新预检。"
			: ""
		: "";

	return {
		missingFields,
		hasUnsavedChanges,
		canSave: hasRequiredFields,
		canTest,
		canCreate:
			hasRequiredFields && !hasUnsavedChanges && hasPassedAgentPreflight,
		testBlockMessage,
	};
}

export function mergeRetainedProjectForRetry<TProject extends { id: string }>(
	projects: TProject[],
	retainedProject: TProject,
): TProject[] {
	const existingIndex = projects.findIndex(
		(project) => project.id === retainedProject.id,
	);
	if (existingIndex === -1) return [retainedProject, ...projects];
	return projects.map((project, index) =>
		index === existingIndex ? retainedProject : project,
	);
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
