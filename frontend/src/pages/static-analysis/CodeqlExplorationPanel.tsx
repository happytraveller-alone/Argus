import { RefreshCw, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CodeqlExplorationProgressEvent } from "@/shared/api/opengrep";
import {
  buildCodeqlExplorationTimelineRows,
  type CodeqlExplorationTimelineRow,
} from "./viewModel";

function EventSnippet({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  if (!value) return null;
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <pre className="mt-1 max-h-24 overflow-auto rounded border border-border bg-background/70 p-2 text-xs leading-5 text-foreground whitespace-pre-wrap">
        {value}
      </pre>
    </div>
  );
}

function TimelineRow({ row }: { row: CodeqlExplorationTimelineRow }) {
  return (
    <div className="grid gap-2 border-t border-border py-3 first:border-t-0">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 shrink-0 rounded-full bg-sky-400" />
          <span className="text-sm font-medium text-foreground">{row.label}</span>
          {row.redacted ? (
            <span className="rounded border border-amber-400/30 bg-amber-500/10 px-1.5 py-0.5 text-[11px] text-amber-300">
              已脱敏
            </span>
          ) : null}
        </div>
        <span className="text-xs text-muted-foreground">{row.timestamp || "-"}</span>
      </div>
      <div className="text-sm text-muted-foreground">{row.detail}</div>
      <div className="grid gap-2 md:grid-cols-2">
        <EventSnippet label="命令" value={row.command} />
        <EventSnippet label="依赖安装" value={row.dependencyInstallation} />
        <EventSnippet label="stdout" value={row.stdout} />
        <EventSnippet label="stderr" value={row.stderr} />
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {row.exitCode !== null ? <span>退出码 {row.exitCode}</span> : null}
        {row.failureCategory ? <span>失败类型 {row.failureCategory}</span> : null}
        {row.reuseReason ? <span>复用原因 {row.reuseReason}</span> : null}
      </div>
    </div>
  );
}

export default function CodeqlExplorationPanel({
  events,
  canReset,
  resetting,
  onReset,
}: {
  events: CodeqlExplorationProgressEvent[];
  canReset: boolean;
  resetting: boolean;
  onReset: () => void;
}) {
  const rows = buildCodeqlExplorationTimelineRows(events);
  if (rows.length === 0 && !canReset) return null;

  return (
    <section className="rounded border border-border bg-card/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-foreground">CodeQL 编译探索</h2>
          <p className="text-xs text-muted-foreground">
            LLM 轮次、沙箱命令、捕获验证和项目级构建方案复用证据
          </p>
        </div>
        {canReset ? (
          <Button
            variant="outline"
            className="cyber-btn-outline h-8"
            disabled={resetting}
            onClick={onReset}
          >
            {resetting ? (
              <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            )}
            重置并重新探索
          </Button>
        ) : null}
      </div>
      <div className="mt-3">
        {rows.length > 0 ? (
          rows.map((row) => <TimelineRow key={row.key} row={row} />)
        ) : (
          <div className="border-t border-border pt-3 text-sm text-muted-foreground">
            暂无编译探索事件。
          </div>
        )}
      </div>
    </section>
  );
}
