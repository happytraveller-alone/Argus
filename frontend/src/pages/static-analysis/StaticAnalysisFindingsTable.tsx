import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	DataTable,
	type AppColumnDef,
	type DataTableQueryState,
} from "@/components/data-table";
import {
	appendReturnTo,
	buildFindingDetailPath,
} from "@/shared/utils/findingRoute";
import type { FindingStatus, UnifiedFindingRow } from "./viewModel";
import {
	getStaticAnalysisConfidenceBadgeClass,
	getStaticAnalysisConfidenceLabel,
	getStaticAnalysisFindingStatusBadgeClass,
	getStaticAnalysisFindingStatusLabel,
	getStaticAnalysisSeverityBadgeClass,
	getStaticAnalysisSeverityLabel,
} from "./viewModel";

const ACTIVE_TRUE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-emerald-500/70 bg-emerald-500/15 text-emerald-200 hover:bg-emerald-500/20";
const IDLE_TRUE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10";
const ACTIVE_FALSE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-rose-500/70 bg-rose-500/15 text-rose-200 hover:bg-rose-500/20";
const IDLE_FALSE_BUTTON_CLASS =
	"cyber-btn-outline h-7 px-2.5 border-rose-500/40 text-rose-400 hover:bg-rose-500/10";

function getEngineLabel(engine: UnifiedFindingRow["engine"]) {
	if (engine === "opengrep") return "Opengrep";
	if (engine === "gitleaks") return "Gitleaks";
	if (engine === "bandit") return "Bandit";
	if (engine === "phpstan") return "PHPStan";
	return "PMD";
}

function getEngineBadgeClass(engine: UnifiedFindingRow["engine"]) {
	if (engine === "opengrep") {
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	}
	if (engine === "gitleaks") {
		return "bg-amber-500/20 text-amber-300 border-amber-500/30";
	}
	if (engine === "bandit") {
		return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
	}
	if (engine === "phpstan") {
		return "bg-violet-500/20 text-violet-300 border-violet-500/30";
	}
	if (engine === "pmd") {
		return "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/30";
	}
	return "bg-cyan-500/20 text-cyan-300 border-cyan-500/30";
}

