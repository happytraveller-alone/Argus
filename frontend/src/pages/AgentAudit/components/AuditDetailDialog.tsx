import { useMemo } from "react";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  ChevronDown,
  FileCode2,
  ListTree,
  Logs,
} from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { AgentFinding, AgentTreeNode } from "@/shared/api/agentTasks";
import type { LogItem } from "../types";
import {
  localizeAuditText,
  toZhAgentName,
  toZhLogType,
  toZhStatus,
} from "../localization";
import FindingCodeWindow from "./FindingCodeWindow";
import FindingNarrativeMarkdown from "./FindingNarrativeMarkdown";
import { collectRawEvidenceEntries } from "./findingNarrative";
import ToolEvidenceDetail from "./ToolEvidenceDetail";
import { isToolEvidenceCapableTool } from "../toolEvidence";

interface AuditDetailDialogProps {
  open: boolean;
  detailType: "log" | "finding" | "agent" | null;
  logItem?: LogItem | null;
  finding?: AgentFinding | null;
  agentNode?: AgentTreeNode | null;
  onBack: () => void;
  onOpenChange: (open: boolean) => void;
}

function prettyJson(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data ?? "");
  }
}

function formatLocation(finding: AgentFinding): string {
  if (!finding.file_path) return "未定位文件";
  if (
    finding.line_start &&
    finding.line_end &&
    finding.line_end !== finding.line_start
  ) {
    return `${finding.file_path}:${finding.line_start}-${finding.line_end}`;
  }
  if (finding.line_start) return `${finding.file_path}:${finding.line_start}`;
  return finding.file_path;
}

function pickFindingCode(finding: AgentFinding): {
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
} | null {
  const context = String(finding.code_context || "").trim();
  if (context) {
    return {
      code: context,
      lineStart:
        typeof finding.context_start_line === "number"
          ? finding.context_start_line
          : finding.line_start ?? null,
      lineEnd:
        typeof finding.context_end_line === "number"
          ? finding.context_end_line
          : finding.line_end ?? null,
    };
  }
  const snippet = String(finding.code_snippet || "").trim();
  if (snippet) {
    return {
      code: snippet,
      lineStart: finding.line_start ?? null,
      lineEnd: finding.line_end ?? null,
    };
  }
  return null;
}

function getRawEvidenceFromFinding(finding: AgentFinding) {
  return collectRawEvidenceEntries({
    description: finding.description,
    verification_evidence: finding.verification_evidence,
    function_trigger_flow: finding.function_trigger_flow,
    reachability_file: finding.reachability_file,
    reachability_function: finding.reachability_function,
    reachability_function_start_line: finding.reachability_function_start_line,
    reachability_function_end_line: finding.reachability_function_end_line,
  });
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card/70 p-3.5 space-y-2">
      <h4 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
        {title}
      </h4>
      {children}
    </section>
  );
}

export interface AuditDetailContentProps
  extends Omit<AuditDetailDialogProps, "open" | "onBack" | "onOpenChange"> { }

