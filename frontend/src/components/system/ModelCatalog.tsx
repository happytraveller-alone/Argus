import { useEffect, useState } from "react";
import { api } from "@/shared/api/database";
import { AlertCircle, Brain, Loader2 } from "lucide-react";

interface CatalogModel {
	id: string;
	provider: string;
	displayName?: string;
	costPer1kInputTokens?: number | null;
	costPer1kOutputTokens?: number | null;
	contextWindow?: number | null;
	supportsThinking?: boolean;
}

type CatalogState =
	| { status: "loading" }
	| { status: "ok"; models: CatalogModel[] }
	| { status: "unavailable"; reason: "sidecar_unconfigured" | "sidecar_unreachable" | "unknown" };

export function useModelCatalog(): CatalogState {
	const [state, setState] = useState<CatalogState>({ status: "loading" });

	useEffect(() => {
		let cancelled = false;
		void (async () => {
			try {
				const data = await api.getModelCatalog();
				if (!cancelled) setState({ status: "ok", models: data.models });
			} catch (err: unknown) {
				if (cancelled) return;
				const anyErr = err as { response?: { status?: number; data?: { error?: string } } };
				const errCode = anyErr?.response?.data?.error;
				if (errCode === "sidecar_unconfigured" || errCode === "sidecar_unreachable") {
					setState({ status: "unavailable", reason: errCode });
				} else {
					setState({ status: "unavailable", reason: "unknown" });
				}
			}
		})();
		return () => { cancelled = true; };
	}, []);

	return state;
}

interface ModelCatalogProps {
	className?: string;
}

export function ModelCatalog({ className }: ModelCatalogProps) {
	const state = useModelCatalog();

	if (state.status === "loading") {
		return (
			<div className={`flex items-center gap-2 py-4 text-muted-foreground ${className ?? ""}`}>
				<Loader2 className="h-4 w-4 animate-spin" />
				<span className="text-xs font-mono">加载模型目录中...</span>
			</div>
		);
	}

	if (state.status === "unavailable") {
		const msg =
			state.reason === "sidecar_unconfigured"
				? "Agent Engine 未配置，模型目录不可用"
				: state.reason === "sidecar_unreachable"
					? "Agent Engine 未运行，模型目录不可用"
					: "模型目录暂时不可用";
		return (
			<div className={`flex items-center gap-2 py-3 text-amber-400 ${className ?? ""}`}>
				<AlertCircle className="h-4 w-4 shrink-0" />
				<span className="text-xs font-mono">{msg}</span>
			</div>
		);
	}

	const { models } = state;

	if (models.length === 0) {
		return (
			<div className={`py-3 text-xs text-muted-foreground font-mono ${className ?? ""}`}>
				模型目录为空
			</div>
		);
	}

	return (
		<div className={`space-y-2 ${className ?? ""}`}>
			<div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 gap-y-0 items-center border-b border-border pb-1 mb-1">
				<span className="text-[11px] font-bold uppercase text-muted-foreground font-mono">模型</span>
				<span className="text-[11px] font-bold uppercase text-muted-foreground font-mono text-right">提供商</span>
				<span className="text-[11px] font-bold uppercase text-muted-foreground font-mono text-right">输入价格/1K</span>
				<span className="text-[11px] font-bold uppercase text-muted-foreground font-mono text-right">输出价格/1K</span>
				<span className="text-[11px] font-bold uppercase text-muted-foreground font-mono text-right">上下文窗口</span>
			</div>
			{models.map((m) => (
				<div
					key={m.id}
					className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-x-4 items-center py-1.5 border-b border-border/40 last:border-0"
				>
					<div className="flex items-center gap-1.5 min-w-0">
						<span className="font-mono text-xs text-foreground truncate">{m.displayName ?? m.id}</span>
						{m.supportsThinking && (
							<span title="支持 Thinking 模式">
								<Brain className="h-3 w-3 text-violet-400 shrink-0" />
							</span>
						)}
					</div>
					<span className="font-mono text-xs text-muted-foreground text-right">{m.provider}</span>
					<span className="font-mono text-xs text-muted-foreground text-right">
						{m.costPer1kInputTokens != null ? `$${m.costPer1kInputTokens.toFixed(4)}` : "-"}
					</span>
					<span className="font-mono text-xs text-muted-foreground text-right">
						{m.costPer1kOutputTokens != null ? `$${m.costPer1kOutputTokens.toFixed(4)}` : "-"}
					</span>
					<span className="font-mono text-xs text-muted-foreground text-right">
						{m.contextWindow != null ? `${(m.contextWindow / 1000).toFixed(0)}K` : "-"}
					</span>
				</div>
			))}
		</div>
	);
}
