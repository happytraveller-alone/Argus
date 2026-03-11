import { useMemo } from "react";
import { Navigate, Link, useParams } from "react-router-dom";
import { ArrowLeft, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DEFAULT_MCP_CATALOG } from "@/pages/intelligent-scan/mcpCatalog";
import { SKILL_TOOLS_CATALOG } from "@/pages/intelligent-scan/skillToolsCatalog";

function decodeToolId(rawToolId?: string) {
	if (!rawToolId) return "";
	try {
		return decodeURIComponent(rawToolId);
	} catch {
		return rawToolId;
	}
}

export default function ScanConfigExternalToolDetail() {
	const params = useParams<{ toolType?: string; toolId?: string }>();
	const toolType = params.toolType;
	const toolId = decodeToolId(params.toolId);

	if (toolType !== "mcp" && toolType !== "skill") {
		return <Navigate to="/scan-config/external-tools" replace />;
	}

	const toolName = useMemo(() => {
		if (toolType === "mcp") {
			return (
				DEFAULT_MCP_CATALOG.find((item) => item.id === toolId)?.name ||
				toolId ||
				"外部工具"
			);
		}

		return (
			SKILL_TOOLS_CATALOG.find((item) => item.id === toolId)?.id ||
			toolId ||
			"外部工具"
		);
	}, [toolId, toolType]);

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			<div className="relative z-10 space-y-6">
				<div className="cyber-card p-5 space-y-6">
					<div className="flex flex-wrap items-start justify-between gap-4">
						<div className="space-y-3">
							<div className="section-header mb-1">
								<Wrench className="w-4 h-4 text-primary" />
								<div className="font-mono font-bold uppercase text-sm text-foreground">
									外部工具详情
								</div>
							</div>
							<div className="space-y-2">
								<div className="flex flex-wrap items-center gap-2">
									<div className="text-lg font-mono font-semibold text-foreground break-all">
										{toolName}
									</div>
									<Badge variant="outline" className="text-[10px] uppercase">
										{toolType === "mcp" ? "MCP" : "SKILL"}
									</Badge>
								</div>
								<div className="text-xs font-mono text-muted-foreground break-all">
									{toolId || "-"}
								</div>
							</div>
						</div>

						<Button asChild variant="outline" size="sm" className="cyber-btn-ghost h-8 px-3">
							<Link to="/scan-config/external-tools">
								<ArrowLeft className="w-4 h-4" />
								返回列表
							</Link>
						</Button>
					</div>

					<div className="border-t border-border/50 pt-6 space-y-3">
						<div className="text-[11px] font-mono font-semibold uppercase tracking-[0.28em] text-muted-foreground">
							详情页待设计
						</div>
						<div className="max-w-2xl text-sm leading-7 text-muted-foreground">
							当前页面只保留详情页骨架，后续会在这里补充外部工具说明、执行约束和展示结构。
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
