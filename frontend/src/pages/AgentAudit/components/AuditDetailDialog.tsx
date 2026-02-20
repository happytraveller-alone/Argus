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

  const triggerFlow =
    detailType === "finding" && finding ? finding.trigger_flow : null;
  const pocChain =
    detailType === "finding" && finding ? finding.poc_trigger_chain : null;
  const functionTriggerFlow =
    detailType === "finding" &&
    finding &&
    Array.isArray(finding.function_trigger_flow)
      ? finding.function_trigger_flow
          .map((step) => String(step || "").trim())
          .filter((step) => step.length > 0)
      : [];
  const hasFunctionTriggerFlow = functionTriggerFlow.length > 0;

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
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
                    {logItem.content}
                  </pre>
                </Section>
              )}

              {logItem.detail && (
                <Section title="原始事件元数据">
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
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
                  {finding.cwe_id && (
                    <Badge variant="outline">CWE: {finding.cwe_id}</Badge>
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

              {finding.code_snippet && (
                <Section title="命中代码片段">
                  <div className="mb-2 rounded-md border border-border bg-card/40 px-3 py-2 text-xs text-muted-foreground space-y-1">
                    <div>所属函数: {finding.reachability_function || "-"}</div>
                    <div>函数所属文件: {finding.reachability_file || finding.file_path || "-"}</div>
                    <div>
                      函数定义行范围: {finding.reachability_function_start_line ?? "-"} -{" "}
                      {finding.reachability_function_end_line ?? "-"}
                    </div>
                    <div>
                      命中行范围: {finding.line_start ?? "-"} - {finding.line_end ?? "-"}
                    </div>
                  </div>
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[45vh]">
                    {finding.code_snippet}
                  </pre>
                </Section>
              )}

              {hasFunctionTriggerFlow && (
                <Section title="所属函数触发流程">
                  <div className="text-xs text-muted-foreground">
                    仅展示命中代码片段所属函数的触发流程。
                  </div>
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[30vh]">
                    {functionTriggerFlow.join("\n")}
                  </pre>
                </Section>
              )}

              {!hasFunctionTriggerFlow && (
                <Section title="PoC 触发链条（Source -> Sink）">
                  {pocChain && Array.isArray(pocChain.nodes) && pocChain.nodes.length >= 2 ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline">engine: {pocChain.engine || "-"}</Badge>
                        <Badge variant="outline">节点数: {pocChain.nodes.length}</Badge>
                        <Badge variant="outline">
                          source: {pocChain.source?.file_path}:{pocChain.source?.line}
                        </Badge>
                        <Badge variant="outline">
                          sink: {pocChain.sink?.file_path}:{pocChain.sink?.line}
                        </Badge>
                      </div>

                      <div className="space-y-2">
                        {pocChain.nodes.map((node) => (
                          <div
                            key={`${node.index}-${node.file_path}-${node.line}`}
                            className="rounded-md border border-border bg-background p-3 space-y-2"
                          >
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <div className="text-xs text-muted-foreground">
                                {node.index + 1}. {node.file_path}:{node.line}
                                {node.function ? `  ${node.function}()` : ""}
                              </div>
                              <div className="flex items-center gap-2">
                                {node.index === 0 && (
                                  <Badge variant="outline">Source</Badge>
                                )}
                                {node.index === pocChain.nodes.length - 1 && (
                                  <Badge variant="outline">Sink</Badge>
                                )}
                              </div>
                            </div>
                            <pre className="text-xs font-mono bg-card/60 border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[40vh]">
                              {node.code}
                            </pre>
                            {node.context && (
                              <details className="rounded-md border border-border bg-card/40 px-3 py-2">
                                <summary className="cursor-pointer text-xs text-muted-foreground">
                                  展开上下文（{node.context_start_line}-{node.context_end_line}）
                                </summary>
                                <pre className="mt-2 text-xs font-mono whitespace-pre-wrap break-words overflow-auto max-h-[40vh]">
                                  {node.context}
                                </pre>
                              </details>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      未生成触发链条（Joern 未命中或回退校验失败）
                    </div>
                  )}
                </Section>
              )}

              {(Boolean(finding.reachability_file || finding.reachability_function) ||
                (!triggerFlow && typeof finding.flow_path_score === "number") ||
                (!triggerFlow &&
                  !hasFunctionTriggerFlow &&
                  finding.flow_call_chain &&
                  finding.flow_call_chain.length > 0) ||
                (!triggerFlow &&
                  finding.flow_control_conditions &&
                  finding.flow_control_conditions.length > 0)) && (
                <Section title="可达性证据">
                  {(finding.reachability_file || finding.reachability_function) && (
                    <div className="text-sm whitespace-pre-wrap break-words">
                      <div>
                        文件: {finding.reachability_file || finding.file_path || "-"}
                      </div>
                      <div>函数: {finding.reachability_function || "-"}</div>
                    </div>
                  )}
                  {!triggerFlow && typeof finding.flow_path_score === "number" && (
                    <div className="text-sm text-muted-foreground">
                      路径评分: {(finding.flow_path_score * 100).toFixed(1)}%
                    </div>
                  )}
                  {!triggerFlow &&
                    !hasFunctionTriggerFlow &&
                    finding.flow_call_chain &&
                    finding.flow_call_chain.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">
                        调用链
                      </div>
                      <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[28vh]">
                        {finding.flow_call_chain.join("\n")}
                      </pre>
                    </div>
                  )}
                  {!triggerFlow &&
                    finding.flow_control_conditions &&
                    finding.flow_control_conditions.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-xs uppercase tracking-wide text-muted-foreground">
                          控制条件
                        </div>
                        <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[24vh]">
                          {finding.flow_control_conditions.join("\n")}
                        </pre>
                      </div>
                    )}
                </Section>
              )}

              {triggerFlow &&
                !hasFunctionTriggerFlow &&
                Array.isArray(triggerFlow.nodes) &&
                triggerFlow.nodes.length > 0 && (
                  <Section title="漏洞触发控制流程图">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Badge variant="outline">节点 {triggerFlow.nodes.length}</Badge>
                      {typeof triggerFlow.path_score === "number" ? (
                        <Badge variant="outline">
                          评分 {(triggerFlow.path_score * 100).toFixed(1)}%
                        </Badge>
                      ) : null}
                      {typeof triggerFlow.path_found === "boolean" ? (
                        <Badge variant="outline">
                          可达 {triggerFlow.path_found ? "是" : "否"}
                        </Badge>
                      ) : null}
                      {triggerFlow.engine ? (
                        <Badge variant="outline">{String(triggerFlow.engine)}</Badge>
                      ) : null}
                    </div>

                    <div className="mt-3 space-y-3">
                      {triggerFlow.nodes.map((node) => {
                        const key = `${node.file_path}:${node.function}:${node.index}`;
                        return (
                          <details
                            key={key}
                            className="rounded-md border border-border bg-background/30"
                          >
                            <summary className="cursor-pointer select-none px-3 py-2 text-xs font-mono flex items-center justify-between gap-2">
                              <span className="break-words">
                                {node.index + 1}. {node.file_path}:{node.function} (
                                {node.start_line}-{node.end_line})
                              </span>
                              {node.code_truncated ? (
                                <Badge variant="outline" className="text-[11px]">
                                  TRUNC
                                </Badge>
                              ) : null}
                            </summary>
                            <div className="px-3 pb-3">
                              <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
                                {node.code}
                              </pre>
                            </div>
                          </details>
                        );
                      })}
                    </div>

                    {Array.isArray(triggerFlow.control_conditions) &&
                    triggerFlow.control_conditions.length > 0 ? (
                      <div className="mt-3 space-y-1">
                        <div className="text-xs uppercase tracking-wide text-muted-foreground">
                          控制条件
                        </div>
                        <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[24vh]">
                          {triggerFlow.control_conditions.join("\n")}
                        </pre>
                      </div>
                    ) : null}
                  </Section>
                )}

              {finding.logic_authz_evidence &&
                finding.logic_authz_evidence.length > 0 && (
                  <Section title="逻辑漏洞证据">
                    <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[24vh]">
                      {finding.logic_authz_evidence.join("\n")}
                    </pre>
                  </Section>
                )}

              {finding.suggestion && (
                <Section title="修复建议">
                  <div className="text-sm whitespace-pre-wrap break-words">
                    {finding.suggestion}
                  </div>
                </Section>
              )}

              {finding.code_context && (
                <Section
                  title={`代码上下文 (${finding.context_start_line ?? "-"} - ${finding.context_end_line ?? "-"})`}
                >
                  <pre className="text-xs font-mono bg-background border border-border rounded-md p-3 whitespace-pre-wrap break-words overflow-auto max-h-[60vh]">
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
