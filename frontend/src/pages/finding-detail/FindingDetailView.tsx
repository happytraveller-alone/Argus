import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import FindingNarrativeMarkdown from "@/pages/AgentAudit/components/FindingNarrativeMarkdown";
import FindingDetailCodePanel, {
  type FindingDetailFullFileLoadResult,
} from "./FindingDetailCodePanel";
import type {
  FindingDetailFullFileRequest,
  FindingDetailPageModel,
  FindingDetailTrackingItem,
} from "./viewModel";

interface FindingDetailViewProps {
  model: FindingDetailPageModel;
  onBack: () => void;
  onLoadFullFile?: (
    request: FindingDetailFullFileRequest,
  ) => Promise<FindingDetailFullFileLoadResult>;
}

interface InfoSectionProps {
  title: string;
  items: FindingDetailTrackingItem[];
}

function InfoSection({ title, items }: InfoSectionProps) {
  return (
    <section className="rounded-xl border border-border/70 bg-card/35 p-4 space-y-3">
      <div>
        <p className="text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
          {title}
        </p>
      </div>
      <div className="grid gap-3">
        {items.map((item) => (
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
              title={item.title || undefined}
            >
              {item.value || "-"}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function FindingDetailView({
  model,
  onBack,
  onLoadFullFile,
}: FindingDetailViewProps) {
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
          <InfoSection title="概览信息" items={model.overviewItems} />
          <InfoSection title="追踪信息" items={model.trackingItems} />

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
        </div>

        <FindingDetailCodePanel
          title={model.codePanelTitle}
          sections={model.codeSections}
          emptyMessage={model.emptyCodeMessage}
          onLoadFullFile={onLoadFullFile}
        />
      </div>
    </div>
  );
}
