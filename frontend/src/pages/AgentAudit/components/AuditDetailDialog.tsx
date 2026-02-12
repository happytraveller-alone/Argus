import { useMemo } from "react";
import { ArrowLeft, FileCode2, ListTree, Logs } from "lucide-react";
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
  if (finding.line_start && finding.line_end && finding.line_end !== finding.line_start) {
    return `${finding.file_path}:${finding.line_start}-${finding.line_end}`;
  }
  if (finding.line_start) return `${finding.file_path}:${finding.line_start}`;
  return finding.file_path;
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
            <div className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{logItem.type}</Badge>
                <Badge variant="outline">{logItem.time}</Badge>
                {logItem.agentName && <Badge variant="outline">{logItem.agentName}</Badge>}
              </div>
              <h3 className="text-base font-semibold break-words">{logItem.title}</h3>
              {logItem.content && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">内容</div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {logItem.content}
                  </pre>
                </div>
              )}
              {logItem.detail && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">原始事件元数据</div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {prettyJson(logItem.detail)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {detailType === "finding" && finding && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{finding.severity?.toUpperCase()}</Badge>
                <Badge variant="outline">{finding.authenticity || "unknown"}</Badge>
                {finding.reachability && <Badge variant="outline">{finding.reachability}</Badge>}
              </div>
              <h3 className="text-base font-semibold break-words">{finding.title}</h3>
              <div className="text-sm text-muted-foreground">{formatLocation(finding)}</div>
              {finding.description && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">漏洞描述</div>
                  <div className="text-sm whitespace-pre-wrap break-words">{finding.description}</div>
                </div>
              )}
              {finding.verification_evidence && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">真实性证据</div>
                  <div className="text-sm whitespace-pre-wrap break-words">{finding.verification_evidence}</div>
                </div>
              )}
              {finding.suggestion && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">修复建议</div>
                  <div className="text-sm whitespace-pre-wrap break-words">{finding.suggestion}</div>
                </div>
              )}
              {finding.code_snippet && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">代码片段</div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {finding.code_snippet}
                  </pre>
                </div>
              )}
              {finding.code_context && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">
                    代码上下文 ({finding.context_start_line ?? "-"} - {finding.context_end_line ?? "-"})
                  </div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {finding.code_context}
                  </pre>
                </div>
              )}
              {finding.poc_code && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">PoC</div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {finding.poc_code}
                  </pre>
                </div>
              )}
            </div>
          )}

          {detailType === "agent" && agentNode && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{agentNode.agent_type}</Badge>
                <Badge variant="outline">{agentNode.status}</Badge>
              </div>
              <h3 className="text-base font-semibold break-words">{agentNode.agent_name}</h3>
              <div className="text-sm text-muted-foreground">
                迭代 {agentNode.iterations} | 工具调用 {agentNode.tool_calls} | Tokens {agentNode.tokens_used}
              </div>
              {agentNode.task_description && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">当前任务</div>
                  <div className="text-sm whitespace-pre-wrap break-words">{agentNode.task_description}</div>
                </div>
              )}
              {agentNode.result_summary && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">执行摘要</div>
                  <pre className="text-xs font-mono bg-card border border-border rounded-md p-3 whitespace-pre-wrap break-words">
                    {agentNode.result_summary}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default AuditDetailDialog;
