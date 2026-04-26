import { ArrowLeft, Bug } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	DataTable,
	type AppColumnDef,
	type DataTableQueryState,
} from "@/components/data-table";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { type AgentFinding, getAgentFindings } from "@/shared/api/agentTasks";
import {
	getOpengrepScanFindings,
	type OpengrepFinding,
} from "@/shared/api/opengrep";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import {
	appendReturnTo,
	buildFindingDetailPath,
} from "@/shared/utils/findingRoute";
import {
	normalizeTaskFindingConfidence,
	normalizeTaskFindingSeverity,
	sortTaskFindings,
	type TaskFindingCategory,
	type TaskFindingConfidence,
	type TaskFindingRow,
	type TaskFindingSeverity,
} from "./projectTaskFindingsDialog.utils";

const DIALOG_PAGE_SIZE = 10;
const FINDING_BATCH_SIZE = 200;
const MAX_FINDING_BATCHES = 50;

type LoadStatus = "idle" | "loading" | "ready" | "failed";

export interface ProjectTaskFindingsDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	taskId: string;
	taskCategory: TaskFindingCategory;
	projectName: string;
	returnTo: string;
	taskLabel: string;
}

function getSeverityText(severity: TaskFindingSeverity): string {
	if (severity === "CRITICAL") return "严重";
	if (severity === "HIGH") return "高危";
	if (severity === "MEDIUM") return "中危";
	if (severity === "LOW") return "低危";
	return "未知";
}

function getSeverityBadgeClassName(severity: TaskFindingSeverity): string {
	if (severity === "CRITICAL") return "cyber-badge-danger";
	if (severity === "HIGH") return "cyber-badge-warning";
	if (severity === "MEDIUM") return "cyber-badge-info";
	if (severity === "LOW") return "cyber-badge-muted";
	return "cyber-badge-muted";
}

function getConfidenceText(confidence: TaskFindingConfidence): string {
	if (confidence === "HIGH") return "高";
	if (confidence === "MEDIUM") return "中";
	if (confidence === "LOW") return "低";
	return "未知";
}

