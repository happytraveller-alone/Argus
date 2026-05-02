export interface FindingNarrativeInput {
	title?: string | null;
	description?: string | null;
	description_markdown?: string | null;
	verification_evidence?: string | null;
	report?: string | null;
	suggestion?: string | null;
	[key: string]: unknown;
}
