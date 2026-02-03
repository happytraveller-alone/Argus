import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { RefreshCw, Save, Star } from "lucide-react";
import {
  getPromptTemplates,
  setDefaultPromptTemplate,
  updatePromptTemplate,
  type PromptTemplate,
} from "@/shared/api/prompts";

type TemplateFormState = {
  name: string;
  description: string;
  template_type: string;
  content_zh: string;
  content_en: string;
  variables_json: string;
  is_active: boolean;
  sort_order: number;
};

const EMPTY_FORM: TemplateFormState = {
  name: "",
  description: "",
  template_type: "system",
  content_zh: "",
  content_en: "",
  variables_json: "{}",
  is_active: true,
  sort_order: 0,
};

interface AgentSettingsPanelProps {
  selectedAgent: string;
}

function toTemplateForm(template: PromptTemplate): TemplateFormState {
  return {
    name: template.name || "",
    description: template.description || "",
    template_type: template.template_type || "system",
    content_zh: template.content_zh || "",
    content_en: template.content_en || "",
    variables_json: JSON.stringify(template.variables || {}, null, 2),
    is_active: template.is_active,
    sort_order: template.sort_order || 0,
  };
}

function normalizeJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text || "{}"));
  } catch {
    return "";
  }
}

export default function AgentSettingsPanel({ selectedAgent }: AgentSettingsPanelProps) {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [form, setForm] = useState<TemplateFormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settingDefault, setSettingDefault] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) || null,
    [templates, selectedTemplateId],
  );

  const isSystemTemplate = selectedTemplate?.is_system ?? false;

  const isDirty = useMemo(() => {
    if (!selectedTemplate) return false;
    const original = toTemplateForm(selectedTemplate);

    if (selectedTemplate.is_system) {
      return original.is_active !== form.is_active;
    }

    return (
      original.name !== form.name ||
      original.description !== form.description ||
      original.template_type !== form.template_type ||
      original.content_zh !== form.content_zh ||
      original.content_en !== form.content_en ||
      normalizeJson(original.variables_json) !== normalizeJson(form.variables_json) ||
      original.sort_order !== form.sort_order ||
      original.is_active !== form.is_active
    );
  }, [selectedTemplate, form]);

  const loadTemplates = async (preferredId?: string) => {
    try {
      setLoading(true);
      const response = await getPromptTemplates({ limit: 100 });
      setTemplates(response.items);

      if (response.items.length === 0) {
        setSelectedTemplateId("");
        setForm(EMPTY_FORM);
        return;
      }

      const nextId =
        (preferredId && response.items.some((item) => item.id === preferredId) && preferredId) ||
        (selectedTemplateId && response.items.some((item) => item.id === selectedTemplateId) && selectedTemplateId) ||
        response.items[0].id;

      setSelectedTemplateId(nextId);
      const target = response.items.find((item) => item.id === nextId);
      if (target) {
        setForm(toTemplateForm(target));
      }
    } catch (error) {
      console.error("Failed to load prompt templates:", error);
      toast.error("加载提示词模板失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!selectedTemplate) return;
    setForm(toTemplateForm(selectedTemplate));
  }, [selectedTemplateId]);

  const handleSave = async () => {
    if (!selectedTemplate) return;

    let variables: Record<string, string> = {};
    if (!isSystemTemplate) {
      try {
        const parsed = JSON.parse(form.variables_json || "{}");
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          variables = parsed as Record<string, string>;
        } else {
          throw new Error("invalid");
        }
      } catch {
        toast.error("变量 JSON 格式错误，请修正后再保存");
        return;
      }
    }

    try {
      setSaving(true);
      await updatePromptTemplate(selectedTemplate.id, isSystemTemplate
        ? {
            is_active: form.is_active,
          }
        : {
            name: form.name.trim(),
            description: form.description.trim() || undefined,
            template_type: form.template_type,
            content_zh: form.content_zh,
            content_en: form.content_en,
            variables,
            sort_order: form.sort_order,
            is_active: form.is_active,
          });

      toast.success("提示词模板保存成功");
      await loadTemplates(selectedTemplate.id);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "保存提示词模板失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSetDefault = async () => {
    if (!selectedTemplate) return;
    try {
      setSettingDefault(true);
      await setDefaultPromptTemplate(selectedTemplate.id);
      toast.success("已设置为默认模板");
      await loadTemplates(selectedTemplate.id);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "设置默认模板失败");
    } finally {
      setSettingDefault(false);
    }
  };

  return (
    <section className="cyber-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Agent 设置</h2>
          <p className="text-sm text-muted-foreground">当前智能体：{selectedAgent}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="cyber-btn-outline"
          onClick={() => loadTemplates(selectedTemplateId || undefined)}
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <div className="border border-border rounded-lg bg-muted/20">
          <div className="px-3 py-2 border-b border-border text-sm text-muted-foreground font-bold">后端提示词模板</div>
          <ScrollArea className="h-[520px]">
            <div className="p-2 space-y-2">
              {templates.map((template) => (
                <button
                  type="button"
                  key={template.id}
                  onClick={() => setSelectedTemplateId(template.id)}
                  className={`w-full text-left rounded-md border p-3 transition ${
                    selectedTemplateId === template.id
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-primary/40 hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground line-clamp-1">{template.name}</span>
                    {template.is_default && <Star className="w-4 h-4 text-amber-400" />}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <Badge className="cyber-badge-info">{template.template_type}</Badge>
                    {template.is_system ? <Badge className="cyber-badge-muted">system</Badge> : <Badge className="cyber-badge-success">custom</Badge>}
                    <Badge className={template.is_active ? "cyber-badge-success" : "cyber-badge-danger"}>
                      {template.is_active ? "enabled" : "disabled"}
                    </Badge>
                  </div>
                </button>
              ))}
              {!loading && templates.length === 0 && (
                <div className="text-sm text-muted-foreground p-3">暂无提示词模板数据</div>
              )}
            </div>
          </ScrollArea>
        </div>

        <div className="border border-border rounded-lg bg-muted/10 p-4">
          {!selectedTemplate ? (
            <div className="text-muted-foreground text-sm">请在左侧选择模板进行查看或编辑。</div>
          ) : (
            <div className="space-y-4">
              {isSystemTemplate && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  系统模板只允许修改“启用状态”，其余字段为只读。
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-muted-foreground font-semibold">模板名称</Label>
                  <Input
                    value={form.name}
                    disabled={isSystemTemplate}
                    onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                    className="cyber-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-muted-foreground font-semibold">模板类型</Label>
                  <Select
                    value={form.template_type}
                    onValueChange={(value) => setForm((prev) => ({ ...prev, template_type: value }))}
                    disabled={isSystemTemplate}
                  >
                    <SelectTrigger className="cyber-input">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="system">system</SelectItem>
                      <SelectItem value="user">user</SelectItem>
                      <SelectItem value="analysis">analysis</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase text-muted-foreground font-semibold">模板描述</Label>
                <Input
                  value={form.description}
                  disabled={isSystemTemplate}
                  onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                  className="cyber-input"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-muted-foreground font-semibold">排序权重</Label>
                  <Input
                    type="number"
                    value={form.sort_order}
                    disabled={isSystemTemplate}
                    onChange={(event) => setForm((prev) => ({ ...prev, sort_order: Number(event.target.value) || 0 }))}
                    className="cyber-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase text-muted-foreground font-semibold">启用状态</Label>
                  <div className="h-10 px-3 border border-border rounded-md flex items-center justify-between bg-background/30">
                    <span className="text-sm text-foreground">{form.is_active ? "启用" : "禁用"}</span>
                    <Switch
                      checked={form.is_active}
                      onCheckedChange={(checked) => setForm((prev) => ({ ...prev, is_active: checked }))}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase text-muted-foreground font-semibold">中文提示词</Label>
                <Textarea
                  value={form.content_zh}
                  disabled={isSystemTemplate}
                  onChange={(event) => setForm((prev) => ({ ...prev, content_zh: event.target.value }))}
                  className="cyber-input min-h-40 font-mono text-xs"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase text-muted-foreground font-semibold">英文提示词</Label>
                <Textarea
                  value={form.content_en}
                  disabled={isSystemTemplate}
                  onChange={(event) => setForm((prev) => ({ ...prev, content_en: event.target.value }))}
                  className="cyber-input min-h-40 font-mono text-xs"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase text-muted-foreground font-semibold">变量配置 JSON</Label>
                <Textarea
                  value={form.variables_json}
                  disabled={isSystemTemplate}
                  onChange={(event) => setForm((prev) => ({ ...prev, variables_json: event.target.value }))}
                  className="cyber-input min-h-32 font-mono text-xs"
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-2">
                <Button
                  variant="outline"
                  className="cyber-btn-outline"
                  onClick={handleSetDefault}
                  disabled={settingDefault || !selectedTemplate || selectedTemplate.is_default}
                >
                  <Star className="w-4 h-4 mr-2" />
                  {selectedTemplate.is_default ? "已是默认模板" : "设为默认"}
                </Button>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    className="cyber-btn-outline"
                    disabled={!selectedTemplate}
                    onClick={() => selectedTemplate && setForm(toTemplateForm(selectedTemplate))}
                  >
                    还原
                  </Button>
                  <Button className="cyber-btn-primary" onClick={handleSave} disabled={!isDirty || saving}>
                    <Save className="w-4 h-4 mr-2" />
                    {saving ? "保存中..." : "保存"}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
