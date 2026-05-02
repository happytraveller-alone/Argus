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

function valueText(value: unknown): string {
	if (value === undefined || value === null) return "";
	if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(", ");
	if (typeof value === "object") return JSON.stringify(value);
	return String(value);
}

function lineRange(entry: Record<string, unknown>): string {
	const matchLine = Number(entry.matchLine);
	const startLine = Number(entry.startLine ?? entry.lineNumber);
	const endLine = Number(entry.endLine ?? entry.lineNumber);
	if (Number.isFinite(matchLine)) return `${matchLine}-${matchLine}`;
	if (Number.isFinite(startLine) && Number.isFinite(endLine)) {
		return `${startLine}-${endLine}`;
	}
	if (Number.isFinite(startLine)) return `${startLine}-${startLine}`;
	return "";
}

function entryText(entry: Record<string, unknown>): string {
	const filePath = valueText(entry.filePath ?? entry.file_path);
	const range = lineRange(entry);
	const heading = filePath && range ? `${filePath}:${range}` : filePath;
	const code = objectSource(entry.code);
	const codeLineNumbers = Array.isArray(code?.lines)
		? code.lines
				.map((line) => Number(objectSource(line)?.lineNumber))
				.filter(Number.isFinite)
		: [];
	const codeRange =
		codeLineNumbers.length > 0
			? `${Math.min(...codeLineNumbers)}-${Math.max(...codeLineNumbers)}`
			: "";
	const titledHeading =
		entry.title && codeRange ? `${entry.title}:${codeRange}` : undefined;
	const codeLines = Array.isArray(code?.lines)
		? code.lines
				.map((line) => {
					const lineObject = objectSource(line);
					return valueText(lineObject?.text ?? lineObject?.content ?? entry.matchText);
				})
				.filter(Boolean)
				.join("\n")
		: "";
	const directLines = Array.isArray(entry.lines)
		? entry.lines
				.map((line) => {
					const lineObject = objectSource(line);
					return valueText(lineObject?.text ?? lineObject?.content);
				})
				.filter(Boolean)
				.join("\n")
		: "";
	return [
		heading,
		titledHeading ?? entry.title,
		entry.summary,
		entry.description,
		entry.location,
		codeLines,
		directLines,
		typeof entry.code === "string" ? entry.code : undefined,
		entry.snippet,
		entry.content,
		entry.matchText,
		entry.stdoutPreview,
		entry.stderrPreview,
		entry.function_name,
		entry.resolvedFunction,
		entry.signature,
		entry.purpose,
		entry.fileRole ? `role=${entry.fileRole}` : undefined,
		entry.entrypoints,
		entry.keySymbols,
		entry.keyCalls,
		entry.vulnerabilityType,
		entry.target,
		entry.evidence,
	]
		.filter((value) => value !== undefined && value !== null && String(value).trim())
		.map(valueText)
		.join("\n");
}

function objectSource(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
}

export default function ToolEvidencePreview({ evidence }: ToolEvidencePreviewProps) {
	const payload = payloadOf(evidence);
	const rawEntries = Array.isArray(payload.entries) ? payload.entries : [];
	const entries =
		payload.renderType === "search_hits" ? rawEntries.slice(0, 8) : rawEntries;
	const normalizedEntries =
		payload.renderType === "execution_result"
			? entries.map((entry) => {
					const item = objectSource(entry) ?? {};
					if (String(item.status ?? "").toLowerCase() !== "failed") return item;
					return { ...item, stdoutPreview: undefined };
				})
			: entries;
	const body =
		normalizedEntries.map((entry) => entryText(entry)).filter(Boolean).join("\n\n") ||
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
