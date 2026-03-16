import { useEffect, useMemo, useState } from "react";
import { Navigate, Link, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Play, Square, Wrench } from "lucide-react";

import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";
import { parseToolEvidence } from "@/pages/AgentAudit/toolEvidence";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  SKILL_TOOLS_CATALOG,
  type SkillToolCatalogItem,
} from "@/pages/intelligent-scan/skillToolsCatalog";
import SkillTestEventLog from "@/pages/skill-test/components/SkillTestEventLog";
import type {
  SkillDetailResponse,
  SkillTestEvent,
  SkillTestResult,
} from "@/pages/skill-test/types";
import { useSkillTestStream } from "@/pages/skill-test/useSkillTestStream";

function decodeToolId(rawToolId?: string) {
  if (!rawToolId) return "";
  try {
    return decodeURIComponent(rawToolId);
  } catch {
    return rawToolId;
  }
}

function buildSkillExamplePrompts(skillId: string): string[] {
  const catalogPrompts: Record<string, string[]> = {
    read_file: ["读取 plist 解析入口", "请读取 src/main.c 的关键入口代码窗口"],
    search_code: ["搜索 plist_from_memory 的调用位置", "帮我定位 XML 解析相关函数"],
    list_files: ["列出和 plist 解析最相关的源文件", "列出 src 目录下的核心 C 文件"],
    extract_function: ["提取 plist_from_memory 函数", "提取主解析入口函数代码"],
    pattern_match: ["搜索是否存在 XML_PARSE_NOENT 风险模式", "帮我匹配危险解析选项"],
    smart_scan: ["请快速扫描 libplist 的高风险区域", "用 smart_scan 看看哪些文件值得优先阅读"],
    quick_audit: ["对 libplist 做一次快速审计", "请总结 libplist 的优先检查点"],
    think: ["如果我要先理解 libplist 的解析入口，你会怎么规划证据收集顺序？"],
    reflect: ["如果目前只读了入口文件，下一步还缺哪些证据？"],
  };
  return catalogPrompts[skillId] ?? ["这个 skill 在 libplist 上最适合怎么测试？"];
}

function resolveToolName(toolId: string): string {
  return SKILL_TOOLS_CATALOG.find((item) => item.id === toolId)?.id || toolId || "外部工具";
}

function resolveCleanupSummary(result: SkillTestResult | null, events: SkillTestEvent[]) {
  if (result?.cleanup) {
    return result.cleanup;
  }
  const cleanupEvent = [...events].reverse().find((event) => event.type === "project_cleanup");
  if (!cleanupEvent) return null;
  return {
    success: Boolean(cleanupEvent.metadata?.cleanup_success),
    temp_dir: String(cleanupEvent.metadata?.temp_dir ?? ""),
    error: cleanupEvent.metadata?.cleanup_error
      ? String(cleanupEvent.metadata?.cleanup_error ?? "")
      : null,
  };
}

export interface ExternalToolDetailContentProps {
  toolType: "skill";
  toolId: string;
  toolName: string;
  skillCatalogItem: SkillToolCatalogItem | null;
  skillDetail: SkillDetailResponse | null;
  prompt: string;
  examplePrompts: string[];
  events: SkillTestEvent[];
  result: SkillTestResult | null;
  running: boolean;
  onPromptChange: (nextPrompt: string) => void;
  onRun: () => void;
  onStop: () => void;
  loading?: boolean;
  error?: string | null;
}

function ToolHeader({ toolType, toolName, toolId }: { toolType: "skill"; toolName: string; toolId: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-3">
        <div className="section-header mb-1">
          <Wrench className="w-4 h-4 text-primary" />
          <div className="font-mono font-bold uppercase text-sm text-foreground">外部工具详情</div>
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-lg font-mono font-semibold text-foreground break-all">{toolName}</div>
            <Badge variant="outline" className="text-[10px] uppercase">
              {toolType === "skill" ? "SKILL" : ""}
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground break-all">{toolId || "-"}</div>
        </div>
      </div>

      <Button asChild variant="outline" size="sm" className="cyber-btn-ghost h-8 px-3">
        <Link to="/scan-config/external-tools">
          <ArrowLeft className="w-4 h-4" />
          返回列表
        </Link>
      </Button>
    </div>
  );
}

