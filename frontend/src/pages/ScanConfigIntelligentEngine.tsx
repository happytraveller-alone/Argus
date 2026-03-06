import { KeyRound, Zap } from "lucide-react";
import { SystemConfig } from "@/components/system/SystemConfig";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";

export default function ScanConfigIntelligentEngine() {
	return (
		<div className="space-y-6 p-6 bg-background min-h-screen relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="relative z-10 space-y-4">
				<SystemConfig
					visibleSections={["llm"]}
					defaultSection="llm"
					mergedView={false}
					llmSummaryOnly
					showFloatingSaveButton={false}
					compactLayout
				/>

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
