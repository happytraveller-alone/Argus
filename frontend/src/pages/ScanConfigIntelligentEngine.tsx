import { DataTable, type AppColumnDef } from "@/components/data-table";
import { KeyRound } from "lucide-react";
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

const ENGINE_SUMMARY_GRID_CLASSNAME =
	"grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3";
const ENGINE_SUMMARY_CARD_CLASSNAME =
	"rounded-sm border border-border bg-card text-card-foreground shadow-sm flex min-w-0 items-center justify-between gap-3 px-3 py-3";
const ENGINE_SUMMARY_CARD_LABEL_CLASSNAME =
	"text-sm uppercase tracking-[0.12em] text-muted-foreground";
const ENGINE_SUMMARY_CARD_VALUE_CLASSNAME =
	"min-w-0 break-all text-right text-xl font-semibold tabular-nums text-foreground";

type EngineSummaryCardRow = {
	label: string;
	value: string;
};

const ENGINE_SUMMARY_COLUMNS: AppColumnDef<EngineSummaryCardRow, unknown>[] = [
	{
		accessorKey: "label",
		header: "指标",
		meta: { label: "指标" },
	},
	{
		accessorKey: "value",
		header: "数值",
		meta: { label: "数值" },
	},
];

export default function ScanConfigIntelligentEngine() {
	const sharedDraftState = useSystemConfigDraftState();
	const summaryConfig = sharedDraftState.config;
	const summaryActiveRow = summaryConfig?.llmConfig.rows.find((row) => row.id === summaryConfig.llmConfig.latestPreflightRun.winningRowId) || summaryConfig?.llmConfig.rows.find((row) => row.enabled) || summaryConfig?.llmConfig.rows[0];
	const [summaryState, setSummaryState] = useState<LlmSummaryState | null>(
		null,
	);
	const summary: LlmSummaryState = {
		providerLabel:
			summaryState?.providerLabel || summaryActiveRow?.provider || "--",
		currentModelName:
			summaryState?.currentModelName || summaryActiveRow?.model || "--",
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
	const summaryCards = [
		{
			label: "模型提供商",
			value: summary.providerLabel,
		},
		{
			label: "当前采用模型",
			value: summary.currentModelName || "--",
		},
		{
			label: "支持模型数量",
			value: modelStatsValue,
		},
	];

	return (
		<div className="min-h-screen bg-background p-6">
			<div className="space-y-5 max-w-[1680px] mx-auto">
				<DataTable
					data={summaryCards}
					columns={ENGINE_SUMMARY_COLUMNS}
					toolbar={false}
					pagination={false}
					className="border-0 bg-transparent shadow-none"
					renderMode={({ rows }) => (
						<div className={ENGINE_SUMMARY_GRID_CLASSNAME}>
							{rows.map((item) => (
								<div key={item.label} className={ENGINE_SUMMARY_CARD_CLASSNAME}>
									<div className={ENGINE_SUMMARY_CARD_LABEL_CLASSNAME}>
										{item.label}
									</div>
									<div className={ENGINE_SUMMARY_CARD_VALUE_CLASSNAME}>
										{item.value}
									</div>
								</div>
							))}
						</div>
					)}
				/>

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
						cardClassName="cyber-card-flat"
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
