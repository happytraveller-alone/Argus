import type { ParsedToolEvidence, ToolEvidencePayload } from "@/pages/AgentAudit/toolEvidence";

export interface ToolEvidencePreviewProps {
	evidence: ParsedToolEvidence | ToolEvidencePayload;
}

function isParsedEvidence(
	evidence: ParsedToolEvidence | ToolEvidencePayload,
): evidence is ParsedToolEvidence {
	return Object.prototype.hasOwnProperty.call(evidence, "payload");
}

function payloadOf(evidence: ParsedToolEvidence | ToolEvidencePayload): ToolEvidencePayload {
	if (isParsedEvidence(evidence)) {
		return evidence.payload ?? { renderType: "unknown" };
	}
	return evidence;
}

function entryText(entry: Record<string, unknown>): string {
	return [
		entry.title,
		entry.summary,
		entry.file_path,
		entry.filePath,
		entry.location,
		entry.code,
		entry.snippet,
		entry.content,
		entry.function_name,
		entry.signature,
	]
		.filter((value) => value !== undefined && value !== null && String(value).trim())
		.map(String)
		.join("\n");
}

export default function ToolEvidencePreview({ evidence }: ToolEvidencePreviewProps) {
	const payload = payloadOf(evidence);
	const entries = Array.isArray(payload.entries) ? payload.entries : [];
	const body =
		entries.map((entry) => entryText(entry)).filter(Boolean).join("\n\n") ||
		String(payload.summary || payload.displayCommand || payload.renderType || "").trim();

	return (
		<div
			data-appearance="native-explorer"
			className="rounded border border-border/50 bg-black/30 p-3 text-xs font-mono text-foreground/80"
		>
			<pre className="whitespace-pre-wrap break-words">{body || "-"}</pre>
		</div>
	);
}
