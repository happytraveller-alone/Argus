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
	const [, setSummaryState] = useState<LlmSummaryState | null>(null);

	return (
		<div className="min-h-screen bg-background p-6">
			<div className="max-w-[1680px] mx-auto">
				<SystemConfig
					visibleSections={["llm"]}
					defaultSection="llm"
					mergedView={false}
					cardClassName="cyber-card-flat"
					showLlmSummaryCards={false}
					showFloatingSaveButton={false}
					compactLayout
					sharedDraftState={sharedDraftState}
					onLlmSummaryChange={setSummaryState}
				/>
			</div>
		</div>
	);
}
