import type { OpengrepRule } from "@/shared/api/opengrep";
import { stripSupportedArchiveSuffix } from "@/features/projects/services/repoZipScan";
import {
	LLM_PROVIDER_API_KEY_FIELD_MAP,
	normalizeLlmProviderId,
	resolveEffectiveLlmApiKey,
} from "@/shared/llm/providerCatalog";

export const CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP =
	LLM_PROVIDER_API_KEY_FIELD_MAP;

export const normalizeCreateProjectScanProvider = normalizeLlmProviderId;

export const resolveCreateProjectScanEffectiveApiKey = resolveEffectiveLlmApiKey;

export function extractCreateProjectScanApiErrorMessage(error: unknown): string {
	const data = (error as any)?.response?.data;
	if (data && typeof data.error === "string" && data.error.trim()) {
		return data.error;
	}
	if (error instanceof Error) {
		const detail = data?.detail;
		if (typeof detail === "string" && detail.trim()) return detail;
		return error.message || "未知错误";
	}
	const detail = data?.detail;
	if (typeof detail === "string" && detail.trim()) return detail;
	return "未知错误";
}

export function buildCreateProjectScanSystemConfigUpdate(options: {
	currentConfig: { llmConfig?: Record<string, unknown> | null; otherConfig?: Record<string, unknown> | null } | null | undefined;
	nextLlmConfig: Record<string, unknown>;
}) {
	const currentLlmConfig = options.currentConfig?.llmConfig || {};
	if (Array.isArray((currentLlmConfig as { rows?: unknown }).rows)) {
		const rows = ((currentLlmConfig as { rows: Array<Record<string, unknown>> }).rows || []).map((row, index) => {
			if (index !== 0) return row;
			const nextApiKey = typeof options.nextLlmConfig.llmApiKey === "string" ? String(options.nextLlmConfig.llmApiKey).trim() : "";
			return {
				...row,
				provider: options.nextLlmConfig.llmProvider,
				model: options.nextLlmConfig.llmModel,
				baseUrl: options.nextLlmConfig.llmBaseUrl,
				secretSource: options.nextLlmConfig.secretSource,
				...(nextApiKey ? { apiKey: nextApiKey, hasApiKey: true } : {}),
			};
		});
		return {
			llmConfig: {
				...currentLlmConfig,
				rows,
			},
			otherConfig: options.currentConfig?.otherConfig || {},
		};
	}
	return {
		llmConfig: options.nextLlmConfig,
		otherConfig: options.currentConfig?.otherConfig || {},
	};
}

export function isSevereCreateProjectScanRule(rule: OpengrepRule) {
	return String(rule.severity || "").toUpperCase() === "ERROR";
}

export function buildCreateProjectStaticTaskRoute(result: {
	primaryTaskId: string;
	params: URLSearchParams;
}) {
	return `/static-analysis/${result.primaryTaskId}${
		result.params.toString() ? `?${result.params.toString()}` : ""
	}`;
}

export function stripCreateProjectScanArchiveSuffix(fileName: string) {
	return stripSupportedArchiveSuffix(fileName);
}
