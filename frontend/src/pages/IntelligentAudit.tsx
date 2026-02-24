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
          <TabsList className="grid w-full grid-cols-2 bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6">
            <TabsTrigger
              value="llm"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Zap className="w-3 h-3" /> LLM 配置
            </TabsTrigger>
            <TabsTrigger
              value="tools"
              className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
            >
              <Wrench className="w-3 h-3" /> 审计工具
            </TabsTrigger>
          </TabsList>

          <TabsContent value="llm" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="cyber-card p-5 space-y-2">
                <div>
                  <div className="font-mono font-bold uppercase text-sm text-foreground">
                    LLM 与 MCP（逻辑推理 / 工具执行）
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    配置模型参数与 MCP 运行时写入约束策略。
                  </div>
                </div>
                <SystemConfig visibleSections={["llm", "mcp"]} defaultSection="llm" mergedView={false} />
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

          <TabsContent value="tools" className="space-y-6">
            <SkillToolsPanel />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
