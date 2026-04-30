import FindingCodeWindow from "./FindingCodeWindow";
import type { ParsedToolEvidence, ToolEvidencePayload } from "../toolEvidence";
import { asParsedToolEvidence, toolEvidenceLinesToCode } from "../toolEvidence";

function statusLabel(status: "passed" | "failed" | "error") {
  if (status === "passed") return "执行成功";
  if (status === "failed") return "执行失败";
  return "执行错误";
}

export default function ToolEvidencePreview({
  evidence,
}: {
  evidence: ParsedToolEvidence | ToolEvidencePayload;
}) {
  const parsed = asParsedToolEvidence(evidence);
  const payload = parsed?.payload;
  if (!parsed || !payload) return null;

  if (payload.renderType === "search_hits") {
    const first = payload.entries[0];
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
        badges={[parsed.state, `${payload.entries.length} 条命中`]}
      />
    );
  }

  if (payload.renderType === "code_window" || payload.renderType === "symbol_body") {
    const first = payload.entries[0];
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
        title={first.title || "代码窗口"}
        density="compact"
        badges={[parsed.state]}
      />
    );
  }

  if (payload.renderType === "execution_result") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = first.code
      ? toolEvidenceLinesToCode(first.code.lines)
      : first.stdoutPreview || first.stderrPreview || first.executionCommand || first.description || "执行证据";
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.title || "execution-result"}
        lineStart={1}
        lineEnd={content.split("\n").length}
        focusLine={1}
        title={first.title || "执行证据"}
        density="compact"
        badges={[statusLabel(first.status), parsed.state]}
      />
    );
  }

  if (payload.renderType === "file_list") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [...first.files.slice(0, 4), ...first.directories.slice(0, 2)].join("\n") || "暂无目录内容";
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.directory}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title="目录摘要"
        density="compact"
        badges={[`${first.fileCount} 文件`, parsed.state]}
      />
    );
  }

  if (payload.renderType === "locator_result") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [first.signature || first.symbolName, ...first.parameters].filter(Boolean).join("\n");
    return (
      <FindingCodeWindow
        code={content || first.symbolName}
        filePath={first.filePath}
        lineStart={first.startLine}
        lineEnd={first.endLine}
        focusLine={first.line}
        highlightStartLine={first.line}
        highlightEndLine={first.line}
        title="定位结果"
        density="compact"
        badges={[first.engine, parsed.state]}
      />
    );
  }

  if (payload.renderType === "analysis_summary") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [first.summary, ...first.highlights.slice(0, 3)].join("\n");
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.title}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title={first.title}
        density="compact"
        badges={[`${first.hitCount} 发现`, parsed.state]}
      />
    );
  }

  if (payload.renderType === "outline_summary") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [
      `role=${first.fileRole}`,
      ...first.entrypoints.slice(0, 3),
      ...first.keySymbols.slice(0, 3),
    ]
      .filter(Boolean)
      .join("\n");
    return (
      <FindingCodeWindow
        code={content || first.filePath}
        filePath={first.filePath}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title="文件概览"
        density="compact"
        badges={[parsed.state]}
      />
    );
  }

  if (payload.renderType === "function_summary") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [
      first.signature || first.resolvedFunction,
      first.purpose,
      ...first.keyCalls.slice(0, 3),
    ]
      .filter(Boolean)
      .join("\n");
    return (
      <FindingCodeWindow
        code={content || first.resolvedFunction}
        filePath={first.filePath}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title={first.resolvedFunction}
        density="compact"
        badges={[parsed.state]}
      />
    );
  }

  if (payload.renderType === "flow_analysis") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [
      `reachability=${first.reachability}`,
      ...first.callChain.slice(0, 3),
      ...first.taintSteps.slice(0, 3),
    ].join("\n");
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.filePath || first.engine}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title="路径摘要"
        density="compact"
        badges={[first.engine, parsed.state]}
      />
    );
  }

  if (payload.renderType === "verification_summary") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [first.target, first.payload, first.evidence].filter(Boolean).join("\n");
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.vulnerabilityType}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title={first.verdict}
        density="compact"
        badges={[parsed.state]}
      />
    );
  }

  if (payload.renderType === "report_summary") {
    const first = payload.entries[0];
    if (!first) return null;
    const content = [first.location, first.recommendation].filter(Boolean).join("\n");
    return (
      <FindingCodeWindow
        code={content}
        filePath={first.title}
        lineStart={1}
        lineEnd={Math.max(1, content.split("\n").length)}
        focusLine={1}
        title={first.severity}
        density="compact"
        badges={[parsed.state]}
      />
    );
  }

  return null;
}