function getConfidenceBadgeClassName(
	confidence: TaskFindingConfidence,
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

function toPositiveLine(value: unknown): number | null {
	const line = Number(value);
	if (!Number.isFinite(line) || line <= 0) return null;
	return line;
}

function isFalsePositiveAgentFinding(finding: AgentFinding): boolean {
	return (
		String(finding.status || "")
			.trim()
			.toLowerCase() === "false_positive" ||
		String(finding.authenticity || "")
			.trim()
			.toLowerCase() === "false_positive"
	);
}

function resolveAgentFindingTitle(finding: AgentFinding): string {
	return (
		String(finding.display_title || "").trim() ||
		String(finding.title || "").trim() ||
		String(finding.vulnerability_type || "").trim() ||
		String(finding.description || "").trim() ||
		"未命名漏洞"
	);
}

function resolveStaticFindingTitle(finding: OpengrepFinding): string {
	const rule = (finding.rule || {}) as Record<string, unknown>;
	return (
		String(finding.rule_name || "").trim() ||
		String(rule.check_id || rule.id || "").trim() ||
		String(finding.description || "").trim() ||
		"未命名漏洞"
	);
}

function toProjectRelativePath(projectName: string, filePath: string): string {
	const normalizedPath = String(filePath || "")
		.trim()
		.replace(/\\/g, "/");
	if (!normalizedPath) return "-";

	const trimmed = normalizedPath.replace(/^\/+/, "");
	const normalizedProjectName = String(projectName || "")
		.trim()
		.replace(/\\/g, "/");
	if (!normalizedProjectName) return trimmed || "-";

	const pathLower = normalizedPath.toLowerCase();
	const projectLower = normalizedProjectName.toLowerCase();
	const marker = `/${projectLower}/`;
	const markerIndex = pathLower.lastIndexOf(marker);
	if (markerIndex >= 0) {
		const relative = normalizedPath.slice(markerIndex + marker.length);
		return relative || "-";
	}

	if (pathLower.startsWith(`${projectLower}/`)) {
		return normalizedPath.slice(normalizedProjectName.length + 1) || "-";
	}

	if (pathLower === projectLower) return "-";

	return trimmed || "-";
}

function toStaticRelativePath(projectName: string, filePath: string): string {
	const normalizedPath = String(filePath || "")
		.trim()
		.replace(/\\/g, "/");
	if (!normalizedPath) return "-";

	const trimmed = normalizedPath.replace(/^\/+/, "");
	if (!trimmed) return "-";

	const segments = trimmed.split("/").filter(Boolean);
	if (segments.length === 0) return "-";

	const normalizedProjectName = String(projectName || "")
		.trim()
		.replace(/\\/g, "/")
		.toLowerCase();
	if (normalizedProjectName) {
		const projectRootIndex = segments.findIndex((segment) => {
			const normalizedSegment = segment.toLowerCase();
			return (
				normalizedSegment === normalizedProjectName ||
				normalizedSegment.startsWith(`${normalizedProjectName}-`) ||
				normalizedSegment.startsWith(`${normalizedProjectName}_`) ||
				normalizedSegment.startsWith(`${normalizedProjectName}.`)
			);
		});

		if (projectRootIndex >= 0) {
			if (projectRootIndex >= segments.length - 1) return "-";
			return segments.slice(projectRootIndex + 1).join("/");
		}
	}

	const sourceRootSegments = new Set([
		"src",
		"include",
		"lib",
		"app",
		"apps",
		"test",
		"tests",
	]);
	const sourceRootIndex = segments.findIndex((segment) =>
		sourceRootSegments.has(segment.toLowerCase()),
	);
	if (sourceRootIndex >= 0) {
		return segments.slice(sourceRootIndex).join("/");
	}

	return trimmed || "-";
}

async function fetchAllStaticFindings(
	taskId: string,
): Promise<OpengrepFinding[]> {
	const findings: OpengrepFinding[] = [];
	for (let batchIndex = 0; batchIndex < MAX_FINDING_BATCHES; batchIndex += 1) {
		const page = await getOpengrepScanFindings({
			taskId,
			skip: batchIndex * FINDING_BATCH_SIZE,
			limit: FINDING_BATCH_SIZE,
		});
		findings.push(...page);
		if (page.length < FINDING_BATCH_SIZE) break;
	}
	return findings;
}

function normalizeAgentFindings(
	taskId: string,
	findings: AgentFinding[],
): TaskFindingRow[] {
	return findings.map((finding) => {
		const typeDisplay = resolveCweDisplay({
			cwe: finding.cwe_id,
			fallbackLabel:
				String(finding.vulnerability_type || "").trim() ||
				resolveAgentFindingTitle(finding),
		});

		return {
			id: finding.id,
			taskId,
			taskCategory: "intelligent",
			title: resolveAgentFindingTitle(finding),
			typeLabel: typeDisplay.label,
			typeTooltip: typeDisplay.tooltip,
			filePath: String(finding.file_path || "").trim() || "-",
			line: toPositiveLine(finding.line_start),
			severity: normalizeTaskFindingSeverity(finding.severity),
			confidence: normalizeTaskFindingConfidence(
				finding.ai_confidence ?? finding.confidence ?? null,
			),
			route: isFalsePositiveAgentFinding(finding)
				? null
				: buildFindingDetailPath({
						source: "agent",
						taskId,
						findingId: finding.id,
					}),
			createdAt: finding.created_at ?? null,
		};
	});
}

function normalizeStaticFindings(
	taskId: string,
	findings: OpengrepFinding[],
): TaskFindingRow[] {
	return findings.map((finding) => {
		const typeDisplay = resolveCweDisplay({
			cwe: finding.cwe,
			fallbackLabel:
				String(finding.rule_name || "").trim() ||
				resolveStaticFindingTitle(finding),
		});

		return {
			id: finding.id,
			taskId,
			taskCategory: "static",
			title: resolveStaticFindingTitle(finding),
			typeLabel: typeDisplay.label,
			typeTooltip: typeDisplay.tooltip,
			filePath: String(finding.file_path || "").trim() || "-",
			line: toPositiveLine(finding.start_line),
			severity: normalizeTaskFindingSeverity(finding.severity),
			confidence: normalizeTaskFindingConfidence(finding.confidence),
			route: buildFindingDetailPath({
				source: "static",
				taskId,
				findingId: finding.id,
				engine: "opengrep",
			}),
			createdAt: null,
		};
	});
}

export default function ProjectTaskFindingsDialog({
	open,
	onOpenChange,
	taskId,
	taskCategory,
	projectName,
	returnTo,
	taskLabel,
}: ProjectTaskFindingsDialogProps) {
	const [status, setStatus] = useState<LoadStatus>("idle");
	const [errorMessage, setErrorMessage] = useState("");
	const [allRows, setAllRows] = useState<TaskFindingRow[]>([]);
	const [tableState, setTableState] = useState<DataTableQueryState>({
		globalFilter: "",
		columnFilters: [],
		sorting: [],
		pagination: {
			pageIndex: 0,
			pageSize: DIALOG_PAGE_SIZE,
		},
		columnVisibility: {},
		columnSizing: {},
		rowSelection: {},
		density: "comfortable",
	});
	const cacheRef = useRef(new Map<string, TaskFindingRow[]>());
	const cacheKey = `${taskCategory}:${taskId}`;

	const formatLocation = useCallback(
		(filePath: string, line: number | null) => {
			const relativePath =
				taskCategory === "static"
					? toStaticRelativePath(projectName, filePath)
					: toProjectRelativePath(projectName, filePath);
			if (typeof line === "number" && Number.isFinite(line) && line > 0) {
				return `${relativePath}:${line}`;
			}
			return relativePath;
		},
		[projectName, taskCategory],
	);

	useEffect(() => {
		if (!open || !taskId) return;

		setErrorMessage("");
		setTableState({
			globalFilter: "",
			columnFilters: [],
			sorting: [],
			pagination: {
				pageIndex: 0,
				pageSize: DIALOG_PAGE_SIZE,
			},
			columnVisibility: {},
			columnSizing: {},
			rowSelection: {},
			density: "comfortable",
		});

		const cachedRows = cacheRef.current.get(cacheKey);
		if (cachedRows) {
			setAllRows(cachedRows);
			setStatus("ready");
			return;
		}

		let cancelled = false;

		const loadFindings = async () => {
			setStatus("loading");
			try {
				const nextRows =
					taskCategory === "static"
						? normalizeStaticFindings(
								taskId,
								await fetchAllStaticFindings(taskId),
							)
						: normalizeAgentFindings(
								taskId,
								await getAgentFindings(taskId, {
									include_false_positive: false,
								}),
							).map((item) => ({
								...item,
								taskCategory,
							}));

				const sortedRows = sortTaskFindings(nextRows);
				if (cancelled) return;

				cacheRef.current.set(cacheKey, sortedRows);
				setAllRows(sortedRows);
				setStatus("ready");
			} catch (error) {
				if (cancelled) return;
				console.error("Failed to load task findings:", error);
				setAllRows([]);
				setErrorMessage("加载漏洞失败");
				setStatus("failed");
			}
		};

		void loadFindings();

		return () => {
			cancelled = true;
		};
	}, [cacheKey, open, taskCategory, taskId]);

	const columns = useMemo<ColumnDef<TaskFindingRow>[]>(
		() =>
			[
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
					id: "typeLabel",
					accessorFn: (row) => row.typeLabel,
					header: "漏洞类型",
					meta: {
						label: "漏洞类型",
						minWidth: 280,
						filterVariant: "text",
					},
					cell: ({ row }) => (
						<div
							className="text-sm text-foreground break-words"
							title={row.original.typeTooltip || row.original.title}
						>
							{row.original.typeLabel}
						</div>
					),
				},
				{
					id: "location",
					accessorFn: (row) => formatLocation(row.filePath, row.line),
					header: "位置",
					meta: {
						label: "位置",
						minWidth: 260,
					},
					cell: ({ row }) => {
						const location = formatLocation(
							row.original.filePath,
							row.original.line,
						);
						return (
							<div
								className="text-xs text-muted-foreground break-all"
								title={location}
							>
								{location}
							</div>
						);
					},
				},
				{
					id: "severity",
					accessorFn: (row) => row.severity,
					header: "危害",
					meta: {
						label: "危害",
						align: "center",
						width: 120,
						filterVariant: "select",
						filterOptions: [
							{ label: "严重", value: "CRITICAL" },
							{ label: "高危", value: "HIGH" },
							{ label: "中危", value: "MEDIUM" },
							{ label: "低危", value: "LOW" },
							{ label: "未知", value: "UNKNOWN" },
						],
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
						align: "center",
						width: 110,
						filterVariant: "select",
						filterOptions: [
							{ label: "高", value: "HIGH" },
							{ label: "中", value: "MEDIUM" },
							{ label: "低", value: "LOW" },
							{ label: "未知", value: "UNKNOWN" },
						],
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
						align: "center",
						width: 120,
					},
					cell: ({ row }) =>
						row.original.route ? (
							<Button
								asChild
								size="sm"
								variant="outline"
								className="cyber-btn-ghost h-8 px-3"
							>
								<Link to={appendReturnTo(row.original.route, returnTo)}>
									详情
								</Link>
							</Button>
						) : (
							<Button
								size="sm"
								variant="outline"
								className="cyber-btn-ghost h-8 px-3"
								disabled
								title="误报不提供统一漏洞详情入口"
							>
								详情
							</Button>
						),
				},
			] satisfies AppColumnDef<TaskFindingRow, unknown>[],
		[formatLocation, returnTo],
	);

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent
				aria-describedby={undefined}
				showCloseButton={false}
				className="!w-[min(96vw,1200px)] !max-w-none max-h-[88vh] overflow-hidden flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
			>
				<DialogHeader className="px-6 py-4 border-b border-border flex-shrink-0">
					<div className="flex items-center justify-between gap-3">
						<div className="min-w-0 space-y-2 text-left">
							<DialogTitle className="flex items-center gap-2 text-base leading-none">
								<Bug className="h-4 w-4 shrink-0 text-amber-400" />
								<span className="truncate">{taskLabel}漏洞详情</span>
							</DialogTitle>

							<div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
								<span className="inline-flex items-center rounded-md border border-border/70 bg-muted/40 px-2.5 py-1">
									任务 ID：{taskId}
								</span>
								<span className="inline-flex items-center rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-200">
									漏洞共 {allRows.length.toLocaleString()} 条
								</span>
							</div>
						</div>
						<Button
							type="button"
							variant="outline"
							size="sm"
							className="cyber-btn-ghost h-8 px-3"
							onClick={() => onOpenChange(false)}
						>
							<ArrowLeft className="w-4 h-4" />
							返回
						</Button>
					</div>
				</DialogHeader>

				<div className="flex-1 min-h-0 overflow-hidden px-6 py-4 space-y-4">
					<div className="flex-1 min-h-0 overflow-hidden [&_[data-slot=table-container]]:overflow-auto">
						<DataTable
							key={`${cacheKey}:${open ? "open" : "closed"}`}
							data={allRows}
							columns={columns}
							state={tableState}
							onStateChange={setTableState}
							loading={status === "loading"}
							error={
								status === "failed" ? errorMessage || "加载漏洞失败" : undefined
							}
							emptyState={{
								title:
									allRows.length === 0
										? "暂无漏洞"
										: "暂无符合条件的漏洞",
							}}
							toolbar={{
								searchPlaceholder: "搜索漏洞类型或位置",
								showColumnVisibility: false,
								showDensityToggle: false,
							}}
							pagination={{
								enabled: true,
								pageSizeOptions: [10, 20, 50],
								infoLabel: ({ table, filteredCount }) => {
									const pageIndex = table.getState().pagination.pageIndex;
									const pageCount = Math.max(1, table.getPageCount());
									return `共 ${filteredCount.toLocaleString()} 条，第 ${pageIndex + 1} / ${pageCount} 页`;
								},
							}}
							className="border border-border rounded-md"
							tableClassName="min-w-[980px] table-fixed"
						/>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}