function SkillOverview({
  skillCatalogItem,
  skillDetail,
}: {
  skillCatalogItem: SkillToolCatalogItem | null;
  skillDetail: SkillDetailResponse;
}) {
  return (
    <div className="space-y-4 border-t border-border/50 pt-6">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{skillCatalogItem?.category ?? "未分类"}</Badge>
        <Badge variant="outline">
          {skillDetail.test_supported ? "单技能严格模式" : "测试已禁用"}
        </Badge>
        <Badge variant="outline">默认数据集 {skillDetail.default_test_project_name}</Badge>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">概览</div>
          <p className="text-sm leading-7 text-foreground/90">{skillDetail.summary}</p>
          <p className="text-sm leading-7 text-muted-foreground">{skillCatalogItem?.goal ?? "暂无补充目标说明。"}</p>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">任务列表</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {(skillCatalogItem?.taskList ?? []).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">输入说明</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {(skillCatalogItem?.inputChecklist ?? []).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">注意事项</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {(skillCatalogItem?.pitfalls ?? []).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function SkillTestBench({
  skillDetail,
  prompt,
  examplePrompts,
  running,
  onPromptChange,
  onRun,
  onStop,
}: {
  skillDetail: SkillDetailResponse;
  prompt: string;
  examplePrompts: string[];
  running: boolean;
  onPromptChange: (nextPrompt: string) => void;
  onRun: () => void;
  onStop: () => void;
}) {
  return (
    <div className="space-y-4 rounded border border-border/40 bg-background/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">测试台</div>
          <div className="mt-1 text-sm text-muted-foreground">默认项目固定为 {skillDetail.default_test_project_name}，仅允许当前 skill + think / reflect。</div>
        </div>
        <Badge variant="outline">{running ? "运行中" : skillDetail.test_supported ? "可运行" : "已禁用"}</Badge>
      </div>
      {skillDetail.test_supported ? (
        <>
          <Textarea value={prompt} onChange={(event) => onPromptChange(event.target.value)} placeholder="请输入基于 libplist 的自然语言测试问题" />
          <div className="space-y-2">
            <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">示例提问</div>
            <div className="flex flex-wrap gap-2">
              {examplePrompts.map((item) => (
                <Button key={item} type="button" variant="outline" size="sm" onClick={() => onPromptChange(item)}>
                  示例提问
                </Button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={onRun} disabled={running || !prompt.trim()}>
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              运行测试
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onStop} disabled={!running}>
              <Square className="w-4 h-4" />
              停止
            </Button>
          </div>
        </>
      ) : (
        <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-6 text-amber-100">
          <div className="font-mono text-xs uppercase tracking-[0.22em] text-amber-200">测试已禁用</div>
          <div className="mt-2">{skillDetail.test_reason ?? "当前 skill 暂未开放测试入口。"}</div>
        </div>
      )}
    </div>
  );
}

function SkillFinalResult({
  result,
  events,
}: {
  result: SkillTestResult | null;
  events: SkillTestEvent[];
}) {
  const cleanup = resolveCleanupSummary(result, events);
  const latestEvidence = [...events].reverse().find((event) => event.type === "tool_result" && parseToolEvidence(event.metadata ?? null));
  const evidence = latestEvidence ? parseToolEvidence(latestEvidence.metadata ?? null) : null;

  return (
    <div className="space-y-4 rounded border border-border/40 bg-background/30 p-4">
      <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">最终结果</div>
      {result ? (
        <div className="space-y-3 text-sm leading-7 text-foreground/90">
          <div>{result.final_text}</div>
          <div className="flex flex-wrap gap-2 text-xs font-mono text-muted-foreground">
            <span>测试项目 {result.project_name}</span>
            <span>模式 {result.test_mode}</span>
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">暂无最终结果，运行测试后会在这里展示 `final_text` 与清理状态。</div>
      )}
      {evidence ? <ToolEvidencePreview evidence={evidence} /> : null}
      {cleanup ? (
        <div className="rounded border border-border/30 bg-black/30 p-3 text-xs font-mono text-muted-foreground">
          <div>{cleanup.success ? "临时目录已清理" : "临时目录清理失败"}</div>
          <div className="mt-1 break-all">{cleanup.temp_dir}</div>
          {cleanup.error ? <div className="mt-1 text-red-300">{cleanup.error}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

export function ScanConfigExternalToolDetailContent({
  toolType,
  toolId,
  toolName,
  skillCatalogItem,
  skillDetail,
  prompt,
  examplePrompts,
  events,
  result,
  running,
  onPromptChange,
  onRun,
  onStop,
  loading = false,
  error = null,
}: ExternalToolDetailContentProps) {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <div className="cyber-card p-5 space-y-6">
          <ToolHeader toolType={toolType} toolName={toolName} toolId={toolId} />
          {loading ? (
            <div className="border-t border-border/50 pt-6 text-sm text-muted-foreground">加载技能详情中…</div>
          ) : error ? (
            <div className="border-t border-border/50 pt-6 text-sm text-red-300">{error}</div>
          ) : skillDetail ? (
            <div className="space-y-6 border-t border-border/50 pt-6">
              <SkillOverview skillCatalogItem={skillCatalogItem} skillDetail={skillDetail} />
              <SkillTestBench
                skillDetail={skillDetail}
                prompt={prompt}
                examplePrompts={examplePrompts}
                running={running}
                onPromptChange={onPromptChange}
                onRun={onRun}
                onStop={onStop}
              />
              <div className="space-y-3">
                <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">事件流</div>
                <SkillTestEventLog events={events} running={running} />
              </div>
              <SkillFinalResult result={result} events={events} />
            </div>
          ) : (
            <div className="border-t border-border/50 pt-6 text-sm text-muted-foreground">未找到技能详情。</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ScanConfigExternalToolDetail() {
  const params = useParams<{ toolType?: string; toolId?: string }>();
  const toolType = params.toolType;
  const toolId = decodeToolId(params.toolId);

  const [skillDetail, setSkillDetail] = useState<SkillDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");

  const skillCatalogItem = useMemo(
    () => SKILL_TOOLS_CATALOG.find((item) => item.id === toolId) ?? null,
    [toolId],
  );
  const toolName = useMemo(() => resolveToolName(toolId), [toolId]);
  const examplePrompts = useMemo(() => buildSkillExamplePrompts(toolId), [toolId]);
  const { events, running, result, run, stop } = useSkillTestStream(toolId);

  useEffect(() => {
    setPrompt((previous) => previous || examplePrompts[0] || "");
  }, [examplePrompts]);

  useEffect(() => {
    if (!toolId) return;
    let cancelled = false;

    async function loadSkillDetail() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/v1/skills/${encodeURIComponent(toolId)}`);
        if (!response.ok) {
          throw new Error(`加载技能详情失败: ${response.status}`);
        }
        const payload = (await response.json()) as SkillDetailResponse;
        if (!cancelled) {
          setSkillDetail(payload);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "加载技能详情失败");
          setSkillDetail(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSkillDetail();
    return () => {
      cancelled = true;
    };
  }, [toolId, toolType]);

  if (toolType !== "skill") {
    return <Navigate to="/scan-config/external-tools" replace />;
  }

  return (
    <ScanConfigExternalToolDetailContent
      toolType="skill"
      toolId={toolId}
      toolName={toolName}
      skillCatalogItem={skillCatalogItem}
      skillDetail={skillDetail}
      prompt={prompt}
      examplePrompts={examplePrompts}
      events={events}
      result={result}
      running={running}
      onPromptChange={setPrompt}
      onRun={() => void run(prompt)}
      onStop={stop}
      loading={loading}
      error={error}
    />
  );
}
