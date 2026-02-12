import { useMemo } from "react";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  FileCode2,
  ListTree,
  Logs,
  XCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { AgentFinding, AgentTreeNode } from "@/shared/api/agentTasks";
import type { LogItem } from "../types";

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
    if (detailType === "agent") return "Agent 详情";
    return "详情";
  }, [detailType]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[88vh] overflow-hidden flex flex-col">
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

        <div className="flex-1 overflow-y-auto custom-scrollbar py-4 space-y-4">
          {detailType === "log" && logItem && (
            <>
              <Section title="概览">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">{logItem.type}</Badge>
                  <Badge variant="outline">{logItem.time}</Badge>
                  {logItem.agentName && (
                    <Badge variant="outline">{logItem.agentName}</Badge>
                  )}
                  {logItem.tool?.status && (
                    <Badge variant="outline">
                      工具状态: {logItem.tool.status}
                    </Badge>
                  )}
                </div>
                <h3 className="text-sm font-semibold break-words">{logItem.title}</h3>
              </Section>

              {logItem.content && (
                <Section title="详细内容">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[35vh]">
                    {logItem.content}
                  </pre>
                </Section>
              )}

              {logItem.detail && (
                <Section title="原始事件元数据">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[35vh]">
                    {prettyJson(logItem.detail)}
                  </pre>
                </Section>
              )}
            </>
          )}

          {detailType === "finding" && finding && (
            <>
              <Section title="概览">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">{finding.severity?.toUpperCase()}</Badge>
                  <Badge variant="outline">
                    真实性: {finding.authenticity || "unknown"}
                  </Badge>
                  <Badge variant="outline">
                    {finding.is_verified ? (
                      <span className="inline-flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        已验证
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <XCircle className="w-3 h-3" />
                        未验证
                      </span>
                    )}
                  </Badge>
                  {finding.reachability && (
                    <Badge variant="outline">可达性: {finding.reachability}</Badge>
                  )}
                </div>
                <h3 className="text-sm font-semibold break-words">{finding.title}</h3>
                <div className="text-xs text-muted-foreground">
                  定位: {formatLocation(finding)}
                </div>
              </Section>

              {finding.description && (
                <Section title="漏洞描述">
                  <div className="text-sm whitespace-pre-wrap break-words">
                    {finding.description}
                  </div>
                </Section>
              )}

              {finding.verification_evidence && (
                <Section title="证据">
                  <div className="text-sm whitespace-pre-wrap break-words">
                    {finding.verification_evidence}
                  </div>
                </Section>
              )}

              {finding.suggestion && (
                <Section title="修复建议">
                  <div className="text-sm whitespace-pre-wrap break-words">
                    {finding.suggestion}
                  </div>
                </Section>
              )}

              {finding.code_snippet && (
                <Section title="代码片段">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[35vh]">
                    {finding.code_snippet}
                  </pre>
                </Section>
              )}

              {finding.code_context && (
                <Section
                  title={`代码上下文 (${finding.context_start_line ?? "-"} - ${finding.context_end_line ?? "-"})`}
                >
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[40vh]">
                    {finding.code_context}
                  </pre>
                </Section>
              )}

              {finding.poc_code && (
                <Section title="PoC">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[35vh]">
                    {finding.poc_code}
                  </pre>
                </Section>
              )}
            </>
          )}

          {detailType === "agent" && agentNode && (
            <>
              <Section title="概览">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline">{agentNode.agent_type}</Badge>
                  <Badge variant="outline">{agentNode.status}</Badge>
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
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default AuditDetailDialog;
