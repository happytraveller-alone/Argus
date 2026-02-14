import { api } from "@/shared/config/database";

type PreflightStage = "llm_config" | "llm_test";

export interface AgentPreflightResult {
	ok: boolean;
	stage?: PreflightStage;
	message: string;
}

const normalizeProvider = (provider: string | undefined | null) =>
	(provider || "").trim().toLowerCase();

export async function runAgentPreflightCheck(): Promise<AgentPreflightResult> {
	const userConfig = await api.getUserConfig();
	const llmConfig = userConfig?.llmConfig || {};

	const llmProvider = normalizeProvider(llmConfig.llmProvider) || "openai";
	const llmApiKey = (llmConfig.llmApiKey || "").trim();
	const llmModel = (llmConfig.llmModel || "").trim();
	const llmBaseUrl = (llmConfig.llmBaseUrl || "").trim();

	if (llmProvider !== "ollama" && !llmApiKey) {
		return {
			ok: false,
			stage: "llm_config",
			message:
				"智能审计初始化失败：LLM 未配置 API Key，请先在系统配置中完成 LLM 配置并测试。",
		};
	}

	try {
		const llmResult = await api.testLLMConnection({
			provider: llmProvider,
			apiKey: llmApiKey,
			model: llmModel || undefined,
			baseUrl: llmBaseUrl || undefined,
		});

		if (!llmResult.success) {
			return {
				ok: false,
				stage: "llm_test",
				message: `智能审计初始化失败：LLM 测试未通过（${llmResult.message || "未知错误"}）。`,
			};
		}
	} catch (error) {
		const message = error instanceof Error ? error.message : "未知错误";
		return {
			ok: false,
			stage: "llm_test",
			message: `智能审计初始化失败：LLM 测试异常（${message}）。`,
		};
	}

	return {
		ok: true,
		message: "LLM 配置测试通过（RAG 可选，未检查）。",
	};
}