export function AuditDetailContent({
  detailType,
  logItem,
  finding,
  agentNode,
}: AuditDetailContentProps) {
  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar py-4 space-y-4">
      {detailType === "log" && logItem && (
        <>
          <Section title="概览">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline">{toZhLogType(logItem.type)}</Badge>
              <Badge variant="outline">{logItem.time}</Badge>
              {logItem.agentName && (
                <Badge variant="outline">{logItem.agentName}</Badge>
              )}
              {logItem.tool?.status && (
                <Badge variant="outline">
                  工具状态: {toZhStatus(logItem.tool.status)}
                </Badge>
              )}
              {logItem.tool?.name ? (
                <Badge variant="outline">{logItem.tool.name}</Badge>
              ) : null}
            </div>
          </Section>

          {isToolEvidenceCapableTool(logItem.tool?.name) ? (
            <ToolEvidenceDetail
              toolName={logItem.tool?.name}
              evidence={logItem.toolEvidence ?? null}
              rawOutput={logItem.detail?.tool_output}
              missingState={logItem.toolEvidenceMissingState ?? null}
              runtimeMetadata={(logItem.detail?.metadata as Record<string, unknown> | undefined) ?? null}
              toolStatus={logItem.tool?.status}
            />
          ) : null}

          {logItem.content && !isToolEvidenceCapableTool(logItem.tool?.name) && (
            <Section title="详细内容">
              <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
                {localizeAuditText(logItem.content)}
              </pre>
            </Section>
          )}

          {logItem.detail && (
            <Section title="原始事件元数据">
              <Collapsible className="rounded-md border border-border bg-card/60">
                <CollapsibleTrigger className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground">
                  <span>查看原始事件元数据</span>
                  <ChevronDown className="w-4 h-4" />
                </CollapsibleTrigger>
                <CollapsibleContent className="px-3 pb-3">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
                    {prettyJson(logItem.detail)}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </Section>
          )}
        </>
      )
      }

      {
        detailType === "finding" && finding && (
          <>
            {(() => {
              const code = pickFindingCode(finding);
              if (!code) return null;
              return (
                <FindingCodeWindow
                  code={code.code}
                  filePath={finding.file_path}
                  lineStart={code.lineStart}
                  lineEnd={code.lineEnd}
                  highlightStartLine={finding.line_start ?? code.lineStart}
                  highlightEndLine={finding.line_end ?? code.lineEnd}
                  focusLine={finding.line_start ?? code.lineStart}
                  title="命中代码"
                />
              );
            })()}

            <Section title="概览">
              <h3 className="text-sm font-semibold break-words">
                {localizeAuditText(finding.title)}
              </h3>
              <div className="text-xs text-muted-foreground">
                定位: {formatLocation(finding)}
              </div>
            </Section>

            <Section title="漏洞详情（根因）">
              <FindingNarrativeMarkdown
                finding={{
                  description: finding.description,
                  description_markdown: finding.description_markdown,
                  code_context: finding.code_context,
                  code_snippet: finding.code_snippet,
                  file_path: finding.file_path,
                  line_start: finding.line_start,
                  line_end: finding.line_end,
                  function_trigger_flow: finding.function_trigger_flow,
                  verification_evidence: finding.verification_evidence,
                  reachability_file: finding.reachability_file,
                  reachability_function: finding.reachability_function,
                  reachability_function_start_line:
                    finding.reachability_function_start_line,
                  reachability_function_end_line:
                    finding.reachability_function_end_line,
                }}
                className="rounded-md border border-border bg-background p-3"
              />

              <Collapsible className="rounded-md border border-border bg-card/60">
                <CollapsibleTrigger className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground">
                  <span>原始证据</span>
                  <ChevronDown className="w-4 h-4" />
                </CollapsibleTrigger>
                <CollapsibleContent className="px-3 pb-3 space-y-2">
                  {getRawEvidenceFromFinding(finding).map((item) => (
                    <div key={item.key} className="space-y-1">
                      <div className="text-[11px] text-muted-foreground font-mono">
                        {item.label}
                        {item.truncated ? " (已截断至 2000 字)" : ""}
                      </div>
                      <pre className="text-xs font-mono bg-background border border-border rounded-md p-2 whitespace-pre-wrap break-words">
                        {item.value}
                      </pre>
                    </div>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            </Section>
          </>
        )
      }

      {
        detailType === "agent" && agentNode && (
          <>
            <Section title="概览">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{toZhAgentName(agentNode.agent_type)}</Badge>
                <Badge variant="outline">{toZhStatus(agentNode.status)}</Badge>
              </div>
              <h3 className="text-sm font-semibold break-words">{agentNode.agent_name}</h3>
              <div className="text-xs text-muted-foreground">
                迭代 {agentNode.iterations} | 工具调用 {agentNode.tool_calls} | Tokens{" "}
                {agentNode.tokens_used}
              </div>
            </Section>

            {agentNode.task_description && (
              <Section title="当前任务">
                <div className="text-sm whitespace-pre-wrap break-words">
                  {agentNode.task_description}
                </div>
              </Section>
            )}

            {agentNode.result_summary && (
              <Section title="执行摘要">
                <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[35vh]">
                  {agentNode.result_summary}
                </pre>
              </Section>
            )}
          </>
        )
      }
    </div >
  );
}

export function AuditDetailDialog({
  open,
  detailType,
  logItem,
  finding,
  agentNode,
  onBack,
  onOpenChange,
}: AuditDetailDialogProps) {
  const title = useMemo(() => {
    if (detailType === "log") return "日志详情";
    if (detailType === "finding") return "漏洞详情";
    if (detailType === "agent") return "智能体详情";
    return "详情";
  }, [detailType]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={undefined}
        className="max-w-5xl h-[88vh] overflow-hidden flex flex-col"
      >
        <DialogHeader className="border-b border-border pb-3">
          <div className="flex items-center justify-between gap-3">
            <DialogTitle className="flex items-center gap-2">
              {detailType === "log" && <Logs className="w-4 h-4" />}
              {detailType === "finding" && <FileCode2 className="w-4 h-4" />}
              {detailType === "agent" && <ListTree className="w-4 h-4" />}
              {title}
            </DialogTitle>
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              返回
            </button>
          </div>
        </DialogHeader>

        <AuditDetailContent
          detailType={detailType}
          logItem={logItem}
          finding={finding}
          agentNode={agentNode}
        />
      </DialogContent>
    </Dialog>
  );
}

export default AuditDetailDialog;
