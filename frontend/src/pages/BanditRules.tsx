/**
 * Bandit Rules Management Page
 *
 * 用途：在不改变现有页面布局的前提下，展示 Bandit 内置规则并提供启停/删除管理。
 * 说明：此处启停与删除状态会影响静态 Bandit 扫描执行规则集。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
// import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
	type AppColumnDef,
	areDataTableQueryStatesEqual,
	createDefaultDataTableState,
	DataTable,
	type DataTableQueryState,
	type DataTableSelectionContext,
	useDataTableUrlState,
} from "@/components/data-table";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { AlertTriangle, Code, Database, Save, Shield } from "lucide-react";
import {
	batchDeleteBanditRules,
	batchRestoreBanditRules,
	batchUpdateBanditRulesEnabled,
	deleteBanditRule,
	getBanditRule,
	getBanditRules,
	restoreBanditRule,
	updateBanditRule,
	updateBanditRuleEnabled,
	type BanditRule,
} from "@/shared/api/bandit";
import { resolveDeletedFilterValue } from "@/pages/rulesTableState";
import {
	SCAN_ENGINE_SELECTOR_OPTIONS,
	type ScanEngineTab,
	isScanEngineTab,
} from "@/shared/constants/scanEngines";
// type DeletedFilterValue = "false" | "true" | "all";

interface BanditRulesProps {
	showEngineSelector?: boolean;
	engineValue?: ScanEngineTab;
	onEngineChange?: (value: ScanEngineTab) => void;
}

const getSourceLabel = () => "内置规则";
const DEFAULT_PAGE_SIZE = 10;

// function formatDate(value?: string | null) {
//   return value ? new Date(value).toLocaleString("zh-CN") : "-";
// }

function getColumnFilterValue(state: DataTableQueryState, columnId: string) {
	return state.columnFilters.find((filter) => filter.id === columnId)?.value;
}

function getStringColumnFilter(
	state: DataTableQueryState,
	columnId: string,
	fallback = "",
) {
	const value = getColumnFilterValue(state, columnId);
	return typeof value === "string" ? value : fallback;
}

function resolveBanditRuleIds(rows: BanditRule[]): string[] {
	return rows
		.map((row) => String(row.test_id || row.id || "").trim())
		.filter((value) => value.length > 0);
}

function buildSelectionSummary({
	selectedCount,
	filteredCount,
}: DataTableSelectionContext<BanditRule>) {
	if (selectedCount > 0) {
		return (
			<>
				已选择 <span className="font-bold text-primary">{selectedCount}</span>{" "}
				条规则
			</>
		);
	}
	return (
		<>
			将对全部 <span className="font-bold text-primary">{filteredCount}</span>{" "}
			条规则进行操作
		</>
	);
}

function createInitialTableState(
	initialState: DataTableQueryState,
): DataTableQueryState {
	const nextState = createDefaultDataTableState({
		...initialState,
		pagination: {
			pageIndex: initialState.pagination.pageIndex,
			pageSize: initialState.pagination.pageSize || DEFAULT_PAGE_SIZE,
		},
	});

	if (
		!nextState.columnFilters.some((filter) => filter.id === "deletedStatus")
	) {
		nextState.columnFilters.push({ id: "deletedStatus", value: "false" });
	}

	return nextState;
}

export default function BanditRules({
	showEngineSelector = false,
	engineValue = "bandit",
	onEngineChange,
}: BanditRulesProps) {
	const [rules, setRules] = useState<BanditRule[]>([]);
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [batchOperating, setBatchOperating] = useState(false);
	const [showRuleDetail, setShowRuleDetail] = useState(false);
	const [selectedRule, setSelectedRule] = useState<BanditRule | null>(null);
	const [loadingDetail, setLoadingDetail] = useState(false);
	const [isEditingRule, setIsEditingRule] = useState(false);
	const [savingRule, setSavingRule] = useState(false);
	// Bandit integration: 规则编辑用于维护规则页字段，启停/删除状态会影响静态审计执行。
	const [editRuleForm, setEditRuleForm] = useState({
		name: "",
		description_summary: "",
		description: "",
		checks_text: "",
	});
	const { initialState, syncStateToUrl } = useDataTableUrlState(true);
	const defaultResetState = useMemo(
		() => createInitialTableState(createDefaultDataTableState()),
		[],
	);
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createInitialTableState(initialState),
	);
	const resolvedUrlState = useMemo(
		() => createInitialTableState(initialState),
		[initialState],
	);
	const deletedFilter = resolveDeletedFilterValue(tableState);
	const activeFilter = getStringColumnFilter(tableState, "status");

	const loadRules = useCallback(async () => {
		try {
			setLoading(true);
			setLoadError(null);
			const data = await getBanditRules({
				deleted: deletedFilter,
				limit: 2000,
			});
			setRules(data);
		} catch (error) {
			console.error("Failed to load bandit rules:", error);
			setLoadError("加载 bandit 规则失败");
			toast.error("加载 bandit 规则失败");
		} finally {
			setLoading(false);
		}
	}, [deletedFilter]);

	useEffect(() => {
		void loadRules();
	}, [deletedFilter]);

	useEffect(() => {
		setTableState((current) =>
			areDataTableQueryStatesEqual(current, resolvedUrlState)
				? current
				: resolvedUrlState,
		);
	}, [resolvedUrlState]);

	useEffect(() => {
		syncStateToUrl(tableState);
	}, [syncStateToUrl, tableState]);

	const stats = useMemo(() => {
		const active = rules.filter((rule) => rule.is_active).length;
		const deleted = rules.filter((rule) => rule.is_deleted).length;
		const sources = new Set(rules.map(() => getSourceLabel()));
		const withChecks = rules.filter(
			(rule) => (rule.checks || []).length > 0,
		).length;
		return {
			total: rules.length,
			active,
			inactive: Math.max(rules.length - active, 0),
			deleted,
			sourceCount: sources.size,
			withChecks,
		};
	}, [rules]);

	const handleStartEditRule = (rule: BanditRule) => {
		setEditRuleForm({
			name: rule.name || "",
			description_summary: rule.description_summary || "",
			description: rule.description || "",
			checks_text: (rule.checks || []).join(", "),
		});
		setIsEditingRule(true);
	};

	const handleViewRuleDetail = useCallback(
		async (rule: BanditRule, mode: "view" | "edit" = "view") => {
			setSelectedRule(rule);
			setShowRuleDetail(true);
			setIsEditingRule(mode === "edit");
			setLoadingDetail(true);
			try {
				const detail = await getBanditRule(rule.test_id);
				setSelectedRule(detail);
				if (mode === "edit") {
					handleStartEditRule(detail);
				}
			} catch (error: any) {
				toast.error(error?.response?.data?.detail || "加载规则详情失败");
			} finally {
				setLoadingDetail(false);
			}
		},
		[],
	);

	const handleCancelEditRule = () => {
		setIsEditingRule(false);
		setSavingRule(false);
	};

	const handleSaveRule = async () => {
		if (!selectedRule) return;
		const normalizedChecks = editRuleForm.checks_text
			.split(/[\n,]/)
			.map((item) => item.trim())
			.filter(Boolean);
		if (!editRuleForm.name.trim()) {
			toast.error("规则名称不能为空");
			return;
		}

		try {
			setSavingRule(true);
			const result = await updateBanditRule({
				ruleId: selectedRule.test_id,
				name: editRuleForm.name.trim(),
				description_summary: editRuleForm.description_summary.trim(),
				description: editRuleForm.description.trim(),
				checks: normalizedChecks,
			});
			const updatedRule = result.rule;
			setSelectedRule(updatedRule);
			setRules((prev) =>
				prev.map((item) =>
					item.id === updatedRule.id ? { ...item, ...updatedRule } : item,
				),
			);
			setIsEditingRule(false);
			toast.success(result.message || "规则更新成功");
		} catch (error: any) {
			toast.error(error?.response?.data?.detail || "更新规则失败");
		} finally {
			setSavingRule(false);
		}
	};

	const handleDeleteRule = useCallback(
		async (rule: BanditRule) => {
			try {
				await deleteBanditRule(rule.test_id);
				toast.success(`规则「${rule.test_id}」已删除`);
				await loadRules();
			} catch (error: any) {
				toast.error(error?.response?.data?.detail || "删除规则失败");
			}
		},
		[loadRules],
	);

	const handleRestoreRule = useCallback(
		async (rule: BanditRule) => {
			try {
				await restoreBanditRule(rule.test_id);
				toast.success(`规则「${rule.test_id}」已恢复`);
				await loadRules();
			} catch (error: any) {
				toast.error(error?.response?.data?.detail || "恢复规则失败");
			}
		},
		[loadRules],
	);

	const handleToggleRule = useCallback(
		async (rule: BanditRule) => {
			if (rule.is_deleted) {
				toast.error("已删除规则请先恢复后再启用/禁用");
				return;
			}
			try {
				await updateBanditRuleEnabled({
					ruleId: rule.test_id,
					is_active: !rule.is_active,
				});
				await loadRules();
				toast.success(`规则已${rule.is_active ? "禁用" : "启用"}`);
			} catch (error: any) {
				toast.error(error?.response?.data?.detail || "更新规则失败");
			}
		},
		[loadRules],
	);

	const columns = useMemo<AppColumnDef<BanditRule, unknown>[]>(
		() => [
			{
				id: "rowNumber",
				header: "序号",
				enableSorting: false,
				enableHiding: false,
				meta: { label: "序号", align: "center", width: 72 },
				cell: ({ row, table }) => {
					const pageRowIndex = table
						.getRowModel()
						.rows.findIndex((r) => r.id === row.id);
					return (
						table.getState().pagination.pageIndex *
							table.getState().pagination.pageSize +
						pageRowIndex +
						1
					);
				},
			},
			{
				id: "ruleName",
				accessorFn: (row) =>
					[
						row.name,
						row.test_id,
						row.description_summary,
						row.description,
						row.id,
					]
						.filter(Boolean)
						.join(" "),
				header: "规则名称",
				meta: { label: "规则名称", minWidth: 200, filterVariant: "text" },
				cell: ({ row }) => (
					<div className="space-y-0.5">
						<div className="font-semibold text-foreground break-all">
							{row.original.name}
						</div>
					</div>
				),
			},
			{
				id: "checks",
				accessorFn: (row) => (row.checks || []).join(", "),
				header: "检查节点",
				meta: { label: "检查节点", minWidth: 120 },
				cell: ({ row }) => (
					<span className="text-sm text-muted-foreground">
						{(row.original.checks || []).join(", ") || "-"}
					</span>
				),
			},
			{
				id: "sourceLabel",
				accessorFn: () => getSourceLabel(),
				header: "来源",
				meta: {
					label: "规则来源",
					width: 120,
					filterVariant: "select",
					filterOptions: [{ label: "内置规则", value: "内置规则" }],
				},
				cell: () => (
					<Badge className="cyber-badge cyber-badge-info">
						{getSourceLabel()}
					</Badge>
				),
			},
			{
				id: "status",
				accessorFn: (row) => String(row.is_active),
				header: "启用状态",
				meta: {
					label: "启用状态",
					width: 136,
					filterVariant: "select",
					filterOptions: [
						{ label: "已启用", value: "true" },
						{ label: "已禁用", value: "false" },
					],
				},
				cell: ({ row }) => (
					<Badge
						className={
							row.original.is_active
								? "cyber-badge cyber-badge-success"
								: "cyber-badge cyber-badge-muted"
						}
					>
						{row.original.is_active ? "已启用" : "已禁用"}
					</Badge>
				),
			},
			{
				id: "actions",
				header: "操作",
				enableSorting: false,
				enableHiding: false,
				meta: { label: "操作", minWidth: 320 },
				cell: ({ row }) => (
					<div className="flex flex-wrap gap-2">
						<Button
							onClick={() => handleViewRuleDetail(row.original)}
							className="cyber-btn-outline h-8 text-xs"
						>
							查看详情
						</Button>
						<Button
							onClick={() => handleViewRuleDetail(row.original, "edit")}
							className="cyber-btn-outline h-8 text-xs"
						>
							编辑
						</Button>
						<Button
							onClick={() => void handleToggleRule(row.original)}
							disabled={row.original.is_deleted}
							className={
								row.original.is_active
									? "cyber-btn-outline h-8 text-xs"
									: "cyber-btn-primary h-8 text-xs"
							}
						>
							{row.original.is_active ? "禁用" : "启用"}
						</Button>
						{!row.original.is_deleted ? (
							<Button
								onClick={() => void handleDeleteRule(row.original)}
								className="cyber-btn-outline h-8 text-xs"
							>
								删除
							</Button>
						) : (
							<Button
								onClick={() => void handleRestoreRule(row.original)}
								className="cyber-btn-primary h-8 text-xs"
							>
								恢复
							</Button>
						)}
					</div>
				),
			},
		],
		[
			handleDeleteRule,
			handleRestoreRule,
			handleToggleRule,
			handleViewRuleDetail,
		],
	);

	const handleBatchToggleEnabled = async (
		selectedRows: BanditRule[],
		isActive: boolean,
	) => {
		try {
			setBatchOperating(true);
			const currentActiveFilter = getStringColumnFilter(tableState, "status");
			const selectableRows = selectedRows.filter((row) => !row.is_deleted);
			if (selectedRows.length > 0 && selectableRows.length === 0) {
				toast.error("所选规则均已删除，请先恢复后再执行批量启用/禁用");
				return;
			}
			const payload =
				selectedRows.length > 0
					? {
							rule_ids: resolveBanditRuleIds(selectableRows),
							is_active: isActive,
						}
					: {
							source: undefined,
							keyword: tableState.globalFilter.trim() || undefined,
							current_is_active:
								currentActiveFilter === ""
									? undefined
									: currentActiveFilter === "true",
							is_active: isActive,
						};
			const result = await batchUpdateBanditRulesEnabled(payload);
			toast.success(result.message);
			setTableState((current) => ({ ...current, rowSelection: {} }));
			await loadRules();
		} catch (error: any) {
			toast.error(error?.response?.data?.detail || "批量启停失败");
		} finally {
			setBatchOperating(false);
		}
	};

	const handleBatchDelete = async (selectedRows: BanditRule[]) => {
		try {
			setBatchOperating(true);
			const payload =
				selectedRows.length > 0
					? { rule_ids: resolveBanditRuleIds(selectedRows) }
					: {
							source: undefined,
							keyword: tableState.globalFilter.trim() || undefined,
							current_is_deleted: false,
						};
			const result = await batchDeleteBanditRules(payload);
			toast.success(result.message);
			setTableState((current) => ({ ...current, rowSelection: {} }));
			await loadRules();
		} catch (error: any) {
			toast.error(error?.response?.data?.detail || "批量删除失败");
		} finally {
			setBatchOperating(false);
		}
	};

	const handleBatchRestore = async (selectedRows: BanditRule[]) => {
		try {
			setBatchOperating(true);
			const payload =
				selectedRows.length > 0
					? { rule_ids: resolveBanditRuleIds(selectedRows) }
					: {
							source: undefined,
							keyword: tableState.globalFilter.trim() || undefined,
							current_is_deleted: true,
						};
			const result = await batchRestoreBanditRules(payload);
			toast.success(result.message);
			setTableState((current) => ({ ...current, rowSelection: {} }));
			await loadRules();
		} catch (error: any) {
			toast.error(error?.response?.data?.detail || "批量恢复失败");
		} finally {
			setBatchOperating(false);
		}
	};

	const engineSelector = showEngineSelector ? (
		<div className="min-w-[150px]">
			<Select
				value={engineValue}
				onValueChange={(val) => {
					if (isScanEngineTab(val)) {
						onEngineChange?.(val);
					}
				}}
			>
				<SelectTrigger className="cyber-input h-10 min-w-[150px]">
					<SelectValue placeholder="选择引擎" />
				</SelectTrigger>
				<SelectContent className="cyber-dialog border-border">
					{SCAN_ENGINE_SELECTOR_OPTIONS.map((option) => (
						<SelectItem key={option.value} value={option.value}>
							{option.label}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		</div>
	) : null;

	return (
		<div className="space-y-6 p-4 md:p-6">
			<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">有效规则总数</p>
							<div className="flex items-end gap-3">
								<p className="stat-value">{stats.total}</p>
								<p className="text-sm mb-1 flex items-center gap-3">
									<span className="inline-flex items-center gap-1 text-emerald-400">
										<span className="w-2 h-2 rounded-full bg-emerald-400" />
										已启用 {stats.active}
									</span>
								</p>
							</div>
						</div>
						<div className="stat-icon text-primary">
							<Database className="w-6 h-6" />
						</div>
					</div>
				</div>
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">规则来源数量</p>
							<p className="stat-value">{stats.sourceCount}</p>
						</div>
						<div className="stat-icon text-indigo-400">
							<AlertTriangle className="w-6 h-6" />
						</div>
					</div>
				</div>
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">含检查节点规则数</p>
							<p className="stat-value">{stats.withChecks}</p>
						</div>
						<div className="stat-icon text-cyan-400">
							<Shield className="w-6 h-6" />
						</div>
					</div>
				</div>
			</div>

			<div className="cyber-card relative z-10 overflow-hidden">
				<DataTable
					data={rules}
					columns={columns}
					state={tableState}
					resetState={defaultResetState}
					onStateChange={setTableState}
					loading={loading}
					error={loadError || undefined}
					emptyState={{
						title: "未找到规则",
						description:
							tableState.globalFilter ||
							activeFilter ||
							deletedFilter !== "false"
								? "调整筛选条件尝试"
								: "暂无规则数据（请先生成并导入 bandit 内置规则快照）",
					}}
					toolbar={{
						searchPlaceholder: "搜索名称/ID/描述...",
						leadingActions: engineSelector,
						showGlobalSearch: false,
						showColumnVisibility: false,
						showDensityToggle: false,
						showReset: false,
					}}
					selection={
						loading
							? undefined
							: {
									enableRowSelection: true,
									summary: buildSelectionSummary,
									actions: ({ selectedRows }) => (
										<>
											<Button
												onClick={() =>
													void handleBatchToggleEnabled(selectedRows, true)
												}
												disabled={batchOperating}
												className="cyber-btn-primary h-8 text-sm"
											>
												{batchOperating ? "处理中..." : "批量启用"}
											</Button>
											<Button
												onClick={() =>
													void handleBatchToggleEnabled(selectedRows, false)
												}
												disabled={batchOperating}
												className="cyber-btn-outline h-8 text-sm"
											>
												{batchOperating ? "处理中..." : "批量禁用"}
											</Button>
											<Button
												onClick={() => void handleBatchDelete(selectedRows)}
												disabled={batchOperating}
												className="cyber-btn-outline h-8 text-sm"
											>
												{batchOperating ? "处理中..." : "批量删除"}
											</Button>
											<Button
												onClick={() => void handleBatchRestore(selectedRows)}
												disabled={batchOperating}
												className="cyber-btn-outline h-8 text-sm"
											>
												{batchOperating ? "处理中..." : "批量恢复"}
											</Button>
										</>
									),
								}
					}
					pagination={{ enabled: true, pageSizeOptions: [10, 20, 50] }}
					tableClassName="min-w-[1380px]"
					getRowId={(row) => row.id}
				/>
			</div>

			<Dialog
				open={showRuleDetail}
				onOpenChange={(open) => {
					setShowRuleDetail(open);
					if (!open) {
						setIsEditingRule(false);
						setSavingRule(false);
					}
				}}
			>
				<DialogContent
					aria-describedby={undefined}
					className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
				>
					<DialogHeader className="px-6 pt-4 flex-shrink-0">
						<DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
							<Code className="w-5 h-5 text-primary" />
							{isEditingRule ? "编辑规则" : "规则详情"}
						</DialogTitle>
					</DialogHeader>

					{loadingDetail ? (
						<div className="flex items-center justify-center p-8">
							<div className="loading-spinner" />
						</div>
					) : selectedRule ? (
						<div className="flex-1 overflow-y-auto p-6">
							<div className="space-y-6">
								<div className="space-y-3">
									<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
										基本信息
									</h3>
									<div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm font-mono">
										<div>
											<p className="text-muted-foreground">规则名称</p>
											{isEditingRule ? (
												<Input
													value={editRuleForm.name}
													onChange={(e) =>
														setEditRuleForm((prev) => ({
															...prev,
															name: e.target.value,
														}))
													}
													className="cyber-input mt-1.5 h-9"
												/>
											) : (
												<p className="text-foreground font-bold mt-1 break-all">
													{selectedRule.name}
												</p>
											)}
										</div>
										<div>
											<p className="text-muted-foreground">规则ID</p>
											<p className="text-foreground font-bold mt-1 break-all">
												{selectedRule.test_id}
											</p>
										</div>
										<div>
											<p className="text-muted-foreground">来源</p>
											<Badge className="cyber-badge cyber-badge-info mt-1">
												{getSourceLabel()}
											</Badge>
										</div>
										<div>
											<p className="text-muted-foreground">Bandit版本</p>
											<p className="text-foreground font-bold mt-1">
												{selectedRule.bandit_version || "-"}
											</p>
										</div>
										<div>
											<p className="text-muted-foreground">启用状态</p>
											{selectedRule.is_deleted ? (
												<Badge className="cyber-badge cyber-badge-muted mt-1">
													已删除
												</Badge>
											) : (
												<Badge
													className={`mt-1 ${selectedRule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}`}
												>
													{selectedRule.is_active ? "已启用" : "已禁用"}
												</Badge>
											)}
										</div>
										<div>
											<p className="text-muted-foreground">规则标识</p>
											<p className="text-foreground font-bold mt-1 break-all">
												{selectedRule.source || "-"}
											</p>
										</div>
									</div>
								</div>

								<div className="space-y-3">
									<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
										摘要
									</h3>
									{isEditingRule ? (
										<Textarea
											value={editRuleForm.description_summary}
											onChange={(e) =>
												setEditRuleForm((prev) => ({
													...prev,
													description_summary: e.target.value,
												}))
											}
											className="cyber-input min-h-24"
										/>
									) : (
										<div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
											{selectedRule.description_summary || "-"}
										</div>
									)}
								</div>

								<div className="space-y-3">
									<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
										描述
									</h3>
									{isEditingRule ? (
										<Textarea
											value={editRuleForm.description}
											onChange={(e) =>
												setEditRuleForm((prev) => ({
													...prev,
													description: e.target.value,
												}))
											}
											className="cyber-input min-h-52 font-mono text-xs"
										/>
									) : (
										<div className="max-h-[320px] overflow-y-auto rounded border border-border/50 p-3 text-xs text-muted-foreground whitespace-pre-wrap break-words font-mono">
											{selectedRule.description || "-"}
										</div>
									)}
								</div>

								<div className="space-y-3">
									<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
										检查节点
									</h3>
									{isEditingRule ? (
										<Textarea
											value={editRuleForm.checks_text}
											onChange={(e) =>
												setEditRuleForm((prev) => ({
													...prev,
													checks_text: e.target.value,
												}))
											}
											placeholder="支持逗号或换行分隔"
											className="cyber-input min-h-24 font-mono text-xs"
										/>
									) : (
										<div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
											{(selectedRule.checks || []).join(", ") || "-"}
										</div>
									)}
								</div>

								<div className="space-y-3">
									<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
										元数据
									</h3>
									<div className="text-sm font-mono text-muted-foreground">
										<p>
											创建时间:{" "}
											{selectedRule.created_at
												? new Date(selectedRule.created_at).toLocaleString(
														"zh-CN",
													)
												: "-"}
										</p>
										<p>
											更新时间:{" "}
											{selectedRule.updated_at
												? new Date(selectedRule.updated_at).toLocaleString(
														"zh-CN",
													)
												: "-"}
										</p>
									</div>
								</div>
							</div>
						</div>
					) : null}

					<div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
						<Button
							variant="outline"
							onClick={() => {
								if (isEditingRule) {
									handleCancelEditRule();
								} else {
									setShowRuleDetail(false);
								}
							}}
							className="cyber-btn-outline"
						>
							{isEditingRule ? "取消编辑" : "关闭"}
						</Button>
						{isEditingRule ? (
							<Button
								onClick={() => void handleSaveRule()}
								className="cyber-btn-primary"
								disabled={savingRule}
							>
								{savingRule ? (
									<>
										<div className="loading-spinner mr-2" />
										保存中...
									</>
								) : (
									<>
										<Save className="w-4 h-4 mr-2" />
										保存规则
									</>
								)}
							</Button>
						) : null}
					</div>
				</DialogContent>
			</Dialog>
		</div>
	);
}