export function getColumns(input: {
	currentRoute: string;
	updatingKey: string | null;
	onToggleStatus: (row: UnifiedFindingRow, target: FindingStatus) => void;
}): AppColumnDef<UnifiedFindingRow, unknown>[] {
	return [
		{
			id: "rowNumber",
			header: "序号",
			enableSorting: false,
			meta: {
				label: "序号",
				align: "center",
				width: 72,
			},
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
			id: "engine",
			accessorFn: (row) => row.engine,
			header: "引擎",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "引擎",
				width: 110,
				filterVariant: "select",
				filterOptions: [
					{ label: "Opengrep", value: "opengrep" },
					{ label: "Gitleaks", value: "gitleaks" },
					{ label: "Bandit", value: "bandit" },
					{ label: "PHPStan", value: "phpstan" },
					{ label: "PMD", value: "pmd" },
				],
			},
			cell: ({ row }) => (
				<Badge className={getEngineBadgeClass(row.original.engine)}>
					{getEngineLabel(row.original.engine)}
				</Badge>
			),
		},
		{
			id: "rule",
			accessorFn: (row) => row.rule,
			header: "命中规则",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "命中规则",
				align: "left",
				width: 220,
				minWidth: 180,
				maxWidth: 260,
				filterVariant: "text",
			},
			cell: ({ row }) => (
				<span
					className="block max-w-full truncate text-sm"
					title={row.original.rule || undefined}
				>
					{row.original.rule || "-"}
				</span>
			),
		},
		{
			id: "location",
			accessorFn: (row) =>
				[
					row.filePath,
					row.line ? `:${row.line}` : "",
					row.rule,
					getEngineLabel(row.engine),
					getStaticAnalysisFindingStatusLabel(row.status),
					getStaticAnalysisSeverityLabel(row.severity),
					getStaticAnalysisConfidenceLabel(row.confidence),
				].join(" "),
			header: "命中位置",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "命中位置",
				align: "left",
				minWidth: 350,
			},
			cell: ({ row }) => (
				<span className="font-mono text-sm break-all">
					{row.original.filePath}
					{row.original.line ? `:${row.original.line}` : ""}
				</span>
			),
		},
		{
			id: "severity",
			accessorFn: (row) => row.severity,
			header: "危害",
			// enableSorting: false,
			enableHiding: false,
			sortingFn: (left, right) =>
				right.original.severityScore - left.original.severityScore,
			meta: {
				label: "漏洞危害",
				width: 150,
				filterVariant: "select",
				filterOptions: [
					{ label: "严重", value: "CRITICAL" },
					{ label: "高危", value: "HIGH" },
					{ label: "中危", value: "MEDIUM" },
					{ label: "低危", value: "LOW" },
				],
			},
			cell: ({ row }) => (
				<Badge
					className={getStaticAnalysisSeverityBadgeClass(row.original.severity)}
				>
					{getStaticAnalysisSeverityLabel(row.original.severity)}
				</Badge>
			),
		},
		{
			id: "confidence",
			accessorFn: (row) => row.confidence,
			header: "置信度",
			// enableSorting: false,
			enableHiding: false,
			sortingFn: (left, right) =>
				right.original.confidenceScore - left.original.confidenceScore,
			meta: {
				label: "置信度",
				width: 180,
				filterVariant: "select",
				filterOptions: [
					{ label: "高", value: "HIGH" },
					{ label: "中", value: "MEDIUM" },
					{ label: "低", value: "LOW" },
				],
			},
			cell: ({ row }) => (
				<Badge
					className={getStaticAnalysisConfidenceBadgeClass(
						row.original.confidence,
					)}
				>
					{getStaticAnalysisConfidenceLabel(row.original.confidence)}
				</Badge>
			),
		},
		{
			id: "status",
			accessorFn: (row) => row.status,
			header: "漏洞状态",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "漏洞状态",
				minWidth: 120,
				filterVariant: "select",
				filterOptions: [
					{ label: "待验证", value: "open" },
					{ label: "确报", value: "verified" },
					{ label: "误报", value: "false_positive" },
				],
			},
			cell: ({ row }) => {
				const rowStatus = String(row.original.status || "open").toLowerCase();
				return (
					<Badge
						className={getStaticAnalysisFindingStatusBadgeClass(rowStatus)}
					>
						{getStaticAnalysisFindingStatusLabel(rowStatus)}
					</Badge>
				);
			},
		},
		{
			id: "actions",
			header: "操作",
			enableSorting: false,
			meta: {
				label: "操作",
				minWidth: 280,
			},
			cell: ({ row }) => {
				const rowStatus = String(row.original.status || "open").toLowerCase();
				const rowUpdatePrefix = `${row.original.engine}:${row.original.id}:`;
				const rowStatusUpdating = Boolean(
					input.updatingKey?.startsWith(rowUpdatePrefix),
				);
				const verifyUpdating =
					input.updatingKey ===
					`${row.original.engine}:${row.original.id}:verified`;
				const falsePositiveUpdating =
					input.updatingKey ===
					`${row.original.engine}:${row.original.id}:false_positive`;
				const detailRoute = appendReturnTo(
					buildFindingDetailPath({
						source: "static",
						taskId: row.original.taskId,
						findingId: row.original.id,
						engine: row.original.engine,
					}),
					input.currentRoute,
				);

				return (
					<div className="flex items-center gap-1.5 flex-wrap">
						<Button
							asChild
							size="sm"
							variant="outline"
							className="cyber-btn-outline h-7 px-2.5"
						>
							<Link to={detailRoute}>详情</Link>
						</Button>
						<Button
							size="sm"
							variant="outline"
							className={
								rowStatus === "verified"
									? ACTIVE_TRUE_BUTTON_CLASS
									: IDLE_TRUE_BUTTON_CLASS
							}
							disabled={rowStatusUpdating}
							aria-pressed={rowStatus === "verified"}
							onClick={() => input.onToggleStatus(row.original, "verified")}
						>
							{verifyUpdating ? (
								<Loader2 className="w-3 h-3 animate-spin" />
							) : (
								"判真"
							)}
						</Button>
						<Button
							size="sm"
							variant="outline"
							className={
								rowStatus === "false_positive"
									? ACTIVE_FALSE_BUTTON_CLASS
									: IDLE_FALSE_BUTTON_CLASS
							}
							disabled={rowStatusUpdating}
							aria-pressed={rowStatus === "false_positive"}
							onClick={() =>
								input.onToggleStatus(row.original, "false_positive")
							}
						>
							{falsePositiveUpdating ? (
								<Loader2 className="w-3 h-3 animate-spin" />
							) : (
								"判假"
							)}
						</Button>
					</div>
				);
			},
		},
	];
}

export default function StaticAnalysisFindingsTable({
	currentRoute,
	loadingInitial,
	rows,
	state,
	onStateChange,
	updatingKey,
	onToggleStatus,
}: {
	currentRoute: string;
	loadingInitial: boolean;
	rows: UnifiedFindingRow[];
	state: DataTableQueryState;
	onStateChange: (state: DataTableQueryState) => void;
	updatingKey: string | null;
	onToggleStatus: (row: UnifiedFindingRow, target: FindingStatus) => void;
}) {
	const columns = getColumns({
		currentRoute,
		updatingKey,
		onToggleStatus,
	}) as ColumnDef<UnifiedFindingRow>[];

	return (
		<DataTable
			data={rows}
			columns={columns}
			state={state}
			onStateChange={onStateChange}
			loading={loadingInitial}
			emptyState={{
				title: "暂无符合条件的漏洞",
				description: loadingInitial
					? undefined
					: "可尝试调整筛选条件或稍后刷新",
			}}
			toolbar={{
				searchPlaceholder: "搜索规则、位置或状态",
				showGlobalSearch: true,
				showColumnVisibility: false,
				showDensityToggle: false,
				showReset: false,
			}}
			pagination={{
				enabled: true,
				pageSizeOptions: [10, 20, 50],
				infoLabel: ({ table, filteredCount }) =>
					`共 ${filteredCount.toLocaleString()} 条，第 ${
						table.getState().pagination.pageIndex + 1
					} / ${Math.max(1, table.getPageCount())} 页`,
			}}
			className="border border-border rounded-md"
			fillContainerWidth
		/>
	);
}
