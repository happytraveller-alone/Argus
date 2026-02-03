import { useMemo, useState } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Bot, Boxes, Puzzle } from "lucide-react";

type SidebarGroup = {
  id: "agent" | "mcp" | "agent-skill";
  title: string;
  subtitle: string;
  items: string[];
};

const SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    id: "agent",
    title: "Agent（智能体）",
    subtitle: "负责调度、分析、验证",
    items: ["Orchestrator 调度智能体", "Recon 侦察智能体", "Analysis 分析智能体", "Verification 验证智能体"],
  },
  {
    id: "mcp",
    title: "MCP（工具协议）",
    subtitle: "统一管理外部能力接入",
    items: ["文件系统 MCP", "代码检索 MCP", "命令执行 MCP", "知识库 MCP"],
  },
  {
    id: "agent-skill",
    title: "Agent Skill（技能）",
    subtitle: "智能体可复用的专项能力",
    items: ["漏洞模式识别技能", "补丁差异分析技能", "误报收敛技能", "审计报告生成技能"],
  },
];

const GROUP_ICON = {
  agent: <Bot className="w-4 h-4 text-cyan-300" />,
  mcp: <Boxes className="w-4 h-4 text-blue-300" />,
  "agent-skill": <Puzzle className="w-4 h-4 text-emerald-300" />,
} as const;

export default function IntelligentAudit() {
  const [selectedGroupId, setSelectedGroupId] = useState<SidebarGroup["id"]>("agent");
  const [selectedItem, setSelectedItem] = useState<string>(SIDEBAR_GROUPS[0].items[0]);

  const selectedGroup = useMemo(
    () => SIDEBAR_GROUPS.find((group) => group.id === selectedGroupId) ?? SIDEBAR_GROUPS[0],
    [selectedGroupId]
  );

  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-6">
        <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
          <aside className="cyber-card p-4 space-y-3 h-fit">
            <h2 className="text-lg font-bold">能力目录</h2>
            <Accordion
              type="single"
              collapsible
              value={selectedGroupId}
              onValueChange={(value) => {
                if (!value) return;
                const groupId = value as SidebarGroup["id"];
                setSelectedGroupId(groupId);
                const firstItem = SIDEBAR_GROUPS.find((group) => group.id === groupId)?.items[0];
                if (firstItem) {
                  setSelectedItem(firstItem);
                }
              }}
              className="w-full"
            >
              {SIDEBAR_GROUPS.map((group) => (
                <AccordionItem key={group.id} value={group.id} className="border-border/70">
                  <AccordionTrigger className="py-3">
                    <div className="flex items-start gap-2">
                      <span className="mt-0.5">{GROUP_ICON[group.id]}</span>
                      <div className="text-left">
                        <p className="text-sm font-bold">{group.title}</p>
                        <p className="text-xs text-muted-foreground">{group.subtitle}</p>
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pt-0 pb-2">
                    <div className="space-y-1">
                      {group.items.map((item) => (
                        <button
                          key={item}
                          type="button"
                          onClick={() => {
                            setSelectedGroupId(group.id);
                            setSelectedItem(item);
                          }}
                          className={`w-full text-left text-sm rounded px-2 py-2 border transition ${
                            selectedItem === item
                              ? "border-primary bg-primary/10 text-foreground"
                              : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"
                          }`}
                        >
                          {item}
                        </button>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </aside>

          <section className="cyber-card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">{selectedGroup.title}</h2>
                <p className="text-sm text-muted-foreground">{selectedGroup.subtitle}</p>
              </div>
              <Badge className="cyber-badge-info">项目数：{selectedGroup.items.length}</Badge>
            </div>

            <div className="rounded border border-primary/20 bg-primary/5 p-4">
              <p className="text-xs text-muted-foreground mb-2">当前选择</p>
              <p className="text-lg font-bold">{selectedItem}</p>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {selectedGroup.items.map((item) => (
                <div
                  key={item}
                  className={`rounded border p-3 transition ${
                    selectedItem === item ? "border-primary bg-primary/10" : "border-border hover:bg-muted/40"
                  }`}
                >
                  <p className="text-sm font-bold">{item}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    用于智能审计流程展示与后续提示词调优。
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
