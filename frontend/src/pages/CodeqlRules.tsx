/**
 * CodeQL Rules Page
 * Cyberpunk Terminal Aesthetic — read-only view mirroring OpengrepRules layout
 */

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	type AppColumnDef,
	createDefaultDataTableState,
	DataTable,
	type DataTableQueryState,
} from "@/components/data-table";
import {
	getCodeqlRulesPage,
	getCodeqlRuleStats,
	type CodeqlRule,
	type CodeqlRuleStats,
} from "@/shared/api/codeqlRules";
import {
	SCAN_ENGINE_SELECTOR_OPTIONS,
	type ScanEngineTab,
	isScanEngineTab,
} from "@/shared/constants/scanEngines";

interface CodeqlRulesProps {
	embedded?: boolean;
	showEngineSelector?: boolean;
	engineValue?: ScanEngineTab;
	onEngineChange?: (value: ScanEngineTab) => void;
}

const DEFAULT_PAGE_SIZE = 10;

const CODEQL_RULE_TABLE_HEADER_CLASSNAME = "text-xs tracking-[0.12em]";
const CODEQL_RULE_TABLE_CELL_CLASSNAME = "text-xs";

function createRuleTableMeta(
	meta: AppColumnDef<CodeqlRule, unknown>["meta"],
) {
	return {
		headerContentClassName: CODEQL_RULE_TABLE_HEADER_CLASSNAME,
		cellClassName: CODEQL_RULE_TABLE_CELL_CLASSNAME,
		...meta,
	};
}

function formatStatValue(value: number | null) {
	return value === null ? " " : value.toLocaleString();
}

function createInitialTableState(): DataTableQueryState {
	return createDefaultDataTableState({
		pagination: {
			pageIndex: 0,
			pageSize: DEFAULT_PAGE_SIZE,
		},
	});
}

