import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Hammer,
  Loader2,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useCodeqlTemplateStatus } from "@/hooks/useCodeqlTemplateStatus";
import type { CubesandboxTemplateStatus } from "@/shared/api/cubesandboxTemplates";
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

interface TemplateStatusBadge {
  label: string;
  className: string;
  icon: JSX.Element;
}

function describeTemplateStatus(
  status: CubesandboxTemplateStatus,
): TemplateStatusBadge {
  switch (status) {
    case "ready":
      return {
        label: "模板就绪",
        className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
        icon: <CheckCircle2 className="h-3.5 w-3.5" />,
      };
    case "building":
      return {
        label: "构建中",
        className: "border-amber-500/30 bg-amber-500/10 text-amber-300",
        icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
      };
    case "pending":
      return {
        label: "排队中",
        className: "border-sky-500/30 bg-sky-500/10 text-sky-300",
        icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
      };
    case "failed":
      return {
        label: "构建失败",
        className: "border-rose-500/30 bg-rose-500/10 text-rose-300",
        icon: <AlertCircle className="h-3.5 w-3.5" />,
      };
    case "invalidated":
      return {
        label: "已失效",
        className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
        icon: <AlertCircle className="h-3.5 w-3.5" />,
      };
    default:
      return {
        label: "未构建",
        className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-300",
        icon: <Hammer className="h-3.5 w-3.5" />,
      };
  }
}

function TemplateStatusCard() {
  const {
    status,
    templateId,
    jobId,
    errorMessage,
    buildLogTail,
    isMutating,
    provision,
    invalidate,
  } = useCodeqlTemplateStatus();
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const badge = describeTemplateStatus(status);
  const isBuilding = status === "building" || status === "pending";

  const handleProvision = async () => {
    setActionError(null);
    try {
      await provision();
    } catch (error) {
      const message =
        (error as { response?: { data?: { error?: string } } })?.response?.data?.error ||
        (error as Error).message ||
        "构建触发失败";
      setActionError(message);
    }
  };

  const handleRebuild = async () => {
    setConfirmRebuild(false);
    setActionError(null);
    try {
      await invalidate();
      await provision();
    } catch (error) {
      const message =
        (error as { response?: { data?: { error?: string } } })?.response?.data?.error ||
        (error as Error).message ||
        "重建触发失败";
      setActionError(message);
    }
  };

  return (
    <div className="rounded border border-border bg-background/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] ${badge.className}`}
          >
            {badge.icon}
            {badge.label}
          </span>
          {templateId ? (
            <span className="font-mono text-xs text-muted-foreground">{templateId}</span>
          ) : null}
          {jobId && isBuilding ? (
            <span className="text-[11px] text-muted-foreground">job {jobId}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {status === "ready" ? (
            <Button
              variant="outline"
              size="sm"
              className="cyber-btn-outline h-7"
              disabled={isMutating}
              onClick={() => setConfirmRebuild(true)}
            >
              <Hammer className="mr-1.5 h-3.5 w-3.5" />
              重建模板
            </Button>
          ) : isBuilding ? (
            <Button
              variant="outline"
              size="sm"
              className="cyber-btn-outline h-7"
              onClick={() => setShowLog((prev) => !prev)}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              {showLog ? "隐藏日志" : "查看日志"}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="cyber-btn-outline h-7"
              disabled={isMutating}
              onClick={handleProvision}
            >
              <Hammer className="mr-1.5 h-3.5 w-3.5" />
              立即构建
            </Button>
          )}
        </div>
      </div>
      {status === "failed" && errorMessage ? (
        <div className="mt-2 rounded border border-rose-500/30 bg-rose-500/5 p-2 text-xs text-rose-200">
          {errorMessage}
        </div>
      ) : null}
      {actionError ? (
        <div className="mt-2 rounded border border-rose-500/30 bg-rose-500/5 p-2 text-xs text-rose-200">
          {actionError}
        </div>
      ) : null}
      {status === "absent" ? (
        <p className="mt-2 text-[11px] text-muted-foreground">
          后端尚未构建 CodeQL C/C++ 沙箱模板。点击「立即构建」触发自动镜像构建+模板注册流程。
        </p>
      ) : null}
      {(showLog || status === "failed") && buildLogTail ? (
        <pre className="mt-2 max-h-40 overflow-auto rounded border border-border bg-background/70 p-2 text-[11px] leading-5 text-foreground whitespace-pre-wrap">
          {buildLogTail}
        </pre>
      ) : null}
      <AlertDialog open={confirmRebuild} onOpenChange={setConfirmRebuild}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认重建模板?</AlertDialogTitle>
            <AlertDialogDescription>
              当前模板 {templateId ?? "(未知)"} 将被标记为失效,并重新执行镜像构建与模板注册。重建期间 CodeQL 扫描将阻塞等待新模板就绪。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleRebuild}>确认重建</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const { status: templateStatus } = useCodeqlTemplateStatus();
  const templateReady = templateStatus === "ready";

  useEffect(() => {
    const scrollArea = scrollAreaRef.current;
    if (!scrollArea || !shouldAutoScrollRef.current) return;
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }, [rows.length]);

  const handleTimelineScroll = () => {
    const scrollArea = scrollAreaRef.current;
    if (!scrollArea) return;
    const distanceToBottom =
      scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight;
    shouldAutoScrollRef.current = distanceToBottom < 24;
  };

  return (
    <section className="flex max-h-full min-h-0 flex-col rounded border border-border bg-card/40 p-4">
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
            disabled={resetting || !templateReady}
            title={
              templateReady
                ? undefined
                : "CodeQL 模板未就绪,请先在下方面板点击「立即构建」或「重建模板」"
            }
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
        <TemplateStatusCard />
      </div>
      <div
        ref={scrollAreaRef}
        className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1"
        onScroll={handleTimelineScroll}
      >
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
