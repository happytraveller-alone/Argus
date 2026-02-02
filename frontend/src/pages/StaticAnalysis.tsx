import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import {
  getOpengrepScanFindings,
  getOpengrepScanTask,
  updateOpengrepFindingStatus,
  type OpengrepFinding,
  type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { showToastQueue } from "@/shared/utils/toastQueue";
import { AlertCircle, ArrowLeft, RefreshCw, Shield, Loader2 } from "lucide-react";

const STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const STATUS_CLASSES: Record<string, string> = {
  pending: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  running: "bg-sky-500/20 text-sky-300 border-sky-500/30",
  completed: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  failed: "bg-rose-500/20 text-rose-300 border-rose-500/30",
};

const SEVERITY_CLASSES: Record<string, string> = {
  ERROR: "bg-rose-500/20 text-rose-300 border-rose-500/30",
  WARNING: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  INFO: "bg-sky-500/20 text-sky-300 border-sky-500/30",
};

const FINDING_STATUS_CLASSES: Record<string, string> = {
  open: "bg-sky-500/20 text-sky-300 border-sky-500/30",
  verified: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  false_positive: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

const normalizePath = (path?: string | null) => {
  if (!path) return "";
  const tmpIndex = path.indexOf("/tmp/");
  if (tmpIndex >= 0) {
    const trimmed = path.slice(tmpIndex + 5);
    const parts = trimmed.split("/");
    if (parts.length > 1) {
      return parts.slice(1).join("/");
    }
  }
  return path;
};

const getCheckIdSuffix = (checkId?: string | null) => {
  const value = String(checkId || "");
  if (!value) return "";
  const parts = value.split(".");
  return parts[parts.length - 1] || value;
};

const getRuleMeta = (finding: OpengrepFinding) => {
  const rule = (finding.rule || {}) as Record<string, any>;
  const extra = (rule.extra || {}) as Record<string, any>;
  const metadata = (extra.metadata || {}) as Record<string, any>;
  return {
    checkId: rule.check_id || rule.id || "unknown-rule",
    message: extra.message || finding.description || "",
    confidence: metadata.confidence,
    references: Array.isArray(metadata.references) ? metadata.references : [],
    path: rule.path || finding.file_path,
    line: rule.start?.line || finding.start_line,
    lines: extra.lines || finding.code_snippet || "",
    fingerprint: extra.fingerprint,
    engineKind: extra.engine_kind,
    validationState: extra.validation_state,
    metavars: extra.metavars,
    start: rule.start,
    end: rule.end,
    metadata,
    extra,
    rule,
  };
};

const formatJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
};

export default function StaticAnalysis() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();

  const [task, setTask] = useState<OpengrepScanTask | null>(null);
  const [findings, setFindings] = useState<OpengrepFinding[]>([]);
  const [loadingTask, setLoadingTask] = useState(false);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("open");
  const [updatingFindingId, setUpdatingFindingId] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [selectedFinding, setSelectedFinding] = useState<OpengrepFinding | null>(null);
  const lastNotifiedStatusRef = useRef<string | null>(null);

  const taskStatusLabel = useMemo(
    () => (task?.status ? STATUS_LABELS[task.status] || task.status : "未知"),
    [task?.status]
  );

  const loadTask = async () => {
    if (!taskId) return;
    setLoadingTask(true);
    try {
      const data = await getOpengrepScanTask(taskId);
      setTask(data);
    } catch (error) {
      toast.error("加载静态分析任务失败");
    } finally {
      setLoadingTask(false);
    }
  };

  const loadFindings = async () => {
    if (!taskId) return;
    setLoadingFindings(true);
    try {
      const data = await getOpengrepScanFindings({
        taskId,
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
        limit: 200,
      });
      setFindings(data);
    } catch (error) {
      toast.error("加载静态分析结果失败");
    } finally {
      setLoadingFindings(false);
    }
  };

  useEffect(() => {
    loadTask();
  }, [taskId]);

  useEffect(() => {
    loadFindings();
  }, [taskId, severityFilter, statusFilter]);

  useEffect(() => {
    if (!taskId) return;
    if (!task || !["pending", "running"].includes(task.status)) return;
    const timer = setInterval(() => {
      loadTask();
      loadFindings();
    }, 5000);
    return () => clearInterval(timer);
  }, [taskId, task?.status]);

  useEffect(() => {
    if (!task?.status) return;
    if (lastNotifiedStatusRef.current === task.status) return;
    lastNotifiedStatusRef.current = task.status;

    if (task.status === "pending") {
      void showToastQueue(
        [{ level: "info", message: "静态扫描任务已创建，等待执行..." }],
        { durationMs: 2200 }
      );
      return;
    }

    if (task.status === "running") {
      void showToastQueue(
        [{ level: "info", message: "静态规则扫描进行中，请稍候..." }],
        { durationMs: 2200 }
      );
      return;
    }

    if (task.status === "completed") {
      const hasFindings = (task.total_findings || 0) > 0;
      void showToastQueue(
        hasFindings
          ? [{ level: "success", message: `扫描完成，共发现 ${task.total_findings} 条结果` }]
          : [{ level: "success", message: "扫描完成，未发现规则命中（结果为 0 也视为成功）" }],
        { durationMs: 2600 }
      );
      return;
    }

    if (task.status === "failed") {
      void showToastQueue(
        [{ level: "error", message: "扫描失败：规则执行异常或规则配置错误" }],
        { durationMs: 2600 }
      );
    }
  }, [task?.status, task?.total_findings]);

  const handleUpdateStatus = async (findingId: string, status: "open" | "verified" | "false_positive") => {
    setUpdatingFindingId(findingId);
    try {
      await updateOpengrepFindingStatus({ findingId, status });
      setFindings((prev) => {
        if (statusFilter && statusFilter !== status) {
          return prev.filter((item) => item.id !== findingId);
        }
        return prev.map((item) =>
          item.id === findingId ? { ...item, status } : item
        );
      });
      toast.success("状态已更新");
    } catch (error) {
      toast.error("更新状态失败");
    } finally {
      setUpdatingFindingId(null);
    }
  };

  const openDetail = (finding: OpengrepFinding) => {
    setSelectedFinding(finding);
    setShowDetail(true);
  };

  return (
    <div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Shield className="w-6 h-6 text-primary" />
              <h1 className="text-2xl font-bold text-foreground uppercase tracking-wider">
                静态分析结果
              </h1>
            </div>
            {task && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge className={`cyber-badge ${STATUS_CLASSES[task.status] || "bg-muted"}`}>
                  {taskStatusLabel}
                </Badge>
                <span>任务：{task.name}</span>
                <span>·</span>
                <span>文件：{task.files_scanned}</span>
                <span>·</span>
                <span>发现：{task.total_findings}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="cyber-btn-outline"
              onClick={() => navigate(-1)}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              返回
            </Button>
            <Button
              variant="outline"
              className="cyber-btn-ghost"
              onClick={() => {
                loadTask();
                loadFindings();
              }}
              disabled={loadingTask || loadingFindings}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              刷新
            </Button>
          </div>
        </div>

        <div className="cyber-card p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-mono font-bold text-muted-foreground mb-1 uppercase">
                严重程度
              </label>
              <Select value={severityFilter || "all"} onValueChange={(val) => setSeverityFilter(val === "all" ? "" : val)}>
                <SelectTrigger className="cyber-input">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent className="cyber-dialog border-border">
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="ERROR">ERROR</SelectItem>
                  <SelectItem value="WARNING">WARNING</SelectItem>
                  <SelectItem value="INFO">INFO</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-xs font-mono font-bold text-muted-foreground mb-1 uppercase">
                状态
              </label>
              <Select value={statusFilter || "all"} onValueChange={(val) => setStatusFilter(val === "all" ? "" : val)}>
                <SelectTrigger className="cyber-input">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent className="cyber-dialog border-border">
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="open">open</SelectItem>
                  <SelectItem value="verified">verified</SelectItem>
                  <SelectItem value="false_positive">false_positive</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <div className="text-xs text-muted-foreground font-mono">
                {loadingFindings ? "加载中..." : `共 ${findings.length} 条结果`}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        {loadingFindings ? (
          <div className="p-16 text-center">
            <div className="loading-spinner mx-auto mb-4" />
            <p className="text-muted-foreground font-mono text-sm">加载静态分析结果...</p>
          </div>
        ) : findings.length === 0 ? (
          <div className="p-16 text-center">
            <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-bold text-foreground mb-2">暂无发现</h3>
            <p className="text-muted-foreground font-mono text-sm">
              {task?.status === "running" ? "扫描进行中，请稍后刷新" : "未检测到问题"}
            </p>
          </div>
        ) : (
          <ScrollArea className="h-[600px]">
            <div className="divide-y divide-border">
              {findings.map((finding) => {
                const meta = getRuleMeta(finding);
                return (
                  <div key={finding.id} className="p-4 space-y-3">
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge className={`cyber-badge ${SEVERITY_CLASSES[finding.severity] || "bg-muted"}`}>
                          {finding.severity}
                        </Badge>
                        <Badge className={`cyber-badge ${FINDING_STATUS_CLASSES[finding.status] || "bg-muted"}`}>
                          {finding.status}
                        </Badge>
                        {meta.confidence && (
                          <Badge className="cyber-badge-muted">CONF: {meta.confidence}</Badge>
                        )}
                        <span className="text-sm text-foreground font-bold">
                          {getCheckIdSuffix(meta.checkId)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="cyber-btn-ghost h-7 text-xs"
                          onClick={() => openDetail(finding)}
                        >
                          详情
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 text-xs border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                          disabled={updatingFindingId === finding.id || finding.status === "verified"}
                          onClick={() => handleUpdateStatus(finding.id, "verified")}
                        >
                          标记已验证
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 text-xs border-amber-500/40 text-amber-500 hover:bg-amber-500/10"
                          disabled={updatingFindingId === finding.id || finding.status === "false_positive"}
                          onClick={() => handleUpdateStatus(finding.id, "false_positive")}
                        >
                          标记误报
                        </Button>
                        {updatingFindingId === finding.id && (
                          <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                        )}
                      </div>
                    </div>

                    <div className="text-xs text-muted-foreground font-mono">
                      {normalizePath(meta.path)}
                      {meta.line ? `:${meta.line}` : ""}
                    </div>

                    {meta.message && (
                      <div className="text-sm text-foreground">
                        {meta.message}
                      </div>
                    )}

                    {meta.lines && (
                      <pre className="text-xs font-mono text-foreground bg-muted border border-border rounded p-3 whitespace-pre-wrap break-words">
                        {meta.lines}
                      </pre>
                    )}

                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </div>

      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="!w-[min(90vw,980px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
          {/* Terminal Header */}
          <div className="flex items-center gap-2 px-4 py-3 cyber-bg-elevated border-b border-border flex-shrink-0">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <span className="ml-2 font-mono text-xs text-muted-foreground tracking-wider">
              static_finding@deepaudit
            </span>
          </div>

          <DialogHeader className="px-6 pt-4 flex-shrink-0">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Shield className="w-5 h-5 text-primary" />
              结果详情
            </DialogTitle>
          </DialogHeader>

          {selectedFinding && (() => {
            const meta = getRuleMeta(selectedFinding);
            return (
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-6">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge className={`cyber-badge ${SEVERITY_CLASSES[selectedFinding.severity] || "bg-muted"}`}>
                      {selectedFinding.severity}
                    </Badge>
                    <Badge className={`cyber-badge ${FINDING_STATUS_CLASSES[selectedFinding.status] || "bg-muted"}`}>
                      {selectedFinding.status}
                    </Badge>
                    {meta.confidence && (
                      <Badge className="cyber-badge-muted">CONF: {meta.confidence}</Badge>
                    )}
                    <span className="text-sm text-foreground font-bold">
                      {getCheckIdSuffix(meta.checkId)}
                    </span>
                  </div>

                  <div className="space-y-3">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                      基本信息
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono text-muted-foreground">
                      <div>
                        <div className="uppercase text-[10px] text-muted-foreground mb-1">文件路径</div>
                        <div className="text-foreground break-all">
                          {normalizePath(meta.path)}
                          {meta.line ? `:${meta.line}` : ""}
                        </div>
                      </div>
                      <div>
                        <div className="uppercase text-[10px] text-muted-foreground mb-1">规则指纹</div>
                        <div className="text-foreground break-all">{meta.fingerprint || "-"}</div>
                      </div>
                      <div>
                        <div className="uppercase text-[10px] text-muted-foreground mb-1">引擎类型</div>
                        <div className="text-foreground">{meta.engineKind || "-"}</div>
                      </div>
                      <div>
                        <div className="uppercase text-[10px] text-muted-foreground mb-1">验证状态</div>
                        <div className="text-foreground">{meta.validationState || "-"}</div>
                      </div>
                    </div>
                  </div>

                  {meta.message && (
                    <div className="space-y-3">
                      <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                        规则描述
                      </h3>
                      <div className="text-sm text-foreground">
                        {meta.message}
                      </div>
                    </div>
                  )}

                  {(meta.lines || selectedFinding.code_snippet) && (
                    <div className="space-y-3">
                      <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                        代码片段
                      </h3>
                      <pre className="text-xs font-mono text-foreground bg-muted border border-border rounded p-3 whitespace-pre-wrap break-words">
                        {meta.lines || selectedFinding.code_snippet}
                      </pre>
                    </div>
                  )}

                  <div className="space-y-3">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                      结构化信息
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="bg-muted border border-border rounded p-3">
                        <div className="text-[10px] uppercase text-muted-foreground font-mono mb-2">起止位置</div>
                        <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                          {formatJson({ start: meta.start, end: meta.end })}
                        </pre>
                      </div>
                      <div className="bg-muted border border-border rounded p-3">
                        <div className="text-[10px] uppercase text-muted-foreground font-mono mb-2">元数据</div>
                        <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                          {formatJson(meta.metadata)}
                        </pre>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                      匹配变量
                    </h3>
                    <div className="bg-muted border border-border rounded p-3">
                      <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                        {formatJson(meta.metavars)}
                      </pre>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                      原始规则数据
                    </h3>
                    <div className="bg-muted border border-border rounded p-3">
                      <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                        {formatJson(meta.rule)}
                      </pre>
                    </div>
                  </div>

                  {meta.references.length > 0 && (
                    <div className="space-y-3">
                      <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                        参考链接
                      </h3>
                      <ul className="text-xs text-muted-foreground font-mono list-disc list-inside space-y-1">
                        {meta.references.map((ref: string) => (
                          <li key={ref} className="break-all">
                            {ref}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
