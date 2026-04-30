import type { ColumnDef } from "@tanstack/react-table";
import { AlertTriangle, Bug, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
	type AppColumnDef,
	DataTable,
	type DataTableQueryState,
} from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ProjectDetailPotentialListItem } from "@/pages/project-detail/potentialVulnerabilities";
import { appendReturnTo } from "@/shared/utils/findingRoute";

type PotentialStatus = "loading" | "ready" | "empty" | "failed";

interface ProjectPotentialVulnerabilitiesSectionProps {
	status: PotentialStatus;
	findings: ProjectDetailPotentialListItem[];
	totalFindings: number;
	currentRoute: string;
	pageSize?: number;
}

const DEFAULT_PAGE_SIZE = 10;

function getStatusMessage(status: PotentialStatus): string | null {
	if (status === "loading") return "加载中...";
	if (status === "failed") return "加载失败";
	if (status === "empty") return "暂无潜在漏洞";
	return null;
}

function getSeverityBadgeClassName(
	severity: ProjectDetailPotentialListItem["severity"],
): string {
	if (severity === "CRITICAL") return "cyber-badge-danger";
	if (severity === "HIGH") return "cyber-badge-warning";
	if (severity === "MEDIUM") return "cyber-badge-info";
	return "cyber-badge-muted";
}

function getSeverityText(
	severity: ProjectDetailPotentialListItem["severity"],
): string {
	if (severity === "CRITICAL") return "严重";
	if (severity === "HIGH") return "高危";
	if (severity === "MEDIUM") return "中危";
	if (severity === "LOW") return "低危";
	return "未知";
}

function getConfidenceBadgeClassName(
	confidence: ProjectDetailPotentialListItem["confidence"],
): string {
	if (confidence === "HIGH") {
		return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
	}
	if (confidence === "MEDIUM") {
		return "bg-amber-500/20 text-amber-300 border-amber-500/30";
	}
	if (confidence === "LOW") {
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	}
	return "cyber-badge-muted";
}

function getConfidenceText(
	confidence: ProjectDetailPotentialListItem["confidence"],
): string {
	if (confidence === "HIGH") return "高";
	if (confidence === "MEDIUM") return "中";
	if (confidence === "LOW") return "低";
	return "-";
}

function getTaskCategoryBadgeClassName(
	category: ProjectDetailPotentialListItem["taskCategory"],
): string {
	if (category === "static") {
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	}
	if (category === "intelligent") {
		return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
	}
	return "bg-amber-500/20 text-amber-300 border-amber-500/30";
}

