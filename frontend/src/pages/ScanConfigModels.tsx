import {
	SystemConfig,
	useSystemConfigDraftState,
} from "@/components/system/SystemConfig";

export default function ScanConfigModels() {
	const sharedDraftState = useSystemConfigDraftState();

	return (
		<div className="min-h-screen bg-background p-6">
			<SystemConfig
				visibleSections={["stageModels"]}
				defaultSection="stageModels"
				mergedView={false}
				cardClassName="cyber-card-flat !bg-transparent !border-0 !shadow-none !p-0"
				showLlmSummaryCards={false}
				showFloatingSaveButton={false}
				showInlineSaveButtons={false}
				compactLayout
				sharedDraftState={sharedDraftState}
			/>
		</div>
	);
}
