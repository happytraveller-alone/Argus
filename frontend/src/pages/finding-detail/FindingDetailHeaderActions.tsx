import { ArrowLeft, Code2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";

export type FindingDetailCodeBrowserAction = {
  label?: string;
  to?: string | null;
  state?: Record<string, unknown>;
  disabledReason?: string | null;
};

interface FindingDetailHeaderActionsProps {
  codeBrowserAction?: FindingDetailCodeBrowserAction | null;
  onBack: () => void;
}

export function FindingDetailHeaderActions({
  codeBrowserAction,
  onBack,
}: FindingDetailHeaderActionsProps) {
  const label = codeBrowserAction?.label || "代码浏览";
  const isActionVisible = Boolean(codeBrowserAction);
  const isActionEnabled = Boolean(codeBrowserAction?.to);
  const disabledReason =
    codeBrowserAction?.disabledReason ||
    (isActionVisible && !isActionEnabled ? "暂不可用" : null);

  return (
    <div className="flex flex-wrap items-center gap-2">
      {isActionVisible ? (
        isActionEnabled ? (
          <Button
            asChild
            size="sm"
            variant="outline"
            className={cn(
              "cyber-btn-outline h-12 px-5 text-[1.1375rem] tracking-[0.14em]",
              "border-sky-500/50 text-sky-100 hover:text-white",
              "hover:border-sky-400/80 hover:bg-sky-500/10",
              "shadow-[0_0_12px_rgba(14,165,233,0.35)] transition duration-200",
              "focus-visible:border-sky-200/70 focus-visible:bg-sky-500/15",
            )}
            >
              <Link
                to={codeBrowserAction?.to as string}
                state={codeBrowserAction?.state}
              >
              <Code2 className="h-5 w-5" />
              <span className="ml-2">{label}</span>
            </Link>
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            className={cn(
              "cyber-btn-outline h-12 px-5 text-[1.1375rem] tracking-[0.14em]",
              "border-border/70 text-muted-foreground opacity-70",
              "cursor-not-allowed",
            )}
            disabled
            title={disabledReason || undefined}
            aria-label={disabledReason ? `${label}（${disabledReason}）` : label}
          >
            <Code2 className="h-5 w-5" />
            <span className="ml-2">{label}</span>
          </Button>
        )
      ) : null}
      <Button
        variant="outline"
        className="cyber-btn-outline h-12 px-5 text-[1.1375rem]"
        onClick={onBack}
      >
        <ArrowLeft className="w-5 h-5 mr-2" />
        返回
      </Button>
    </div>
  );
}

export default FindingDetailHeaderActions;
