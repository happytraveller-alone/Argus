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

const VALIDATION_STATUS_STYLES: Record<string, string> = {
	confirmed: "bg-green-900/40 text-green-300 border-green-700/50",
	rejected: "bg-red-900/40 text-red-300 border-red-700/50",
	needs_more_info: "bg-yellow-900/40 text-yellow-300 border-yellow-700/50",
};

function ValidationBadge({ status }: { status: string }) {
	const style =
		VALIDATION_STATUS_STYLES[status] ??
		"bg-slate-800/60 text-slate-300 border-slate-600/50";
	return (
		<span
			className={cn(
				"inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium",
				style,
			)}
		>
			{status}
		</span>
	);
}

export default function FindingNarrativeMarkdown({
	finding,
	variant = "detail",
	className,
}: FindingNarrativeMarkdownProps) {
	const validationStatus =
		typeof finding.validationStatus === "string"
			? finding.validationStatus
			: null;
	const reachable =
		typeof finding.reachable === "boolean" ? finding.reachable : null;
	const traceSummary =
		typeof finding.traceSummary === "string" && finding.traceSummary.trim()
			? finding.traceSummary.trim()
			: null;

	const hasMetadata =
		validationStatus !== null || reachable !== null || traceSummary !== null;

	return (
		<div
			data-variant={variant}
			className={cn("flex flex-col gap-2", className)}
		>
			{hasMetadata && (
				<div className="flex flex-wrap items-center gap-2 text-sm">
					{validationStatus !== null && (
						<ValidationBadge status={validationStatus} />
					)}
					{reachable !== null && (
						<span
							className={cn(
								"inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium",
								reachable
									? "border-green-700/50 bg-green-900/40 text-green-300"
									: "border-slate-600/50 bg-slate-800/60 text-slate-400",
							)}
						>
							{reachable ? "✓" : "✗"} Reachable
						</span>
					)}
				</div>
			)}
			<div className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground/90">
				{resolveNarrativeText(finding)}
			</div>
			{traceSummary !== null && (
				<blockquote className="border-l-2 border-slate-600 pl-3 text-sm italic text-slate-400">
					{traceSummary}
				</blockquote>
			)}
		</div>
	);
}
