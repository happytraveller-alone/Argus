import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import { cn } from "@/shared/utils/utils";
import type {
	FindingCodeTokenSegment,
	FindingCodeWindowDisplayLine,
} from "@/shared/code-highlighting/types";

export type { FindingCodeWindowDisplayLine } from "@/shared/code-highlighting/types";

export type FindingCodeWindowAppearance =
  | "native-explorer"
  | "terminal-flat"
  | "dense-ide";

export type FindingCodeWindowDisplayPreset =
  | "default"
  | "project-browser";

interface FindingCodeWindowProps {
  code: string;
  displayLines?: FindingCodeWindowDisplayLine[];
  filePath?: string | null;
  lineStart?: number | null;
  lineEnd?: number | null;
  highlightStartLine?: number | null;
  highlightEndLine?: number | null;
  focusLine?: number | null;
  title?: string;
  density?: "compact" | "detail";
  chrome?: "editor" | "plain";
  badges?: string[];
  meta?: string[];
  variant?: "default" | "detail";
  appearance?: FindingCodeWindowAppearance;
  displayPreset?: FindingCodeWindowDisplayPreset;
}

const TOKEN_CLASS_COLOR_GROUPS: Array<{ names: string[]; className: string }> = [
	{
		names: ["comment", "quote", "meta"],
		className: "text-slate-400",
	},
	{
		names: ["keyword", "selector-tag", "doctag"],
		className: "text-sky-300",
	},
	{
		names: ["string", "regexp", "template-variable"],
		className: "text-emerald-300",
	},
	{
		names: ["number", "literal", "symbol", "bullet"],
		className: "text-amber-300",
	},
	{
		names: ["title", "function", "section", "type", "class"],
		className: "text-cyan-300",
	},
	{
		names: ["attr", "attribute", "property", "variable"],
		className: "text-blue-300",
	},
];

const CODE_FONT_FAMILY =
	'Consolas, "Liberation Mono", Menlo, Monaco, "Courier New", monospace';

function getCodeTypographyStyle(
	isDetail: boolean,
	displayPreset: FindingCodeWindowDisplayPreset,
): CSSProperties {
	if (displayPreset === "project-browser") {
		return {
			fontFamily: CODE_FONT_FAMILY,
			lineHeight: 1.52,
			letterSpacing: "0.012em",
		};
	}
	if (isDetail) {
		return {
			fontFamily: CODE_FONT_FAMILY,
			lineHeight: 1.45,
			letterSpacing: "0.01em",
		};
	}
	return {
		fontFamily: CODE_FONT_FAMILY,
		lineHeight: 1.38,
		letterSpacing: "0.01em",
	};
}

function getLineNumberTypographyStyle(
	isDetail: boolean,
	displayPreset: FindingCodeWindowDisplayPreset,
): CSSProperties {
	if (displayPreset === "project-browser") {
		return {
			fontFamily: CODE_FONT_FAMILY,
			lineHeight: 1.52,
			letterSpacing: "0.01em",
		};
	}
	if (isDetail) {
		return {
			fontFamily: CODE_FONT_FAMILY,
			lineHeight: 1.45,
			letterSpacing: "0.008em",
		};
	}
	return {
		fontFamily: CODE_FONT_FAMILY,
		lineHeight: 1.38,
		letterSpacing: "0.008em",
	};
}

function normalizeTokenClassName(tokenClass: string): string {
	return String(tokenClass || "")
		.trim()
		.replace(/^hljs-/, "");
}

function resolveTokenColorClass(tokenClasses?: string[]): string {
	if (!Array.isArray(tokenClasses) || tokenClasses.length === 0) {
		return "";
	}
	const normalizedClasses = tokenClasses
		.map((tokenClass) => normalizeTokenClassName(tokenClass))
		.filter(Boolean);
	for (const group of TOKEN_CLASS_COLOR_GROUPS) {
		if (
			group.names.some((groupClassName) => normalizedClasses.includes(groupClassName))
		) {
			return group.className;
		}
	}
	return "";
}

function applyLineDecorations(
	lines: FindingCodeWindowDisplayLine[],
	options: {
		focusLine: number | null;
		highlightStartLine: number | null;
		highlightEndLine: number | null;
	},
): FindingCodeWindowDisplayLine[] {
	const normalizedHighlightStart =
		typeof options.highlightStartLine === "number" &&
		Number.isFinite(options.highlightStartLine)
			? options.highlightStartLine
			: null;
	const normalizedHighlightEnd =
		typeof options.highlightEndLine === "number" &&
		Number.isFinite(options.highlightEndLine)
			? options.highlightEndLine
			: normalizedHighlightStart;
	const normalizedFocusLine =
		typeof options.focusLine === "number" && Number.isFinite(options.focusLine)
			? options.focusLine
			: null;

	return lines.map((line) => {
		if (line.lineNumber === null) {
			return line;
		}

		const inHighlightRange =
			normalizedHighlightStart !== null &&
			normalizedHighlightEnd !== null &&
			line.lineNumber >= normalizedHighlightStart &&
			line.lineNumber <= normalizedHighlightEnd;
		const isFocusLine =
			normalizedFocusLine !== null && line.lineNumber === normalizedFocusLine;
		const nextIsHighlighted = Boolean(line.isHighlighted) || inHighlightRange;
		const nextIsFocus = Boolean(line.isFocus) || isFocusLine;

		if (nextIsHighlighted === Boolean(line.isHighlighted) && nextIsFocus === Boolean(line.isFocus)) {
			return line;
		}

		return {
			...line,
			isHighlighted: nextIsHighlighted || undefined,
			isFocus: nextIsFocus || undefined,
		};
	});
}

