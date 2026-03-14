import { startTransition, useEffect, useRef, useState } from "react";
import { AlertCircle, FileSearch, LoaderCircle, SearchCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";
import type { FindingCodeWindowDisplayLine } from "@/pages/AgentAudit/components/FindingCodeWindow";
import type {
  FindingDetailCodeView,
  FindingDetailFullFileRequest,
} from "./viewModel";
import { buildFullFileDisplayLines } from "./viewModel";

export type FindingDetailFullFileLoadResult = {
  content: string;
  isText: boolean;
};

type FullFileViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; lines: FindingCodeWindowDisplayLine[] }
  | { status: "unavailable"; message: string }
  | { status: "failed"; message: string };

export type FindingDetailPanelState = {
  expandedSectionId: string | null;
  fullFileStates: Record<string, FullFileViewState>;
};

type FindingDetailPanelAction =
  | { type: "expand"; sectionId: string }
  | { type: "collapse" }
  | { type: "resolve"; sectionId: string; nextState: FullFileViewState };

export function reduceFindingDetailPanelState(
  state: FindingDetailPanelState,
  action: FindingDetailPanelAction,
): FindingDetailPanelState {
  if (action.type === "expand") {
    return {
      ...state,
      expandedSectionId: action.sectionId,
    };
  }

  if (action.type === "collapse") {
    return {
      ...state,
      expandedSectionId: null,
    };
  }

  return {
    ...state,
    fullFileStates: {
      ...state.fullFileStates,
      [action.sectionId]: action.nextState,
    },
  };
}

interface FindingDetailCodePanelProps {
  title: string;
  sections: FindingDetailCodeView[];
  emptyMessage: string;
  onLoadFullFile?: (
    request: FindingDetailFullFileRequest,
  ) => Promise<FindingDetailFullFileLoadResult>;
}

const UNAVAILABLE_MESSAGE = "当前项目暂不支持查看完整文件，仅展示漏洞相关代码";
const FAILED_MESSAGE = "完整文件加载失败，请稍后重试";

function getDefaultState(section: FindingDetailCodeView): FullFileViewState {
  if (section.fullFileAvailable === false) {
    return { status: "unavailable", message: UNAVAILABLE_MESSAGE };
  }
  return { status: "idle" };
}

function renderCodeLine(line: FindingCodeWindowDisplayLine, index: number) {
  const isPlaceholder = line.kind === "placeholder" || line.lineNumber === null;
  const isHighlighted = Boolean(line.isHighlighted);
  const isFocus = Boolean(line.isFocus);

  return (
    <div
      key={`${line.lineNumber ?? `placeholder-${index}`}-${index}`}
      data-line-number={line.lineNumber ?? undefined}
      className={cn(
        "grid grid-cols-[42px_minmax(0,1fr)] sm:grid-cols-[48px_minmax(0,1fr)]",
        isPlaceholder ? "bg-slate-900/45" : "bg-[#0f1720]",
        isHighlighted && "bg-red-950/55",
        isFocus && "bg-red-950/85",
      )}
    >
      <div
        className={cn(
          "select-none px-1.5 py-0.5 text-right font-mono text-[10px] text-slate-500 sm:px-2 sm:text-[11px]",
          isPlaceholder && "text-slate-700",
          isHighlighted && "text-red-300",
          isFocus && "text-red-100",
        )}
      >
        {line.lineNumber ?? ""}
      </div>
      <pre
        className={cn(
          "overflow-x-auto whitespace-pre px-2 py-0.5 font-mono text-[11px] leading-5 text-slate-100 sm:px-2.5 sm:text-[11.5px]",
          isPlaceholder && "italic text-slate-500",
          isHighlighted && "border-l-2 border-red-500 bg-red-950/35 text-red-50",
          isFocus && "border-l-2 border-red-400 bg-red-950/60 font-semibold text-white",
        )}
      >
        {line.content || " "}
      </pre>
    </div>
  );
}

