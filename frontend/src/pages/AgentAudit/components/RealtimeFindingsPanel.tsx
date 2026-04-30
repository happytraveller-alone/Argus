import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
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
import { DataTable } from "@/components/data-table/DataTable";
import type { AppColumnDef } from "@/components/data-table/types";
import {
	AGENT_AUDIT_FINDINGS_PAGE_SIZE,
	calculateResponsiveFindingsPageSize,
	buildFindingTableState,
	getAgentAuditFindingDisplayStatus,
	getAgentAuditFindingStatusBadgeClass,
	getAgentAuditFindingStatusLabel,
	type AgentAuditFindingDisplayStatus,
	type FindingTableRow,
	resolveAgentAuditPaginationTransition,
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
	verdict?: string | null;
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

const ACTIVE_TRUE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-emerald-500/70 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/20";
const IDLE_TRUE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10";
const ACTIVE_FALSE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-rose-500/70 bg-rose-500/15 text-rose-200 hover:bg-rose-500/20";
const IDLE_FALSE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-rose-500/40 text-rose-400 hover:bg-rose-500/10";

function isFalsePositiveFinding(item: RealtimeMergedFindingItem): boolean {
	return (
		item.detailMode === "false_positive_reason" ||
		String(item.authenticity || "")
			.trim()
			.toLowerCase() === "false_positive" ||
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
	const phase = String(currentPhase || "")
		.trim()
		.toLowerCase();
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
	onPaginationChange?: (
		next: { page: number; pageSize: number },
		source?: "user" | "layout",
	) => void;
	updatingKey?: string | null;
	onToggleStatus?: (
		item: RealtimeMergedFindingItem,
		target: Exclude<AgentAuditFindingDisplayStatus, "open">,
	) => void;
	getDisplayStatus?: (
		item: RealtimeMergedFindingItem,
	) => AgentAuditFindingDisplayStatus;
}) {
	const [internalPage, setInternalPage] = useState(1);
	const [internalPageSize, setInternalPageSize] = useState(() =>
		typeof props.pageSize === "number" &&
		Number.isFinite(props.pageSize) &&
		props.pageSize > 0
			? Math.floor(props.pageSize)
			: AGENT_AUDIT_FINDINGS_PAGE_SIZE,
	);
	const previousFiltersRef = useRef<FindingsViewFilters>(props.filters);
	const previousPropPageSizeRef = useRef<number | null>(null);
	const viewportRef = useRef<HTMLDivElement | null>(null);
	const page =
		typeof props.page === "number" &&
		Number.isFinite(props.page) &&
		props.page > 0
			? Math.floor(props.page)
			: internalPage;
	const pageSize = internalPageSize;

	useEffect(() => {
		if (
			typeof props.pageSize !== "number" ||
			!Number.isFinite(props.pageSize) ||
			props.pageSize <= 0
		) {
			return;
		}
		const normalized = Math.floor(props.pageSize);
		if (previousPropPageSizeRef.current === normalized) {
			return;
		}
		previousPropPageSizeRef.current = normalized;
		setInternalPageSize(normalized);
	}, [props.pageSize]);

	const updatePagination = useCallback(
		(
			next: { page?: number; pageSize?: number },
			source: "user" | "layout" = "user",
		) => {
			const resolved = resolveAgentAuditPaginationTransition({
				current: {
					page,
					pageSize,
				},
				update: next,
				source,
			});
			if (resolved.routeSync) {
				props.onPaginationChange?.(resolved.routeSync, source);
			}
			if (typeof props.page !== "number") {
				setInternalPage(resolved.state.page);
			}
			setInternalPageSize(resolved.state.pageSize);
		},
		[page, pageSize, props.onPaginationChange, props.page, props.pageSize],
	);

	const syncViewportRef = useCallback(
		(node: HTMLDivElement | null) => {
			viewportRef.current = node;
			if (props.scrollContainerRef) {
				(
					props.scrollContainerRef as MutableRefObject<HTMLDivElement | null>
				).current = node;
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
	const emptyStateMessage = props.isRunning
		? getEmptyStateMessage(props.currentPhase)
		: props.items.length === 0
			? "暂无漏洞"
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
	}, [
		page,
		props.isLoading,
		tableState.page,
		tableState.totalRows,
		updatePagination,
	]);

	useEffect(() => {
		if (typeof ResizeObserver === "undefined" || !viewportRef.current) {
			return;
		}

		const node = viewportRef.current;
		const updatePageSize = (height: number) => {
			const next = calculateResponsiveFindingsPageSize(height);
			if (pageSize !== next) {
				updatePagination({ pageSize: next }, "layout");
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

	const findingColumns = useMemo<AppColumnDef<FindingTableRow>[]>(
		() => {
			const columns: AppColumnDef<FindingTableRow>[] = [
				{
					id: "order",
					header: "序号",
					cell: ({ row }) => (
						<span className="font-mono text-xs text-muted-foreground">
							{(tableState.pageStart + row.index + 1).toLocaleString()}
						</span>
					),
					meta: {
						label: "序号",
						width: 72,
						minWidth: 72,
						plainHeader: false,
					},
				},
				{
					id: "typeLabel",
					accessorKey: "typeLabel",
					header: "漏洞类型",
					cell: ({ row }) => (
						<div
							className="truncate text-sm font-medium text-foreground"
							title={row.original.typeTooltip || row.original.typeLabel}
						>
							{row.original.typeLabel}
						</div>
					),
					meta: {
						label: "漏洞类型",
						minWidth: 220,
					},
				},
				{
					id: "severity",
					accessorKey: "severity",
					header: "漏洞危害",
					cell: ({ row }) => (
						<Badge
							variant="outline"
							className={`text-[11px] ${getSeverityBadgeClass(row.original.severity)}`}
						>
							{row.original.severityLabel}
						</Badge>
					),
					meta: {
						label: "漏洞危害",
						width: 120,
						minWidth: 120,
						dataNoI18n: true,
					},
				},
			];

			if (tableState.hasVisibleConfidence) {
				columns.push({
					id: "confidence",
					accessorKey: "confidenceScore",
					header: "置信度",
					cell: ({ row }) =>
						row.original.confidenceLabel ? (
							<Badge
								variant="outline"
								className={`text-[11px] ${getConfidenceBadgeClass(row.original.confidenceLabel)}`}
							>
								{row.original.confidenceLabel}
							</Badge>
						) : null,
					meta: {
						label: "置信度",
						width: 110,
						minWidth: 110,
					},
				});
			}

			columns.push(
				{
					id: "status",
					accessorKey: "statusValue",
					header: "漏洞状态",
					cell: ({ row }) => {
						const findingItem = row.original.raw as RealtimeMergedFindingItem;
						const statusValue =
							props.getDisplayStatus?.(findingItem) ??
							row.original.statusValue ??
							getAgentAuditFindingDisplayStatus(findingItem);
						return (
							<Badge
								variant="outline"
								className={`text-[11px] ${getAgentAuditFindingStatusBadgeClass(
									statusValue,
								)}`}
							>
								{getAgentAuditFindingStatusLabel(statusValue)}
							</Badge>
						);
					},
					meta: {
						label: "漏洞状态",
						align: "center",
						width: 120,
						minWidth: 120,
					},
				},
				{
					id: "actions",
					header: "操作",
					cell: ({ row }) => {
						const findingItem = row.original.raw as RealtimeMergedFindingItem;
						const statusValue =
							props.getDisplayStatus?.(findingItem) ??
							row.original.statusValue ??
							getAgentAuditFindingDisplayStatus(findingItem);
						const rowUpdatePrefix = `${findingItem.id}:`;
						const rowStatusUpdating = Boolean(
							props.updatingKey?.startsWith(rowUpdatePrefix),
						);
						const verifyUpdating =
							props.updatingKey === `${findingItem.id}:verified`;
						const falsePositiveUpdating =
							props.updatingKey === `${findingItem.id}:false_positive`;

						return (
							<div className="flex flex-wrap items-center justify-center gap-1.5">
								<Button
									type="button"
									size="sm"
									variant="outline"
									className="cyber-btn-ghost h-8 px-3"
									onClick={() => props.onOpenDetail(findingItem)}
								>
									{getActionLabel(findingItem)}
								</Button>
								<Button
									type="button"
									size="sm"
									variant="outline"
									className={
										statusValue === "verified"
											? ACTIVE_TRUE_BUTTON_CLASS
											: IDLE_TRUE_BUTTON_CLASS
									}
									disabled={rowStatusUpdating}
									aria-pressed={statusValue === "verified"}
									onClick={() => props.onToggleStatus?.(findingItem, "verified")}
								>
									{verifyUpdating ? (
										<Loader2 className="h-3 w-3 animate-spin" />
									) : (
										"判真"
									)}
								</Button>
								<Button
									type="button"
									size="sm"
									variant="outline"
									className={
										statusValue === "false_positive"
											? ACTIVE_FALSE_BUTTON_CLASS
											: IDLE_FALSE_BUTTON_CLASS
									}
									disabled={rowStatusUpdating}
									aria-pressed={statusValue === "false_positive"}
									onClick={() =>
										props.onToggleStatus?.(findingItem, "false_positive")
									}
								>
									{falsePositiveUpdating ? (
										<Loader2 className="h-3 w-3 animate-spin" />
									) : (
										"判假"
									)}
								</Button>
							</div>
						);
					},
					meta: {
						label: "操作",
						align: "center",
						width: 280,
						minWidth: 280,
						hideable: false,
					},
				},
			);

			return columns;
		},
		[
			props.getDisplayStatus,
			props.onOpenDetail,
			props.onToggleStatus,
			props.updatingKey,
			tableState.hasVisibleConfidence,
			tableState.pageStart,
		],
	);

	return (
		<div className="rounded-xl bg-card/50" style={{ height: "100%" }}>
			<div className="flex h-full min-h-0 flex-col overflow-hidden">
				<div className="flex flex-wrap items-center gap-3 border-b border-border/70 px-4 py-3">
					<div className="relative min-w-0 flex-1 basis-[320px]">
						<Input
							value={props.filters.keyword}
							onChange={(event) =>
								props.onFiltersChange(
									{
										...props.filters,
										keyword: event.target.value,
									},
									{ source: "user" },
								)
							}
							placeholder="搜索漏洞类型 / 危害"
							className="cyber-input h-10 pl-11 pr-3 text-sm"
						/>
					</div>
					<Select
						value={props.filters.severity}
						onValueChange={(value) =>
							props.onFiltersChange(
								{
									...props.filters,
									severity: value,
								},
								{ source: "user" },
							)
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
						<DataTable
							data={tableState.rows}
							columns={findingColumns}
							getRowId={(row) => row.id}
							toolbar={false}
							pagination={false}
							emptyState={{ title: emptyStateMessage }}
							className="h-full border-border bg-background/20"
							containerClassName="h-full overflow-x-auto overflow-y-hidden"
							tableContainerClassName="h-full overflow-x-auto overflow-y-hidden rounded-sm border border-border"
							tableClassName="min-w-[980px] caption-bottom text-base font-mono"
						/>
					</div>
				</div>

				<div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
					<div className="text-xs text-muted-foreground">
						共 {tableState.totalRows.toLocaleString()} 条，当前显示{" "}
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
