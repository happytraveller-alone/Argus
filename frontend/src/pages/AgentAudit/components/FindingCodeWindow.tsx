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
	title?: string;
	density?: string;
	badges?: string[];
	appearance?: FindingCodeWindowAppearance;
	displayPreset?: string;
	className?: string;
}

function normalizeLines({
	lines,
	code,
	lineStart,
}: Pick<
	FindingCodeWindowProps,
	"lines" | "code" | "lineStart"
>): FindingCodeWindowDisplayLine[] {
	if (Array.isArray(lines) && lines.length > 0) return lines;
	const start =
		typeof lineStart === "number" && Number.isFinite(lineStart) ? lineStart : 1;
	return String(code || "")
		.split("\n")
		.map((content, index) => ({
			lineNumber: start + index,
			content,
			kind: "code" as const,
			isHighlighted: false,
			isFocus: false,
		}));
}

function isLineHighlighted(
	line: FindingCodeWindowDisplayLine,
	highlightStartLine?: number | null,
	highlightEndLine?: number | null,
): boolean {
	if (line.isHighlighted) return true;
	if (typeof line.lineNumber !== "number") return false;
	if (
		typeof highlightStartLine !== "number" ||
		typeof highlightEndLine !== "number"
	) {
		return false;
	}
	return line.lineNumber >= highlightStartLine && line.lineNumber <= highlightEndLine;
}

function isLineFocus(
	line: FindingCodeWindowDisplayLine,
	focusLine?: number | null,
): boolean {
	return (
		line.isFocus ||
		(typeof line.lineNumber === "number" && line.lineNumber === focusLine)
	);
}

function getTokenClassName(tokenClasses?: string[]): string {
	const joined = (tokenClasses || []).join(" ");
	if (/\b(hljs-keyword|keyword)\b/.test(joined)) return "text-sky-300";
	if (/\b(number|hljs-number)\b/.test(joined)) return "text-amber-300";
	if (/\b(string|hljs-string)\b/.test(joined)) return "text-emerald-300";
	if (/\b(comment|hljs-comment)\b/.test(joined)) return "text-slate-500";
	return "";
}

function formatFileTitle(
	filePath?: string | null,
	lineStart?: number | null,
	lineEnd?: number | null,
): string {
	const path = String(filePath || "").trim();
	if (!path) return "";
	if (typeof lineStart !== "number" || !Number.isFinite(lineStart)) return path;
	if (
		typeof lineEnd === "number" &&
		Number.isFinite(lineEnd) &&
		lineEnd !== lineStart
	) {
		return `${path}:${lineStart}-${lineEnd}`;
	}
	return `${path}:${lineStart}`;
}

export function shouldAutoScrollToFocusTarget(
	previousTarget: string | null | undefined,
	nextTarget: string | null | undefined,
): boolean {
	const previous = String(previousTarget || "").trim();
	const next = String(nextTarget || "").trim();
	return Boolean(next) && previous !== next;
}

export default function FindingCodeWindow({
	lines,
	displayLines,
	code,
	filePath,
	lineStart,
	lineEnd,
	highlightStartLine,
	highlightEndLine,
	focusLine,
	meta,
	appearance = "native-explorer",
	displayPreset,
	className,
}: FindingCodeWindowProps) {
	const resolvedDisplayLines = normalizeLines({
		lines: lines ?? displayLines,
		code,
		lineStart,
	});
	const fileTitle = formatFileTitle(filePath, lineStart, lineEnd);
	const isProjectBrowser = displayPreset === "project-browser";

	return (
		<div
			data-appearance={appearance}
			data-display-preset={displayPreset}
			className={cn(
				"overflow-hidden rounded-md border border-border/60 bg-slate-950 text-slate-100",
				isProjectBrowser && "flex h-full min-h-0 flex-col",
				className,
			)}
		>
			{(fileTitle || (meta && meta.length > 0)) && (
				<div className="flex items-center justify-between gap-3 border-b border-border/60 px-3 py-2">
					{fileTitle && (
						<div className="truncate text-xs font-medium text-slate-200" title={fileTitle}>
							{fileTitle}
						</div>
					)}
					{meta && meta.length > 0 && (
						<div className="flex shrink-0 flex-wrap items-center gap-1">
							{meta.map((item) => (
								<span
									key={item}
									className="rounded border border-slate-700 px-1.5 py-0.5 text-[11px] text-slate-300"
								>
									{item}
								</span>
							))}
						</div>
					)}
				</div>
			)}
			<div
				className={cn(
					isProjectBrowser
						? "min-h-0 flex-1 max-h-none overflow-auto overflow-x-auto custom-scrollbar-dark"
						: "custom-scrollbar-dark overflow-auto overflow-x-auto max-h-[46vh]",
				)}
			>
				{resolvedDisplayLines.map((line, index) => {
					const highlighted = isLineHighlighted(
						line,
						highlightStartLine,
						highlightEndLine,
					);
					const focused = isLineFocus(line, focusLine);
					const lineClassName = [
						"grid grid-cols-[minmax(56px,max-content)_minmax(0,1fr)] font-mono text-[15px] leading-7",
						highlighted ? "bg-[#101720] bg-white/[0.04]" : "",
						focused ? "bg-[#151d27] bg-white/[0.08]" : "",
						line.kind === "placeholder" ? "text-slate-500" : "",
					]
						.filter(Boolean)
						.join(" ");
					return (
						<div
							key={`${line.lineNumber ?? "placeholder"}-${index}`}
							data-line-number={line.lineNumber ?? undefined}
							className={lineClassName}
						>
							<span className="select-none px-2 text-right text-slate-500">
								{line.lineNumber ?? ""}
							</span>
							<pre className="overflow-x-auto whitespace-pre px-3 text-[15px] leading-6">
								{Array.isArray(line.segments) && line.segments.length > 0
									? line.segments.map((segment, segmentIndex) => {
											const tokenClassName = getTokenClassName(
												segment.tokenClasses,
											);
											return tokenClassName ? (
												<span
													key={`${segment.text}-${segmentIndex}`}
													className={tokenClassName}
												>
													{segment.text}
												</span>
											) : (
												segment.text
											);
										})
									: line.content || " "}
							</pre>
						</div>
					);
				})}
			</div>
		</div>
	);
}
