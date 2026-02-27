import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Wrench, Zap } from "lucide-react";
import { SystemConfig } from "@/components/system/SystemConfig";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";
import SkillToolsPanel from "@/pages/intelligent-audit/SkillToolsPanel";

export default function IntelligentAudit() {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <Tabs defaultValue="llm" className="w-full">
          <TabsList className="grid w-full grid-cols-3 bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6">
            <TabsTrigger
              value="llm"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Zap className="w-3 h-3" /> LLM 配置
            </TabsTrigger>
            <TabsTrigger
              value="mcp"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Wrench className="w-3 h-3" /> MCP 配置
            </TabsTrigger>
            <TabsTrigger
              value="skill"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Wrench className="w-3 h-3" /> SKILL 配置
            </TabsTrigger>
          </TabsList>

          <TabsContent value="llm" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="cyber-card p-5 space-y-2">
                <div>
                  <div className="font-mono font-bold uppercase text-sm text-foreground">
                    LLM（逻辑推理 / 编排决策）
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    配置模型参数与超时预算。
                  </div>
                </div>
                <SystemConfig
                  visibleSections={["llm"]}
                  defaultSection="llm"
                  mergedView={false}
                />
              </div>

              <div className="cyber-card p-5 space-y-2">
                <div>
                  <div className="font-mono font-bold uppercase text-sm text-foreground">
                    RAG（向量索引 / 代码向量化）
                  </div>
                </div>
                <EmbeddingConfig />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="mcp" className="space-y-6">
            <div className="cyber-card p-5 space-y-2">
              <div>
                <div className="font-mono font-bold uppercase text-sm text-foreground">
                  MCP 运行时配置
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  管理 MCP 启停策略、运行域和写入约束。
                </div>
              </div>
              <SystemConfig
                visibleSections={["mcp"]}
                defaultSection="mcp"
                mergedView={false}
              />
            </div>
            <SkillToolsPanel mode="mcp" />
          </TabsContent>

          <TabsContent value="skill" className="space-y-6">
            <SkillToolsPanel mode="skill" />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
