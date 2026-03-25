import { memo, type ReactNode } from "react";
import { Switch } from "@/components/ui/switch";
import FindingNarrativeMarkdown from "../components/FindingNarrativeMarkdown";
import type { AgentTask } from "@/shared/api/agentTasks";
import {
  AlertTriangle,
  Bug,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Search,
  Settings2,
  X,
  Zap,
} from "lucide-react";
import { getReportExportScoreColor } from "./utils";

export type ReportFormat = "markdown" | "json" | "pdf";

export interface ExportOptions {
  includeCodeSnippets: boolean;
  includeRemediation: boolean;
  includeMetadata: boolean;
  compactMode: boolean;
}

const CircularProgress = memo(function CircularProgress({
  value,
  size = 80,
  strokeWidth = 6,
  className = "",
}: {
  value: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (value / 100) * circumference;
  const colors = getReportExportScoreColor(value);

  return (
    <div className={`relative inline-flex items-center justify-center ${className}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-slate-300 dark:text-slate-700"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={`${colors.bg} ${colors.glow} transition-all duration-1000 ease-out`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-xl font-bold font-mono ${colors.text}`}>
          {value.toFixed(0)}
        </span>
        <span className="text-[8px] text-muted-foreground uppercase tracking-wider">
          分
        </span>
      </div>
    </div>
  );
});

export const EnhancedStatsPanel = memo(function EnhancedStatsPanel({
  task,
}: {
  task: AgentTask;
}) {
  const totalFindings = task.findings_count || 0;
  const criticalAndHigh = (task.critical_count || 0) + (task.high_count || 0);
  const verified = task.verified_count || 0;
  const score = task.security_score || 0;

  const stats = [
    {
      icon: <Bug className="w-4 h-4" />,
      label: "漏洞总数",
      value: totalFindings,
      color: "text-foreground",
      iconColor: "text-rose-600 dark:text-rose-400",
      trend: totalFindings > 0 ? "up" : null,
    },
    {
      icon: <AlertTriangle className="w-4 h-4" />,
      label: "高危问题",
      value: criticalAndHigh,
      color:
        criticalAndHigh > 0
          ? "text-rose-600 dark:text-rose-400"
          : "text-muted-foreground",
      iconColor: "text-orange-600 dark:text-orange-400",
      trend: criticalAndHigh > 0 ? "critical" : null,
    },
    {
      icon: <CheckCircle2 className="w-4 h-4" />,
      label: "已验证",
      value: verified,
      color: "text-emerald-600 dark:text-emerald-400",
      iconColor: "text-emerald-600 dark:text-emerald-400",
      trend: null,
    },
  ];

  return (
    <div className="flex items-stretch gap-4">
      <div className="flex items-center justify-center p-3 rounded-xl bg-gradient-to-br from-muted to-background border border-border backdrop-blur-sm">
        <CircularProgress value={score} size={72} strokeWidth={5} />
      </div>

      <div className="flex-1 grid grid-cols-3 gap-2">
        {stats.map((stat, index) => (
          <div
            key={index}
            className="relative p-3 rounded-xl bg-gradient-to-br from-muted/40 to-background/40 border border-border backdrop-blur-sm group hover:border-border transition-all duration-300"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <div className={`${stat.iconColor} opacity-80`}>{stat.icon}</div>
              <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
                {stat.label}
              </span>
            </div>
            <div className="flex items-baseline gap-1">
              <span className={`text-2xl font-bold font-mono ${stat.color}`}>
                {stat.value}
              </span>
              {stat.trend === "critical" && stat.value > 0 && (
                <Zap className="w-3 h-3 text-rose-600 dark:text-rose-400" />
              )}
            </div>
            <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary/0 via-primary/5 to-primary/0 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          </div>
        ))}
      </div>
    </div>
  );
});

export const FormatSelector = memo(function FormatSelector({
  activeFormat,
  onFormatChange,
  items,
}: {
  activeFormat: ReportFormat;
  onFormatChange: (format: ReportFormat) => void;
  items: Array<{
    key: ReportFormat;
    label: string;
    description: string;
    icon: ReactNode;
    color: string;
    bgColor: string;
  }>;
}) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map((config) => {
        const isActive = config.key === activeFormat;
        return (
          <button
            key={config.key}
            onClick={() => onFormatChange(config.key)}
            className={`relative p-4 rounded-xl border transition-all duration-300 text-left group ${
              isActive
                ? `${config.bgColor} border-opacity-100 shadow-lg`
                : "bg-muted border-border hover:border-border hover:bg-muted"
            }`}
          >
            {isActive && (
              <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
                <Check className="w-3 h-3 text-foreground" />
              </div>
            )}
            <div className={`mb-2 ${isActive ? config.color : "text-muted-foreground group-hover:text-foreground"}`}>
              {config.icon}
            </div>
            <div className="text-sm font-semibold mb-0.5 text-foreground">
              {config.label}
            </div>
            <div className="text-xs text-muted-foreground">
              {config.description}
            </div>
            <div
              className={`absolute bottom-0 left-1/2 -translate-x-1/2 h-0.5 rounded-full transition-all duration-300 ${
                isActive
                  ? "w-12 bg-gradient-to-r from-transparent via-primary to-transparent"
                  : "w-0"
              }`}
            />
          </button>
        );
      })}
    </div>
  );
});

