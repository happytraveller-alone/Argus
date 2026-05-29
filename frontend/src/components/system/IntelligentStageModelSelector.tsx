import { useState } from "react";
import { Save, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { api } from "@/shared/api/database";
import { ModelCatalog, useModelCatalog } from "@/components/system/ModelCatalog";

const AUDIT_STAGES = [
	{ id: "recon", label: "Recon（侦察）" },
	{ id: "hunt", label: "Hunt（搜寻）" },
	{ id: "validate", label: "Validate（验证）" },
	{ id: "gapfill", label: "Gapfill（补全）" },
	{ id: "dedupe", label: "Dedupe（去重）" },
	{ id: "trace", label: "Trace（追踪）" },
	{ id: "feedback", label: "Feedback（反馈）" },
	{ id: "report", label: "Report（报告）" },
] as const;

export type AuditStageId = (typeof AUDIT_STAGES)[number]["id"];

export interface StageModelAssignment {
	provider: string;
	modelId: string;
}

type StageModelsMap = Partial<Record<AuditStageId, StageModelAssignment>>;

interface Props {
	rawOtherConfig: Record<string, unknown>;
	onSaved?: (nextOtherConfig: Record<string, unknown>) => void;
}

function parseStageModels(raw: unknown): StageModelsMap {
	if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
	const result: StageModelsMap = {};
	for (const stage of AUDIT_STAGES) {
		const entry = (raw as Record<string, unknown>)[stage.id];
		if (entry && typeof entry === "object" && !Array.isArray(entry)) {
			const e = entry as Record<string, unknown>;
			if (typeof e.provider === "string" && typeof e.modelId === "string") {
				result[stage.id] = { provider: e.provider, modelId: e.modelId };
			}
		}
	}
	return result;
}

const NONE_VALUE = "__none__";

export function IntelligentStageModelSelector({ rawOtherConfig, onSaved }: Props) {
	const catalogState = useModelCatalog();
	const initialAssignments = parseStageModels(
		(rawOtherConfig as Record<string, unknown>).intelligentStageModels,
	);
	const [assignments, setAssignments] = useState<StageModelsMap>(initialAssignments);
	const [saving, setSaving] = useState(false);

	const models =
		catalogState.status === "ok" ? catalogState.models : [];

	const handleChange = (stageId: AuditStageId, modelId: string) => {
		setAssignments((prev) => {
			if (modelId === NONE_VALUE) {
				const next = { ...prev };
				delete next[stageId];
				return next;
			}
			const model = models.find((m) => m.id === modelId);
			if (!model) return prev;
			return { ...prev, [stageId]: { provider: model.provider, modelId: model.id } };
		});
	};

	const handleSave = async () => {
		setSaving(true);
		try {
			const nextOtherConfig = {
				...rawOtherConfig,
				intelligentStageModels: assignments,
			};
			await api.updateUserConfig({ otherConfig: nextOtherConfig });
			toast.success("阶段模型配置已保存");
			onSaved?.(nextOtherConfig);
		} catch (err) {
			toast.error(`保存失败: ${err instanceof Error ? err.message : "未知错误"}`);
		} finally {
			setSaving(false);
		}
	};

	return (
		<div className="space-y-6">
			<div className="space-y-1">
				<h3 className="font-mono text-sm font-bold uppercase text-muted-foreground">
					阶段模型分配
				</h3>
				<p className="text-xs text-muted-foreground">
					为每个审计阶段指定使用的 LLM 模型（未指定时使用全局默认配置）
				</p>
			</div>

			<div className="space-y-2">
				{AUDIT_STAGES.map((stage) => {
					const current = assignments[stage.id];
					const currentValue = current?.modelId ?? NONE_VALUE;
					return (
						<div
							key={stage.id}
							className="grid grid-cols-[160px_1fr] gap-4 items-center py-2 border-b border-border/40 last:border-0"
						>
							<span className="font-mono text-xs font-bold uppercase text-foreground/80">
								{stage.label}
							</span>
							<Select
								value={currentValue}
								onValueChange={(v) => handleChange(stage.id, v)}
								disabled={catalogState.status === "loading"}
							>
								<SelectTrigger className="cyber-input h-9 text-xs font-mono">
									<SelectValue placeholder="使用默认模型" />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value={NONE_VALUE} className="font-mono text-xs">
										— 使用默认模型 —
									</SelectItem>
									{models.map((m) => (
										<SelectItem key={m.id} value={m.id} className="font-mono text-xs">
											{m.displayName ?? m.id}
											<span className="ml-2 text-muted-foreground">({m.provider})</span>
										</SelectItem>
									))}
									{catalogState.status !== "ok" && current && (
										<SelectItem value={current.modelId} className="font-mono text-xs">
											{current.modelId}
											<span className="ml-2 text-muted-foreground">({current.provider})</span>
										</SelectItem>
									)}
								</SelectContent>
							</Select>
						</div>
					);
				})}
			</div>

			<div className="border-t border-border pt-4 flex items-start gap-6">
				<div className="flex-1 space-y-2">
					<h4 className="font-mono text-xs font-bold uppercase text-muted-foreground">
						可用模型目录
					</h4>
					<ModelCatalog />
				</div>
				<Button onClick={handleSave} disabled={saving} className="cyber-btn-primary h-9 shrink-0">
					{saving ? (
						<>
							<Loader2 className="h-4 w-4 mr-2 animate-spin" />
							保存中...
						</>
					) : (
						<>
							<Save className="h-4 w-4 mr-2" />
							保存配置
						</>
					)}
				</Button>
			</div>
		</div>
	);
}
