import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import FindingCodeWindow from "./FindingCodeWindow";
import type { ParsedToolEvidence, ToolEvidencePayload } from "../toolEvidence";
import { asParsedToolEvidence } from "../toolEvidence";
import type { ToolEvidenceMissingState, ToolStatus } from "../types";
import {
  buildToolEvidenceDetailViewModel,
  type ToolEvidencePrimaryPanel,
} from "../toolEvidenceDetailModel";

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border/60 bg-card/60 p-4 space-y-3">
      <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">{title}</div>
      {children}
    </section>
  );
}

function badgeToneClass(tone?: "default" | "success" | "warning" | "danger") {
  if (tone === "success") {
    return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
  }
  if (tone === "warning") {
    return "border-amber-500/40 bg-amber-500/10 text-amber-100";
  }
  if (tone === "danger") {
    return "border-rose-500/40 bg-rose-500/10 text-rose-100";
  }
  return "";
}

function RawDataSection({
  content,
  triggerLabel,
}: {
  content: string;
  triggerLabel: string;
}) {
  return (
    <DetailSection title="原始数据">
      <Collapsible className="rounded-xl border border-border/70 bg-background/40">
        <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground">
          <span>{triggerLabel}</span>
          <ChevronDown className="h-4 w-4" />
        </CollapsibleTrigger>
        <CollapsibleContent className="px-3 pb-3">
          <pre className="max-h-[60vh] overflow-auto rounded-lg border border-border/70 bg-background px-3 py-3 text-xs whitespace-pre-wrap break-words">
            {content}
          </pre>
        </CollapsibleContent>
      </Collapsible>
    </DetailSection>
  );
}

function toRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function extractResultText(rawOutput: unknown): string {
  if (typeof rawOutput === "string") return rawOutput;
  const record = toRecord(rawOutput);
  return typeof record?.result === "string" ? record.result : "";
}

function MissingEvidenceDetail({
  missingState,
  rawOutput,
  runtimeMetadata,
  toolStatus,
}: {
  missingState: ToolEvidenceMissingState;
  rawOutput: unknown;
  runtimeMetadata?: Record<string, unknown> | null;
  toolStatus?: ToolStatus;
}) {
  const resultText = extractResultText(rawOutput);
  const outputRecord = toRecord(rawOutput);
  const errorCode =
    (typeof outputRecord?.error_code === "string" && outputRecord.error_code) ||
    (typeof runtimeMetadata?.error_code === "string" && runtimeMetadata.error_code) ||
    "";
  const validationError =
    typeof runtimeMetadata?.validation_error === "string" ? runtimeMetadata.validation_error : "";
  const inputRepaired =
    runtimeMetadata?.input_repaired !== undefined
      ? JSON.stringify(runtimeMetadata.input_repaired, null, 2)
      : "";
  const statusLabel =
    toolStatus === "failed"
      ? "失败"
      : toolStatus === "cancelled"
        ? "已取消"
        : toolStatus === "completed"
          ? "已完成"
          : "未知";
  const headline =
    missingState === "historical_rerun_required"
      ? "历史任务未保存结构化证据，需要重跑任务才能查看结构化详情。"
      : missingState === "missing_failed"
        ? "该工具执行失败，且当前事件未记录结构化证据。"
        : missingState === "missing_cancelled"
          ? "该工具已取消，且当前事件未记录结构化证据。"
          : "该事件未记录结构化证据。";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-100">
        {headline}
      </div>

      {missingState !== "historical_rerun_required" ? (
        <DetailSection title="失败详情">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-2.5">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">tool_status</div>
              <div className="mt-1 break-words font-mono text-sm">{statusLabel}</div>
            </div>
            {errorCode ? (
              <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">error_code</div>
                <div className="mt-1 break-words font-mono text-sm">{errorCode}</div>
              </div>
            ) : null}
            {validationError ? (
              <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-2.5 md:col-span-2">
                <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">validation_error</div>
                <div className="mt-1 break-words font-mono text-sm">{validationError}</div>
              </div>
            ) : null}
            {inputRepaired ? (
              <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-2.5 md:col-span-2">
                <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">input_repaired</div>
                <pre className="mt-1 break-words whitespace-pre-wrap font-mono text-sm">{inputRepaired}</pre>
              </div>
            ) : null}
          </div>
        </DetailSection>
      ) : null}

      {resultText ? (
        <DetailSection title="输出结果">
          <pre className="max-h-[52vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border/70 bg-background px-3 py-3 text-xs font-mono">
            {resultText}
          </pre>
        </DetailSection>
      ) : null}

      <RawDataSection
        content={JSON.stringify(rawOutput ?? null, null, 2)}
        triggerLabel="查看原始数据"
      />
    </div>
  );
}

