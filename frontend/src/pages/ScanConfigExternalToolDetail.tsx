import { useEffect, useMemo, useState } from "react";
import { Navigate, Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Play, Square, Trash2, Wrench } from "lucide-react";
import { toast } from "sonner";

import ToolEvidencePreview from "@/pages/AgentAudit/components/ToolEvidencePreview";
import { parseToolEvidenceFromLog } from "@/pages/AgentAudit/toolEvidence";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import SilentLoadingState from "@/components/performance/SilentLoadingState";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type ExternalToolResourcePayload,
  type ExternalToolType,
  type PromptSkillDetailPayload,
  type PromptSkillScopePayload,
} from "@/shared/api/database";
import PromptSkillEditorDialog from "@/pages/intelligent-scan/PromptSkillEditorDialog";
import {
  buildPromptSkillAgentOptions,
  buildPromptSkillFormState,
  extractPromptSkillErrorMessage,
  normalizePromptSkillUpdatePayload,
  resolvePromptAgentLabel,
  scopeLabel,
  type PromptSkillFormState,
} from "@/pages/intelligent-scan/promptSkillShared";
import SkillTestEventLog from "@/pages/skill-test/components/SkillTestEventLog";
import type {
  SkillDetailResponse,
  SkillTestEvent,
  SkillTestResult,
  ToolTestPreset,
} from "@/pages/skill-test/types";
import { useSkillTestStream } from "@/pages/skill-test/useSkillTestStream";

function normalizeScanCoreDetail(
  resource: ExternalToolResourcePayload,
): SkillDetailResponse | null {
  const detail = resource.scan_core_detail;
  if (!detail) {
    return null;
  }

  return {
    enabled: detail.enabled,
    skill_id: detail.skill_id,
    name: detail.name,
    namespace: detail.namespace,
    summary: detail.summary,
    category: detail.category,
    goal: detail.goal,
    task_list: detail.task_list,
    input_checklist: detail.input_checklist,
    example_input: detail.example_input,
    pitfalls: detail.pitfalls,
    sample_prompts: detail.sample_prompts,
    entrypoint: detail.entrypoint,
    mirror_dir: detail.mirror_dir,
    source_root: detail.source_root,
    source_dir: detail.source_dir,
    source_skill_md: detail.source_skill_md,
    aliases: detail.aliases,
    has_scripts: detail.has_scripts,
    has_bin: detail.has_bin,
    has_assets: detail.has_assets,
    files_count: detail.files_count,
    workflow_content: detail.workflow_content,
    workflow_truncated: detail.workflow_truncated,
    workflow_error: detail.workflow_error,
    test_supported: detail.test_supported,
    test_mode: detail.test_mode,
    test_reason: detail.test_reason,
    default_test_project_name: detail.default_test_project_name,
    tool_test_preset: (detail.tool_test_preset as ToolTestPreset | null) ?? null,
  };
}

