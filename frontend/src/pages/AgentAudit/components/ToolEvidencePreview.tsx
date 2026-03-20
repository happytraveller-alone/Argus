import FindingCodeWindow from "./FindingCodeWindow";
import type { ToolEvidencePayload } from "../toolEvidence";
import { toolEvidenceLinesToCode } from "../toolEvidence";

function statusLabel(status: "passed" | "failed" | "error") {
  if (status === "passed") return "执行成功";
  if (status === "failed") return "执行失败";
  return "执行错误";
}

export default function ToolEvidencePreview({
  evidence,
}: {
  evidence: ToolEvidencePayload;
}) {
  if (evidence.renderType === "search_hits") {
    const first = evidence.entries[0];
    if (!first) return null;

    return (
      <FindingCodeWindow
        code={first.matchText || "命中代码"}
        filePath={first.filePath}
        lineStart={first.matchLine}
        lineEnd={first.matchLine}
        highlightStartLine={first.matchLine}
        highlightEndLine={first.matchLine}
        focusLine={first.matchLine}
        title="命中定位"
        density="compact"
        badges={[evidence.displayCommand, "命中"]}
        meta={[
          `${first.filePath}:${first.matchLine}${first.column ? `:${first.column}` : ""}`,
          `${evidence.entries.length} 条命中`,
          first.symbolName || "",
        ]}
      />
    );
  }

  if (evidence.renderType === "outline_summary") {
    const first = evidence.entries[0];
    if (!first) return null;

    return (
      <FindingCodeWindow
        code={[
          `角色: ${first.fileRole || "unknown"}`,
          `关键符号: ${first.keySymbols.join(", ") || "无"}`,
          `入口点: ${first.entrypoints.join(", ") || "无"}`,
          `风险标记: ${first.riskMarkers.join(", ") || "无"}`,
        ].join("\n")}
        filePath={first.filePath}
        lineStart={1}
        lineEnd={4}
        focusLine={1}
        title="文件概览"
        density="compact"
        badges={[evidence.displayCommand, "outline"]}
      />
    );
  }

  if (evidence.renderType === "function_summary") {
    const first = evidence.entries[0];
    if (!first) return null;

    return (
      <FindingCodeWindow
        code={[
          `签名: ${first.signature || "未知"}`,
          `职责: ${first.purpose || "未提供"}`,
          `关键调用: ${first.keyCalls.join(", ") || "无"}`,
          `风险点: ${first.riskPoints.join(", ") || "无"}`,
        ].join("\n")}
        filePath={first.filePath}
        lineStart={1}
        lineEnd={4}
        focusLine={1}
        title={first.resolvedFunction || "函数摘要"}
        density="compact"
        badges={[evidence.displayCommand, "summary"]}
      />
    );
  }

  if (evidence.renderType === "execution_result") {
    const first = evidence.entries[0];
    if (!first) return null;

    if (first.code) {
      return (
        <FindingCodeWindow
          code={toolEvidenceLinesToCode(first.code.lines)}
          filePath={first.title || "inline-harness"}
          lineStart={first.code.lines[0]?.lineNumber ?? 1}
          lineEnd={first.code.lines.at(-1)?.lineNumber ?? 1}
          highlightStartLine={first.code.lines.find((line) => line.kind === "focus")?.lineNumber ?? 1}
          highlightEndLine={first.code.lines.find((line) => line.kind === "focus")?.lineNumber ?? 1}
          focusLine={first.code.lines.find((line) => line.kind === "focus")?.lineNumber ?? 1}
          title="执行代码"
          density="compact"
          badges={[evidence.displayCommand, statusLabel(first.status)]}
          meta={[
            `退出码 ${first.exitCode}`,
            first.language || "",
            first.description || first.executionCommand || "",
          ]}
        />
      );
    }

    return (
      <FindingCodeWindow
        code={first.stdoutPreview || first.stderrPreview || first.executionCommand || first.description || "执行证据"}
        filePath={first.title || "execution-result"}
        lineStart={1}
        lineEnd={(first.stdoutPreview || first.stderrPreview || first.executionCommand || first.description || "")
          .split("\n").length}
        focusLine={1}
        title="执行代码"
        density="compact"
        badges={[evidence.displayCommand, statusLabel(first.status)]}
        meta={[`退出码 ${first.exitCode}`, first.language || "text"]}
      />
    );
  }

  const first = evidence.entries[0];
  if (!first) return null;

  return (
    <FindingCodeWindow
      code={toolEvidenceLinesToCode(first.lines)}
      filePath={first.filePath}
      lineStart={first.startLine}
      lineEnd={first.endLine}
      highlightStartLine={first.focusLine}
      highlightEndLine={first.focusLine}
      focusLine={first.focusLine}
      title="代码窗口"
      density="compact"
      badges={[evidence.displayCommand, first.focusLine ? "focus" : "code"]}
      meta={[
        first.language,
        first.symbolName ? `${first.symbolKind || "symbol"} ${first.symbolName}` : "",
        first.focusLine ? `焦点行 ${first.focusLine}` : "",
      ]}
    />
  );
}
