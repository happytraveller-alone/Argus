/**
 * Agent 扫描模式选择器
 * Cyberpunk Terminal Aesthetic
 */

import { Bot, Zap, CheckCircle2, Clock, Shield, Code, Settings2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";

export type ScanMode = "static" | "agent";

export type StaticTool = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "pmd";

export interface StaticToolSelection {
  opengrep: boolean;
  gitleaks: boolean;
  bandit: boolean;
  phpstan: boolean;
  pmd: boolean;
}

interface AgentModeSelectorProps {
  value: ScanMode;
  onChange: (mode: ScanMode) => void;
  disabled?: boolean;
  staticTools?: StaticToolSelection;
  onStaticToolsChange?: (next: StaticToolSelection) => void;
  disabledStaticTools?: Partial<Record<StaticTool, boolean>>;
  blockedStaticToolMessages?: Partial<Record<StaticTool, string>>;
  onOpenStaticToolConfig?: (tool: StaticTool) => void;
}

export default function AgentModeSelector({
  value,
  onChange,
  disabled = false,
  staticTools,
  onStaticToolsChange,
  disabledStaticTools,
  blockedStaticToolMessages,
  onOpenStaticToolConfig,
}: AgentModeSelectorProps) {
  const isStaticSelected = value === "static";
  const isAgentSelected = value === "agent";
  const resolvedTools: StaticToolSelection = staticTools || {
    opengrep: true,
    gitleaks: false,
    bandit: false,
    phpstan: false,
    pmd: false,
  };

  const updateStaticTool = (tool: StaticTool, checked: boolean) => {
    if (!onStaticToolsChange) return;
    onStaticToolsChange({
      ...resolvedTools,
      [tool]: checked,
    });
  };

  const staticToolItems: Array<{
    key: StaticTool;
    label: string;
  }> = [
    { key: "opengrep", label: "规则扫描" },
    { key: "gitleaks", label: "密钥泄露扫描" },
    { key: "bandit", label: "Python 安全扫描" },
    { key: "phpstan", label: "PHPStan 扫描" },
    { key: "pmd", label: "PMD Java 扫描" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <Shield className="w-4 h-4 text-sky-600 dark:text-sky-400" />
        <span className="font-mono text-xs font-bold text-muted-foreground uppercase tracking-wider">
          扫描模式
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* 静态分析模式 */}
        <label
          className={cn(
            "relative flex flex-col p-4 border cursor-pointer transition-all rounded",
            isStaticSelected
              ? "border-sky-500/50 bg-sky-50 dark:bg-sky-950/30"
              : "border-border hover:border-border bg-muted/50",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <input
            type="radio"
            name="scanMode"
            value="static"
            checked={value === "static"}
            onChange={() => onChange("static")}
            disabled={disabled}
            className="sr-only"
          />

          {/* 推荐标签 */}
          <div className="absolute -top-2 -right-2 px-2 py-0.5 bg-sky-600 text-white text-xs font-bold uppercase font-mono rounded shadow-[0_0_10px_rgba(14,165,233,0.45)]">
            推荐
          </div>

          <div className="flex items-center gap-2 mb-2">
            <div className={cn(
              "p-1.5 rounded border",
              isStaticSelected
                ? "bg-sky-500/20 border-sky-500/50"
                : "bg-muted border-border"
            )}>
              <Zap className={cn(
                "w-4 h-4",
                isStaticSelected ? "text-sky-600 dark:text-sky-400" : "text-muted-foreground"
              )} />
            </div>
            <span className={cn(
              "font-bold text-sm font-mono uppercase",
              isStaticSelected ? "text-sky-700 dark:text-sky-300" : "text-foreground/70"
            )}>
              静态分析
            </span>
            {isStaticSelected && (
              <CheckCircle2 className="w-4 h-4 text-sky-600 dark:text-sky-400 ml-auto" />
            )}
          </div>

          <ul
            className={cn(
              "text-xs space-y-1 mb-3 font-mono",
              isStaticSelected ? "text-sky-700 dark:text-sky-300" : "text-foreground/70",
            )}
          >
            <li className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              基于规则的静态审计
            </li>
            <li className="flex items-center gap-1">
              <Code className="w-3 h-3" />
              选择规则多次分析
            </li>
            <li className="flex items-center gap-1">
              <Shield className="w-3 h-3" />
              无沙箱验证
            </li>
          </ul>

          {isStaticSelected && (
            <div className="mt-2 border-t border-border pt-3 space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-sky-700 dark:text-sky-300 font-bold font-mono">
                静态工具
              </div>
              {staticToolItems.map((tool) => (
                <div
                  key={tool.key}
                  className="flex items-center justify-between gap-2 rounded border border-sky-500/15 bg-background/30 px-2 py-1.5"
                >
                  <label className="flex min-w-0 items-center gap-2 text-xs font-mono text-sky-700 dark:text-sky-300 cursor-pointer">
                    <Checkbox
                      checked={resolvedTools[tool.key]}
                      onCheckedChange={(checked) =>
                        updateStaticTool(tool.key, Boolean(checked))
                      }
                      disabled={disabled || Boolean(disabledStaticTools?.[tool.key])}
                      className="border-border data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
                    />
                    <span className="tracking-wider">{tool.label}</span>
                  </label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0 text-sky-700 hover:bg-sky-500/10 hover:text-sky-600 dark:text-sky-300"
                    disabled={disabled || !onOpenStaticToolConfig}
                    aria-label={`配置 ${tool.label}`}
                    onClick={() => onOpenStaticToolConfig?.(tool.key)}
                  >
                    <Settings2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              {blockedStaticToolMessages?.pmd ? (
                <p className="text-[10px] text-amber-300">
                  {blockedStaticToolMessages.pmd}
                </p>
              ) : null}
            </div>
          )}

          <div className="mt-auto pt-2 border-t border-border">
            <span
              className={cn(
                "text-xs uppercase tracking-wider font-bold font-mono",
                isStaticSelected ? "text-sky-700 dark:text-sky-300" : "text-foreground/70",
              )}
            >
              适合: 合规检查、规则扫描
            </span>
          </div>
        </label>

        {/* Agent 扫描模式 */}
        <label
          className={cn(
            "relative flex flex-col p-4 border cursor-pointer transition-all rounded",
            isAgentSelected
              ? "border-violet-500/50 bg-violet-50 dark:bg-violet-950/30"
              : "border-border hover:border-border bg-muted/50",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <input
            type="radio"
            name="scanMode"
            value="agent"
            checked={value === "agent"}
            onChange={() => onChange("agent")}
            disabled={disabled}
            className="sr-only"
          />

          <div className="flex items-center gap-2 mb-2">
            <div className={cn(
              "p-1.5 rounded border",
              isAgentSelected
                ? "bg-violet-500/20 border-violet-500/50"
                : "bg-muted border-border"
            )}>
              <Bot className={cn(
                "w-4 h-4",
                isAgentSelected ? "text-violet-600 dark:text-violet-400" : "text-muted-foreground"
              )} />
            </div>
            <span className={cn(
              "font-bold text-sm font-mono uppercase",
              isAgentSelected ? "text-violet-700 dark:text-violet-300" : "text-foreground/70"
            )}>
              智能审计
            </span>
            {isAgentSelected && (
              <CheckCircle2 className="w-4 h-4 text-violet-600 dark:text-violet-400 ml-auto" />
            )}
          </div>

          <ul
            className={cn(
              "text-xs space-y-1 mb-3 font-mono",
              isAgentSelected ? "text-violet-700 dark:text-violet-300" : "text-foreground/70",
            )}
          >
            <li className="flex items-center gap-1">
              <Bot className="w-3 h-3" />
              AI Agent 自主分析
            </li>
            <li className="flex items-center gap-1">
              <Code className="w-3 h-3" />
              跨文件关联 + 结构化代码分析
            </li>
            <li className={cn(
              "flex items-center gap-1",
              isAgentSelected ? "text-violet-700 dark:text-violet-300 font-medium" : "text-foreground/70"
            )}>
              <Shield className="w-3 h-3" />
              沙箱漏洞验证
            </li>
          </ul>

          <div className="mt-auto pt-2 border-t border-border">
            <span
              className={cn(
                "text-xs uppercase tracking-wider font-bold font-mono",
                isAgentSelected ? "text-violet-700 dark:text-violet-300" : "text-foreground/70",
              )}
            >
              适合: 发版前扫描、深度安全评估
            </span>
          </div>
        </label>
      </div>

      {/* 模式说明 */}
      {value === "agent" ? (
        <div className="p-3 bg-violet-50 dark:bg-violet-950/30 border border-violet-500/30 text-xs text-violet-700 dark:text-violet-300 rounded font-mono">
          <p className="font-bold mb-1 uppercase text-violet-700 dark:text-violet-400">智能审计模式说明：</p>
          <ul className="list-disc list-inside space-y-0.5 text-violet-600 dark:text-violet-300/80">
            <li>AI Agent 会自主规划扫描策略</li>
            <li>使用跨文件关联与结构化代码分析定位风险</li>
            <li>在 Docker 沙箱中验证发现的漏洞</li>
            <li>可生成可复现的 PoC（概念验证）代码</li>
            <li>扫描时间较长，但结果更全面准确</li>
          </ul>
        </div>
      ) : (
        <div className="p-3 bg-sky-50 dark:bg-sky-950/30 border border-sky-500/30 text-xs text-sky-700 dark:text-sky-300 rounded font-mono">
          <p className="font-bold mb-1 uppercase text-sky-700 dark:text-sky-400">静态分析模式说明：</p>
          <ul className="list-disc list-inside space-y-0.5 text-sky-600 dark:text-sky-300/80">
            <li>基于规则引擎快速扫描代码漏洞</li>
            <li>支持按工具组合执行（Opengrep / Gitleaks）</li>
            <li>支持 Python Bandit 扫描</li>
            <li>结果稳定、反馈快，适合日常基线检查</li>
          </ul>
        </div>
      )}
    </div>
  );
}