function renderPanel(panel: ToolEvidencePrimaryPanel) {
  if (panel.kind === "code-window") {
    return (
      <FindingCodeWindow
        code={panel.code}
        displayLines={panel.displayLines}
        filePath={panel.filePath}
        lineStart={panel.lineStart}
        lineEnd={panel.lineEnd}
        focusLine={panel.focusLine}
        highlightStartLine={panel.highlightStartLine}
        highlightEndLine={panel.highlightEndLine}
        title={panel.title}
        density="detail"
        meta={panel.meta}
      />
    );
  }

  if (panel.kind === "monospace") {
    return (
      <div className="space-y-2">
        <div className="text-[11px] uppercase tracking-[0.22em] text-cyan-200/80">
          {panel.title}
        </div>
        <div className="overflow-hidden rounded-xl border border-slate-800/90 bg-[#07111c] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
          <pre className="max-h-[52vh] overflow-auto whitespace-pre-wrap break-words px-4 py-4 font-mono text-[12px] leading-6 text-slate-100">
            {panel.content}
          </pre>
        </div>
        {panel.note ? (
          <div className="text-xs text-muted-foreground">{panel.note}</div>
        ) : null}
      </div>
    );
  }

  if (panel.kind === "fact-list") {
    return (
      <div className="space-y-3 rounded-xl border border-border/70 bg-background/40 px-4 py-4">
        <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
          {panel.title}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {panel.items.map((item) => (
            <div
              key={`${panel.title}-${item.label}`}
              className="rounded-lg border border-border/60 bg-background/70 px-3 py-2.5"
            >
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                {item.label}
              </div>
              <div className={item.mono ? "mt-1 break-words font-mono text-sm" : "mt-1 break-words text-sm"}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-xl border border-border/70 bg-background/40 px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
        {panel.title}
      </div>
      <div className="space-y-2">
        {panel.items.map((item) => (
          <div
            key={`${panel.title}-${item}`}
            className="rounded-lg border border-border/60 bg-background/70 px-3 py-2 text-sm break-words"
          >
            {item}
          </div>
        ))}
      </div>
      {panel.note ? <div className="text-xs text-muted-foreground">{panel.note}</div> : null}
    </div>
  );
}

export default function ToolEvidenceDetail({
  toolName,
  evidence,
  rawOutput,
  missingState,
  runtimeMetadata,
  toolStatus,
}: {
  toolName?: string | null;
  evidence: ParsedToolEvidence | ToolEvidencePayload | null;
  rawOutput: unknown;
  missingState?: ToolEvidenceMissingState | null;
  runtimeMetadata?: Record<string, unknown> | null;
  toolStatus?: ToolStatus;
}) {
  if (missingState) {
    return (
      <MissingEvidenceDetail
        missingState={missingState}
        rawOutput={rawOutput}
        runtimeMetadata={runtimeMetadata}
        toolStatus={toolStatus}
      />
    );
  }

  const parsed = asParsedToolEvidence(evidence);
  if (!parsed) return null;

  if (!parsed.payload) return null;

  const viewModel = buildToolEvidenceDetailViewModel({
    toolName,
    evidence: parsed,
    rawOutput,
  });

  if (!viewModel) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {viewModel.headerBadges.map((badge) => (
          <Badge
            key={`${badge.label}-${badge.tone || "default"}`}
            variant="outline"
            className={`${badge.mono ? "font-mono" : ""} ${badgeToneClass(badge.tone)}`.trim()}
          >
            {badge.label}
          </Badge>
        ))}
        {viewModel.notices.map((notice) => (
          <span key={notice} className="text-xs text-muted-foreground">
            {notice}
          </span>
        ))}
      </div>

      <DetailSection title="概览">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {viewModel.overview.chips.map((chip) => (
            <div
              key={`${chip.label}-${chip.value}`}
              className="rounded-xl border border-border/70 bg-background/55 px-3 py-3"
            >
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                {chip.label}
              </div>
              <div className={chip.mono ? "mt-1 break-words font-mono text-sm" : "mt-1 break-words text-sm"}>
                {chip.value}
              </div>
            </div>
          ))}
        </div>
      </DetailSection>

      <DetailSection title="">
        <div className="space-y-0">
          {viewModel.primaryEvidence.panels.map((panel, index) => (
            <div key={`${panel.kind}-${index}`}>{renderPanel(panel)}</div>
          ))}
        </div>
      </DetailSection>

      <RawDataSection
        content={viewModel.rawData.content}
        triggerLabel={viewModel.rawData.triggerLabel}
      />
    </div>
  );
}
