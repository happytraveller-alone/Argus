import { api } from "@/shared/api/database";

type PreflightStage = "llm_config" | "llm_test" | "runner";
export type PreflightMissingField = "llmModel" | "llmBaseUrl" | "llmApiKey";
export type AgentPreflightReasonCode =
	| "default_config"
	| "missing_fields"
	| "llm_test_failed"
	| "llm_test_timeout"
	| "llm_test_exception"
	| "llm_test_stale"
	| "unsupported_provider"
	| "request_failed"
	| "empty_response"
	| "runner_missing";

export interface LlmQuickConfigSnapshot {
	provider: string;
	model: string;
	baseUrl: string;
	apiKey?: string;
	hasSavedApiKey?: boolean;
	secretSource?: "saved" | "imported" | "entered" | "none";
}

export interface AgentPreflightResult {
	ok: boolean;
	stage?: PreflightStage;
	message: string;
	reasonCode?: AgentPreflightReasonCode;
	missingFields?: PreflightMissingField[];
	effectiveConfig: LlmQuickConfigSnapshot;
	savedConfig?: LlmQuickConfigSnapshot | null;
	llmTestMetadata?: Record<string, unknown> | null;
}

const EMPTY_QUICK_CONFIG: LlmQuickConfigSnapshot = {
	provider: "openai_compatible",
	model: "",
	baseUrl: "",
	apiKey: "",
};

export async function runAgentPreflightCheck(): Promise<AgentPreflightResult> {
	try {
		const result = await api.runAgentTaskPreflight();
		return {
			ok: Boolean(result.ok),
			stage: result.stage,
			message: String(result.message || ""),
			reasonCode: result.reasonCode,
			missingFields: Array.isArray(result.missingFields)
				? result.missingFields
				: undefined,
			effectiveConfig: result.effectiveConfig || EMPTY_QUICK_CONFIG,
			savedConfig: result.savedConfig ?? null,
			llmTestMetadata: result.llmTestMetadata ?? null,
		};
	} catch (error) {
		const message = error instanceof Error ? error.message : "未知错误";
		return {
			ok: false,
			stage: "llm_test",
			reasonCode: "llm_test_exception",
			message: `智能审计初始化失败：LLM 预检异常（${message}）。`,
			effectiveConfig: EMPTY_QUICK_CONFIG,
			savedConfig: null,
			llmTestMetadata: null,
		};
	}
}
