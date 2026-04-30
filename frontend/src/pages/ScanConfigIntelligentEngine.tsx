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
			<SystemConfig
				visibleSections={["llm"]}
				defaultSection="llm"
				mergedView={false}
				cardClassName="cyber-card-flat !bg-transparent !border-0 !shadow-none !p-0"
				showLlmSummaryCards={false}
				showFloatingSaveButton={false}
				showInlineSaveButtons={false}
				compactLayout
				sharedDraftState={sharedDraftState}
				onLlmSummaryChange={setSummaryState}
			/>
		</div>
	);
}
