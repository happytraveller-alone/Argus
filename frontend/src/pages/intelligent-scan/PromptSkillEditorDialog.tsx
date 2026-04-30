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
import type { PromptSkillScopePayload } from "@/shared/api/database";
import type { PromptSkillFormState } from "./promptSkillShared";

export interface PromptSkillAgentOption {
  key: string;
  label: string;
}

interface PromptSkillEditorDialogProps {
  open: boolean;
  saving: boolean;
  title: string;
  description: string;
  submitLabel: string;
  form: PromptSkillFormState;
  agentOptions: PromptSkillAgentOption[];
  onOpenChange: (open: boolean) => void;
  onFormChange: (updater: (current: PromptSkillFormState) => PromptSkillFormState) => void;
  onScopeChange: (scope: PromptSkillScopePayload) => void;
  onSubmit: () => void;
}

export default function PromptSkillEditorDialog({
  open,
  saving,
  title,
  description,
  submitLabel,
  form,
  agentOptions,
  onOpenChange,
  onFormChange,
  onScopeChange,
  onSubmit,
}: PromptSkillEditorDialogProps) {
  const fallbackAgentKey = agentOptions[0]?.key || "";

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!saving) {
          onOpenChange(nextOpen);
        }
      }}
    >
      <DialogContent className="!w-[min(92vw,760px)] !max-w-none gap-0 rounded-lg border border-border p-0 cyber-dialog">
        <DialogHeader className="border-b border-border bg-muted px-5 py-4">
          <DialogTitle className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-5 py-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm text-foreground/90">
              <span className="font-medium">名称</span>
              <Input
                value={form.name}
                onChange={(event) =>
                  onFormChange((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                placeholder="例如：全局证据约束"
                className="cyber-input"
              />
            </label>

            <label className="space-y-2 text-sm text-foreground/90">
              <span className="font-medium">作用域</span>
              <Select
                value={form.scope}
                onValueChange={(value) => onScopeChange(value as PromptSkillScopePayload)}
              >
                <SelectTrigger className="cyber-input">
                  <SelectValue placeholder="选择作用域" />
                </SelectTrigger>
                <SelectContent className="border-border cyber-dialog">
                  <SelectItem value="global">通用（作用于全部智能体）</SelectItem>
                  <SelectItem value="agent_specific">智能体专属</SelectItem>
                </SelectContent>
              </Select>
            </label>
          </div>

          <label className="space-y-2 text-sm text-foreground/90">
            <span className="font-medium">目标智能体</span>
            <Select
              value={
                form.scope === "agent_specific"
                  ? form.agent_key || fallbackAgentKey
                  : fallbackAgentKey
              }
              onValueChange={(value) =>
                onFormChange((current) => ({
                  ...current,
                  agent_key: value,
                }))
              }
              disabled={form.scope !== "agent_specific" || agentOptions.length === 0}
            >
              <SelectTrigger className="cyber-input">
                <SelectValue placeholder="选择智能体" />
              </SelectTrigger>
              <SelectContent className="border-border cyber-dialog">
                {agentOptions.map((agent) => (
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
              onChange={(event) =>
                onFormChange((current) => ({
                  ...current,
                  content: event.target.value,
                }))
              }
              placeholder="输入你要注入给智能体的策略文本"
              className="min-h-[180px] cyber-input"
            />
          </label>
        </div>

        <DialogFooter className="border-t border-border bg-muted px-5 py-4">
          <Button
            type="button"
            variant="outline"
            className="cyber-btn-ghost"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button
            type="button"
            className="cyber-btn-primary"
            onClick={onSubmit}
            disabled={saving}
          >
            {saving ? "保存中..." : submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
