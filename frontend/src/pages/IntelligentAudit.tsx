import { type ReactNode, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Bot, Brain, Crosshair, PlayCircle, ShieldCheck, Sparkles } from "lucide-react";

type AgentConfig = {
  id: string;
  name: string;
  role: string;
  icon: ReactNode;
  colorClass: string;
  systemPrompt: string;
  taskPrompt: string;
};

const AGENT_CONFIGS: AgentConfig[] = [
  {
    id: "orchestrator",
    name: "Orchestrator Agent",
    role: "调度全流程并分发任务",
    icon: <Bot className="w-4 h-4" />,
    colorClass: "text-cyan-300 border-cyan-400/30 bg-cyan-500/10",
    systemPrompt: "你是审计流程调度器，负责制定任务拆分与执行顺序。",
    taskPrompt: "根据项目上下文分配子任务，并跟踪执行状态与结果汇总。",
  },
  {
    id: "reconnaissance",
    name: "Reconnaissance Agent",
    role: "侦察项目结构与攻击面",
    icon: <Crosshair className="w-4 h-4" />,
    colorClass: "text-sky-300 border-sky-400/30 bg-sky-500/10",
    systemPrompt: "你负责快速识别关键目录、入口点、依赖与可疑代码区块。",
    taskPrompt: "输出高风险文件清单与优先审计建议。",
  },
  {
    id: "analysis",
    name: "Analysis Agent",
    role: "执行漏洞分析与证据提取",
    icon: <Brain className="w-4 h-4" />,
    colorClass: "text-blue-200 border-blue-400/30 bg-blue-500/10",
    systemPrompt: "你是漏洞分析专家，给出漏洞类型、利用路径和风险等级。",
    taskPrompt: "结合规则与代码上下文输出可复现的分析证据。",
  },
  {
    id: "verification",
    name: "Verification Agent",
    role: "验证漏洞与收敛误报",
    icon: <ShieldCheck className="w-4 h-4" />,
    colorClass: "text-emerald-300 border-emerald-400/30 bg-emerald-500/10",
    systemPrompt: "你负责确认漏洞真实性，并说明误报或不可利用原因。",
    taskPrompt: "输出验证结果、验证方法与最终建议处理优先级。",
  },
];

export default function IntelligentAudit() {
  const [activeAgentId, setActiveAgentId] = useState<string>(AGENT_CONFIGS[0].id);
  const [projectName, setProjectName] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [promptDrafts, setPromptDrafts] = useState<Record<string, { systemPrompt: string; taskPrompt: string }>>(
    () =>
      AGENT_CONFIGS.reduce((acc, item) => {
        acc[item.id] = {
          systemPrompt: item.systemPrompt,
          taskPrompt: item.taskPrompt,
        };
        return acc;
      }, {} as Record<string, { systemPrompt: string; taskPrompt: string }>)
  );

  const activeAgent = useMemo(
    () => AGENT_CONFIGS.find((item) => item.id === activeAgentId) ?? AGENT_CONFIGS[0],
    [activeAgentId]
  );

  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-wide flex items-center gap-2">
              <Sparkles className="w-7 h-7 text-primary" />
              智能审计 Agent 控制台
            </h1>
            <p className="text-sm text-muted-foreground">
              展示智能审计中全部 Agent，支持后续提示词调优与项目参数预配置。
            </p>
          </div>
          <Badge className="cyber-badge-info">Agent 数量：{AGENT_CONFIGS.length}</Badge>
        </div>

        <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
          <section className="cyber-card p-4 space-y-3">
            <h2 className="text-lg font-bold">Agent 列表</h2>
            <p className="text-xs text-muted-foreground">选择左侧 Agent，在右侧调优其提示词。</p>
            <div className="space-y-2">
              {AGENT_CONFIGS.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => setActiveAgentId(agent.id)}
                  className={`w-full text-left p-3 rounded border transition ${
                    activeAgentId === agent.id ? "border-primary bg-primary/10" : "border-border hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center justify-center rounded p-1 border ${agent.colorClass}`}>
                      {agent.icon}
                    </span>
                    <div>
                      <p className="text-sm font-bold">{agent.name}</p>
                      <p className="text-xs text-muted-foreground">{agent.role}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="space-y-6">
            <div className="cyber-card p-4 space-y-4">
              <h2 className="text-lg font-bold">项目配置</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="project-name">项目名称</Label>
                  <Input
                    id="project-name"
                    className="cyber-input"
                    value={projectName}
                    onChange={(event) => setProjectName(event.target.value)}
                    placeholder="请输入项目名称"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="project-path">项目路径/仓库地址</Label>
                  <Input
                    id="project-path"
                    className="cyber-input"
                    value={projectPath}
                    onChange={(event) => setProjectPath(event.target.value)}
                    placeholder="请输入本地路径或仓库地址"
                  />
                </div>
              </div>
            </div>

            <div className="cyber-card p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold">{activeAgent.name} 提示词调优</h2>
                  <p className="text-xs text-muted-foreground">{activeAgent.role}</p>
                </div>
                <Badge className="cyber-badge-muted">{activeAgent.id}</Badge>
              </div>

              <div className="space-y-2">
                <Label htmlFor="system-prompt">System Prompt</Label>
                <Textarea
                  id="system-prompt"
                  className="cyber-input min-h-[110px]"
                  value={promptDrafts[activeAgent.id]?.systemPrompt ?? ""}
                  onChange={(event) =>
                    setPromptDrafts((prev) => ({
                      ...prev,
                      [activeAgent.id]: {
                        ...prev[activeAgent.id],
                        systemPrompt: event.target.value,
                      },
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="task-prompt">Task Prompt</Label>
                <Textarea
                  id="task-prompt"
                  className="cyber-input min-h-[140px]"
                  value={promptDrafts[activeAgent.id]?.taskPrompt ?? ""}
                  onChange={(event) =>
                    setPromptDrafts((prev) => ({
                      ...prev,
                      [activeAgent.id]: {
                        ...prev[activeAgent.id],
                        taskPrompt: event.target.value,
                      },
                    }))
                  }
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <Button variant="outline" className="cyber-btn-outline">
                  重置当前 Agent
                </Button>
                <Button className="cyber-btn-primary">
                  <PlayCircle className="w-4 h-4 mr-2" />
                  保存调优配置
                </Button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
