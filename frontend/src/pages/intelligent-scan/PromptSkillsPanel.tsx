import { useCallback, useEffect, useMemo, useState } from "react";
import { Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type PromptSkillBuiltinItemPayload,
  type PromptSkillCreatePayload,
  type PromptSkillItemPayload,
  type PromptSkillScopePayload,
  type PromptSkillUpdatePayload,
} from "@/shared/api/database";

const BUILTIN_PROMPT_SKILLS = [
  {
    key: "recon",
    agentLabel: "Recon Agent",
    content:
      "优先快速建立项目画像：先识别入口、认证边界、外部输入面，再按风险优先级推进目录扫描。所有风险点必须基于真实代码证据，并尽量附带触发条件。",
  },
  {
    key: "business_logic_recon",
    agentLabel: "Business Logic Recon Agent",
    content:
      "优先枚举业务对象与敏感动作，重点关注对象所有权、状态跃迁、金额计算、权限边界。若项目缺少业务入口，应尽早给出终止依据。",
  },
  {
    key: "analysis",
    agentLabel: "Analysis Agent",
    content:
      "围绕单风险点做证据闭环：先定位代码，再追踪输入到敏感操作的数据流与控制流，结论必须可复核并明确漏洞成立条件。",
  },
  {
    key: "business_logic_analysis",
    agentLabel: "Business Logic Analysis Agent",
    content:
      "优先验证授权与状态机约束，必须检查全局补偿逻辑（中间件、依赖注入、service guard、repository filter），避免将已补偿场景误报为漏洞。",
  },
  {
    key: "verification",
    agentLabel: "Verification Agent",
    content:
      "验证阶段必须坚持可复现证据优先：先读取上下文，再最小化构造触发路径。无法稳定触发时，应明确记录阻断条件并谨慎降级结论。",
  },
] as const;

const AGENT_OPTIONS = [
  { key: "recon", label: "Recon Agent" },
  { key: "business_logic_recon", label: "Business Logic Recon Agent" },
  { key: "analysis", label: "Analysis Agent" },
  { key: "business_logic_analysis", label: "Business Logic Analysis Agent" },
  { key: "verification", label: "Verification Agent" },
] as const;

const AGENT_LABEL_MAP: Record<string, string> = AGENT_OPTIONS.reduce(
  (acc, item) => {
    acc[item.key] = item.label;
    return acc;
  },
  {} as Record<string, string>,
);

type ScopeFilter = "all" | PromptSkillScopePayload;

type FormState = {
  name: string;
  content: string;
  scope: PromptSkillScopePayload;
  agent_key: string;
  is_active: boolean;
};

const DEFAULT_FORM: FormState = {
  name: "",
  content: "",
  scope: "global",
  agent_key: "",
  is_active: true,
};

function extractErrorMessage(error: unknown): string {
  const maybeAxios = error as {
    response?: {
      data?: {
        detail?: string;
      };
    };
    message?: string;
  };
  const detail = maybeAxios?.response?.data?.detail;
  if (detail && String(detail).trim()) {
    return String(detail);
  }
  return String(maybeAxios?.message || "请求失败");
}

function scopeLabel(scope: PromptSkillScopePayload): string {
  return scope === "global" ? "通用" : "智能体专属";
}

function normalizeCreatePayload(form: FormState): PromptSkillCreatePayload {
  return {
    name: form.name.trim(),
    content: form.content.trim(),
    scope: form.scope,
    agent_key: form.scope === "agent_specific" ? form.agent_key || null : null,
    is_active: form.is_active,
  };
}

function normalizeUpdatePayload(form: FormState): PromptSkillUpdatePayload {
  return {
    name: form.name.trim(),
    content: form.content.trim(),
    scope: form.scope,
    agent_key: form.scope === "agent_specific" ? form.agent_key || null : null,
    is_active: form.is_active,
  };
}

