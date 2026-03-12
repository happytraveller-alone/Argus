import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import FindingCodeWindow from "@/pages/AgentAudit/components/FindingCodeWindow";
import FindingNarrativeMarkdown from "@/pages/AgentAudit/components/FindingNarrativeMarkdown";
import type {
  FindingDetailPageModel,
  FindingDetailSummaryStat,
} from "./viewModel";

interface FindingDetailViewProps {
  model: FindingDetailPageModel;
  onBack: () => void;
}

function getToneClass(stat: FindingDetailSummaryStat): string {
  if (stat.tone === "danger") {
    return "border-rose-500/30 bg-rose-500/10 text-rose-100";
  }
  if (stat.tone === "warning") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  }
  if (stat.tone === "info") {
    return "border-sky-500/30 bg-sky-500/10 text-sky-100";
  }
  if (stat.tone === "success") {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-100";
  }
  return "border-white/10 bg-white/[0.04] text-slate-100";
}

export default function FindingDetailView({ model, onBack }: FindingDetailViewProps) {
  return (
    <div className="min-h-screen bg-background p-4 sm:p-6 flex flex-col gap-4 sm:gap-5">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-[0.08em] text-foreground">
            {model.pageTitle}
          </h1>
        </div>
        <Button variant="outline" className="cyber-btn-outline" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          返回
        </Button>
      </div>

      <div className="min-h-0 flex-1 grid grid-cols-1 xl:grid-cols-[minmax(0,0.98fr)_minmax(0,1.02fr)] gap-4">
        <div className="order-1 xl:order-2 cyber-card p-5 min-h-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
          <section className="relative overflow-hidden rounded-2xl border border-primary/20 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.18),rgba(15,23,42,0.92)_56%)] p-5 shadow-[0_18px_45px_rgba(15,23,42,0.22)]">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="cyber-badge-muted">{model.sourceLabel}</Badge>
              <Badge className="cyber-badge-muted">状态：{model.statusLabel}</Badge>
            </div>

            <div className="mt-4">
              <p className="text-[11px] font-mono uppercase tracking-[0.24em] text-sky-100/75">
                {model.heroEyebrow}
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-foreground break-words">
                {model.heroTitle}
              </h2>
              {model.heroSubtitle ? (
                <p className="mt-2 text-sm leading-7 text-foreground/82 break-words">
                  {model.heroSubtitle}
                </p>
              ) : null}
              {model.helperLocation ? (
                <p className="mt-3 text-xs font-mono text-slate-300/80 break-all">
                  {model.helperLocation}
                </p>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {model.summaryStats.map((stat) => (
                <div
                  key={`${stat.label}-${stat.value}`}
                  className={`rounded-xl border px-4 py-3 ${getToneClass(stat)}`}
                >
                  <div className="text-[11px] uppercase tracking-[0.2em] text-current/75">
                    {stat.label}
                  </div>
                  <div className="mt-2 text-lg font-semibold text-current break-words">
                    {stat.value}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-border/70 bg-card/50 p-4 space-y-3">
            <div>
              <p className="text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                {model.rootCause.title}
              </p>
            </div>
            {model.rootCause.finding ? (
              <FindingNarrativeMarkdown finding={model.rootCause.finding} variant="detail" />
            ) : (
              <p className="text-base leading-7 text-foreground/92 whitespace-pre-wrap break-words">
                {model.rootCause.body || "-"}
              </p>
            )}
          </section>

          <section className="rounded-xl border border-border/70 bg-card/35 p-4 space-y-3">
            <div>
              <p className="text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                追踪信息
              </p>
            </div>
            <div className="grid gap-3">
              {model.trackingItems.map((item) => (
                <div
                  key={`${item.label}-${item.value}`}
                  className="grid gap-1 sm:grid-cols-[108px_minmax(0,1fr)] sm:gap-3"
                >
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                    {item.label}
                  </div>
                  <div
                    className={`text-sm text-foreground break-all ${
                      item.mono ? "font-mono text-[13px]" : ""
                    }`}
                  >
                    {item.value || "-"}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="order-2 xl:order-1 cyber-card p-5 min-h-0 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold uppercase tracking-[0.18em] text-foreground">
              {model.codePanelTitle}
            </h2>
            <span className="text-sm text-muted-foreground">
              {model.codeSections.length} 个代码块
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-1">
            {model.codeSections.length > 0 ? (
              model.codeSections.map((section) => (
                <FindingCodeWindow
                  key={section.id}
                  code={section.code}
                  displayLines={section.displayLines}
                  filePath={section.filePath}
                  lineStart={section.lineStart}
                  lineEnd={section.lineEnd}
                  highlightStartLine={section.highlightStartLine}
                  highlightEndLine={section.highlightEndLine}
                  focusLine={section.focusLine}
                  title={section.title || "命中代码"}
                  variant="detail"
                />
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-border/80 bg-card/25 p-5 text-sm leading-7 text-muted-foreground">
                {model.emptyCodeMessage}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