function renderTokenizedLine(segments: FindingCodeTokenSegment[]) {
	if (!segments.length) return " ";
	return segments.map((segment, index) => {
		const tokenColorClass = resolveTokenColorClass(segment.tokenClasses);
		return (
			<span
				key={`${index}-${segment.text.slice(0, 16)}`}
				className={tokenColorClass || undefined}
			>
				{segment.text}
			</span>
		);
	});
}

function formatHeader(
  filePath?: string | null,
  lineStart?: number | null,
  lineEnd?: number | null,
): string {
  const path = String(filePath || "").trim() || "未定位文件";
  if (
    typeof lineStart === "number" &&
    Number.isFinite(lineStart) &&
    typeof lineEnd === "number" &&
    Number.isFinite(lineEnd) &&
    lineEnd >= lineStart
  ) {
    return `${path}:${lineStart}-${lineEnd}`;
  }
  if (typeof lineStart === "number" && Number.isFinite(lineStart)) {
    return `${path}:${lineStart}`;
  }
  return path;
}

function getShellClasses(appearance: FindingCodeWindowAppearance) {
  if (appearance === "terminal-flat") {
    return "rounded-md border border-white/14 shadow-[0_0_0_1px_rgba(255,255,255,0.04)]";
  }
  if (appearance === "dense-ide") {
    return "rounded-lg border border-white/14 shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_14px_32px_rgba(0,0,0,0.28)]";
  }
  return "rounded-2xl border border-white/14 shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_18px_44px_rgba(0,0,0,0.34)]";
}

function getHeaderClasses(appearance: FindingCodeWindowAppearance, isDetail: boolean) {
  return cn(
    "border-b border-white/8 bg-[#050505]",
    isDetail ? "px-4 py-3" : "px-3 py-2.5",
    appearance === "terminal-flat" && "bg-black",
    appearance === "dense-ide" && "bg-[#080808]",
  );
}

function getViewportClasses(
  appearance: FindingCodeWindowAppearance,
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return cn(
      "min-h-0 flex-1 max-h-none overflow-auto overflow-x-auto custom-scrollbar-dark bg-[#0a0d12]",
      appearance === "dense-ide" && "bg-[#070a10]",
    );
  }

  return cn(
    isDetail ? "max-h-[52vh]" : "max-h-[46vh]",
    "overflow-auto overflow-x-auto custom-scrollbar-dark bg-black",
    appearance === "dense-ide" && "bg-[#040404]",
  );
}

function getGridColumns(
  appearance: FindingCodeWindowAppearance,
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return "grid-cols-[minmax(56px,max-content)_minmax(0,1fr)]";
  }

  if (appearance === "dense-ide") {
    return isDetail ? "grid-cols-[72px_minmax(0,1fr)]" : "grid-cols-[64px_minmax(0,1fr)]";
  }
  if (appearance === "terminal-flat") {
    return isDetail ? "grid-cols-[60px_minmax(0,1fr)]" : "grid-cols-[52px_minmax(0,1fr)]";
  }
  return isDetail ? "grid-cols-[68px_minmax(0,1fr)]" : "grid-cols-[60px_minmax(0,1fr)]";
}

function getHeaderTextClasses(
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return "text-[15px] leading-6";
  }
  return isDetail ? "text-[13px] leading-5" : "text-[12px] leading-5";
}

function getBodyTextClasses(
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return "text-[15px] leading-7";
  }
  return isDetail ? "text-[12.5px] leading-6" : "text-[11.5px] leading-5";
}

function getLineNumberPaddingClasses(
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return "px-2.5 py-0.5";
  }
  return isDetail ? "px-3 py-0.5" : "px-2 py-0.5";
}

function getCodePaddingClasses(
  isDetail: boolean,
  displayPreset: FindingCodeWindowDisplayPreset,
) {
  if (displayPreset === "project-browser") {
    return "px-4 py-0.5";
  }
  return isDetail ? "px-4 py-0.5" : "px-3 py-0.5";
}

