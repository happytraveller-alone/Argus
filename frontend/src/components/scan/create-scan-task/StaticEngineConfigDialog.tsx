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

export interface StaticEngineConfigDialogContentProps {
  engine: ScanEngineTab;
  scanMode: "static";
  enabled: boolean;
  blockedReason: string | null;
  creating: boolean;
  onNavigateToEngineConfig: (engine: ScanEngineTab) => void;
  onRequestClose?: () => void;
}

export interface StaticEngineConfigDialogProps extends StaticEngineConfigDialogContentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const PLACEHOLDER_COPY: Record<ScanEngineTab, string> = {
  opengrep: "后续将支持按规则集、严重级别等任务级配置。",
  codeql: "后续将支持语言、查询包和构建命令等任务级配置。",
  gitleaks: "后续将支持 no_git、规则集等任务级配置。",
  bandit: "后续将支持 severity、confidence 等任务级配置。",
  phpstan: "后续将支持 level 等任务级配置。",
  pmd: "后续将支持 ruleset 等任务级配置。",
};

function getEngineTitle(engine: ScanEngineTab) {
  switch (engine) {
    case "opengrep":
      return "Opengrep";
    case "codeql":
      return "CodeQL";
    case "gitleaks":
      return "Gitleaks";
    case "bandit":
      return "Bandit";
    case "phpstan":
      return "PHPStan";
    case "pmd":
      return "PMD";
  }
}

export function StaticEngineConfigDialogContent({
  engine,
  enabled,
  blockedReason,
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
            <p className="text-xs text-muted-foreground">该引擎的任务级配置即将开放。</p>
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

        <div className="rounded-md border border-border/60 bg-muted/20 p-4 text-sm text-muted-foreground">
          <div className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 text-sky-300" />
            <div>
              <p className="text-foreground">任务级配置即将开放</p>
              <p className="mt-1">{PLACEHOLDER_COPY[engine]}</p>
            </div>
          </div>
        </div>
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
