import type { ToolEvidencePayload } from "@/pages/AgentAudit/toolEvidence";
import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";

export interface ToolEvidenceDetailProps {
	toolName?: string | null;
	evidence?: ToolEvidencePayload | null;
	rawOutput?: unknown;
}

export default function ToolEvidenceDetail({
	toolName,
	evidence,
	rawOutput,
}: ToolEvidenceDetailProps) {
	if (!evidence) {
		return null;
	}

	return (
		<div className="space-y-3 rounded border border-border/50 bg-background/40 p-3">
			{toolName ? (
				<div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
					{toolName}
				</div>
			) : null}
			<ToolEvidencePreview evidence={evidence} />
			{rawOutput !== undefined ? (
				<pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-3 text-xs text-muted-foreground">
					{typeof rawOutput === "string"
						? rawOutput
						: JSON.stringify(rawOutput, null, 2)}
				</pre>
			) : null}
		</div>
	);
}
