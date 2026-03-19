// import { FileSearch, LoaderCircle, SearchCode } from "lucide-react";
import {useEffect, useRef, useState } from "react";
// import { Button } from "@/components/ui/button";
import type { FindingCodeWindowDisplayLine } from "@/pages/AgentAudit/components/FindingCodeWindow";
import { cn } from "@/shared/utils/utils";
// import { classifyFullFileLoadError } from "./fullFileLoad";
import type {
	FindingDetailCodeView,
	FindingDetailFullFileRequest,
} from "./viewModel";

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
				"grid w-full grid-cols-[48px_minmax(0,1fr)]",
				isPlaceholder ? "bg-slate-900/45" : "bg-[#0f1720]",
				isHighlighted && "bg-red-950/55",
				isFocus && "bg-red-950/85",
			)}
		>
			<div
				className={cn(
					"select-none px-2 py-0.5 text-right font-mono text-[13px] leading-[1.4] text-slate-500 sm:text-[14px]",
					isPlaceholder && "text-slate-700",
					isHighlighted && "text-red-300",
					isFocus && "text-red-100",
				)}
			>
				{line.lineNumber ?? ""}
			</div>
			<pre
				className={cn(
					"whitespace-pre px-2.5 py-0.5 font-mono text-[14px] leading-[1.7] text-slate-100 sm:text-[15px]",
					isPlaceholder && "italic text-slate-500",
					isHighlighted &&
						"border-l-2 border-red-500 bg-red-950/35 text-red-50",
					isFocus &&
						"border-l-2 border-red-400 bg-red-950/60 font-semibold text-white",
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
	// onLoadFullFile,
}: FindingDetailCodePanelProps) {
	const [panelState] = useState<FindingDetailPanelState>({
		expandedSectionId: null,
		fullFileStates: {},
	});
	const scrollRefs = useRef<Record<string, HTMLDivElement | null>>({});
	const expandedSectionId = panelState.expandedSectionId;
	const fullFileStates = panelState.fullFileStates;
	const expandedSectionStateStatus = expandedSectionId
		? (fullFileStates[expandedSectionId]?.status ?? "idle")
		: "idle";

	useEffect(() => {
		if (!expandedSectionId) return;
		if (expandedSectionStateStatus === "loading") return;
		const container = scrollRefs.current[expandedSectionId];
		const section = sections.find((item) => item.id === expandedSectionId);
		if (!container || !section || !section.focusLine) return;
		const target = container.querySelector<HTMLElement>(
			`[data-line-number="${section.focusLine}"]`,
		);
		target?.scrollIntoView({ block: "center", behavior: "smooth" });
	}, [expandedSectionId, expandedSectionStateStatus, sections]);

	// const handleOpenFullFile = async (section: FindingDetailCodeView) => {
	// 	if (
	// 		!section.fullFileAvailable ||
	// 		!section.fullFileRequest ||
	// 		!onLoadFullFile
	// 	) {
	// 		setPanelState((current) =>
	// 			reduceFindingDetailPanelState(current, {
	// 				type: "resolve",
	// 				sectionId: section.id,
	// 				nextState: { status: "unavailable", message: UNAVAILABLE_MESSAGE },
	// 			}),
	// 		);
	// 		return;
	// 	}

	// 	setPanelState((current) =>
	// 		reduceFindingDetailPanelState(current, {
	// 			type: "expand",
	// 			sectionId: section.id,
	// 		}),
	// 	);
	// 	const existingState = fullFileStates[section.id];
	// 	if (existingState?.status === "ready") {
	// 		return;
	// 	}

	// 	setPanelState((current) =>
	// 		reduceFindingDetailPanelState(current, {
	// 			type: "resolve",
	// 			sectionId: section.id,
	// 			nextState: { status: "loading" },
	// 		}),
	// 	);

	// 	try {
	// 		const result = await onLoadFullFile(section.fullFileRequest);
	// 		if (!result.isText) {
	// 			startTransition(() => {
	// 				setPanelState((current) =>
	// 					reduceFindingDetailPanelState(current, {
	// 						type: "resolve",
	// 						sectionId: section.id,
	// 						nextState: {
	// 							status: "unavailable",
	// 							message: "当前文件不是文本内容，无法展示完整文件",
	// 						},
	// 					}),
	// 				);
	// 			});
	// 			return;
	// 		}

	// 		const lines = buildFullFileDisplayLines({
	// 			content: result.content,
	// 			focusLine: section.focusLine,
	// 			highlightStartLine: section.highlightStartLine,
	// 			highlightEndLine: section.highlightEndLine,
	// 			lineStart: 1,
	// 		});

	// 		startTransition(() => {
	// 			setPanelState((current) =>
	// 				reduceFindingDetailPanelState(current, {
	// 					type: "resolve",
	// 					sectionId: section.id,
	// 					nextState: { status: "ready", lines },
	// 				}),
	// 			);
	// 		});
	// 	} catch (error) {
	// 		const failure = classifyFullFileLoadError(error);
	// 		startTransition(() => {
	// 			setPanelState((current) =>
	// 				reduceFindingDetailPanelState(current, {
	// 					type: "resolve",
	// 					sectionId: section.id,
	// 					nextState:
	// 						failure.kind === "unavailable"
	// 							? { status: "unavailable", message: failure.message }
	// 							: { status: "failed", message: failure.message },
	// 				}),
	// 			);
	// 		});
	// 	}
	// };

	return (
		<section
			aria-label={title}
			className="order-2 xl:order-2 cyber-card p-5 min-h-0 flex flex-col gap-4"
		>
			<div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar-dark space-y-4 pr-1">
				{sections.length === 0 ? (
					<div className="rounded-2xl border border-dashed border-slate-700/80 bg-slate-950/60 p-5 text-[1.1375rem] leading-[1.7] text-slate-400">
						{emptyMessage}
					</div>
				) : null}

				{sections.map((section) => {
					const fullFileState =
						fullFileStates[section.id] ?? getDefaultState(section);
					const isExpanded = expandedSectionId === section.id;
					const helperMessage =
						fullFileState.status === "unavailable" ||
						fullFileState.status === "failed"
							? fullFileState.message
							: null;
					const codeLines =
						isExpanded && fullFileState.status === "ready"
							? fullFileState.lines
							: (section.relatedLines ?? []);

					return (
						<article
							key={section.id}
							className="rounded-xl border border-border/70 bg-card/35 p-5 space-y-4"
						>
							<p className="break-all font-mono text-[1.05625rem] leading-[1.6] text-foreground">
								{section.displayFilePath || section.filePath || "未定位文件"}
							</p>

							<div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
								<div className="flex flex-wrap items-center gap-2 text-[0.975rem] text-muted-foreground">
									<span className="inline-flex items-center rounded-full border border-border/70 bg-background/55 px-3 py-1.5 font-mono text-[0.89375rem] text-muted-foreground">
										{section.locationLabel || "行号未提供"}
									</span>
									<span className="inline-flex items-center rounded-full border border-red-500/30 bg-red-950/45 px-3 py-1.5 font-mono text-[0.89375rem] text-red-200">
										核心漏洞代码
									</span>
								</div>

								{/* <Button
									type="button"
									variant="outline"
									size="sm"
									className="shrink-0 self-start border-border/70 bg-background/60 text-foreground hover:bg-card/80"
									disabled={!isExpanded && !section.fullFileAvailable}
									title={
										!isExpanded && !section.fullFileAvailable
											? UNAVAILABLE_MESSAGE
											: undefined
									}
									onClick={() => {
										if (isExpanded) {
											setPanelState((current) =>
												reduceFindingDetailPanelState(current, {
													type: "collapse",
												}),
											);
											return;
										}
										void handleOpenFullFile(section);
									}}
								>
									{fullFileState.status === "loading" ? (
										<LoaderCircle className="h-4 w-4 animate-spin" />
									) : isExpanded ? (
										<SearchCode className="h-4 w-4" />
									) : (
										<FileSearch className="h-4 w-4" />
									)}
									{isExpanded ? "仅看漏洞代码" : "查看文件"}
								</Button> */}
							</div>

							{helperMessage ? (
								<p className="text-[0.975rem] leading-[1.6] text-muted-foreground">
									{helperMessage}
								</p>
							) : null}

							<div
								ref={(node) => {
									scrollRefs.current[section.id] = node;
								}}
								className="max-h-[52vh] overflow-auto custom-scrollbar-dark rounded-lg border border-border/60 bg-[#0b1120]"
							>
								<div className="min-w-max min-h-full pb-3 pr-3">
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
