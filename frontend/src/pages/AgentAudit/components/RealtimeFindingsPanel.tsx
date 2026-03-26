import {
	AlertTriangle,
	ChevronLeft,
	ChevronRight,
} from "lucide-react";
import {
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
	type MutableRefObject,
	type RefObject,
} from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import {
	AGENT_AUDIT_FINDINGS_PAGE_SIZE,
	calculateResponsiveFindingsPageSize,
	buildFindingTableState,
	shouldSyncFindingPageFromTableState,
	shouldResetFindingPage,
} from "../detailViewModel";
import type {
	FindingsFiltersChangeOptions,
	FindingsViewFilters,
} from "../types";

export type RealtimeVerificationProgress = "pending" | "verified";
export type RealtimeDisplaySeverity =
	| "critical"
	| "high"
	| "medium"
	| "low"
	| "invalid";

export type RealtimeMergedFindingItem = {
	id: string;
	merge_key?: string;
	fingerprint: string;
	title: string;
	display_title?: string | null;
	description?: string | null;
	description_markdown?: string | null;
	severity: string;
	display_severity: RealtimeDisplaySeverity;
	verification_progress: RealtimeVerificationProgress;
	vulnerability_type: string;
	file_path?: string | null;
	line_start?: number | null;
	line_end?: number | null;
	cwe_id?: string | null;
	code_snippet?: string | null;
	code_context?: string | null;
	function_trigger_flow?: string[] | null;
	reachability_file?: string | null;
	reachability_function?: string | null;
	reachability_function_start_line?: number | null;
	reachability_function_end_line?: number | null;
	context_start_line?: number | null;
	context_end_line?: number | null;
	status?: string | null;
	verification_status?: string | null;
	authenticity?: string | null;
	verification_evidence?: string | null;
	verification_todo_id?: string | null;
	verification_fingerprint?: string | null;
	detailMode?: "detail" | "false_positive_reason";
	confidence?: number | null;
	timestamp?: string | null;
	is_verified: boolean;
};

function isFalsePositiveFinding(item: RealtimeMergedFindingItem): boolean {
	return (
		item.detailMode === "false_positive_reason" ||
		String(item.authenticity || "").trim().toLowerCase() === "false_positive" ||
		item.display_severity === "invalid"
	);
}

function getSeverityBadgeClass(severity: string): string {
	if (severity === "critical") {
		return "border-rose-500/30 bg-rose-500/15 text-rose-300";
	}
	if (severity === "high") {
		return "border-amber-500/30 bg-amber-500/15 text-amber-300";
	}
	if (severity === "medium") {
		return "border-sky-500/30 bg-sky-500/15 text-sky-300";
	}
	if (severity === "low") {
		return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
	}
	return "border-border bg-muted text-muted-foreground";
}

function getConfidenceBadgeClass(confidenceLabel: string): string {
	if (confidenceLabel === "误报") {
		return "border-zinc-500/30 bg-zinc-500/15 text-zinc-300";
	}
	if (confidenceLabel === "高") {
		return "border-emerald-500/30 bg-emerald-500/15 text-emerald-300";
	}
	if (confidenceLabel === "中") {
		return "border-amber-500/30 bg-amber-500/15 text-amber-300";
	}
	if (confidenceLabel === "低") {
		return "border-sky-500/30 bg-sky-500/15 text-sky-300";
	}
	return "border-border bg-muted text-muted-foreground";
}

function getEmptyStateMessage(currentPhase?: string | null): string {
	const phase = String(currentPhase || "").trim().toLowerCase();
	if (phase === "verification") {
		return "验证进行中，扫描结束后可查看漏洞详情";
	}
	if (phase === "analysis") {
		return "分析中，候选漏洞进入验证后会继续更新";
	}
	return "侦察中，发现的漏洞会逐步进入列表";
}

