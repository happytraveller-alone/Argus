export type ToolEvidenceRenderType =
	| "search_hits"
	| "code_window"
	| "execution_result"
	| "analysis_summary"
	| "outline_summary"
	| "function_summary"
	| "verification_summary"
	| string;

export interface ToolEvidencePayload {
	renderType: ToolEvidenceRenderType;
	displayCommand?: string;
	commandChain?: string[];
	entries?: Array<Record<string, unknown>>;
	[key: string]: unknown;
}

export interface ParsedToolEvidence {
	toolName?: string | null;
	payload: ToolEvidencePayload | null;
	rawOutput?: unknown;
}

function toCamelKey(key: string): string {
	return key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

function normalizeEvidencePayload(source: Record<string, unknown>): ToolEvidencePayload | null {
	const renderType = String(source.render_type || source.renderType || "").trim();
	if (!renderType) return null;

	const payload: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(source)) {
		payload[toCamelKey(key)] = value;
	}
	payload.renderType = renderType;
	if (source.display_command !== undefined) {
		payload.displayCommand = source.display_command;
	}
	if (source.command_chain !== undefined) {
		payload.commandChain = source.command_chain;
	}
	return payload as ToolEvidencePayload;
}

function objectSource(value: unknown): Record<string, unknown> | null {
	return value && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
}

export function parseToolEvidence(params: {
	metadata?: unknown;
	toolOutput?: unknown;
}): ToolEvidencePayload | null {
	const metadata = objectSource(params.metadata);
	const fromMetadata = metadata ? normalizeEvidencePayload(metadata) : null;
	if (fromMetadata) return fromMetadata;

	const output = objectSource(params.toolOutput);
	if (!output) return null;
	const nestedMetadata = objectSource(output.metadata);
	const fromNested = nestedMetadata ? normalizeEvidencePayload(nestedMetadata) : null;
	if (fromNested) return fromNested;
	return normalizeEvidencePayload(output);
}

export function parseToolEvidenceFromLog(params: {
	toolName?: string | null;
	toolOutput?: unknown;
	toolMetadata?: unknown;
}): ParsedToolEvidence | null {
	const payload = parseToolEvidence({
		metadata: params.toolMetadata,
		toolOutput: params.toolOutput,
	});
	if (!payload) return null;
	return {
		toolName: params.toolName,
		payload,
		rawOutput: params.toolOutput,
	};
}
