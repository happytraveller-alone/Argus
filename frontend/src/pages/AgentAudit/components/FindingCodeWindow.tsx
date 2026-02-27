import { useEffect, useMemo, useRef } from "react";

interface FindingCodeWindowProps {
  code: string;
  filePath?: string | null;
  lineStart?: number | null;
  lineEnd?: number | null;
  highlightStartLine?: number | null;
  highlightEndLine?: number | null;
  focusLine?: number | null;
  title?: string;
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
  filePath,
  lineStart,
  lineEnd,
  highlightStartLine,
  highlightEndLine,
  focusLine,
  title = "命中代码",
}: FindingCodeWindowProps) {
  const lines = useMemo(() => String(code || "").replace(/\r\n/g, "\n").split("\n"), [code]);
  const firstLine = typeof lineStart === "number" && Number.isFinite(lineStart) ? lineStart : 1;
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

  useEffect(() => {
    if (!containerRef.current || !normalizedFocusLine) return;
    const target = containerRef.current.querySelector<HTMLElement>(
      `[data-line-number="${normalizedFocusLine}"]`,
    );
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [normalizedFocusLine, code]);

  return (
    <section className="rounded-lg border border-border bg-card/70 overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/40">
        <div className="text-xs font-mono uppercase text-muted-foreground">{title}</div>
        <div className="text-xs text-foreground break-all">{header}</div>
      </div>

      <div ref={containerRef} className="max-h-[46vh] overflow-auto">
        <div className="min-w-max font-mono text-[12px] leading-6">
          {lines.map((line, index) => {
            const lineNumber = firstLine + index;
            const inHighlightRange =
              normalizedHighlightStart !== null &&
              normalizedHighlightEnd !== null &&
              lineNumber >= normalizedHighlightStart &&
              lineNumber <= normalizedHighlightEnd;
            const isFocusLine = normalizedFocusLine !== null && lineNumber === normalizedFocusLine;
            return (
              <div
                key={`${lineNumber}-${index}`}
                data-line-number={lineNumber}
                className={`grid grid-cols-[64px_1fr] border-b border-border/30 last:border-b-0 ${
                  inHighlightRange ? "bg-orange-500/10" : ""
                } ${isFocusLine ? "ring-1 ring-red-500/60 ring-inset" : ""}`}
              >
                <div
                  className={`px-2 py-0.5 text-right text-muted-foreground select-none ${
                    isFocusLine
                      ? "bg-red-500/15 text-red-700 dark:text-red-200"
                      : inHighlightRange
                        ? "bg-orange-500/15 text-orange-700 dark:text-orange-200"
                        : "bg-muted/20"
                  }`}
                >
                  {lineNumber}
                </div>
                <pre
                  className={`px-3 py-0.5 whitespace-pre-wrap break-words text-foreground ${
                    isFocusLine
                      ? "bg-red-500/10"
                      : inHighlightRange
                        ? "bg-orange-500/5"
                        : "bg-background/60"
                  }`}
                >
                  {line || " "}
                </pre>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