export const ExportOptionsPanel = memo(function ExportOptionsPanel({
  options,
  onOptionsChange,
  expanded,
  onToggle,
}: {
  options: ExportOptions;
  onOptionsChange: (options: ExportOptions) => void;
  expanded: boolean;
  onToggle: () => void;
}) {
  const optionItems = [
    {
      key: "includeCodeSnippets",
      label: "包含代码片段",
      description: "导出相关的代码示例",
    },
    {
      key: "includeRemediation",
      label: "包含修复建议",
      description: "导出漏洞修复方案",
    },
    {
      key: "includeMetadata",
      label: "包含元数据",
      description: "导出任务和文件信息",
    },
    { key: "compactMode", label: "紧凑模式", description: "减少空白和间距" },
  ];

  return (
    <div className="rounded-xl border border-border bg-muted/50 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">导出选项</span>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>

      <div className={`grid transition-all duration-300 ease-out ${
        expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      }`}>
        <div className="overflow-hidden">
          <div className="p-3 pt-0 space-y-2">
            {optionItems.map((item) => (
              <label
                key={item.key}
                className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/20 cursor-pointer transition-colors"
              >
                <div className="flex-1">
                  <div className="text-xs font-medium text-foreground">
                    {item.label}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {item.description}
                  </div>
                </div>
                <Switch
                  checked={options[item.key as keyof ExportOptions]}
                  onCheckedChange={(checked) =>
                    onOptionsChange({ ...options, [item.key]: checked })
                  }
                  className="data-[state=checked]:bg-primary"
                />
              </label>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
});

export const PreviewSearchBar = memo(function PreviewSearchBar({
  searchQuery,
  onSearchChange,
  matchCount,
  onClear,
}: {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  matchCount: number;
  onClear: () => void;
}) {
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-muted border border-border">
      <Search className="w-3.5 h-3.5 text-muted-foreground" />
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="搜索..."
        className="w-24 bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none"
      />
      {searchQuery && (
        <>
          <span className="text-xs text-muted-foreground font-mono">
            {matchCount}
          </span>
          <button
            onClick={onClear}
            className="p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-3 h-3" />
          </button>
        </>
      )}
    </div>
  );
});

export const PreviewSkeleton = memo(function PreviewSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-6 bg-muted/30 rounded w-3/4" />
      <div className="space-y-2">
        <div className="h-4 bg-muted/20 rounded w-full" />
        <div className="h-4 bg-muted/20 rounded w-5/6" />
        <div className="h-4 bg-muted/20 rounded w-4/6" />
      </div>
      <div className="h-20 bg-muted/20 rounded" />
      <div className="space-y-2">
        <div className="h-4 bg-muted/20 rounded w-full" />
        <div className="h-4 bg-muted/20 rounded w-3/4" />
      </div>
      <div className="h-16 bg-muted/20 rounded" />
    </div>
  );
});

export const MarkdownPreview = memo(function MarkdownPreview({
  content,
  searchQuery = "",
}: {
  content: string;
  searchQuery?: string;
}) {
  return (
    <div className="prose prose-invert max-w-none break-words overflow-wrap-anywhere">
      <FindingNarrativeMarkdown
        finding={{ description_markdown: content }}
        searchQuery={searchQuery}
      />
    </div>
  );
});

export const JsonPreview = memo(function JsonPreview({
  content,
  searchQuery = "",
}: {
  content: string;
  searchQuery?: string;
}) {
  const highlightJson = (json: string) => {
    try {
      const parsed = JSON.parse(json);
      const formatted = JSON.stringify(parsed, null, 2);

      let result = formatted
        .replace(/"([^"]+)":/g, '<span class="text-violet-400">"$1"</span>:')
        .replace(/: "([^"]+)"/g, ': <span class="text-emerald-400">"$1"</span>')
        .replace(/: (\d+\.?\d*)/g, ': <span class="text-amber-400">$1</span>')
        .replace(/: (true|false)/g, ': <span class="text-sky-400">$1</span>')
        .replace(/: (null)/g, ': <span class="text-muted-foreground">$1</span>');

      if (searchQuery) {
        const regex = new RegExp(
          `(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
          "gi",
        );
        result = result.replace(
          regex,
          '<mark class="bg-primary/40 text-foreground px-0.5 rounded">$1</mark>',
        );
      }

      return result;
    } catch {
      return json;
    }
  };

  const lines = content.split("\n");
  return (
    <div className="relative">
      <div className="absolute left-0 top-0 bottom-0 w-10 bg-background border-r border-border select-none">
        <div className="py-3 text-xs font-mono text-muted-foreground text-right pr-2 leading-5">
          {lines.map((_, index) => (
            <div key={index}>{index + 1}</div>
          ))}
        </div>
      </div>
      <pre
        className="text-xs font-mono text-foreground whitespace-pre-wrap break-all pl-14 py-3 leading-5"
        dangerouslySetInnerHTML={{ __html: highlightJson(content) }}
      />
    </div>
  );
});

export const HtmlPreview = memo(function HtmlPreview({
  content,
  searchQuery = "",
}: {
  content: string;
  searchQuery?: string;
}) {
  const highlightHtml = (html: string) => {
    let result = html
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/(&lt;\/?[a-zA-Z][a-zA-Z0-9]*)/g, '<span class="text-rose-400">$1</span>')
      .replace(/(\s[a-zA-Z-]+)=/g, '<span class="text-amber-400">$1</span>=')
      .replace(/"([^"]*)"/g, '"<span class="text-emerald-400">$1</span>"')
      .replace(/(&lt;!DOCTYPE[^&]*&gt;)/gi, '<span class="text-muted-foreground">$1</span>');

    if (searchQuery) {
      const regex = new RegExp(
        `(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`,
        "gi",
      );
      result = result.replace(
        regex,
        '<mark class="bg-primary/40 text-foreground px-0.5 rounded">$1</mark>',
      );
    }

    return result;
  };

  return (
    <div className="relative">
      <pre
        className="text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all leading-5"
        dangerouslySetInnerHTML={{ __html: highlightHtml(content) }}
      />
    </div>
  );
});
