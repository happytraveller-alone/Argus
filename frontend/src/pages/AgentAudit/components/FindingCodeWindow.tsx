import { useEffect, useMemo, useRef, useState } from "react";
import type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";
import type { PocResult } from "@/shared/api/intelligentTasks";
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
	pocResult?: PocResult | null;
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

function PocResultSection({ pocResult }: { pocResult: PocResult }) {
	const [open, setOpen] = useState(false);
	const output = [pocResult.stdout, pocResult.stderr].filter(Boolean).join("\n").trim();
	return (
		<div className="border-t border-border/60">
			<button
				type="button"
				onClick={() => setOpen((v) => !v)}
				className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-300 hover:bg-white/[0.03]"
			>
				<span className="font-medium">PoC Result</span>
				<span
					className={cn(
						"rounded border px-1.5 py-0.5 text-[11px] font-medium",
						pocResult.reproduced
							? "border-green-700/50 bg-green-900/40 text-green-300"
							: "border-slate-600/50 bg-slate-800/60 text-slate-400",
					)}
				>
					{pocResult.reproduced ? "Reproduced" : "Not Reproduced"}
				</span>
				<span className="ml-auto text-slate-500">{open ? "▲" : "▼"}</span>
			</button>
			{open && output && (
				<pre className="overflow-x-auto whitespace-pre px-3 py-2 font-mono text-[13px] leading-5 text-slate-300 custom-scrollbar-dark">
					{output}
				</pre>
			)}
		</div>
	);
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
	pocResult,
}: FindingCodeWindowProps) {
	const resolvedDisplayLines = normalizeLines({
		lines: lines ?? displayLines,
		code,
		lineStart,
	});
	const fileTitle = formatFileTitle(filePath, lineStart, lineEnd);
	const isProjectBrowser = displayPreset === "project-browser";
	const shellBackgroundClassName = isProjectBrowser
		? "bg-[#050505] text-slate-100"
		: "bg-slate-950 text-slate-100";
	const highlightedLineClassName = isProjectBrowser
		? "bg-[#111111] bg-white/[0.035]"
		: "bg-[#101720] bg-white/[0.04]";
	const focusedLineClassName = isProjectBrowser
		? "bg-[#1a1a1a] bg-white/[0.06]"
		: "bg-[#151d27] bg-white/[0.08]";
	const scrollContainerRef = useRef<HTMLDivElement | null>(null);
	const previousFocusTargetRef = useRef<string | null>(null);
	const focusTarget = useMemo(() => {
		if (typeof focusLine !== "number" || !Number.isFinite(focusLine)) {
			return null;
		}
		return `${fileTitle || String(filePath || "").trim() || "unknown"}::${focusLine}`;
	}, [filePath, fileTitle, focusLine]);

	useEffect(() => {
		if (
			!shouldAutoScrollToFocusTarget(
				previousFocusTargetRef.current,
				focusTarget,
			)
		) {
			previousFocusTargetRef.current = focusTarget;
			return;
		}
		previousFocusTargetRef.current = focusTarget;
		if (typeof focusLine !== "number" || !Number.isFinite(focusLine)) {
			return;
		}
		const container = scrollContainerRef.current;
		const target = container?.querySelector<HTMLElement>(
			`[data-line-number="${focusLine}"]`,
		);
		target?.scrollIntoView({ block: "center", behavior: "smooth" });
	}, [focusLine, focusTarget]);

	return (
		<div
			data-appearance={appearance}
			data-display-preset={displayPreset}
			className={cn(
				"overflow-hidden rounded-md border border-border/60",
				shellBackgroundClassName,
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
				ref={scrollContainerRef}
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
						highlighted ? highlightedLineClassName : "",
						focused ? focusedLineClassName : "",
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
			{pocResult != null && <PocResultSection pocResult={pocResult} />}
		</div>
	);
}
