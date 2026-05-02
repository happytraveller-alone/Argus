import type { FindingNarrativeInput } from "@/pages/AgentAudit/components/findingNarrative";
import { cn } from "@/shared/utils/utils";

export interface FindingNarrativeMarkdownProps {
	finding: FindingNarrativeInput;
	variant?: "detail" | "compact";
	className?: string;
}

function resolveNarrativeText(finding: FindingNarrativeInput): string {
	return (
		String(finding.description_markdown || "").trim() ||
		String(finding.report || "").trim() ||
		String(finding.verification_evidence || "").trim() ||
		String(finding.description || "").trim() ||
		String(finding.suggestion || "").trim() ||
		"-"
	);
}

export default function FindingNarrativeMarkdown({
	finding,
	variant = "detail",
	className,
}: FindingNarrativeMarkdownProps) {
	return (
		<div
			data-variant={variant}
			className={cn(
				"whitespace-pre-wrap break-words text-sm leading-7 text-foreground/90",
				className,
			)}
		>
			{resolveNarrativeText(finding)}
		</div>
	);
}
