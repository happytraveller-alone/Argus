export interface FindingCodeTokenSegment {
	text: string;
	tokenClasses?: string[];
}

export interface FindingCodeWindowDisplayLine {
	lineNumber: number | null;
	content: string;
	kind?: "code" | "placeholder";
	isHighlighted?: boolean;
	isFocus?: boolean;
	segments?: FindingCodeTokenSegment[];
}

export type CodeHighlightFallbackReason =
	| "path-not-supported"
	| "content-too-large"
	| "line-count-too-large"
	| "engine-load-failed"
	| "tokenize-failed";

export interface CodeHighlightResult {
	lines: FindingCodeWindowDisplayLine[];
	languageKey: string | null;
	languageLabel: string | null;
	status: "highlighted" | "plain-text";
	fallbackReason: CodeHighlightFallbackReason | null;
}
