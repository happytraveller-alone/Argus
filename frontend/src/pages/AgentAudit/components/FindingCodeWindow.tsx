import { useMemo } from "react";

interface FindingCodeWindowProps {
  code: string;
  filePath?: string | null;
  lineStart?: number | null;
  lineEnd?: number | null;
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
  title = "命中代码",
}: FindingCodeWindowProps) {
  const lines = useMemo(() => String(code || "").replace(/\r\n/g, "\n").split("\n"), [code]);
  const firstLine = typeof lineStart === "number" && Number.isFinite(lineStart) ? lineStart : 1;
  const header = formatHeader(filePath, lineStart, lineEnd);

  return (
    <section className="rounded-lg border border-border bg-card/70 overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/40">
        <div className="text-xs font-mono uppercase text-muted-foreground">{title}</div>
        <div className="text-xs text-foreground break-all">{header}</div>
      </div>

      <div className="max-h-[46vh] overflow-auto">
        <div className="min-w-max font-mono text-[12px] leading-6">
          {lines.map((line, index) => {
            const lineNumber = firstLine + index;
            return (
              <div
                key={`${lineNumber}-${index}`}
                className="grid grid-cols-[64px_1fr] border-b border-border/30 last:border-b-0"
              >
                <div className="px-2 py-0.5 text-right text-muted-foreground bg-muted/20 select-none">
                  {lineNumber}
                </div>
                <pre className="px-3 py-0.5 whitespace-pre-wrap break-words text-foreground bg-background/60">
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
