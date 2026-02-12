import { useMemo } from "react";
import type { RefObject } from "react";
import {
  AlertTriangle,
  Bug,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type { FindingsViewFilters } from "../types";

interface FindingsPanelProps {
  findings: AgentFinding[];
  loading: boolean;
  error: string | null;
  filters: FindingsViewFilters;
  highlightedFindingId: string | null;
  onRetry: () => void;
  onFiltersChange: (next: FindingsViewFilters) => void;
  onOpenDetail: (item: AgentFinding) => void;
  containerRef?: RefObject<HTMLDivElement>;
}

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const SEVERITY_BADGE_CLASS: Record<string, string> = {
  critical:
    "bg-rose-500/20 text-rose-600 dark:text-rose-300 border-rose-500/40",
  high:
    "bg-orange-500/20 text-orange-600 dark:text-orange-300 border-orange-500/40",
  medium:
    "bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/40",
  low: "bg-sky-500/20 text-sky-600 dark:text-sky-300 border-sky-500/40",
  info: "bg-zinc-500/20 text-zinc-700 dark:text-zinc-300 border-zinc-500/40",
};

function isFalsePositive(item: AgentFinding): boolean {
  return (
    item.status === "false_positive" || item.authenticity === "false_positive"
  );
}

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatLocation(item: AgentFinding): string {
  if (!item.file_path) return "未定位文件";
  if (item.line_start && item.line_end && item.line_end !== item.line_start) {
    return `${item.file_path}:${item.line_start}-${item.line_end}`;
  }
  if (item.line_start) return `${item.file_path}:${item.line_start}`;
  return item.file_path;
}

export function FindingsPanel({
  findings,
  loading,
  error,
  filters,
  highlightedFindingId,
  onRetry,
  onFiltersChange,
  onOpenDetail,
  containerRef,
}: FindingsPanelProps) {
  const filteredFindings = useMemo(() => {
    const normalizedKeyword = filters.keyword.trim().toLowerCase();
    const sorted = [...findings].sort((a, b) => {
      const aSeverity = SEVERITY_ORDER[a.severity?.toLowerCase() || "info"] ?? 99;
      const bSeverity = SEVERITY_ORDER[b.severity?.toLowerCase() || "info"] ?? 99;
      if (aSeverity !== bSeverity) return aSeverity - bSeverity;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });

    return sorted.filter((item) => {
      const matchedKeyword =
        normalizedKeyword.length === 0 ||
        (item.title || "").toLowerCase().includes(normalizedKeyword) ||
        (item.description || "").toLowerCase().includes(normalizedKeyword) ||
        (item.file_path || "").toLowerCase().includes(normalizedKeyword);
      const matchedSeverity =
        filters.severity === "all" ||
        (item.severity || "").toLowerCase() === filters.severity;
      const matchedVerification =
        filters.verification === "all" ||
        (filters.verification === "verified" && item.is_verified) ||
        (filters.verification === "unverified" && !item.is_verified);
      const matchedFilteredView = filters.showFiltered
        ? isFalsePositive(item)
        : !isFalsePositive(item);
      return (
        matchedKeyword &&
        matchedSeverity &&
        matchedVerification &&
        matchedFilteredView
      );
    });
  }, [filters, findings]);

  const falsePositiveCount = useMemo(
    () => findings.filter((item) => isFalsePositive(item)).length,
    [findings],
  );

  const renderBody = () => {
    if (loading && findings.length === 0) {
      return (
        <div className="h-full flex items-center justify-center text-muted-foreground">
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载审计结果中...
          </div>
        </div>
      );
    }

    if (error && findings.length === 0) {
      return (
        <div className="h-full flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 text-center max-w-md px-4">
            <AlertTriangle className="w-6 h-6 text-amber-500" />
            <div className="text-sm text-muted-foreground">{error}</div>
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCw className="w-3.5 h-3.5 mr-2" />
              重试加载
            </Button>
          </div>
        </div>
      );
    }

    if (filteredFindings.length === 0) {
      return (
        <div className="h-full flex items-center justify-center text-muted-foreground">
          <div className="flex flex-col items-center gap-2 text-center">
            <Bug className="w-5 h-5 opacity-60" />
            <span className="text-sm">
              {filters.showFiltered ? "当前无已过滤漏洞" : "当前筛选条件下暂无有效漏洞"}
            </span>
          </div>
        </div>
      );
    }

    return (
      <div className="p-3 space-y-2">
        <div className="hidden lg:grid lg:grid-cols-[106px_minmax(0,2.5fr)_minmax(0,1.6fr)_92px_82px_114px_130px_auto] gap-3 px-3 py-2 text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
          <span>严重度</span>
          <span>标题</span>
          <span>文件定位</span>
          <span>验证状态</span>
          <span>置信度</span>
          <span>可达性</span>
          <span>时间</span>
          <span>操作</span>
        </div>

        {filteredFindings.map((item) => {
          const severityKey = (item.severity || "info").toLowerCase();
          const confidence =
            typeof item.ai_confidence === "number"
              ? `${Math.round(item.ai_confidence * 100)}%`
              : "未设置";
          const anchorId = `finding-item-${item.id}`;
          return (
            <div
              id={anchorId}
              key={item.id}
              className={`rounded-lg border border-border bg-card/70 px-3 py-3 hover:border-primary/35 transition-colors ${
                highlightedFindingId === item.id ? "ring-2 ring-primary/60" : ""
              }`}
            >
              <div className="flex flex-col gap-2 lg:grid lg:grid-cols-[106px_minmax(0,2.5fr)_minmax(0,1.6fr)_92px_82px_114px_130px_auto] lg:items-start lg:gap-3">
                <div>
                  <Badge
                    className={`border text-[11px] ${SEVERITY_BADGE_CLASS[severityKey] || SEVERITY_BADGE_CLASS.info}`}
                  >
                    {severityKey.toUpperCase()}
                  </Badge>
                </div>

                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground leading-5 break-words line-clamp-2">
                    {item.title || "未命名漏洞"}
                  </p>
                  {item.description && (
                    <p className="mt-1 text-xs text-muted-foreground break-words line-clamp-2">
                      {item.description}
                    </p>
                  )}
                </div>

                <div className="text-xs text-muted-foreground break-words leading-5">
                  {formatLocation(item)}
                </div>

                <div>
                  <Badge variant="outline" className="text-[11px]">
                    {item.is_verified ? "已验证" : "未验证"}
                  </Badge>
                </div>

                <div className="text-xs text-muted-foreground">{confidence}</div>

                <div className="text-xs text-muted-foreground">
                  {item.reachability || "-"}
                </div>

                <div className="text-xs text-muted-foreground">
                  {formatCreatedAt(item.created_at)}
                </div>

                <div className="flex justify-start lg:justify-end">
                  <button
                    type="button"
                    onClick={() => onOpenDetail(item)}
                    className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
                  >
                    查看详情
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
        <div className="flex flex-col md:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filters.keyword}
              onChange={(event) =>
                onFiltersChange({ ...filters, keyword: event.target.value })
              }
              placeholder="搜索标题 / 描述 / 文件路径"
              className="pl-9 h-9"
            />
          </div>
          <select
            value={filters.severity}
            onChange={(event) =>
              onFiltersChange({ ...filters, severity: event.target.value })
            }
            className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
          >
            <option value="all">全部严重度</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>
          <select
            value={filters.verification}
            onChange={(event) =>
              onFiltersChange({ ...filters, verification: event.target.value })
            }
            className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
          >
            <option value="all">全部验证状态</option>
            <option value="verified">已验证</option>
            <option value="unverified">未验证</option>
          </select>
          <button
            type="button"
            onClick={() =>
              onFiltersChange({ ...filters, showFiltered: !filters.showFiltered })
            }
            className={`h-9 px-3 rounded-md border text-sm ${
              filters.showFiltered
                ? "border-amber-500/50 text-amber-600 dark:text-amber-300 bg-amber-500/10"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {filters.showFiltered
              ? "查看有效漏洞"
              : `查看已过滤(${falsePositiveCount})`}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto custom-scrollbar">
        {renderBody()}
      </div>
    </div>
  );
}

export default FindingsPanel;