export default function PromptSkillsPanel() {
  const [items, setItems] = useState<PromptSkillItemPayload[]>([]);
  const [builtinItems, setBuiltinItems] = useState<PromptSkillBuiltinItemPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingItem, setEditingItem] = useState<PromptSkillItemPayload | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [searchQuery, setSearchQuery] = useState("");
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");

  const loadPromptSkills = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await api.getPromptSkills({ limit: 500 });
      setItems(payload.items);
      setBuiltinItems(payload.builtinItems);
    } catch (error) {
      toast.error(`加载 Prompt Skill 失败：${extractErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPromptSkills();
  }, [loadPromptSkills]);

  const filteredItems = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return items.filter((item) => {
      if (scopeFilter !== "all" && item.scope !== scopeFilter) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = [
        item.name,
        item.content,
        item.scope,
        item.agent_key || "",
        AGENT_LABEL_MAP[item.agent_key || ""] || "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [items, scopeFilter, searchQuery]);

  const builtinStateMap = useMemo(() => {
    const map: Record<string, PromptSkillBuiltinItemPayload> = {};
    for (const item of builtinItems) {
      map[item.agent_key] = item;
    }
    return map;
  }, [builtinItems]);

  const builtinRows = useMemo(
    () =>
      BUILTIN_PROMPT_SKILLS.map((row) => ({
        ...row,
        content: builtinStateMap[row.key]?.content || row.content,
        is_active: builtinStateMap[row.key]?.is_active ?? true,
      })),
    [builtinStateMap],
  );

  const openCreateDialog = () => {
    setEditingItem(null);
    setForm(DEFAULT_FORM);
    setDialogOpen(true);
  };

  const openEditDialog = (item: PromptSkillItemPayload) => {
    setEditingItem(item);
    setForm({
      name: item.name,
      content: item.content,
      scope: item.scope,
      agent_key: item.agent_key || "",
      is_active: item.is_active,
    });
    setDialogOpen(true);
  };

  const handleScopeChange = (nextScope: PromptSkillScopePayload) => {
    setForm((current) => ({
      ...current,
      scope: nextScope,
      agent_key:
        nextScope === "agent_specific"
          ? current.agent_key || AGENT_OPTIONS[0].key
          : "",
    }));
  };

  const handleSubmit = async () => {
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
      if (editingItem) {
        await api.updatePromptSkill(editingItem.id, normalizeUpdatePayload(form));
        toast.success("Prompt Skill 已更新");
      } else {
        await api.createPromptSkill(normalizeCreatePayload(form));
        toast.success("Prompt Skill 已创建");
      }
      setDialogOpen(false);
      setEditingItem(null);
      setForm(DEFAULT_FORM);
      await loadPromptSkills();
    } catch (error) {
      toast.error(`保存失败：${extractErrorMessage(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: PromptSkillItemPayload) => {
    const confirmed = window.confirm(`确认删除 Prompt Skill「${item.name}」？`);
    if (!confirmed) {
      return;
    }

    try {
      await api.deletePromptSkill(item.id);
      toast.success("Prompt Skill 已删除");
      await loadPromptSkills();
    } catch (error) {
      toast.error(`删除失败：${extractErrorMessage(error)}`);
    }
  };

  const handleToggleActive = async (item: PromptSkillItemPayload) => {
    try {
      await api.updatePromptSkill(item.id, { is_active: !item.is_active });
      toast.success(item.is_active ? "Prompt Skill 已停用" : "Prompt Skill 已启用");
      await loadPromptSkills();
    } catch (error) {
      toast.error(`更新状态失败：${extractErrorMessage(error)}`);
    }
  };

  const handleToggleBuiltinActive = async (agentKey: string, isActive: boolean) => {
    try {
      await api.updateBuiltinPromptSkill(agentKey, { is_active: !isActive });
      toast.success(isActive ? "内置 Prompt Skill 已停用" : "内置 Prompt Skill 已启用");
      await loadPromptSkills();
    } catch (error) {
      toast.error(`更新内置 Skill 状态失败：${extractErrorMessage(error)}`);
    }
  };

  return (
    <div className="flex flex-1 min-h-[20rem] flex-col gap-5">
      <div className="space-y-2 rounded-sm border border-border/50 bg-background/20 p-4">
        <p className="text-sm text-foreground/90">
          系统内置 Prompt Skill 用于提供基础审计策略；下方可新增“通用”或“智能体专属”技能并参与运行时注入。
        </p>
      </div>

      <div className="overflow-x-auto rounded-sm border border-border/50 bg-background/20">
        <table className="min-w-[1080px] w-full border-collapse">
          <thead>
            <tr className="border-b border-border/50 bg-background/60 text-left">
              <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">序号</th>
              <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">Agent 角色</th>
              <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">Skill Key</th>
              <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">内置 Prompt Skill</th>
              <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">状态</th>
              <th className="px-4 py-3 text-right text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">操作</th>
            </tr>
          </thead>
          <tbody>
            {builtinRows.map((row, index) => (
              <tr
                key={row.key}
                className="border-b border-border/30 align-top transition-colors duration-150 hover:bg-background/40"
              >
                <td className="px-4 py-4 text-sm font-mono text-muted-foreground">{String(index + 1).padStart(2, "0")}</td>
                <td className="px-4 py-4 text-sm font-semibold text-foreground whitespace-nowrap">{row.agentLabel}</td>
                <td className="px-4 py-4 text-sm font-mono text-primary whitespace-nowrap">{row.key}</td>
                <td className="px-4 py-4 text-sm leading-6 text-foreground/90">{row.content}</td>
                <td className="px-4 py-4">
                  <Badge variant={row.is_active ? "default" : "secondary"}>
                    {row.is_active ? "启用" : "停用"}
                  </Badge>
                </td>
                <td className="px-4 py-4">
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="cyber-btn-ghost h-8 px-3"
                      onClick={() => void handleToggleBuiltinActive(row.key, row.is_active)}
                    >
                      {row.is_active ? "停用" : "启用"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 rounded-sm border border-border/50 bg-background/20 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="搜索名称、内容或智能体"
            className="cyber-input h-10 w-full max-w-[360px]"
          />
          <Select value={scopeFilter} onValueChange={(value) => setScopeFilter(value as ScopeFilter)}>
            <SelectTrigger className="cyber-input h-10 w-[180px]">
              <SelectValue placeholder="选择作用域" />
            </SelectTrigger>
            <SelectContent className="cyber-dialog border-border">
              <SelectItem value="all">全部作用域</SelectItem>
              <SelectItem value="global">通用</SelectItem>
              <SelectItem value="agent_specific">智能体专属</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            className="cyber-btn-ghost"
            onClick={() => {
              void loadPromptSkills();
            }}
            disabled={loading}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
          <Button type="button" className="cyber-btn-primary" onClick={openCreateDialog}>
            <Plus className="mr-2 h-4 w-4" />
            新增 Prompt Skill
          </Button>
        </div>

        <div className="overflow-x-auto rounded-sm border border-border/50 bg-background/20">
          <table className="min-w-[1080px] w-full border-collapse">
            <thead>
              <tr className="border-b border-border/50 bg-background/60 text-left">
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">序号</th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">名称</th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">作用域</th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">目标智能体</th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">内容</th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">状态</th>
                <th className="px-4 py-3 text-right text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.length ? (
                filteredItems.map((item, index) => (
                  <tr
                    key={item.id}
                    className="border-b border-border/30 align-top transition-colors duration-150 hover:bg-background/40"
                  >
                    <td className="px-4 py-4 text-sm font-mono text-muted-foreground">{String(index + 1).padStart(2, "0")}</td>
                    <td className="px-4 py-4 text-sm font-semibold text-foreground whitespace-nowrap">{item.name}</td>
                    <td className="px-4 py-4">
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {scopeLabel(item.scope)}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 text-sm text-foreground whitespace-nowrap">
                      {item.scope === "global"
                        ? "全部智能体"
                        : AGENT_LABEL_MAP[item.agent_key || ""] || item.agent_key || "-"}
                    </td>
                    <td className="px-4 py-4 text-sm text-foreground/90 leading-6">
                      <div className="max-w-[460px] whitespace-pre-wrap break-words">{item.content}</div>
                    </td>
                    <td className="px-4 py-4">
                      <Badge variant={item.is_active ? "default" : "secondary"}>
                        {item.is_active ? "启用" : "停用"}
                      </Badge>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="cyber-btn-ghost h-8 px-3"
                          onClick={() => void handleToggleActive(item)}
                        >
                          {item.is_active ? "停用" : "启用"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="cyber-btn-ghost h-8 px-3"
                          onClick={() => openEditDialog(item)}
                        >
                          <Pencil className="mr-1 h-3.5 w-3.5" /> 编辑
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-8 px-3 border-red-500/40 text-red-400 hover:text-red-300"
                          onClick={() => void handleDelete(item)}
                        >
                          <Trash2 className="mr-1 h-3.5 w-3.5" /> 删除
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-sm text-muted-foreground">
                    {loading ? "加载中..." : "暂无自定义 Prompt Skill，点击“新增 Prompt Skill”开始配置。"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          if (!saving) {
            setDialogOpen(open);
          }
        }}
      >
        <DialogContent className="!w-[min(92vw,760px)] !max-w-none p-0 gap-0 cyber-dialog border border-border rounded-lg">
          <DialogHeader className="px-5 py-4 border-b border-border bg-muted">
            <DialogTitle className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
              {editingItem ? "编辑 Prompt Skill" : "新增 Prompt Skill"}
            </DialogTitle>
            <DialogDescription>
              配置运行时注入的自定义 Prompt Skill，支持通用和智能体专属两种作用域。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 px-5 py-4">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm text-foreground/90">
                <span className="font-medium">名称</span>
                <Input
                  value={form.name}
                  onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="例如：全局证据约束"
                  className="cyber-input"
                />
              </label>

              <label className="space-y-2 text-sm text-foreground/90">
                <span className="font-medium">作用域</span>
                <Select value={form.scope} onValueChange={(value) => handleScopeChange(value as PromptSkillScopePayload)}>
                  <SelectTrigger className="cyber-input">
                    <SelectValue placeholder="选择作用域" />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <SelectItem value="global">通用（作用于全部智能体）</SelectItem>
                    <SelectItem value="agent_specific">智能体专属</SelectItem>
                  </SelectContent>
                </Select>
              </label>
            </div>

            <label className="space-y-2 text-sm text-foreground/90">
              <span className="font-medium">目标智能体</span>
              <Select
                value={form.scope === "agent_specific" ? (form.agent_key || AGENT_OPTIONS[0].key) : AGENT_OPTIONS[0].key}
                onValueChange={(value) => setForm((current) => ({ ...current, agent_key: value }))}
                disabled={form.scope !== "agent_specific"}
              >
                <SelectTrigger className="cyber-input">
                  <SelectValue placeholder="选择智能体" />
                </SelectTrigger>
                <SelectContent className="cyber-dialog border-border">
                  {AGENT_OPTIONS.map((agent) => (
                    <SelectItem key={agent.key} value={agent.key}>
                      {agent.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>

            <label className="space-y-2 text-sm text-foreground/90">
              <span className="font-medium">Skill 内容</span>
              <Textarea
                value={form.content}
                onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
                placeholder="输入你要注入给智能体的策略文本"
                className="min-h-[180px] cyber-input"
              />
            </label>
          </div>

          <DialogFooter className="px-5 py-4 border-t border-border bg-muted">
            <Button
              type="button"
              variant="outline"
              className="cyber-btn-ghost"
              onClick={() => setDialogOpen(false)}
              disabled={saving}
            >
              取消
            </Button>
            <Button type="button" className="cyber-btn-primary" onClick={() => void handleSubmit()} disabled={saving}>
              {saving ? "保存中..." : editingItem ? "保存修改" : "创建 Skill"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
