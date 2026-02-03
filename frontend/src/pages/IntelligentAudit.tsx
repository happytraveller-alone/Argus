import { useState } from "react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Bot, Brain, Settings, Zap } from "lucide-react";
import { SystemConfig } from "@/components/system/SystemConfig";
import AgentSettingsPanel from "@/components/agent/AgentSettingsPanel";

const AGENT_ITEMS = ["调度智能体", "侦察智能体", "分析智能体", "验证智能体"] as const;

function CapabilityPanel() {
  const [selectedAgent, setSelectedAgent] = useState<string>(AGENT_ITEMS[0]);

  return (
    <div className="space-y-4">
      <div className="cyber-card p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[220px] max-w-sm flex-1">
            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
              智能体选择
            </Label>
            <Select value={selectedAgent} onValueChange={setSelectedAgent}>
              <SelectTrigger className="cyber-input mt-1.5">
                <SelectValue placeholder="选择智能体" />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                {AGENT_ITEMS.map((agent) => (
                  <SelectItem key={agent} value={agent}>
                    {agent}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground pb-1">
            <Bot className="w-4 h-4 text-cyan-300" />
            <span>当前智能体：{selectedAgent}</span>
          </div>
        </div>
      </div>

      <AgentSettingsPanel selectedAgent={selectedAgent} />
    </div>
  );
}

export default function IntelligentAudit() {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <Tabs defaultValue="capability" className="w-full">
          <TabsList className="grid w-full grid-cols-4 bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6">
            <TabsTrigger
              value="capability"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Bot className="w-3 h-3" /> 审计能力
            </TabsTrigger>
            <TabsTrigger
              value="llm"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Zap className="w-3 h-3" /> LLM 配置
            </TabsTrigger>
            <TabsTrigger
              value="embedding"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Brain className="w-3 h-3" /> 嵌入模型
            </TabsTrigger>
            <TabsTrigger
              value="analysis"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Settings className="w-3 h-3" /> 分析参数
            </TabsTrigger>
          </TabsList>

          <TabsContent value="capability" className="space-y-6">
            <CapabilityPanel />
          </TabsContent>

          <TabsContent value="llm" className="space-y-6">
            <SystemConfig visibleSections={["llm"]} defaultSection="llm" />
          </TabsContent>

          <TabsContent value="embedding" className="space-y-6">
            <SystemConfig visibleSections={["embedding"]} defaultSection="embedding" />
          </TabsContent>

          <TabsContent value="analysis" className="space-y-6">
            <SystemConfig visibleSections={["analysis"]} defaultSection="analysis" />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
