import { useEffect, useMemo, useRef } from "react";

export interface FindingCodeWindowDisplayLine {
  lineNumber: number | null;
  content: string;
  kind?: "code" | "placeholder";
  isHighlighted?: boolean;
  isFocus?: boolean;
}

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
}: FindingCodeWindowProps) {
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
      : lineStart ?? null;
  const normalizedHighlightEnd =
    typeof highlightEndLine === "number" && Number.isFinite(highlightEndLine)
      ? highlightEndLine
      : lineEnd ?? normalizedHighlightStart;
  const normalizedFocusLine =
    typeof focusLine === "number" && Number.isFinite(focusLine)
      ? focusLine
      : lineStart ?? null;
  const resolvedDensity = density ?? (variant === "detail" ? "detail" : "compact");
  const isDetail = resolvedDensity === "detail";
  const headerMeta = meta.filter((item) => String(item || "").trim().length > 0);
  const headerBadges = badges.filter((item) => String(item || "").trim().length > 0);
  const showEditorChrome = chrome === "editor";
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
    <section className="overflow-hidden rounded-xl border border-border/70 bg-[linear-gradient(180deg,rgba(15,23,42,0.86),rgba(15,23,42,0.68))] shadow-[0_8px_24px_rgba(0,0,0,0.16)]">
      <div
        className={`border-b border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.03))] ${
          isDetail ? "px-4 py-3" : "px-3 py-2.5"
        }`}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {showEditorChrome ? (
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-300/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
              </div>
            ) : null}
            <div className="min-w-0">
              <div
                className={`truncate font-mono uppercase tracking-[0.22em] text-slate-300 ${
                  isDetail ? "text-[11px]" : "text-[10px]"
                }`}
              >
                {title}
              </div>
              <div
                className={`truncate font-mono text-slate-100 ${
                  isDetail ? "text-[13px]" : "text-[12px]"
                }`}
              >
                {header}
              </div>
            </div>
          </div>

          {headerBadges.length > 0 ? (
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {headerBadges.map((badge) => (
                <span
                  key={badge}
                  className="rounded-md border border-cyan-400/20 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.18em] text-cyan-100"
                >
                  {badge}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        {headerMeta.length > 0 ? (
          <div
            className={`mt-2 flex flex-wrap items-center gap-2 ${
              isDetail ? "text-[11px]" : "text-[10px]"
            }`}
          >
            {headerMeta.map((item) => (
              <span
                key={item}
                className="rounded-md border border-white/8 bg-white/5 px-2 py-0.5 font-mono text-slate-300"
              >
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div
        ref={containerRef}
        className={`${isDetail ? "max-h-[52vh]" : "max-h-[46vh]"} overflow-auto overflow-x-auto bg-[#151922]/85`}
      >
        <div
          className={`min-w-max font-mono ${
            isDetail ? "text-[12.5px] leading-6" : "text-[11.5px] leading-5"
          }`}
        >
          {renderedLines.map((line, index) => {
            const inHighlightRange = Boolean(line.isHighlighted);
            const isFocusLine = Boolean(line.isFocus);
            const isPlaceholder = line.kind === "placeholder" || line.lineNumber === null;

            return (
              <div
                key={`${line.lineNumber ?? `placeholder-${index}`}-${index}`}
                data-line-number={line.lineNumber ?? undefined}
                className={`grid ${isDetail ? "grid-cols-[64px_1fr]" : "grid-cols-[56px_1fr]"} ${
                  inHighlightRange ? "bg-cyan-400/8" : ""
                } ${isFocusLine ? "bg-cyan-400/12" : ""}`}
              >
                <div
                  className={`${isDetail ? "px-3 py-0.5" : "px-2 py-0.5"} select-none text-right font-mono ${
                    isPlaceholder
                      ? "border-r border-white/6 bg-white/[0.02] text-slate-600"
                      : isFocusLine
                        ? "border-r border-cyan-300/30 bg-cyan-400/10 text-cyan-100"
                        : inHighlightRange
                          ? "border-r border-cyan-300/15 bg-cyan-400/5 text-cyan-200/85"
                          : "border-r border-white/6 bg-white/[0.03] text-slate-500"
                  }`}
                >
                  {line.lineNumber ?? ""}
                </div>
                <pre
                  className={`${isDetail ? "px-4 py-0.5" : "px-3 py-0.5"} overflow-visible whitespace-pre ${
                    isPlaceholder ? "italic text-slate-400/80" : "text-slate-100"
                  } ${
                    isFocusLine
                      ? "bg-cyan-400/6"
                      : inHighlightRange
                        ? "bg-cyan-400/[0.03]"
                        : "bg-transparent"
                  }`}
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
