import { ExternalLink, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { buildScanEngineConfigRoute, type ScanEngineTab } from "@/shared/constants/scanEngines";
import type { OpengrepSandboxMode } from "@/shared/api/opengrep";

export interface StaticEngineConfigDialogContentProps {
  engine: ScanEngineTab;
  scanMode: "static";
  enabled: boolean;
  blockedReason: string | null;
  creating: boolean;
  onNavigateToEngineConfig: (engine: ScanEngineTab) => void;
  opengrepSandbox?: OpengrepSandboxMode;
  onOpengrepSandboxChange?: (mode: OpengrepSandboxMode) => void;
  onRequestClose?: () => void;
}

export interface StaticEngineConfigDialogProps extends StaticEngineConfigDialogContentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const PLACEHOLDER_COPY: Record<ScanEngineTab, string> = {
  opengrep: "选择本次 Opengrep 任务使用 Dockerfile 容器或 A3S Box MicroVM。",
  codeql: "后续将支持语言、查询包和构建命令等任务级配置。",
};

function getEngineTitle(engine: ScanEngineTab) {
  switch (engine) {
    case "opengrep":
      return "Opengrep";
    case "codeql":
      return "CodeQL";
  }
}

export function StaticEngineConfigDialogContent({
  engine,
  enabled,
  blockedReason,
  opengrepSandbox = "dockerfile_container",
  onOpengrepSandboxChange,
  onNavigateToEngineConfig,
  onRequestClose,
}: StaticEngineConfigDialogContentProps) {
  const engineTitle = getEngineTitle(engine);
  const effectiveBlockedReason = blockedReason?.trim() || null;

  return (
    <>
      <div className="px-5 py-4 border-b border-border bg-muted">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
              {engineTitle} 配置
            </h2>
            <p className="text-xs text-muted-foreground">
              {engine === "opengrep" ? "选择本次任务的沙箱执行方式。" : "该引擎的任务级配置即将开放。"}
            </p>
          </div>
          <Badge className={enabled ? "cyber-badge-success" : "cyber-badge-muted"}>
            {enabled ? "已启用" : "未启用"}
          </Badge>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {effectiveBlockedReason ? (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
            <p className="font-semibold">当前项目暂不支持该引擎</p>
            <p className="mt-1">{effectiveBlockedReason}</p>
          </div>
        ) : null}

        {engine === "opengrep" ? (
          <div className="space-y-3 rounded-md border border-border/60 bg-muted/20 p-4">
            <div className="flex items-start gap-2 text-sm text-muted-foreground">
              <Info className="mt-0.5 h-4 w-4 text-sky-300" />
              <div>
                <p className="text-foreground">沙箱选择</p>
                <p className="mt-1">{PLACEHOLDER_COPY[engine]}</p>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-1">
              {[
                {
                  value: "dockerfile_container" as const,
                  title: "Dockerfile 容器",
                  description: "使用 docker/opengrep-runner.Dockerfile 构建的当前默认容器。",
                },
              ].map((item) => {
                const selected = opengrepSandbox === item.value;
                return (
                  <button
                    key={item.value}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onOpengrepSandboxChange?.(item.value)}
                    className={`rounded-md border p-3 text-left transition-colors ${
                      selected
                        ? "border-sky-500/60 bg-sky-500/10"
                        : "border-border bg-background/40 hover:border-sky-500/30"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className={`h-3 w-3 rounded-full border ${
                          selected ? "border-sky-300 bg-sky-400" : "border-muted-foreground"
                        }`}
                      />
                      <span className="text-sm font-semibold text-foreground">{item.title}</span>
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                      {item.description}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-border/60 bg-muted/20 p-4 text-sm text-muted-foreground">
            <div className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 text-sky-300" />
              <div>
                <p className="text-foreground">任务级配置即将开放</p>
                <p className="mt-1">{PLACEHOLDER_COPY[engine]}</p>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap justify-end gap-3 px-5 py-4 bg-muted border-t border-border">
        <Button
          type="button"
          variant="outline"
          className="cyber-btn-outline"
          onClick={onRequestClose}
        >
          关闭
        </Button>
        <Button
          type="button"
          className="cyber-btn-primary"
          onClick={() => onNavigateToEngineConfig(engine)}
        >
          <ExternalLink className="w-4 h-4" />
          前往扫描引擎配置页
        </Button>
      </div>
    </>
  );
}

export default function StaticEngineConfigDialog({
  open,
  onOpenChange,
  ...contentProps
}: StaticEngineConfigDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-describedby={undefined}
        className="!w-[min(92vw,760px)] !max-w-none p-0 gap-0 cyber-dialog border border-border rounded-lg"
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{getEngineTitle(contentProps.engine)} 配置</DialogTitle>
        </DialogHeader>
        <StaticEngineConfigDialogContent
          {...contentProps}
          onRequestClose={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

export function getStaticEngineConfigRoute(engine: ScanEngineTab) {
  return buildScanEngineConfigRoute(engine);
}