export default function CodeqlRules({
	embedded = false,
	showEngineSelector = false,
	engineValue = "codeql",
	onEngineChange,
}: CodeqlRulesProps) {
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createInitialTableState(),
	);
	const [rules, setRules] = useState<CodeqlRule[]>([]);
	const [pageTotal, setPageTotal] = useState(0);
	const [loading, setLoading] = useState(false);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [stats, setStats] = useState<CodeqlRuleStats | null>(null);
	const [selectedRule, setSelectedRule] = useState<CodeqlRule | null>(null);
	const [showDetail, setShowDetail] = useState(false);

	const keyword = String(tableState.globalFilter || "").trim();
	const languageFilter = useMemo(() => {
		const f = tableState.columnFilters.find((c) => c.id === "language");
		return typeof f?.value === "string" ? f.value : "";
	}, [tableState.columnFilters]);

	// Fetch stats once on mount
	useEffect(() => {
		getCodeqlRuleStats()
			.then(setStats)
			.catch(() => {/* silently ignore stats errors */});
	}, []);

	// Fetch rules when pagination/filter changes
	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		setLoadError(null);

		const skip =
			tableState.pagination.pageIndex * tableState.pagination.pageSize;
		const limit = tableState.pagination.pageSize;

		getCodeqlRulesPage({
			skip,
			limit,
			keyword: keyword || undefined,
			language: languageFilter || undefined,
		})
			.then((res) => {
				if (cancelled) return;
				setRules(res.data);
				setPageTotal(res.total);
			})
			.catch((err: unknown) => {
				if (cancelled) return;
				setLoadError(
					err instanceof Error ? err.message : "加载规则失败",
				);
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});

		return () => {
			cancelled = true;
		};
	}, [
		tableState.pagination.pageIndex,
		tableState.pagination.pageSize,
		keyword,
		languageFilter,
	]);

	const columns = useMemo<AppColumnDef<CodeqlRule, unknown>[]>(
		() => [
			{
				id: "index",
				header: "序号",
				cell: ({ row }) =>
					tableState.pagination.pageIndex *
						tableState.pagination.pageSize +
					row.index +
					1,
				meta: createRuleTableMeta({ width: 60 }),
			},
			{
				accessorKey: "name",
				header: "规则名称",
				cell: ({ row }) => (
					<button
						type="button"
						className="text-left font-mono text-cyan-300 hover:text-cyan-100 hover:underline cursor-pointer"
						onClick={() => {
							setSelectedRule(row.original);
							setShowDetail(true);
						}}
					>
						{row.original.name}
					</button>
				),
				meta: createRuleTableMeta({}),
			},
			{
				accessorKey: "language",
				header: "语言",
				cell: ({ row }) => (
					<Badge className="border-violet-500/30 bg-violet-500/10 text-violet-300 font-mono text-xs">
						{row.original.language}
					</Badge>
				),
				meta: createRuleTableMeta({ width: 100 }),
			},
			{
				accessorKey: "asset_path",
				header: "路径",
				cell: ({ row }) => (
					<span className="font-mono text-muted-foreground text-xs truncate max-w-[300px] block">
						{row.original.asset_path}
					</span>
				),
				meta: createRuleTableMeta({}),
			},
			{
				accessorKey: "is_active",
				header: "状态",
				cell: ({ row }) =>
					row.original.is_active ? (
						<Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300 text-xs">
							启用
						</Badge>
					) : (
						<Badge className="border-red-500/30 bg-red-500/10 text-red-300 text-xs">
							禁用
						</Badge>
					),
				meta: createRuleTableMeta({ width: 80 }),
			},
		],
		[tableState.pagination.pageIndex, tableState.pagination.pageSize],
	);

	return (
		<div
			className={`flex flex-col bg-background font-mono relative ${embedded ? "" : "h-screen overflow-hidden"}`}
		>
			{!embedded && (
				<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			)}

			<div className={`flex-1 ${embedded ? "" : "overflow-y-auto"}`}>
				<div className={`space-y-6 ${embedded ? "p-0" : "p-6"} relative z-10`}>
					{/* Search + Stats Badges + Engine Selector */}
					<div className="flex flex-nowrap items-center justify-between gap-3 relative z-10">
						<div className="flex min-w-0 flex-1 items-center gap-3">
							{showEngineSelector && (
								<div className="min-w-[150px]">
									<Select
										value={engineValue}
										onValueChange={(value) => {
											if (isScanEngineTab(value)) {
												onEngineChange?.(value);
											}
										}}
									>
										<SelectTrigger className="cyber-input h-9 min-w-[150px]">
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
							)}
							{/* Language filter dropdown */}
							<div className="min-w-[120px]">
								<Select
									value={languageFilter || "__all__"}
									onValueChange={(value) => {
										const lang = value === "__all__" ? "" : value;
										setTableState((current) => ({
											...current,
											columnFilters: lang
												? [{ id: "language", value: lang }]
												: [],
											pagination: { ...current.pagination, pageIndex: 0 },
										}));
									}}
								>
									<SelectTrigger className="cyber-input h-9">
										<SelectValue placeholder="全部语言" />
									</SelectTrigger>
									<SelectContent className="cyber-dialog border-border">
										<SelectItem value="__all__">全部语言</SelectItem>
										{(stats?.languages ?? []).map((lang) => (
											<SelectItem key={lang} value={lang}>
												{lang}
											</SelectItem>
										))}
									</SelectContent>
								</Select>
							</div>
							<div className="relative w-full max-w-sm">
								<Input
									value={tableState.globalFilter as string}
									onChange={(e) =>
										setTableState((current) => ({
											...current,
											globalFilter: e.target.value,
											pagination: {
												...current.pagination,
												pageIndex: 0,
											},
										}))
									}
									placeholder="搜索规则名称..."
									className="cyber-input h-9 font-mono"
								/>
							</div>
							<div className="flex items-center gap-2">
								<Badge className="border-cyan-500/30 bg-cyan-500/10 text-cyan-300 gap-1.5">
									规则数量{" "}
									<span className="font-semibold tabular-nums">
										{formatStatValue(stats?.total ?? null)}
									</span>
								</Badge>
								<Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300 gap-1.5">
									支持语言{" "}
									<span className="font-semibold tabular-nums">
										{formatStatValue(stats?.language_count ?? null)}
									</span>
								</Badge>
							</div>
						</div>
					</div>

					{/* Table */}
					<DataTable
						data={rules}
						columns={columns}
						mode="manual"
						state={tableState}
						onStateChange={setTableState}
						loading={loading}
						error={loadError || undefined}
						emptyState={{
							title: "未找到规则",
							description: keyword || languageFilter
								? "调整筛选条件尝试"
								: "暂无规则数据",
						}}
						toolbar={false}
						pagination={{
							enabled: true,
							manual: true,
							totalCount: pageTotal,
							pageSizeOptions: [10, 20, 50, 100],
						}}
						enableColumnResizing
						fillContainerWidth
						tableClassName="w-full"
						getRowId={(row) => row.id}
					/>
				</div>
			</div>

			{/* Rule Detail Dialog */}
			<Dialog
				open={showDetail}
				onOpenChange={(open) => {
					setShowDetail(open);
					if (!open) setSelectedRule(null);
				}}
			>
				<DialogContent
					aria-describedby={undefined}
					className="!w-[min(90vw,800px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
				>
					<DialogHeader className="px-6 pt-4 flex-shrink-0">
						<DialogTitle className="font-mono text-sm text-foreground">
							{selectedRule?.name ?? "规则详情"}
						</DialogTitle>
					</DialogHeader>
					{selectedRule && (
						<div className="flex-1 overflow-y-auto px-6 pb-6 pt-2 space-y-3">
							<div className="grid grid-cols-2 gap-3 text-xs font-mono">
								<div>
									<span className="text-muted-foreground">语言：</span>
									<span className="text-foreground">{selectedRule.language}</span>
								</div>
								<div>
									<span className="text-muted-foreground">格式：</span>
									<span className="text-foreground">{selectedRule.file_format}</span>
								</div>
								<div>
									<span className="text-muted-foreground">来源：</span>
									<span className="text-foreground">{selectedRule.source}</span>
								</div>
								<div>
									<span className="text-muted-foreground">状态：</span>
									<span className={selectedRule.is_active ? "text-emerald-400" : "text-red-400"}>
										{selectedRule.is_active ? "启用" : "禁用"}
									</span>
								</div>
							</div>
							<div className="text-xs font-mono">
								<span className="text-muted-foreground">路径：</span>
								<span className="text-foreground break-all">{selectedRule.asset_path}</span>
							</div>
							{Object.keys(selectedRule.metadata).length > 0 && (
								<div>
									<div className="text-xs text-muted-foreground font-mono mb-1">元数据：</div>
									<pre className="text-xs font-mono bg-muted/30 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all">
										{JSON.stringify(selectedRule.metadata, null, 2)}
									</pre>
								</div>
							)}
							<div>
								<div className="text-xs text-muted-foreground font-mono mb-1">规则内容：</div>
								<pre className="text-xs font-mono text-foreground/90 whitespace-pre-wrap break-words bg-muted/30 rounded-lg p-4 border border-border">
									{selectedRule.content || "无内容"}
								</pre>
							</div>
						</div>
					)}
				</DialogContent>
			</Dialog>
		</div>
	);
}
