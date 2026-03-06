import { Link } from "react-router-dom";
import { Bot, SearchCheck, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface EngineCard {
  id: string;
  name: string;
  description: string;
  icon: ReactNode;
  to: string;
}

const ENGINE_CARDS: EngineCard[] = [
  {
    id: "opengrep",
    name: "opengrep",
    description: "代码规则扫描引擎，适合做语义规则匹配与漏洞模式检测。",
    icon: <SearchCheck className="w-5 h-5 text-sky-100" />,
    to: "/scan-config/engines?tab=opengrep",
  },
  {
    id: "gitleaks",
    name: "gitleaks",
    description: "仓库密钥与敏感信息检测引擎，聚焦凭证泄露风险识别。",
    icon: <ShieldAlert className="w-5 h-5 text-sky-100" />,
    to: "/scan-config/engines?tab=gitleaks",
  },
  {
    id: "smart-engine",
    name: "智能引擎",
    description: "智能分析引擎，支撑智能审计、总结归纳与上下文推理。",
    icon: <Bot className="w-5 h-5 text-sky-100" />,
    to: "/scan-config/intelligent-engine",
  },
];

export default function ScanConfigOverview() {
  return (
    <div className="space-y-6 p-6 bg-background min-h-screen relative">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 space-y-4">
        <div className="cyber-card p-5 space-y-1">
          <h2 className="font-mono text-lg font-bold text-foreground">
            扫描配置总览
          </h2>
          <p className="text-sm text-muted-foreground">
            统一管理扫描引擎入口，点击右侧按钮进入对应配置或使用页面。
          </p>
        </div>

        {ENGINE_CARDS.map((engine) => (
          <div
            key={engine.id}
            className="cyber-card p-4 flex flex-wrap items-center gap-4 md:gap-5"
          >
            <div className="shrink-0">
              <div className="w-12 h-12 rounded-lg bg-sky-700/90 border border-sky-400/40 flex items-center justify-center shadow-[0_0_16px_rgba(14,165,233,0.25)]">
                {engine.icon}
              </div>
            </div>

            <div className="min-w-[160px]">
              <h3 className="font-mono text-base font-semibold text-foreground lowercase">
                {engine.name}
              </h3>
            </div>

            <div className="h-10 w-px bg-border/80 shrink-0" />

            <div className="flex-1 min-w-[260px] text-sm text-muted-foreground">
              {engine.description}
            </div>

            <Link to={engine.to} className="shrink-0">
              <Button
                size="sm"
                className="h-9 px-4 bg-blue-600 hover:bg-blue-500 text-white"
              >
                引擎配置
              </Button>
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