export default function FindingCodeWindow({
  code,
  displayLines,
  filePath,
  lineStart,
  lineEnd,
  highlightStartLine,
  highlightEndLine,
  focusLine,
  title = "命中代码",
  density,
  chrome = "editor",
  badges = [],
  meta = [],
  variant = "default",
  appearance = "native-explorer",
  displayPreset = "default",
}: FindingCodeWindowProps) {
  void title;
  void chrome;
  void badges;
  const rawLines = useMemo(
    () => String(code || "").replace(/\r\n/g, "\n").split("\n"),
    [code],
  );
  const firstLine =
    typeof lineStart === "number" && Number.isFinite(lineStart) ? lineStart : 1;
  const header = formatHeader(filePath, lineStart, lineEnd);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const normalizedHighlightStart =
    typeof highlightStartLine === "number" && Number.isFinite(highlightStartLine)
      ? highlightStartLine
      : null;
  const normalizedHighlightEnd =
    typeof highlightEndLine === "number" && Number.isFinite(highlightEndLine)
      ? highlightEndLine
      : normalizedHighlightStart;
  const normalizedFocusLine =
    typeof focusLine === "number" && Number.isFinite(focusLine)
      ? focusLine
      : null;
  const resolvedDensity = density ?? (variant === "detail" ? "detail" : "compact");
  const isDetail = resolvedDensity === "detail";
  const gridColumns = getGridColumns(appearance, isDetail, displayPreset);
  const codeTypographyStyle = getCodeTypographyStyle(isDetail, displayPreset);
  const lineNumberTypographyStyle = getLineNumberTypographyStyle(
    isDetail,
    displayPreset,
  );
  const renderedLines = useMemo(() => {
    const baseLines = (() => {
      if (Array.isArray(displayLines) && displayLines.length > 0) {
        return displayLines;
      }

      return rawLines.map((line, index) => ({
        lineNumber: firstLine + index,
        content: line,
        kind: "code" as const,
      }));
    })();

    return applyLineDecorations(baseLines, {
      focusLine: normalizedFocusLine,
      highlightStartLine: normalizedHighlightStart,
      highlightEndLine: normalizedHighlightEnd,
    });
  }, [
    displayLines,
    firstLine,
    normalizedFocusLine,
    normalizedHighlightEnd,
    normalizedHighlightStart,
    rawLines,
  ]);

  useEffect(() => {
    if (!containerRef.current || !normalizedFocusLine) return;
    const target = containerRef.current.querySelector<HTMLElement>(
      `[data-line-number="${normalizedFocusLine}"]`,
    );
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [displayLines, normalizedFocusLine, code]);

  return (
    <section
      data-appearance={appearance}
      data-display-preset={displayPreset}
      className={cn(
        "overflow-hidden bg-black text-white",
        getShellClasses(appearance),
        displayPreset === "project-browser" && "flex h-full min-h-0 flex-col",
      )}
    >
      <div className={getHeaderClasses(appearance, isDetail)}>
        <div className="flex items-start justify-between gap-3">
          <div
            title={header}
            className={cn(
              "min-w-0 truncate font-mono text-white/78",
              getHeaderTextClasses(isDetail, displayPreset),
            )}
          >
            {header}
          </div>
          {meta.length > 0 ? (
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              {meta.map((metaItem, index) => (
                <span
                  key={`${metaItem}-${index}`}
                  className="rounded-full border border-white/12 bg-white/[0.04] px-2 py-0.5 text-[10px] tracking-[0.08em] text-white/62"
                >
                  {metaItem}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div
        ref={containerRef}
        className={getViewportClasses(appearance, isDetail, displayPreset)}
      >
        <div
          className={cn(
            "min-w-max font-mono",
            getBodyTextClasses(isDetail, displayPreset),
          )}
        >
          {renderedLines.map((line, index) => {
            const inHighlightRange = Boolean(line.isHighlighted);
            const isFocusLine = Boolean(line.isFocus);
            const isPlaceholder = line.kind === "placeholder" || line.lineNumber === null;
            const hasTokenSegments = Array.isArray(line.segments) && line.segments.length > 0;

            return (
              <div
                key={`${line.lineNumber ?? `placeholder-${index}`}-${index}`}
                data-line-number={line.lineNumber ?? undefined}
                className={cn(
                  "grid",
                  gridColumns,
                  isPlaceholder && "bg-white/[0.015]",
                  inHighlightRange && "bg-white/[0.04]",
                  isFocusLine && "bg-white/[0.08]",
                )}
              >
                <div
                  className={cn(
                    getLineNumberPaddingClasses(isDetail, displayPreset),
                    "select-none text-right font-mono tabular-nums border-r border-white/8",
                    isPlaceholder && "bg-white/[0.02] text-white/20",
                    !isPlaceholder &&
                      !inHighlightRange &&
                      !isFocusLine &&
                      "bg-white/[0.03] text-white/42",
                    inHighlightRange && "bg-[#131922] text-white/62",
                    isFocusLine && "bg-[#1a212b] text-white/84",
                  )}
                  style={lineNumberTypographyStyle}
                >
                  {line.lineNumber ?? ""}
                </div>
                <pre
                  className={cn(
                    getCodePaddingClasses(isDetail, displayPreset),
                    "overflow-visible whitespace-pre bg-transparent",
                    isPlaceholder ? "italic text-white/35" : "text-white/92",
                    inHighlightRange && "bg-[#101720] text-white/98",
                    isFocusLine && "bg-[#151d27] font-medium text-white shadow-[inset_3px_0_0_rgba(199,255,106,0.72)]",
                  )}
                  style={codeTypographyStyle}
                >
                  {hasTokenSegments
                    ? renderTokenizedLine(line.segments ?? [])
                    : line.content || " "}
                </pre>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
