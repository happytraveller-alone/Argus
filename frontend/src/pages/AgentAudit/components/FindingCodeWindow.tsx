import type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";
import { cn } from "@/shared/utils/utils";

export type { FindingCodeWindowDisplayLine };

export type FindingCodeWindowAppearance =
	| "default"
	| "terminal-flat"
	| "dense-ide"
	| "native-explorer";

export interface FindingCodeWindowProps {
	lines?: FindingCodeWindowDisplayLine[];
	displayLines?: FindingCodeWindowDisplayLine[];
	code?: string | null;
	filePath?: string | null;
	lineStart?: number | null;
	lineEnd?: number | null;
	highlightStartLine?: number | null;
	highlightEndLine?: number | null;
	focusLine?: number | null;
	meta?: string[];
	variant?: string;
	appearance?: FindingCodeWindowAppearance;
	displayPreset?: string;
	className?: string;
}

function normalizeLines({
	lines,
	code,
	lineStart,
}: Pick<FindingCodeWindowProps, "lines" | "code" | "lineStart">) {
	if (Array.isArray(lines) && lines.length > 0) return lines;
	const start =
		typeof lineStart === "number" && Number.isFinite(lineStart) ? lineStart : 1;
	return String(code || "")
		.split("\n")
		.map((content, index) => ({
			lineNumber: start + index,
			content,
			kind: "code" as const,
		}));
}

export default function FindingCodeWindow({
	lines,
	displayLines,
	code,
	lineStart,
	appearance = "default",
	className,
}: FindingCodeWindowProps) {
	const resolvedDisplayLines = normalizeLines({
		lines: lines ?? displayLines,
		code,
		lineStart,
	});

	return (
		<div
			data-appearance={appearance}
			className={cn(
				"overflow-hidden rounded-md border border-border/60 bg-slate-950 text-slate-100",
				className,
			)}
		>
			{resolvedDisplayLines.map((line, index) => (
				<div
					key={`${line.lineNumber ?? "placeholder"}-${index}`}
					className={cn(
						"grid grid-cols-[48px_minmax(0,1fr)] font-mono text-xs leading-6",
						line.isHighlighted && "bg-red-950/40",
						line.isFocus && "bg-red-950/70",
						line.kind === "placeholder" && "text-slate-500",
					)}
				>
					<span className="select-none px-2 text-right text-slate-500">
						{line.lineNumber ?? ""}
					</span>
					<pre className="overflow-x-auto whitespace-pre px-3">
						{line.content || " "}
					</pre>
				</div>
			))}
		</div>
	);
}
