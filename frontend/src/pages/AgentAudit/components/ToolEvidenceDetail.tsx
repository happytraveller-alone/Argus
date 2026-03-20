import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import FindingCodeWindow from "./FindingCodeWindow";
import type {
  ToolEvidenceCodeWindowEntry,
  ToolEvidenceExecutionResultEntry,
  ToolEvidenceFunctionSummaryEntry,
  ToolEvidenceOutlineSummaryEntry,
  ToolEvidencePayload,
  ToolEvidenceSearchHitEntry,
} from "../toolEvidence";
import { isToolEvidenceCapableTool, toolEvidenceLinesToCode } from "../toolEvidence";

function UnsupportedProtocol({
  rawOutput,
}: {
  rawOutput: unknown;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-100">
        旧版工具结果协议，无法在新版证据视图中展示
      </div>
      <details className="rounded-lg border border-border bg-background/70">
        <summary className="cursor-pointer px-4 py-3 text-sm text-primary">查看原始 JSON</summary>
        <pre className="border-t border-border px-4 py-3 text-xs whitespace-pre-wrap break-words">
          {JSON.stringify(rawOutput ?? null, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function statusLabel(status: ToolEvidenceExecutionResultEntry["status"]) {
  if (status === "passed") return "执行成功";
  if (status === "failed") return "执行失败";
  return "执行错误";
}

function SearchHitDetail({ entry, command }: { entry: ToolEvidenceSearchHitEntry; command: string }) {
  return (
    <section className="rounded-xl border border-border/60 bg-card/60 p-4">
      <div className="mb-3 text-xs uppercase tracking-[0.24em] text-muted-foreground">命中定位</div>
      <div className="font-mono text-sm text-foreground">
        {entry.filePath}:{entry.matchLine}
        {entry.column ? `:${entry.column}` : ""}
      </div>
      <div className="mt-2 text-sm text-foreground">{entry.matchText || "命中代码"}</div>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span>{command}</span>
        {entry.symbolName ? <span>symbol {entry.symbolName}</span> : null}
        {entry.matchKind ? <span>{entry.matchKind}</span> : null}
      </div>
    </section>
  );
}

function CodeWindowDetail({ entry, command }: { entry: ToolEvidenceCodeWindowEntry; command: string }) {
  return (
    <FindingCodeWindow
      code={toolEvidenceLinesToCode(entry.lines)}
      filePath={entry.filePath}
      lineStart={entry.startLine}
      lineEnd={entry.endLine}
      highlightStartLine={entry.focusLine}
      highlightEndLine={entry.focusLine}
      focusLine={entry.focusLine}
      title={entry.title || "代码窗口"}
      density="detail"
      badges={[
        command,
        entry.symbolName ? `${entry.symbolKind || "symbol"} ${entry.symbolName}` : "窗口",
      ]}
      meta={[
        entry.language,
        entry.focusLine ? `焦点行 ${entry.focusLine}` : "",
      ]}
    />
  );
}

function OutlineSummaryDetail({ entry }: { entry: ToolEvidenceOutlineSummaryEntry }) {
  return (
    <section className="rounded-xl border border-border/60 bg-card/60 p-4">
      <div className="mb-3 text-xs uppercase tracking-[0.24em] text-muted-foreground">文件概览</div>
      <div className="space-y-2 text-sm text-foreground">
        <div className="font-mono">{entry.filePath}</div>
        <div>角色: {entry.fileRole || "unknown"}</div>
        <div>关键符号: {entry.keySymbols.join(", ") || "无"}</div>
        <div>入口点: {entry.entrypoints.join(", ") || "无"}</div>
        <div>风险标记: {entry.riskMarkers.join(", ") || "无"}</div>
        <div>框架提示: {entry.frameworkHints.join(", ") || "无"}</div>
      </div>
    </section>
  );
}

function FunctionSummaryDetail({ entry }: { entry: ToolEvidenceFunctionSummaryEntry }) {
  return (
    <section className="rounded-xl border border-border/60 bg-card/60 p-4">
      <div className="mb-3 text-xs uppercase tracking-[0.24em] text-muted-foreground">函数摘要</div>
      <div className="space-y-2 text-sm text-foreground">
        <div className="font-mono">
          {entry.filePath} :: {entry.resolvedFunction}
        </div>
        <div>签名: {entry.signature || "未知"}</div>
        <div>职责: {entry.purpose || "未提供"}</div>
        <div>输入: {entry.inputs.join(", ") || "未识别"}</div>
        <div>输出: {entry.outputs.join(", ") || "未识别"}</div>
        <div>关键调用: {entry.keyCalls.join(", ") || "无"}</div>
        <div>风险点: {entry.riskPoints.join(", ") || "无"}</div>
      </div>
    </section>
  );
}

function ExecutionTextWindow({
  title,
  content,
  tone = "default",
}: {
  title: string;
  content: string;
  tone?: "default" | "error";
}) {
  return (
    <FindingCodeWindow
      code={content}
      filePath={title}
      lineStart={1}
      lineEnd={String(content || "").split("\n").length}
      focusLine={1}
      title={title}
      density="detail"
      chrome="plain"
      badges={[tone === "error" ? "stderr" : "stdout"]}
    />
  );
}

function ExecutionResultDetail({
  entry,
  command,
}: {
  entry: ToolEvidenceExecutionResultEntry;
  command: string;
}) {
  const codeFocusLine = entry.code?.lines.find((line) => line.kind === "focus")?.lineNumber ?? 1;

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-border/60 bg-card/60 p-4">
        <div className="mb-3 text-xs uppercase tracking-[0.24em] text-muted-foreground">执行摘要</div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
            {command}
          </Badge>
          <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-200">
            {statusLabel(entry.status)}
          </Badge>
          <span className="rounded-md border border-border/70 bg-background/60 px-2 py-1 text-[11px] font-mono text-foreground">
            退出码 {entry.exitCode}
          </span>
          {entry.language ? (
            <span className="rounded-md border border-border/70 bg-background/60 px-2 py-1 text-[11px] font-mono text-muted-foreground">
              {entry.language}
            </span>
          ) : null}
          {entry.runtimeImage ? (
            <span className="rounded-md border border-border/70 bg-background/60 px-2 py-1 text-[11px] font-mono text-muted-foreground">
              {entry.runtimeImage}
            </span>
          ) : null}
        </div>
        {entry.description ? (
          <div className="mt-3 text-sm text-foreground">{entry.description}</div>
        ) : null}
      </section>

      {entry.executionCommand ? (
        <FindingCodeWindow
          code={entry.executionCommand}
          filePath={entry.title || "execution-command"}
          lineStart={1}
          lineEnd={String(entry.executionCommand).split("\n").length}
          focusLine={1}
          title="执行命令"
          density="detail"
          chrome="plain"
          badges={[command]}
        />
      ) : null}

      {entry.code ? (
        <FindingCodeWindow
          code={toolEvidenceLinesToCode(entry.code.lines)}
          filePath={entry.title || "inline-harness"}
          lineStart={entry.code.lines[0]?.lineNumber ?? 1}
          lineEnd={entry.code.lines.at(-1)?.lineNumber ?? 1}
          highlightStartLine={codeFocusLine}
          highlightEndLine={codeFocusLine}
          focusLine={codeFocusLine}
          title="执行代码"
          density="detail"
          badges={[command, statusLabel(entry.status)]}
          meta={[entry.code.language]}
        />
      ) : null}

      {entry.stdoutPreview ? (
        <ExecutionTextWindow title="执行输出" content={entry.stdoutPreview} />
      ) : null}

      {entry.stderrPreview ? (
        <ExecutionTextWindow title="错误输出" content={entry.stderrPreview} tone="error" />
      ) : null}

      {entry.artifacts.length > 0 ? (
        <section className="rounded-xl border border-border/60 bg-card/60 p-4">
          <div className="mb-3 text-xs uppercase tracking-[0.24em] text-muted-foreground">附加证据</div>
          <div className="grid gap-2">
            {entry.artifacts.map((artifact) => (
              <div
                key={`${artifact.label}-${artifact.value}`}
                className="rounded-md border border-border/70 bg-background/60 px-3 py-2"
              >
                <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                  {artifact.label}
                </div>
                <div className="mt-1 break-all font-mono text-xs text-foreground">{artifact.value}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default function ToolEvidenceDetail({
  toolName,
  evidence,
  rawOutput,
}: {
  toolName?: string | null;
  evidence: ToolEvidencePayload | null;
  rawOutput: unknown;
}) {
  const activeCapableTool = isToolEvidenceCapableTool(toolName);
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSearchEntry = useMemo(() => {
    if (!evidence || evidence.renderType !== "search_hits") return null;
    return evidence.entries[Math.max(0, Math.min(activeIndex, evidence.entries.length - 1))] || null;
  }, [activeIndex, evidence]);

  if (!evidence) {
    return activeCapableTool ? <UnsupportedProtocol rawOutput={rawOutput} /> : null;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
          {evidence.displayCommand}
        </Badge>
        <span className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
          {evidence.renderType === "search_hits"
            ? `${evidence.entries.length} 条命中`
            : evidence.renderType === "outline_summary"
              ? `${evidence.entries.length} 份文件概览`
              : evidence.renderType === "function_summary"
                ? `${evidence.entries.length} 份函数摘要`
            : evidence.renderType === "execution_result"
              ? `${evidence.entries.length} 次执行`
              : `${evidence.entries.length} 个窗口`}
        </span>
      </div>

      {evidence.renderType === "search_hits" ? (
        <>
          <div className="flex flex-wrap gap-2">
            {evidence.entries.map((entry, index) => (
              <button
                key={`${entry.filePath}-${entry.matchLine}`}
                type="button"
                onClick={() => setActiveIndex(index)}
                className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                  index === activeIndex
                    ? "border-cyan-400/30 bg-cyan-400/10 text-foreground"
                    : "border-border/60 bg-background/60 text-muted-foreground hover:text-foreground"
                }`}
              >
                <div className="text-xs font-mono">{entry.filePath}:{entry.matchLine}</div>
                <div className="mt-1 text-sm">{entry.matchText || "命中代码"}</div>
              </button>
            ))}
          </div>
          {activeSearchEntry ? (
            <SearchHitDetail entry={activeSearchEntry} command={evidence.displayCommand} />
          ) : null}
        </>
      ) : evidence.renderType === "outline_summary" ? (
        <div className="space-y-3">
          {evidence.entries.map((entry) => (
            <OutlineSummaryDetail key={entry.filePath} entry={entry} />
          ))}
        </div>
      ) : evidence.renderType === "function_summary" ? (
        <div className="space-y-3">
          {evidence.entries.map((entry) => (
            <FunctionSummaryDetail
              key={`${entry.filePath}-${entry.resolvedFunction}`}
              entry={entry}
            />
          ))}
        </div>
      ) : evidence.renderType === "execution_result" ? (
        <div className="space-y-4">
          {evidence.entries.map((entry, index) => (
            <ExecutionResultDetail
              key={`${entry.executionCommand || entry.description || "execution"}-${index}`}
              entry={entry}
              command={evidence.displayCommand}
            />
          ))}
        </div>
      ) : (
        evidence.entries.map((entry) => (
          <CodeWindowDetail
            key={`${entry.filePath}-${entry.startLine}-${entry.endLine}`}
            entry={entry}
            command={evidence.displayCommand}
          />
        ))
      )}
    </div>
  );
}
