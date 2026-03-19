import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/shared/utils/utils";

export interface FindingCodeWindowDisplayLine {
  lineNumber: number | null;
  content: string;
  kind?: "code" | "placeholder";
  isHighlighted?: boolean;
  isFocus?: boolean;
}

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
  void meta;
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
  const renderedLines = useMemo(() => {
    if (Array.isArray(displayLines) && displayLines.length > 0) {
      return displayLines;
    }

    return rawLines.map((line, index) => {
      const lineNumber = firstLine + index;
      const isHighlighted =
        normalizedHighlightStart !== null &&
        normalizedHighlightEnd !== null &&
        lineNumber >= normalizedHighlightStart &&
        lineNumber <= normalizedHighlightEnd;
      const isFocus = normalizedFocusLine !== null && lineNumber === normalizedFocusLine;
      return {
        lineNumber,
        content: line,
        kind: "code" as const,
        isHighlighted,
        isFocus,
      };
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
        <div
          title={header}
          className={cn(
            "truncate font-mono text-white/78",
            getHeaderTextClasses(isDetail, displayPreset),
          )}
        >
          {header}
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
                >
                  {line.content || " "}
                </pre>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