export default function RealtimeFindingsPanel(props: {
	taskId: string;
	items: RealtimeMergedFindingItem[];
	isRunning: boolean;
	isLoading?: boolean;
	currentPhase?: string | null;
	filters: FindingsViewFilters;
	onFiltersChange: (
		next: FindingsViewFilters,
		options?: FindingsFiltersChangeOptions,
	) => void;
	onOpenDetail: (item: RealtimeMergedFindingItem) => void;
	scrollContainerRef?: RefObject<HTMLDivElement | null>;
	page?: number;
	pageSize?: number;
	onPaginationChange?: (next: { page: number; pageSize: number }) => void;
}) {
	const [internalPage, setInternalPage] = useState(1);
	const [internalPageSize, setInternalPageSize] = useState(
		AGENT_AUDIT_FINDINGS_PAGE_SIZE,
	);
	const previousFiltersRef = useRef<FindingsViewFilters>(props.filters);
	const viewportRef = useRef<HTMLDivElement | null>(null);
	const page =
		typeof props.page === "number" && Number.isFinite(props.page) && props.page > 0
			? Math.floor(props.page)
			: internalPage;
	const pageSize =
		typeof props.pageSize === "number" &&
		Number.isFinite(props.pageSize) &&
		props.pageSize > 0
			? Math.floor(props.pageSize)
			: internalPageSize;

	const updatePagination = useCallback(
		(next: { page?: number; pageSize?: number }) => {
			const resolved = {
				page:
					typeof next.page === "number" && Number.isFinite(next.page) && next.page > 0
						? Math.floor(next.page)
						: page,
				pageSize:
					typeof next.pageSize === "number" &&
					Number.isFinite(next.pageSize) &&
					next.pageSize > 0
						? Math.floor(next.pageSize)
						: pageSize,
			};
			props.onPaginationChange?.(resolved);
			if (typeof props.page !== "number") {
				setInternalPage(resolved.page);
			}
			if (typeof props.pageSize !== "number") {
				setInternalPageSize(resolved.pageSize);
			}
		},
		[page, pageSize, props.onPaginationChange, props.page, props.pageSize],
	);

	const syncViewportRef = useCallback(
		(node: HTMLDivElement | null) => {
			viewportRef.current = node;
			if (props.scrollContainerRef) {
				(props.scrollContainerRef as MutableRefObject<HTMLDivElement | null>).current =
					node;
			}
		},
		[props.scrollContainerRef],
	);

	useEffect(() => {
		if (shouldResetFindingPage(previousFiltersRef.current, props.filters)) {
			updatePagination({ page: 1 });
		}
		previousFiltersRef.current = props.filters;
	}, [props.filters, updatePagination]);

	const tableState = useMemo(
		() =>
			buildFindingTableState({
				items: props.items,
				filters: props.filters,
				page,
				pageSize,
			}),
		[page, pageSize, props.filters, props.items],
	);
	const hasNoRows = tableState.rows.length === 0;
	const emptyStateMessage = props.isRunning
		? getEmptyStateMessage(props.currentPhase)
		: props.items.length === 0
			? "暂无已验证漏洞"
			: "暂无符合条件的漏洞";

	useEffect(() => {
		if (
			shouldSyncFindingPageFromTableState({
				requestedPage: page,
				resolvedPage: tableState.page,
				totalRows: tableState.totalRows,
				isLoading: props.isLoading === true,
			})
		) {
			updatePagination({ page: tableState.page });
		}
	}, [page, props.isLoading, tableState.page, tableState.totalRows, updatePagination]);

	useEffect(() => {
		if (typeof ResizeObserver === "undefined" || !viewportRef.current) {
			return;
		}

		const node = viewportRef.current;
		const updatePageSize = (height: number) => {
			const next = calculateResponsiveFindingsPageSize(height);
			if (pageSize !== next) {
				updatePagination({ pageSize: next });
			}
		};

		updatePageSize(node.clientHeight);
		const observer = new ResizeObserver((entries) => {
			const entry = entries[0];
			if (!entry) return;
			updatePageSize(entry.contentRect.height);
		});
		observer.observe(node);
		return () => observer.disconnect();
	}, [pageSize, updatePagination]);

	function getActionLabel(item: RealtimeMergedFindingItem): string {
		if (!props.isRunning && isFalsePositiveFinding(item)) {
			return "查看判定依据";
		}
		return "详情";
	}

	return (
		<div
			className="rounded-xl bg-card/50"
			style={{ height: "100%" }}
		>
			<div className="flex h-full min-h-0 flex-col overflow-hidden">
				<div className="flex flex-wrap items-center gap-3 border-b border-border/70 px-4 py-3">
					<div className="relative min-w-0 flex-1 basis-[320px]">
						<Input
							value={props.filters.keyword}
							onChange={(event) =>
								props.onFiltersChange({
									...props.filters,
									keyword: event.target.value,
								}, { source: "user" })
							}
							placeholder="搜索漏洞类型 / 危害"
							className="cyber-input h-10 pl-11 pr-3 text-sm"
						/>
					</div>
					<Select
						value={props.filters.severity}
						onValueChange={(value) =>
							props.onFiltersChange({
								...props.filters,
								severity: value,
							}, { source: "user" })
						}
					>
						<SelectTrigger className="cyber-input h-10 w-full sm:w-[180px]">
							<SelectValue placeholder="严重度" />
						</SelectTrigger>
						<SelectContent className="cyber-dialog border-border">
							<SelectItem value="all">全部严重度</SelectItem>
							<SelectItem value="critical">严重</SelectItem>
							<SelectItem value="high">高危</SelectItem>
							<SelectItem value="medium">中危</SelectItem>
							<SelectItem value="low">低危</SelectItem>
							<SelectItem value="invalid">无效</SelectItem>
						</SelectContent>
					</Select>
				</div>

				<div className="min-h-0 flex-1 px-4 py-3">
					<div ref={syncViewportRef} className="h-full">
						{hasNoRows ? (
							<div className="flex h-full items-center justify-center text-muted-foreground">
								<div className="flex flex-col items-center gap-3 px-6 text-center">
									<AlertTriangle className="h-5 w-5 opacity-60" />
									<span className="text-sm">{emptyStateMessage}</span>
								</div>
							</div>
						) : (
							<table className="w-full caption-bottom text-base font-mono">
								<TableHeader className="bg-transparent">
									<TableRow className="border-b border-border/60 hover:bg-transparent">
										<TableHead className="w-[72px]">序号</TableHead>
										<TableHead className="w-auto">漏洞类型</TableHead>
										<TableHead className="w-[120px]" data-no-i18n="true">
											漏洞危害
										</TableHead>
										{tableState.hasVisibleConfidence ? (
											<TableHead className="w-[110px]">置信度</TableHead>
										) : null}
										<TableHead className="w-[160px] text-center">操作</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{tableState.rows.map((row, index) => {
										const findingItem = row.raw as RealtimeMergedFindingItem;

										return (
											<TableRow
												key={row.id}
												id={`finding-item-${row.id}`}
												className="border-b border-border/40 last:border-b-0"
											>
												<TableCell className="py-3 font-mono text-xs text-muted-foreground">
													{(tableState.pageStart + index + 1).toLocaleString()}
												</TableCell>
												<TableCell className="py-3 align-top">
													<div
														className="truncate text-sm font-medium text-foreground"
														title={row.typeTooltip || row.typeLabel}
													>
														{row.typeLabel}
													</div>
												</TableCell>
												<TableCell className="py-3">
													<Badge
														variant="outline"
														className={`text-[11px] ${getSeverityBadgeClass(row.severity)}`}
													>
														{row.severityLabel}
													</Badge>
												</TableCell>
												{tableState.hasVisibleConfidence ? (
													<TableCell className="py-3">
														{row.confidenceLabel ? (
															<Badge
																variant="outline"
																className={`text-[11px] ${getConfidenceBadgeClass(row.confidenceLabel)}`}
															>
																{row.confidenceLabel}
															</Badge>
														) : null}
													</TableCell>
												) : null}
												<TableCell className="py-3 text-center">
													<Button
														type="button"
														size="sm"
														variant="outline"
														className="cyber-btn-ghost h-8 px-3"
														disabled={props.isRunning}
														onClick={() => props.onOpenDetail(findingItem)}
													>
														{getActionLabel(findingItem)}
													</Button>
												</TableCell>
											</TableRow>
										);
									})}
								</TableBody>
							</table>
						)}
					</div>
				</div>

				<div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
					<div className="text-xs text-muted-foreground">
						共 {tableState.totalRows.toLocaleString()} 条，当前显示 {" "}
						{tableState.rows.length.toLocaleString()} 条
					</div>
					<div className="flex items-center gap-2">
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="cyber-btn-outline h-8"
							disabled={tableState.page <= 1}
							onClick={() =>
								updatePagination({ page: Math.max(tableState.page - 1, 1) })
							}
						>
							<ChevronLeft className="h-3.5 w-3.5" />
							上一页
						</Button>
						<span className="text-xs text-muted-foreground">
							第 {tableState.page} / {tableState.totalPages} 页
						</span>
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="cyber-btn-outline h-8"
							disabled={tableState.page >= tableState.totalPages}
							onClick={() =>
								updatePagination({
									page: Math.min(tableState.page + 1, tableState.totalPages),
								})
							}
						>
							下一页
							<ChevronRight className="h-3.5 w-3.5" />
						</Button>
					</div>
				</div>
			</div>
		</div>
	);
}
