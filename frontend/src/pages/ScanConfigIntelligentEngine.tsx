import { useState } from "react";
import { Brain, KeyRound, Settings, Zap } from "lucide-react";
import { SystemConfig, useSystemConfigDraftState } from "@/components/system/SystemConfig";
import type { LlmModelStatsSource, LlmModelStatsStatus } from "@/components/system/llmModelStatsSummary";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";

type LlmSummaryState = {
	providerLabel: string;
	currentModelName: string;
	availableModelCount: number;
	availableModelMetadataCount: number;
	supportsModelFetch: boolean;
	modelStatsStatus: LlmModelStatsStatus;
	modelStatsSource: LlmModelStatsSource;
	shouldPreferOnlineStats: boolean;
};

export default function ScanConfigIntelligentEngine() {
	const sharedDraftState = useSystemConfigDraftState();
	const summaryConfig = sharedDraftState.config;
	const [summaryState, setSummaryState] = useState<LlmSummaryState | null>(null);
	const summary: LlmSummaryState = {
		providerLabel: summaryState?.providerLabel || summaryConfig?.llmProvider || "--",
		currentModelName:
			summaryState?.currentModelName || summaryConfig?.llmModel || "--",
		availableModelCount: summaryState?.availableModelCount ?? 0,
		availableModelMetadataCount:
			summaryState?.availableModelMetadataCount ?? 0,
		supportsModelFetch: summaryState?.supportsModelFetch || false,
		modelStatsStatus: summaryState?.modelStatsStatus || "static",
		modelStatsSource: summaryState?.modelStatsSource || "static",
		shouldPreferOnlineStats: summaryState?.shouldPreferOnlineStats || false,
	};

	const modelStatsValue =
		summary.modelStatsStatus === "loading"
			? "加载中..."
			: summary.modelStatsStatus === "empty"
				? "--"
				: `${summary.availableModelCount} 个模型`;

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="relative z-10 space-y-4">
				<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
					<div className="cyber-card p-4">
						<div className="flex items-center justify-between">
							<div>
								<p className="stat-label">模型提供商</p>
								<p className="stat-value text-2xl break-all">
									{summary.providerLabel}
								</p>
								<p className="text-sm text-muted-foreground mt-1">
									{summary.supportsModelFetch ? "支持在线拉取" : "静态模型列表"}
								</p>
							</div>
							<div className="stat-icon text-primary">
								<Settings className="w-6 h-6" />
							</div>
						</div>
					</div>

					<div className="cyber-card p-4">
						<div className="flex items-center justify-between">
							<div>
								<p className="stat-label">当前采用模型</p>
								<p className="stat-value text-2xl break-all">
									{summary.currentModelName || "--"}
								</p>
							</div>
							<div className="stat-icon text-sky-400">
								<Brain className="w-6 h-6" />
							</div>
						</div>
					</div>

					<div className="cyber-card p-4">
						<div className="flex items-center justify-between">
							<div>
								<p className="stat-label">模型统计</p>
								<p className="stat-value">{modelStatsValue}</p>
							</div>
							<div className="stat-icon text-emerald-400">
								<Zap className="w-6 h-6" />
							</div>
						</div>
					</div>
				</div>

				<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
					<div className="cyber-card p-4 space-y-2">
						<div className="section-header mb-0">
							<KeyRound className="w-4 h-4 text-primary" />
							<div className="font-mono font-bold uppercase text-sm text-foreground">
								推理模块
							</div>
						</div>
						<div className="text-xs text-muted-foreground">
							配置模型参数、请求预算和超时策略。
						</div>
						<SystemConfig
							visibleSections={["llm"]}
							defaultSection="llm"
							mergedView={false}
							showLlmSummaryCards={false}
							showFloatingSaveButton={false}
							compactLayout
							sharedDraftState={sharedDraftState}
							onLlmSummaryChange={setSummaryState}
						/>
					</div>

					<div className="cyber-card p-4 space-y-2">
						<div className="section-header mb-0">
							<Zap className="w-4 h-4 text-primary" />
							<div className="font-mono font-bold uppercase text-sm text-foreground">
								搜索增强模块
							</div>
						</div>
						<EmbeddingConfig compact />
					</div>
				</div>
			</div>
		</div>
	);
}