export default function FindingDetailCodePanel({
  title,
  sections,
  emptyMessage,
  onLoadFullFile,
}: FindingDetailCodePanelProps) {
  const [panelState, setPanelState] = useState<FindingDetailPanelState>({
    expandedSectionId: null,
    fullFileStates: {},
  });
  const scrollRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const expandedSectionId = panelState.expandedSectionId;
  const fullFileStates = panelState.fullFileStates;

  useEffect(() => {
    if (!expandedSectionId) return;
    const container = scrollRefs.current[expandedSectionId];
    const section = sections.find((item) => item.id === expandedSectionId);
    if (!container || !section || !section.focusLine) return;
    const target = container.querySelector<HTMLElement>(
      `[data-line-number="${section.focusLine}"]`,
    );
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [expandedSectionId, fullFileStates, sections]);

  const handleOpenFullFile = async (section: FindingDetailCodeView) => {
    if (!section.fullFileAvailable || !section.fullFileRequest || !onLoadFullFile) {
      setPanelState((current) =>
        reduceFindingDetailPanelState(current, {
          type: "resolve",
          sectionId: section.id,
          nextState: { status: "unavailable", message: UNAVAILABLE_MESSAGE },
        }),
      );
      return;
    }

    setPanelState((current) =>
      reduceFindingDetailPanelState(current, { type: "expand", sectionId: section.id }),
    );
    const existingState = fullFileStates[section.id];
    if (existingState?.status === "ready") {
      return;
    }

    setPanelState((current) =>
      reduceFindingDetailPanelState(current, {
        type: "resolve",
        sectionId: section.id,
        nextState: { status: "loading" },
      }),
    );

    try {
      const result = await onLoadFullFile(section.fullFileRequest);
      if (!result.isText) {
        startTransition(() => {
          setPanelState((current) =>
            reduceFindingDetailPanelState(current, {
              type: "resolve",
              sectionId: section.id,
              nextState: {
                status: "unavailable",
                message: "当前文件不是文本内容，无法展示完整文件",
              },
            }),
          );
        });
        return;
      }

      const lines = buildFullFileDisplayLines({
        content: result.content,
        focusLine: section.focusLine,
        highlightStartLine: section.highlightStartLine,
        highlightEndLine: section.highlightEndLine,
        lineStart: 1,
      });

      startTransition(() => {
        setPanelState((current) =>
          reduceFindingDetailPanelState(current, {
            type: "resolve",
            sectionId: section.id,
            nextState: { status: "ready", lines },
          }),
        );
      });
    } catch {
      startTransition(() => {
        setPanelState((current) =>
          reduceFindingDetailPanelState(current, {
            type: "resolve",
            sectionId: section.id,
            nextState: { status: "failed", message: FAILED_MESSAGE },
          }),
        );
      });
    }
  };

  return (
    <section className="order-2 xl:order-1 cyber-card p-5 min-h-0 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold uppercase tracking-[0.18em] text-foreground">
          {title}
        </h2>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-1">
        {sections.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-700/80 bg-slate-950/60 p-5 text-sm leading-7 text-slate-400">
            {emptyMessage}
          </div>
        ) : null}

        {sections.map((section) => {
          const fullFileState = fullFileStates[section.id] ?? getDefaultState(section);
          const isExpanded = expandedSectionId === section.id;
          const codeLines =
            isExpanded && fullFileState.status === "ready"
              ? fullFileState.lines
              : section.relatedLines ?? [];

          return (
            <article
              key={section.id}
              className="overflow-hidden rounded-2xl border border-slate-800/90 bg-[linear-gradient(180deg,rgba(11,18,32,0.98),rgba(15,23,42,0.94))] shadow-[0_14px_32px_rgba(2,6,23,0.38)]"
            >
              <div className="border-b border-slate-800/90 px-4 py-4 sm:px-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 space-y-2">
                    <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-slate-500">
                      文件路径
                    </p>
                    <p className="break-all font-mono text-[13px] leading-6 text-slate-100">
                      {section.displayFilePath || section.filePath || "未定位文件"}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <span className="inline-flex items-center rounded-full border border-slate-700 bg-slate-900/90 px-2.5 py-1 font-mono text-slate-300">
                        {section.locationLabel || "行号未提供"}
                      </span>
                      <span className="inline-flex items-center rounded-full border border-red-500/30 bg-red-950/60 px-2.5 py-1 font-mono text-red-200">
                        核心漏洞代码
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col items-start gap-2 sm:items-end">
                    {isExpanded ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="border-slate-700 bg-slate-900/80 text-slate-100 hover:bg-slate-800"
                        onClick={() =>
                          setPanelState((current) =>
                            reduceFindingDetailPanelState(current, { type: "collapse" }),
                          )
                        }
                      >
                        <SearchCode className="h-4 w-4" />
                        仅看漏洞相关代码
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="border-slate-700 bg-slate-900/80 text-slate-100 hover:bg-slate-800"
                        disabled={!section.fullFileAvailable}
                        title={!section.fullFileAvailable ? UNAVAILABLE_MESSAGE : undefined}
                        onClick={() => {
                          void handleOpenFullFile(section);
                        }}
                      >
                        {fullFileState.status === "loading" ? (
                          <LoaderCircle className="h-4 w-4 animate-spin" />
                        ) : (
                          <FileSearch className="h-4 w-4" />
                        )}
                        查看文件全部内容
                      </Button>
                    )}

                    {fullFileState.status === "unavailable" || fullFileState.status === "failed" ? (
                      <p className="max-w-[320px] text-xs leading-5 text-slate-500">
                        {fullFileState.message}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>

              {isExpanded && fullFileState.status === "loading" ? (
                <div className="flex items-center gap-2 border-b border-slate-800/80 bg-slate-950/80 px-4 py-3 text-sm text-slate-400 sm:px-5">
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                  正在加载完整文件内容...
                </div>
              ) : null}

              {isExpanded && fullFileState.status === "ready" ? (
                <div className="flex items-center gap-2 border-b border-slate-800/80 bg-slate-950/80 px-4 py-3 text-sm text-slate-400 sm:px-5">
                  <FileSearch className="h-4 w-4" />
                  已切换到完整文件视图，并定位到漏洞代码附近
                </div>
              ) : null}

              {fullFileState.status === "failed" ? (
                <div className="flex items-center gap-2 border-b border-red-500/20 bg-red-950/70 px-4 py-3 text-sm text-red-200 sm:px-5">
                  <AlertCircle className="h-4 w-4" />
                  {fullFileState.message}
                </div>
              ) : null}

              <div
                ref={(node) => {
                  scrollRefs.current[section.id] = node;
                }}
                className="max-h-[52vh] overflow-auto bg-[#0b1120]"
              >
                <div className="min-w-full">
                  {codeLines.map((line, index) => renderCodeLine(line, index))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
