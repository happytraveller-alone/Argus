import type { OpengrepRule } from "@/shared/api/opengrep";
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
	if (error instanceof Error) {
		const detail = (error as any)?.response?.data?.detail;
		if (typeof detail === "string" && detail.trim()) return detail;
		return error.message || "未知错误";
	}
	const detail = (error as any)?.response?.data?.detail;
	if (typeof detail === "string" && detail.trim()) return detail;
	return "未知错误";
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
	return fileName.replace(
		/\.(tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|zip|tar|7z|rar)$/i,
		"",
	);
}

export function buildHybridStaticBootstrapConfig(params: {
	opengrepEnabled: boolean;
	banditEnabled: boolean;
	gitleaksEnabled: boolean;
	phpstanEnabled: boolean;
	pmdEnabled: boolean;
}) {
	return {
		mode: "embedded" as const,
		opengrep_enabled: params.opengrepEnabled,
		bandit_enabled: params.banditEnabled,
		gitleaks_enabled: params.gitleaksEnabled,
		phpstan_enabled: params.phpstanEnabled,
		pmd_enabled: params.pmdEnabled,
	};
}
