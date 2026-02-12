import { Link } from "react-router-dom";
import { ExternalLink, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { OpengrepFinding } from "@/shared/api/opengrep";
import type { BootstrapInputsSummary } from "../types";

interface BootstrapInputsPanelProps {
  summary: BootstrapInputsSummary;
  findings: OpengrepFinding[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

function formatLocation(item: OpengrepFinding): string {
  if (!item.file_path) return "未定位";
  if (item.start_line) {
    return `${item.file_path}:${item.start_line}`;
  }
  return item.file_path;
}

function formatConfidence(confidence?: string | null): string {
  const normalized = String(confidence || "").toUpperCase();
  if (normalized === "HIGH" || normalized === "MEDIUM" || normalized === "LOW") {
    return normalized;
  }
  return "未设置";
}

export function BootstrapInputsPanel({
  summary,
  findings,
  loading,
  error,
  onRetry,
}: BootstrapInputsPanelProps) {
  return (
    <details className="mx-4 mt-4 rounded-lg border border-border bg-card/70" open={false}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">静态输入</span>
          <Badge variant="outline" className="text-[11px]">
            仅 ERROR + HIGH/MEDIUM
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>总扫描 {summary.totalFindings}</span>
          <span>入选 {summary.candidateCount}</span>
        </div>
      </summary>

      <div className="border-t border-border px-4 py-3 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            该智能审计任务的预扫描输入（来源: {summary.source}）
          </p>
          <Link
            to={`/static-analysis/${summary.taskId}?opengrepTaskId=${summary.taskId}`}
            className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            查看原始静态扫描详情
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
        </div>

        {loading ? (
          <div className="h-24 flex items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            加载静态输入中...
          </div>
        ) : error ? (
          <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2">
            <p className="text-xs text-rose-300">{error}</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="mt-2 h-7 text-xs"
              onClick={onRetry}
            >
              重试
            </Button>
          </div>
        ) : findings.length === 0 ? (
          <div className="h-20 flex items-center justify-center text-xs text-muted-foreground">
            当前无符合口径的静态输入项
          </div>
        ) : (
          <div className="space-y-2">
            {findings.map((item) => (
              <div
                key={item.id}
                className="rounded-md border border-border/80 bg-background/70 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge className="border border-rose-500/40 bg-rose-500/15 text-rose-200">
                    ERROR
                  </Badge>
                  <Badge variant="outline" className="text-[11px]">
                    {formatConfidence(item.confidence)}
                  </Badge>
                  <span className="font-medium text-foreground break-all">
                    {item.rule_name || item.description || item.id}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground break-all">
                  {formatLocation(item)}
                </p>
                {item.code_snippet && (
                  <pre className="mt-2 max-h-28 overflow-auto rounded bg-muted/50 p-2 text-[11px] text-muted-foreground whitespace-pre-wrap break-words">
                    {item.code_snippet}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

export default BootstrapInputsPanel;