function decodeToolId(rawToolId?: string) {
  if (!rawToolId) return "";
  try {
    return decodeURIComponent(rawToolId);
  } catch {
    return rawToolId;
  }
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

function resolveToolBadgeLabel(toolType: ExternalToolType) {
  if (toolType === "skill") return "SCAN CORE";
  if (toolType === "prompt-builtin") return "BUILTIN PROMPT";
  return "CUSTOM PROMPT";
}

export interface ExternalToolDetailContentProps {
  toolType: ExternalToolType;
  toolId: string;
  toolName: string;
  skillDetail?: SkillDetailResponse | null;
  promptSkillDetail?: PromptSkillDetailPayload | null;
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
  promptSkillBusy?: boolean;
  onTogglePromptSkill?: () => void;
  onEditPromptSkill?: () => void;
  onDeletePromptSkill?: () => void;
  returnToSearch?: string;
}

function ToolHeader({
  toolType,
  toolName,
  toolId,
  returnToSearch = "",
}: {
  toolType: ExternalToolType;
  toolName: string;
  toolId: string;
  returnToSearch?: string;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-3">
        <div className="section-header mb-1">
          <Wrench className="w-4 h-4 text-primary" />
          <div className="font-mono font-bold uppercase text-sm text-foreground">
            {toolType === "skill" ? "外部工具详情" : "Prompt Skill 详情"}
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-lg font-mono font-semibold text-foreground break-all">{toolName}</div>
            <Badge variant="outline" className="text-[10px] uppercase">
              {resolveToolBadgeLabel(toolType)}
            </Badge>
          </div>
          <div className="text-xs font-mono text-muted-foreground break-all">{toolId || "-"}</div>
        </div>
      </div>

      <Button asChild variant="outline" size="sm" className="cyber-btn-ghost h-8 px-3">
        <Link to={`/scan-config/external-tools${returnToSearch}`}>
          <ArrowLeft className="w-4 h-4" />
          返回列表
        </Link>
      </Button>
    </div>
  );
}

function SkillOverview({
  skillDetail,
}: {
  skillDetail: SkillDetailResponse;
}) {
  return (
    <div className="space-y-4 border-t border-border/50 pt-6">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{skillDetail.category || "未分类"}</Badge>
        <Badge variant="outline">
          {formatTestModeLabel(skillDetail.test_mode, skillDetail.test_supported)}
        </Badge>
        <Badge variant="outline">默认数据集 {skillDetail.default_test_project_name}</Badge>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">概览</div>
          <p className="text-sm leading-7 text-foreground/90">{skillDetail.summary}</p>
          <p className="text-sm leading-7 text-muted-foreground">{skillDetail.goal || "暂无补充目标说明。"}</p>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">任务列表</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {skillDetail.task_list.map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">输入说明</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {skillDetail.input_checklist.map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">注意事项</div>
          <ul className="space-y-2 text-sm leading-6 text-foreground/90">
            {skillDetail.pitfalls.map((item) => (
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
            默认项目固定为 {skillDetail.default_test_project_name}，仅允许当前 skill 和测试 runner 必需的宿主辅助能力。
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

function PromptSkillDetailSection({
  detail,
  busy,
  onToggle,
  onEdit,
  onDelete,
}: {
  detail: PromptSkillDetailPayload;
  busy: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const agentLabel =
    detail.scope === "global"
      ? "全部智能体"
      : resolvePromptAgentLabel({
          agentKey: detail.agent_key,
          agentLabel: detail.agent_label,
          displayName: detail.display_name,
        });

  return (
    <div className="space-y-6 border-t border-border/50 pt-6">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{detail.resource_kind_label}</Badge>
        <Badge variant={detail.is_enabled ? "default" : "secondary"}>
          {detail.status_label}
        </Badge>
        {detail.scope ? <Badge variant="outline">{scopeLabel(detail.scope)}</Badge> : null}
        <Badge variant="outline">{agentLabel}</Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">
            概览
          </div>
          <p className="text-sm leading-7 text-foreground/90">{detail.summary}</p>
          <div className="text-xs font-mono text-muted-foreground">
            {detail.scope ? scopeLabel(detail.scope) : "内置"} · {agentLabel}
          </div>
        </div>
        <div className="space-y-3 rounded border border-border/40 bg-background/40 p-4">
          <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">
            操作
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="cyber-btn-ghost h-8 px-3"
              onClick={onToggle}
              disabled={busy || !detail.can_toggle}
            >
              {detail.is_enabled ? "停用" : "启用"}
            </Button>
            {detail.can_edit ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="cyber-btn-ghost h-8 px-3"
                onClick={onEdit}
                disabled={busy}
              >
                编辑
              </Button>
            ) : null}
            {detail.can_delete ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 border-red-500/40 px-3 text-red-400 hover:text-red-300"
                onClick={onDelete}
                disabled={busy}
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <div className="space-y-3 rounded border border-border/40 bg-background/30 p-4">
        <div className="text-xs font-mono uppercase tracking-[0.28em] text-muted-foreground">
          Skill 内容
        </div>
        <div className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground/90">
          {detail.content}
        </div>
      </div>
    </div>
  );
}

export function ScanConfigExternalToolDetailContent({
  toolType,
  toolId,
  toolName,
  skillDetail = null,
  promptSkillDetail = null,
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
  promptSkillBusy = false,
  onTogglePromptSkill = () => {},
  onEditPromptSkill = () => {},
  onDeletePromptSkill = () => {},
  returnToSearch = "",
}: ExternalToolDetailContentProps) {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <div className="cyber-card p-5 space-y-6">
          <ToolHeader
            toolType={toolType}
            toolName={toolName}
            toolId={toolId}
            returnToSearch={returnToSearch}
          />
          {loading ? (
            <SilentLoadingState
              className="border-t border-border/50 pt-6"
              minHeight={96}
            />
          ) : error ? (
            <div className="border-t border-border/50 pt-6 text-sm text-red-300">{error}</div>
          ) : toolType !== "skill" && promptSkillDetail ? (
            <PromptSkillDetailSection
              detail={promptSkillDetail}
              busy={promptSkillBusy}
              onToggle={onTogglePromptSkill}
              onEdit={onEditPromptSkill}
              onDelete={onDeletePromptSkill}
            />
          ) : skillDetail ? (
            <div className="space-y-6 border-t border-border/50 pt-6">
              <SkillOverview skillDetail={skillDetail} />
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
            <div className="border-t border-border/50 pt-6 text-sm text-muted-foreground">
              未找到{toolType === "skill" ? "技能" : "Prompt Skill"}详情。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ScanConfigExternalToolDetail() {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams<{ toolType?: string; toolId?: string }>();
  const rawToolType = params.toolType;
  const toolId = decodeToolId(params.toolId);
  const toolType = rawToolType as ExternalToolType | undefined;
  const returnToSearch = location.search || "";

  const [skillDetail, setSkillDetail] = useState<SkillDetailResponse | null>(null);
  const [promptSkillDetail, setPromptSkillDetail] =
    useState<PromptSkillDetailPayload | null>(null);
  const [promptSkillList, setPromptSkillList] =
    useState<Awaited<ReturnType<typeof api.getPromptSkills>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [promptSkillBusy, setPromptSkillBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [toolTestPreset, setToolTestPreset] = useState<ToolTestPreset | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<PromptSkillFormState>(
    buildPromptSkillFormState(null),
  );

  const agentOptions = useMemo(
    () =>
      buildPromptSkillAgentOptions({
        supportedAgentKeys: promptSkillList?.supportedAgentKeys,
        builtinAgentKeys: promptSkillList?.builtinItems.map((item) => item.agent_key),
        customAgentKeys: promptSkillList?.items.map((item) => item.agent_key),
      }),
    [promptSkillList],
  );
  const toolName = useMemo(() => {
    if (promptSkillDetail) {
      return promptSkillDetail.name;
    }
    if (toolType === "prompt-custom") {
      return toolId || "Prompt Skill";
    }
    if (toolType === "prompt-builtin") {
      return toolId || "Prompt Skill";
    }
    return skillDetail?.name || toolId || "外部工具";
  }, [promptSkillDetail, skillDetail, toolId, toolType]);
  const examplePrompts = useMemo(() => skillDetail?.sample_prompts ?? [], [skillDetail]);
  const { events, running, result, runPrompt, runStructured, stop } =
    useSkillTestStream(toolType === "skill" ? toolId : "");

  useEffect(() => {
    setPrompt((previous) => previous || examplePrompts[0] || "");
  }, [examplePrompts]);

  useEffect(() => {
    setToolTestPreset(skillDetail?.tool_test_preset ?? null);
  }, [skillDetail]);

  useEffect(() => {
    if (!toolId) return;
    let cancelled = false;

    async function loadDetail() {
      setLoading(true);
      setError(null);
      try {
        const [detailPayload, promptPayload] = await Promise.all([
          api.getExternalToolResourceDetail(toolType!, toolId),
          toolType === "skill" ? Promise.resolve(null) : api.getPromptSkills({ limit: 1 }),
        ]);

        if (cancelled) {
          return;
        }

        if (toolType === "skill") {
          setSkillDetail(normalizeScanCoreDetail(detailPayload));
          setPromptSkillDetail(null);
        } else {
          if (!detailPayload.content) {
            throw new Error("未找到 Prompt Skill 详情");
          }
          setPromptSkillList(promptPayload);
          setPromptSkillDetail(detailPayload as PromptSkillDetailPayload);
          setSkillDetail(null);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "加载详情失败");
          setSkillDetail(null);
          setPromptSkillDetail(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [toolId, toolType]);

  useEffect(() => {
    if (promptSkillDetail) {
      setForm(buildPromptSkillFormState(promptSkillDetail));
    }
  }, [promptSkillDetail]);

  const handlePromptScopeChange = (nextScope: PromptSkillScopePayload) => {
    setForm((current) => ({
      ...current,
      scope: nextScope,
      agent_key:
        nextScope === "agent_specific"
          ? current.agent_key || agentOptions[0]?.key || ""
          : "",
    }));
  };

  const handleTogglePromptSkill = async () => {
    if (!promptSkillDetail) {
      return;
    }
    setPromptSkillBusy(true);
    try {
      if (promptSkillDetail.tool_type === "prompt-builtin") {
        await api.updateBuiltinPromptSkill(promptSkillDetail.tool_id, {
          is_active: !promptSkillDetail.is_enabled,
        });
      } else {
        await api.updatePromptSkill(promptSkillDetail.tool_id, {
          is_active: !promptSkillDetail.is_enabled,
        });
      }
      const [detailPayload, promptPayload] = await Promise.all([
        api.getExternalToolResourceDetail(promptSkillDetail.tool_type, promptSkillDetail.tool_id),
        api.getPromptSkills({ limit: 1 }),
      ]);
      setPromptSkillList(promptPayload);
      setPromptSkillDetail(detailPayload as PromptSkillDetailPayload);
      toast.success(
        promptSkillDetail.is_enabled ? "Prompt Skill 已停用" : "Prompt Skill 已启用",
      );
    } catch (toggleError) {
      toast.error(`更新状态失败：${extractPromptSkillErrorMessage(toggleError)}`);
    } finally {
      setPromptSkillBusy(false);
    }
  };

  const handleSavePromptSkill = async () => {
    if (!promptSkillDetail || promptSkillDetail.tool_type !== "prompt-custom") {
      return;
    }
    const name = form.name.trim();
    const content = form.content.trim();
    if (!name) {
      toast.error("请填写 Skill 名称");
      return;
    }
    if (!content) {
      toast.error("请填写 Skill 内容");
      return;
    }
    if (form.scope === "agent_specific" && !form.agent_key) {
      toast.error("请选择目标智能体");
      return;
    }

    setSaving(true);
    try {
      await api.updatePromptSkill(
        promptSkillDetail.tool_id,
        normalizePromptSkillUpdatePayload(form),
      );
      const [detailPayload, promptPayload] = await Promise.all([
        api.getExternalToolResourceDetail("prompt-custom", promptSkillDetail.tool_id),
        api.getPromptSkills({ limit: 1 }),
      ]);
      setPromptSkillList(promptPayload);
      setPromptSkillDetail(detailPayload as PromptSkillDetailPayload);
      setDialogOpen(false);
      toast.success("Prompt Skill 已更新");
    } catch (saveError) {
      toast.error(`保存失败：${extractPromptSkillErrorMessage(saveError)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePromptSkill = async () => {
    if (!promptSkillDetail || promptSkillDetail.tool_type !== "prompt-custom") {
      return;
    }
    if (!window.confirm(`确认删除 Prompt Skill「${promptSkillDetail.name}」？`)) {
      return;
    }
    setPromptSkillBusy(true);
    try {
      await api.deletePromptSkill(promptSkillDetail.tool_id);
      toast.success("Prompt Skill 已删除");
      navigate(`/scan-config/external-tools${returnToSearch}`);
    } catch (deleteError) {
      toast.error(`删除失败：${extractPromptSkillErrorMessage(deleteError)}`);
    } finally {
      setPromptSkillBusy(false);
    }
  };

  if (
    toolType !== "skill" &&
    toolType !== "prompt-builtin" &&
    toolType !== "prompt-custom"
  ) {
    return <Navigate to="/scan-config/external-tools" replace />;
  }

  return (
    <>
      <ScanConfigExternalToolDetailContent
        toolType={toolType}
        toolId={toolId}
        toolName={toolName}
        skillDetail={skillDetail}
        promptSkillDetail={promptSkillDetail}
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
        promptSkillBusy={promptSkillBusy}
        onTogglePromptSkill={() => void handleTogglePromptSkill()}
        onEditPromptSkill={() => setDialogOpen(true)}
        onDeletePromptSkill={() => void handleDeletePromptSkill()}
        returnToSearch={returnToSearch}
      />
      {promptSkillDetail?.tool_type === "prompt-custom" ? (
        <PromptSkillEditorDialog
          open={dialogOpen}
          saving={saving}
          title="编辑 Prompt Skill"
          description="更新当前自定义 Prompt Skill 的作用域和注入内容。"
          submitLabel="保存修改"
          form={form}
          agentOptions={agentOptions}
          onOpenChange={setDialogOpen}
          onFormChange={(updater) => setForm((current) => updater(current))}
          onScopeChange={handlePromptScopeChange}
          onSubmit={() => void handleSavePromptSkill()}
        />
      ) : null}
    </>
  );
}
