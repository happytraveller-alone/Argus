import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Circle,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getAiAnalysisStatus,
  triggerAiAnalysis,
  type AiAnalysisStatusResponse,
} from "@/shared/api/opengrep";

const STEP_LABELS = ["代码分析", "规则评估", "修复建议"] as const;

const POLL_INTERVAL_MS = 5000;

function StepTimeline({ currentStep, status }: { currentStep: number | null; status: string }) {
  return (
    <div className="flex items-center justify-center gap-3">
      {STEP_LABELS.map((label, i) => {
        const stepNum = i + 1;
        const isCompleted = status === "completed" || (currentStep !== null && stepNum < currentStep);
        const isCurrent = status === "analyzing" && currentStep === stepNum;
        return (
          <div key={label} className="flex items-center gap-2">
            {i > 0 && (
              <div className={`h-px w-8 ${isCompleted || isCurrent ? "bg-primary/60" : "bg-border"}`} />
            )}
            <div className="flex items-center gap-1.5">
              {isCompleted ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : isCurrent ? (
                <Loader2 className="w-5 h-5 text-primary animate-spin" />
              ) : (
                <Circle className="w-5 h-5 text-muted-foreground/50" />
              )}
              <span className={`text-sm ${isCompleted ? "text-emerald-400" : isCurrent ? "text-primary font-medium" : "text-muted-foreground/50"}`}>
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function OverviewTab({ data }: { data: AiAnalysisStatusResponse }) {
  const rules = data.result?.rules ?? [];
  const severityCounts = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 };
    for (const rule of rules) {
      const sev = rule.severity?.toUpperCase();
      if (sev === "ERROR" || sev === "HIGH") counts.high++;
      else if (sev === "WARNING" || sev === "MEDIUM") counts.medium++;
      else counts.low++;
    }
    return counts;
  }, [rules]);

  const priorityCounts = useMemo(() => {
    const counts = { high: 0, medium: 0, low: 0 };
    for (const rule of rules) {
      const p = rule.priority?.toLowerCase();
      if (p === "high") counts.high++;
      else if (p === "medium") counts.medium++;
      else counts.low++;
    }
    return counts;
  }, [rules]);

  const totalHits = useMemo(() => rules.reduce((sum, r) => sum + (r.hitCount || 0), 0), [rules]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="cyber-card p-4 text-center">
          <p className="text-2xl font-bold text-foreground">{rules.length}</p>
          <p className="text-xs text-muted-foreground mt-1">分析规则数</p>
        </div>
        <div className="cyber-card p-4 text-center">
          <p className="text-2xl font-bold text-foreground">{totalHits}</p>
          <p className="text-xs text-muted-foreground mt-1">总命中数</p>
        </div>
        <div className="cyber-card p-4 text-center">
          <p className="text-2xl font-bold text-rose-400">{severityCounts.high}</p>
          <p className="text-xs text-muted-foreground mt-1">高危规则</p>
        </div>
        <div className="cyber-card p-4 text-center">
          <p className="text-2xl font-bold text-amber-400">{severityCounts.medium}</p>
          <p className="text-xs text-muted-foreground mt-1">中危规则</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="cyber-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">严重度分布</h3>
          <div className="space-y-2">
            {(["high", "medium", "low"] as const).map((sev) => {
              const count = severityCounts[sev];
              const total = rules.length || 1;
              const pct = Math.round((count / total) * 100);
              const colors = { high: "bg-rose-500", medium: "bg-amber-500", low: "bg-sky-500" };
              const labels = { high: "高危", medium: "中危", low: "低危" };
              return (
                <div key={sev} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-10">{labels[sev]}</span>
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${colors[sev]}`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-xs text-muted-foreground w-8 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="cyber-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">修复优先级分布</h3>
          <div className="space-y-2">
            {(["high", "medium", "low"] as const).map((pri) => {
              const count = priorityCounts[pri];
              const total = rules.length || 1;
              const pct = Math.round((count / total) * 100);
              const colors = { high: "bg-rose-500", medium: "bg-amber-500", low: "bg-emerald-500" };
              const labels = { high: "高", medium: "中", low: "低" };
              return (
                <div key={pri} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-10">{labels[pri]}</span>
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full ${colors[pri]}`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-xs text-muted-foreground w-8 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {data.model && (
        <div className="text-xs text-muted-foreground">
          模型: {data.model} · 分析完成于 {data.completed_at ? new Date(data.completed_at).toLocaleString("zh-CN") : "-"}
        </div>
      )}
    </div>
  );
}

function RuleDetailsTab({ data }: { data: AiAnalysisStatusResponse }) {
  const rules = data.result?.rules ?? [];
  if (rules.length === 0) return <div className="text-muted-foreground text-center py-8">暂无规则分析数据</div>;

  return (
    <div className="space-y-4">
      {rules.map((rule, index) => (
        <div key={rule.ruleName || index} className="cyber-card p-5 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-base">{rule.ruleName}</span>
              <Badge className={`text-xs ${rule.severity === "ERROR" || rule.severity === "HIGH" ? "border-rose-500/40 text-rose-300" : rule.severity === "WARNING" || rule.severity === "MEDIUM" ? "border-amber-500/40 text-amber-300" : "border-border text-muted-foreground"}`}>
                {rule.severity}
              </Badge>
            </div>
            <span className="text-sm text-muted-foreground">命中 {rule.hitCount} 次</span>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">问题描述</p>
            <p className="text-sm leading-relaxed">{rule.problem}</p>
          </div>
          {rule.codeExamples && rule.codeExamples.length > 0 && (
            <div>
              <p className="text-sm font-medium text-muted-foreground mb-1">代码示例</p>
              {rule.codeExamples.map((ex, i) => (
                <div key={i} className="rounded bg-black/40 border border-border p-3 mt-1">
                  <p className="text-xs text-muted-foreground mb-1">{ex.file}</p>
                  <pre className="text-sm font-mono whitespace-pre-wrap text-foreground">{ex.code}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function FixSuggestionsTab({ data }: { data: AiAnalysisStatusResponse }) {
  const rules = useMemo(() => {
    const items = [...(data.result?.rules ?? [])];
    const order = { high: 0, medium: 1, low: 2 };
    items.sort((a, b) => (order[a.priority as keyof typeof order] ?? 2) - (order[b.priority as keyof typeof order] ?? 2));
    return items;
  }, [data]);

  if (rules.length === 0) return <div className="text-muted-foreground text-center py-8">暂无修复建议</div>;

  return (
    <div className="space-y-4">
      {rules.map((rule, index) => (
        <div key={rule.ruleName || index} className="cyber-card p-5 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold">{rule.ruleName}</span>
              {rule.priority && (
                <Badge className={`text-xs ${rule.priority === "high" ? "border-rose-500/40 text-rose-300" : rule.priority === "medium" ? "border-amber-500/40 text-amber-300" : "border-emerald-500/40 text-emerald-300"}`}>
                  优先级: {rule.priority}
                </Badge>
              )}
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">修复建议</p>
            <p className="text-sm leading-relaxed">{rule.suggestion}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AiAnalysisResult() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<AiAnalysisStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!taskId) return;
    try {
      const result = await getAiAnalysisStatus(taskId);
      setData(result);
      return result;
    } catch {
      toast.error("获取分析状态失败");
      return null;
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (data?.status === "analyzing") {
      pollRef.current = setInterval(() => {
        void fetchStatus();
      }, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [data?.status, fetchStatus]);

  const handleTrigger = async () => {
    if (!taskId) return;
    setTriggering(true);
    try {
      await triggerAiAnalysis(taskId);
      toast.success("AI 分析任务已启动");
      await fetchStatus();
    } catch (error: any) {
      const msg = error?.response?.data?.error || error?.message || "启动分析失败";
      toast.error(msg);
    } finally {
      setTriggering(false);
    }
  };

  const handleReAnalyze = async () => {
    await handleTrigger();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-6 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const status = data?.status ?? "not_started";

  return (
    <div className="space-y-5 p-6 bg-background min-h-screen">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-wider uppercase text-foreground">
            AI 研判分析
          </h1>
          {status === "completed" && (
            <Badge className="cyber-badge cyber-badge-info">已完成</Badge>
          )}
          {status === "analyzing" && (
            <Badge className="cyber-badge border-sky-500/40 text-sky-300">分析中</Badge>
          )}
          {status === "failed" && (
            <Badge className="cyber-badge border-rose-500/40 text-rose-300">失败</Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {status === "completed" && (
            <Button
              variant="outline"
              className="cyber-btn-outline h-8"
              onClick={() => void handleReAnalyze()}
              disabled={triggering}
            >
              {triggering ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
              重新分析
            </Button>
          )}
          <Button
            variant="outline"
            className="cyber-btn-outline h-8"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            返回
          </Button>
        </div>
      </div>

      {status === "not_started" && (
        <div className="cyber-card p-12 flex flex-col items-center gap-6">
          <StepTimeline currentStep={null} status="not_started" />
          <p className="text-sm text-muted-foreground">点击下方按钮，将依次执行以上 3 个分析步骤</p>
          <Button
            className="cyber-btn-outline h-10 px-6"
            variant="outline"
            onClick={() => void handleTrigger()}
            disabled={triggering}
          >
            {triggering ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
            开始分析
          </Button>
        </div>
      )}

      {status === "analyzing" && (
        <div className="cyber-card p-12 flex flex-col items-center gap-6">
          <StepTimeline currentStep={data?.current_step ?? 1} status="analyzing" />
          <p className="text-sm text-primary">
            正在执行: {data?.step_name ?? "分析中"}...
          </p>
        </div>
      )}

      {status === "failed" && (
        <div className="cyber-card p-12 flex flex-col items-center gap-6">
          <AlertCircle className="w-10 h-10 text-rose-400" />
          <p className="text-sm text-rose-300">{data?.error || "分析执行失败"}</p>
          <Button
            className="cyber-btn-outline h-10 px-6"
            variant="outline"
            onClick={() => void handleTrigger()}
            disabled={triggering}
          >
            {triggering ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            重新分析
          </Button>
        </div>
      )}

      {status === "completed" && data && (
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="w-full justify-start border-b border-border bg-transparent rounded-none h-auto p-0 gap-0">
            <TabsTrigger value="overview" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2.5">
              概览
            </TabsTrigger>
            <TabsTrigger value="rules" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2.5">
              规则详情
            </TabsTrigger>
            <TabsTrigger value="fixes" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2.5">
              修复建议
            </TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="mt-4">
            <OverviewTab data={data} />
          </TabsContent>
          <TabsContent value="rules" className="mt-4">
            <RuleDetailsTab data={data} />
          </TabsContent>
          <TabsContent value="fixes" className="mt-4">
            <FixSuggestionsTab data={data} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
