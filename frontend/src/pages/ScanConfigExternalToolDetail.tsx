import { useEffect, useMemo, useState } from "react";
import { Navigate, Link, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Play, Square, Wrench } from "lucide-react";

import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";
import { parseToolEvidenceFromLog } from "@/pages/AgentAudit/toolEvidence";
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
  ToolTestPreset,
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
    get_code_window: ["读取 plist 解析入口附近的最小代码窗口", "请围绕 src/main.c 第 12 行取证"],
    search_code: ["搜索 plist_from_memory 的调用位置", "帮我定位 XML 解析相关函数"],
    list_files: ["列出和 plist 解析最相关的源文件", "列出 src 目录下的核心 C 文件"],
    get_file_outline: ["概览 src/main.c 的整体职责", "这个文件在 plist 解析流程里扮演什么角色？"],
    get_function_summary: ["总结 plist_from_memory 函数做什么", "帮我理解主解析入口函数的风险点"],
    get_symbol_body: ["提取 plist_from_memory 函数源码", "提取主解析入口函数代码"],
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

function formatTestModeLabel(testMode: SkillDetailResponse["test_mode"], testSupported: boolean) {
  if (!testSupported) return "测试已禁用";
  if (testMode === "structured_tool") return "结构化工具测试";
  return "单技能严格模式";
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

function updateToolPresetField(
  preset: ToolTestPreset,
  field: keyof Omit<ToolTestPreset, "tool_input" | "project_name">,
  value: string,
): ToolTestPreset {
  if (field === "line_start" || field === "line_end") {
    const normalized = value.trim();
    return {
      ...preset,
      [field]: normalized ? Number(normalized) : null,
    };
  }
  return {
    ...preset,
    [field]: value,
  };
}

function toolInputListValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join("\n");
  }
  return String(value ?? "");
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
  toolTestPreset?: ToolTestPreset | null;
  onToolTestPresetChange?: (next: ToolTestPreset) => void;
  onRunStructured?: () => void;
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
          {formatTestModeLabel(skillDetail.test_mode, skillDetail.test_supported)}
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
          <div className="mt-1 text-sm text-muted-foreground">
            默认项目固定为 {skillDetail.default_test_project_name}，仅允许当前 skill + think / reflect。
          </div>
        </div>
        <Badge variant="outline">{running ? "运行中" : skillDetail.test_supported ? "可运行" : "已禁用"}</Badge>
      </div>
      {skillDetail.test_supported ? (
        <>
          <Textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            placeholder="请输入基于 libplist 的自然语言测试问题"
          />
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

function StructuredToolTestBench({
  toolId,
  skillDetail,
  toolTestPreset,
  running,
  onToolTestPresetChange,
  onRun,
  onStop,
}: {
  toolId: string;
  skillDetail: SkillDetailResponse;
  toolTestPreset: ToolTestPreset | null;
  running: boolean;
  onToolTestPresetChange: (next: ToolTestPreset) => void;
  onRun: () => void;
  onStop: () => void;
}) {
  const preset = toolTestPreset ?? skillDetail.tool_test_preset;
  if (!preset) {
    return (
      <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-6 text-amber-100">
        当前 skill 缺少结构化测试预置参数。
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded border border-border/40 bg-background/30 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">
            结构化工具测试
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            默认项目固定为 {skillDetail.default_test_project_name}，运行前会先通过 flow parser runner
            解析 `{preset.function_name}` 的函数范围。
          </div>
        </div>
        <Badge variant="outline">{running ? "运行中" : "可运行"}</Badge>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1">
          <div className="text-xs font-mono text-muted-foreground">file_path</div>
          <input
            value={preset.file_path}
            onChange={(event) =>
              onToolTestPresetChange(updateToolPresetField(preset, "file_path", event.target.value))
            }
            className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
          />
        </label>
        <label className="space-y-1">
          <div className="text-xs font-mono text-muted-foreground">function_name</div>
          <input
            value={preset.function_name}
            onChange={(event) =>
              onToolTestPresetChange(updateToolPresetField(preset, "function_name", event.target.value))
            }
            className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
          />
        </label>
        <label className="space-y-1">
          <div className="text-xs font-mono text-muted-foreground">line_start</div>
          <input
            value={preset.line_start ?? ""}
            onChange={(event) =>
              onToolTestPresetChange(updateToolPresetField(preset, "line_start", event.target.value))
            }
            className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
          />
        </label>
        <label className="space-y-1">
          <div className="text-xs font-mono text-muted-foreground">line_end</div>
          <input
            value={preset.line_end ?? ""}
            onChange={(event) =>
              onToolTestPresetChange(updateToolPresetField(preset, "line_end", event.target.value))
            }
            className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
          />
        </label>
      </div>

      {toolId === "dataflow_analysis" ? (
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <div className="text-xs font-mono text-muted-foreground">variable_name</div>
            <input
              value={String(preset.tool_input.variable_name ?? "")}
              onChange={(event) =>
                onToolTestPresetChange({
                  ...preset,
                  tool_input: {
                    ...preset.tool_input,
                    variable_name: event.target.value,
                  },
                })
              }
              className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-mono text-muted-foreground">sink_hints</div>
            <Textarea
              value={toolInputListValue(preset.tool_input.sink_hints)}
              onChange={(event) =>
                onToolTestPresetChange({
                  ...preset,
                  tool_input: {
                    ...preset.tool_input,
                    sink_hints: event.target.value
                      .split(/\r?\n|,/)
                      .map((item) => item.trim())
                      .filter(Boolean),
                  },
                })
              }
              placeholder="每行一个 sink hint"
            />
          </label>
        </div>
      ) : null}

      {toolId === "controlflow_analysis_light" ? (
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <div className="text-xs font-mono text-muted-foreground">entry_points</div>
            <Textarea
              value={toolInputListValue(preset.tool_input.entry_points)}
              onChange={(event) =>
                onToolTestPresetChange({
                  ...preset,
                  tool_input: {
                    ...preset.tool_input,
                    entry_points: event.target.value
                      .split(/\r?\n|,/)
                      .map((item) => item.trim())
                      .filter(Boolean),
                  },
                })
              }
              placeholder="每行一个 entry point"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-mono text-muted-foreground">vulnerability_type</div>
            <input
              value={String(preset.tool_input.vulnerability_type ?? "")}
              onChange={(event) =>
                onToolTestPresetChange({
                  ...preset,
                  tool_input: {
                    ...preset.tool_input,
                    vulnerability_type: event.target.value,
                  },
                })
              }
              className="cyber-input h-9 w-full rounded-sm border border-input bg-background px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
            />
          </label>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={onRun}
          disabled={running || !preset.file_path.trim() || !preset.function_name.trim()}
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          运行测试
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onStop} disabled={!running}>
          <Square className="w-4 h-4" />
          停止
        </Button>
      </div>
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
  const latestEvidence = [...events].reverse().find((event) => {
    if (event.type !== "tool_result") return false;
    const parsed = parseToolEvidenceFromLog({
      toolName: event.tool_name,
      toolOutput: event.tool_output,
      toolMetadata: event.metadata ?? null,
    });
    return Boolean(parsed?.payload);
  });
  const evidence = latestEvidence
    ? parseToolEvidenceFromLog({
        toolName: latestEvidence.tool_name,
        toolOutput: latestEvidence.tool_output,
        toolMetadata: latestEvidence.metadata ?? null,
      })
    : null;

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
          {result.test_mode === "structured_tool" ? (
            <div className="rounded border border-border/30 bg-black/20 p-3 text-xs font-mono text-muted-foreground">
              <div>tool_name: {result.tool_name ?? "-"}</div>
              <div>target_function: {result.target_function ?? "-"}</div>
              <div>resolved_file_path: {result.resolved_file_path ?? "-"}</div>
              <div>
                resolved_lines: {result.resolved_line_start ?? "-"} - {result.resolved_line_end ?? "-"}
              </div>
              <div>runner_image: {result.runner_image ?? "-"}</div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">暂无最终结果，运行测试后会在这里展示 `final_text` 与清理状态。</div>
      )}
      {evidence?.payload ? <ToolEvidencePreview evidence={evidence} /> : null}
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
  toolTestPreset = null,
  onToolTestPresetChange = () => {},
  onRunStructured = () => {},
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
              {skillDetail.test_mode === "structured_tool" ? (
                <StructuredToolTestBench
                  toolId={toolId}
                  skillDetail={skillDetail}
                  toolTestPreset={toolTestPreset}
                  running={running}
                  onToolTestPresetChange={onToolTestPresetChange}
                  onRun={onRunStructured}
                  onStop={onStop}
                />
              ) : (
                <SkillTestBench
                  skillDetail={skillDetail}
                  prompt={prompt}
                  examplePrompts={examplePrompts}
                  running={running}
                  onPromptChange={onPromptChange}
                  onRun={onRun}
                  onStop={onStop}
                />
              )}
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
  const [toolTestPreset, setToolTestPreset] = useState<ToolTestPreset | null>(null);

  const skillCatalogItem = useMemo(
    () => SKILL_TOOLS_CATALOG.find((item) => item.id === toolId) ?? null,
    [toolId],
  );
  const toolName = useMemo(() => resolveToolName(toolId), [toolId]);
  const examplePrompts = useMemo(() => buildSkillExamplePrompts(toolId), [toolId]);
  const { events, running, result, runPrompt, runStructured, stop } = useSkillTestStream(toolId);

  useEffect(() => {
    setPrompt((previous) => previous || examplePrompts[0] || "");
  }, [examplePrompts]);

  useEffect(() => {
    setToolTestPreset(skillDetail?.tool_test_preset ?? null);
  }, [skillDetail]);

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
      onRun={() => void runPrompt(prompt)}
      onStop={stop}
      toolTestPreset={toolTestPreset}
      onToolTestPresetChange={setToolTestPreset}
      onRunStructured={() => {
        if (toolTestPreset) {
          void runStructured(toolTestPreset);
        }
      }}
      loading={loading}
      error={error}
    />
  );
}
