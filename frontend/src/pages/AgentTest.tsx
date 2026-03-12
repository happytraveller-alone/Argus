/**
 * Agent 单体测试页面
 * 用于独立测试 ReconAgent / AnalysisAgent / VerificationAgent / BusinessLogicScanAgent
 * / BusinessLogicReconAgent / BusinessLogicAnalysisAgent
 */

import {
  Bot,
  ChevronRight,
  Code2,
  Cpu,
  Search,
  Shield,
  Telescope,
  Zap,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AnalysisPanel,
  BusinessLogicPanel,
  BusinessLogicReconPanel,
  BusinessLogicAnalysisPanel,
  ReconPanel,
  VerificationPanel,
} from "./agent-test/panels";

export default function AgentTestPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-background font-mono">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      <div className="relative z-10 flex flex-col h-full p-6 gap-4">
        <div className="flex items-center gap-3 shrink-0">
          <Bot className="w-6 h-6 text-primary" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">Agent 单体测试</h1>
            <p className="text-xs text-muted-foreground">
              独立测试单个 Agent 的能力，实时查看执行过程
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground/60">
            <ChevronRight className="w-3 h-3" />
            <span>直连 Agent，不创建审计任务</span>
          </div>
        </div>

        <div className="cyber-card flex-1 min-h-0 p-4 overflow-hidden flex flex-col">
          <Tabs defaultValue="recon" className="flex flex-col flex-1 min-h-0">
            <TabsList className="shrink-0 grid grid-cols-6 w-full mb-4">
              <TabsTrigger value="recon" className="gap-1.5 text-xs">
                <Search className="w-3.5 h-3.5" /> Recon
              </TabsTrigger>
              <TabsTrigger value="analysis" className="gap-1.5 text-xs">
                <Cpu className="w-3.5 h-3.5" /> Analysis
              </TabsTrigger>
              <TabsTrigger value="verification" className="gap-1.5 text-xs">
                <Shield className="w-3.5 h-3.5" /> Verification
              </TabsTrigger>
              <TabsTrigger value="business-logic" className="gap-1.5 text-xs">
                <Code2 className="w-3.5 h-3.5" /> BL Scan
              </TabsTrigger>
              <TabsTrigger value="bl-recon" className="gap-1.5 text-xs">
                <Telescope className="w-3.5 h-3.5" /> BL Recon
              </TabsTrigger>
              <TabsTrigger value="bl-analysis" className="gap-1.5 text-xs">
                <Zap className="w-3.5 h-3.5" /> BL Analysis
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 min-h-0 overflow-y-auto pr-1">
              <TabsContent value="recon" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">ReconAgent</strong> —
                    信息收集阶段：扫描项目结构、识别技术栈、发现 HTTP 入口点和高风险区域。
                  </p>
                </div>
                <ReconPanel />
              </TabsContent>

              <TabsContent value="analysis" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">AnalysisAgent</strong> —
                    漏洞分析阶段：深度分析代码，发现 SQL 注入、XSS、越权等安全漏洞。
                    可提供 Recon 阶段的入口点和高风险区域作为上下文。
                  </p>
                </div>
                <AnalysisPanel />
              </TabsContent>

              <TabsContent value="verification" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">VerificationAgent</strong> —
                    漏洞验证阶段：对已发现的漏洞进行深度代码审查，验证真实性并评估可利用性。
                    以 JSON 数组形式输入待验证的漏洞列表。
                  </p>
                </div>
                <VerificationPanel />
              </TabsContent>

              <TabsContent value="business-logic" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">
                      BusinessLogicScanAgent
                    </strong>{" "}
                    —
                    业务逻辑漏洞扫描（旧版单体 Agent）：检测 IDOR、权限绕过、金额篡改、批量赋值、竞态条件等业务逻辑缺陷。
                    指定入口点列表可启用聚焦模式，留空则全局扫描。
                  </p>
                </div>
                <BusinessLogicPanel />
              </TabsContent>

              <TabsContent value="bl-recon" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">BusinessLogicReconAgent</strong>{" "}
                    —
                    业务逻辑风险侦察：扫描整个项目，识别 IDOR、权限绕过、支付逻辑、竞态条件、批量赋值等业务逻辑风险点，
                    推入 BL 风险队列供 <strong className="text-cyan-400">BusinessLogicAnalysisAgent</strong> 深度分析。
                  </p>
                </div>
                <BusinessLogicReconPanel />
              </TabsContent>

              <TabsContent value="bl-analysis" className="mt-0">
                <div className="mb-3 p-2.5 rounded bg-muted/30 border border-border/30">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">BusinessLogicAnalysisAgent</strong>{" "}
                    —
                    业务逻辑漏洞深度分析：对单个 BL 风险点进行深度代码审查，确认漏洞真实性、评估影响范围，
                    将确认的漏洞推入漏洞队列。输入来自 BL Recon 阶段的风险点 JSON 对象。
                  </p>
                </div>
                <BusinessLogicAnalysisPanel />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
