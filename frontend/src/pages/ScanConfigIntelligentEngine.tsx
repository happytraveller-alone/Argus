import { Brain, KeyRound, Settings, Zap } from "lucide-react";
import { useState } from "react";
import type {
	LlmModelStatsSource,
	LlmModelStatsStatus,
} from "@/components/system/llmModelStatsSummary";
import {
	SystemConfig,
	useSystemConfigDraftState,
} from "@/components/system/SystemConfig";

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
	const [summaryState, setSummaryState] = useState<LlmSummaryState | null>(
		null,
	);
	const summary: LlmSummaryState = {
		providerLabel:
			summaryState?.providerLabel || summaryConfig?.llmProvider || "--",
		currentModelName:
			summaryState?.currentModelName || summaryConfig?.llmModel || "--",
		availableModelCount: summaryState?.availableModelCount ?? 0,
		availableModelMetadataCount: summaryState?.availableModelMetadataCount ?? 0,
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
				: `${summary.availableModelCount}`;

	return (
		<div className="min-h-screen bg-background p-6">
			<div className="space-y-5 max-w-[1680px] mx-auto">
				<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
					<div className="rounded-sm border border-border bg-card px-4 py-4 text-card-foreground shadow-sm">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-sm font-semibold uppercase tracking-[0.1em] text-muted-foreground">
									模型提供商
								</p>
								<p className="mt-2 break-all text-2xl font-semibold text-foreground">
									{summary.providerLabel}
								</p>
							</div>
							<div className="flex h-14 w-14 items-center justify-center rounded-sm border border-border bg-muted/40 text-primary">
								<Settings className="w-6 h-6" />
							</div>
						</div>
					</div>

					<div className="rounded-sm border border-border bg-card px-4 py-4 text-card-foreground shadow-sm">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-sm font-semibold uppercase tracking-[0.1em] text-muted-foreground">
									当前采用模型
								</p>
								<p className="mt-2 break-all text-2xl font-semibold text-foreground">
									{summary.currentModelName || "--"}
								</p>
							</div>
							<div className="flex h-14 w-14 items-center justify-center rounded-sm border border-border bg-muted/40 text-sky-500">
								<Brain className="w-6 h-6" />
							</div>
						</div>
					</div>

					<div className="rounded-sm border border-border bg-card px-4 py-4 text-card-foreground shadow-sm">
						<div className="flex items-center justify-between">
							<div>
								<p className="text-sm font-semibold uppercase tracking-[0.1em] text-muted-foreground">
									支持模型数量
								</p>
								<p className="mt-2 break-all text-2xl font-semibold text-foreground">
									{modelStatsValue}
								</p>
							</div>
							<div className="flex h-14 w-14 items-center justify-center rounded-sm border border-border bg-muted/40 text-emerald-500">
								<Zap className="w-6 h-6" />
							</div>
						</div>
					</div>
				</div>

				<div className="space-y-4">
					<div className="mb-0 flex items-center gap-3 border-b border-border pb-3">
						<KeyRound className="w-4 h-4 text-primary" />
						<div className="font-mono font-bold uppercase text-sm text-foreground">
							推理模块
						</div>
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
			</div>
		</div>
	);
}