export function ProjectPotentialVulnerabilitiesSection({
	status,
	findings,
	totalFindings,
	currentRoute,
	pageSize = DEFAULT_PAGE_SIZE,
}: ProjectPotentialVulnerabilitiesSectionProps) {
	const statusMessage = getStatusMessage(status);
	const [tableState, setTableState] = useState<DataTableQueryState>(() => ({
		globalFilter: "",
		columnFilters: [],
		sorting: [],
		pagination: {
			pageIndex: 0,
			pageSize: Math.max(1, pageSize),
		},
		columnVisibility: {},
		columnSizing: {},
		rowSelection: {},
		density: "comfortable",
	}));
	const handleSearchChange = useCallback((value: string) => {
		setTableState((previous) => ({
			...previous,
			globalFilter: value,
			pagination: {
				...previous.pagination,
				pageIndex: 0,
			},
		}));
	}, []);
	useEffect(() => {
		const nextPageSize = Math.max(1, pageSize);
		setTableState((previous) => {
			if (previous.pagination.pageSize === nextPageSize) return previous;
			return {
				...previous,
				pagination: {
					...previous.pagination,
					pageIndex: 0,
					pageSize: nextPageSize,
				},
			};
		});
	}, [pageSize]);
	const columns = useMemo<ColumnDef<ProjectDetailPotentialListItem>[]>(
		() =>
			[
				{
					id: "sequence",
					header: "序号",
					enableSorting: false,
					meta: {
						label: "序号",
						plainHeader: true,
						headerClassName: "w-[6%] border-r border-border/50 text-center",
						cellClassName:
							"border-r border-border/30 text-center text-sm text-muted-foreground whitespace-nowrap",
					},
					cell: ({ row, table }) => {
						const pageRowIndex = table
							.getRowModel()
							.rows.findIndex((candidateRow) => candidateRow.id === row.id);
						const pagination = table.getState().pagination;
						return (
							pagination.pageIndex * pagination.pageSize + pageRowIndex + 1
						);
					},
				},
				{
					id: "findingTitle",
					accessorFn: (row) => `${row.id} ${row.title} ${row.cweLabel}`,
					header: "漏洞",
					meta: {
						label: "漏洞",
						plainHeader: true,
						headerClassName: "w-[48%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-left",
					},
					cell: ({ row }) => (
						<div
							className="space-y-1 text-left"
							title={row.original.cweTooltip || undefined}
						>
							<div className="text-sm font-semibold text-foreground">
								{row.original.cweLabel}
							</div>
						</div>
					),
				},
				{
					id: "taskCategory",
					accessorFn: (row) =>
						`${row.taskCategory} ${row.taskLabel} ${row.taskId} ${row.taskName}`,
					header: "任务",
					meta: {
						label: "任务",
						plainHeader: true,
						headerClassName: "w-[14%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-center",
					},
					cell: ({ row }) => (
						<div className="flex flex-col items-center gap-2">
							<Badge
								className={getTaskCategoryBadgeClassName(
									row.original.taskCategory,
								)}
							>
								{row.original.taskLabel}
							</Badge>
						</div>
					),
				},
				{
					id: "severity",
					accessorFn: (row) => row.severity,
					header: "严重度",
					meta: {
						label: "严重度",
						plainHeader: true,
						headerClassName: "w-[10%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-center",
					},
					cell: ({ row }) => (
						<Badge className={getSeverityBadgeClassName(row.original.severity)}>
							{getSeverityText(row.original.severity)}
						</Badge>
					),
				},
				{
					id: "confidence",
					accessorFn: (row) => row.confidence,
					header: "置信度",
					meta: {
						label: "置信度",
						plainHeader: true,
						headerClassName: "w-[10%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-center",
					},
					cell: ({ row }) => (
						<Badge
							className={getConfidenceBadgeClassName(row.original.confidence)}
						>
							{getConfidenceText(row.original.confidence)}
						</Badge>
					),
				},
				{
					id: "actions",
					header: "操作",
					enableSorting: false,
					meta: {
						label: "操作",
						plainHeader: true,
						headerClassName: "w-[12%] text-center",
						cellClassName: "text-center",
					},
					cell: ({ row }) =>
						row.original.route ? (
							<Button
								asChild
								size="sm"
								variant="outline"
								className="cyber-btn-ghost h-7 px-3"
							>
								<Link to={appendReturnTo(row.original.route, currentRoute)}>
									详情
								</Link>
							</Button>
						) : (
							<Button
								size="sm"
								variant="outline"
								className="cyber-btn-ghost h-7 px-3"
								disabled
								title="误报不提供统一漏洞详情入口"
							>
								详情
							</Button>
						),
				},
			] satisfies AppColumnDef<ProjectDetailPotentialListItem, unknown>[],
		[currentRoute],
	);
	return (
		<section className="space-y-3">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div className="space-y-2">
					<div className="flex items-center gap-2">
						<Bug className="h-4 w-4 text-amber-400" />
						<h3 className="text-sm font-semibold uppercase tracking-wider">
							潜在漏洞
						</h3>
						<Badge className="cyber-badge-muted">{totalFindings}</Badge>
					</div>
				</div>
				{statusMessage ? null : (
					<Input
						value={tableState.globalFilter}
						onChange={(event) => handleSearchChange(event.target.value)}
						placeholder="搜索漏洞 ID、类型或任务"
						startIcon={<Search className="h-4 w-4" />}
						className="h-9 border-border/60 bg-muted/40 focus:bg-muted/40"
						wrapperClassName="w-full max-w-xs sm:w-80"
					/>
				)}
			</div>

			{statusMessage ? (
				<div className="rounded-sm border border-border/60 bg-slate-950/35 px-4 py-8 text-center text-sm text-muted-foreground">
					{status === "failed" ? (
						<div className="mb-2 flex justify-center">
							<AlertTriangle className="h-4 w-4 text-rose-300" />
						</div>
					) : null}
					{statusMessage}
				</div>
			) : (
				<div className="space-y-3">
					<DataTable
						data={findings}
						columns={columns}
						state={tableState}
						onStateChange={setTableState}
						emptyState={{
							title: "暂无潜在漏洞",
						}}
						toolbar={false}
						pagination={{
							enabled: true,
							pageSizeOptions: [10, 20, 50],
							infoLabel: ({ table }) => {
								const pageIndex = table.getState().pagination.pageIndex;
								const pageCount = Math.max(1, table.getPageCount());
								return `第 ${pageIndex + 1} / ${pageCount} 页`;
							},
						}}
						className="border-border/60 bg-slate-950/20"
						tableClassName="table-fixed"
					/>
				</div>
			)}
		</section>
	);
}

export default ProjectPotentialVulnerabilitiesSection;
