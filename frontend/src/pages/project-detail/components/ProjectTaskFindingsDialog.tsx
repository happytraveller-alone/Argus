import { AlertTriangle, ArrowLeft, Bug, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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
	filterTaskFindings,
	normalizeTaskFindingConfidence,
	normalizeTaskFindingSeverity,
	paginateTaskFindings,
	sortTaskFindings,
	type TaskFindingCategory,
	type TaskFindingConfidence,
	type TaskFindingConfidenceFilter,
	type TaskFindingRow,
	type TaskFindingSeverity,
	type TaskFindingSeverityFilter,
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
			route: buildFindingDetailPath({
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
	const [severityFilter, setSeverityFilter] =
		useState<TaskFindingSeverityFilter>("ALL");
	const [confidenceFilter, setConfidenceFilter] =
		useState<TaskFindingConfidenceFilter>("ALL");
	const [page, setPage] = useState(1);
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

		setSeverityFilter("ALL");
		setConfidenceFilter("ALL");
		setPage(1);
		setErrorMessage("");

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
								await getAgentFindings(taskId),
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

	const filteredRows = useMemo(
		() => filterTaskFindings(allRows, severityFilter, confidenceFilter),
		[allRows, confidenceFilter, severityFilter],
	);

	const pagination = useMemo(
		() => paginateTaskFindings(filteredRows, page, DIALOG_PAGE_SIZE),
		[filteredRows, page],
	);

	const paginationPage =
		filteredRows.length === 0 ? 1 : Math.min(page, pagination.totalPages);

	const renderBody = () => {
		if (status === "loading") {
			return (
				<TableRow>
					<TableCell colSpan={6} className="py-12 text-center">
						<div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
							<Loader2 className="h-4 w-4 animate-spin" />
							加载漏洞中...
						</div>
					</TableCell>
				</TableRow>
			);
		}

		if (status === "failed") {
			return (
				<TableRow>
					<TableCell colSpan={6} className="py-12 text-center">
						<div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
							<AlertTriangle className="h-4 w-4 text-rose-400" />
							{errorMessage || "加载漏洞失败"}
						</div>
					</TableCell>
				</TableRow>
			);
		}

		if (allRows.length === 0) {
			return (
				<TableRow>
					<TableCell
						colSpan={6}
						className="py-12 text-center text-sm text-muted-foreground"
					>
						暂无漏洞
					</TableCell>
				</TableRow>
			);
		}

		if (filteredRows.length === 0) {
			return (
				<TableRow>
					<TableCell
						colSpan={6}
						className="py-12 text-center text-sm text-muted-foreground"
					>
						暂无符合条件的漏洞
					</TableCell>
				</TableRow>
			);
		}

		return pagination.items.map((item, index) => {
			const order = pagination.startIndex + index + 1;
			const location = formatLocation(item.filePath, item.line);
			return (
				<TableRow key={item.id}>
					<TableCell className="w-[72px] text-sm text-muted-foreground">
						{order}
					</TableCell>
					<TableCell
						className="min-w-[280px] text-sm text-foreground break-words"
						title={item.typeTooltip || item.title}
					>
						{item.typeLabel}
					</TableCell>
					<TableCell
						className="min-w-[260px] text-xs text-muted-foreground break-all"
						title={location}
					>
						{location}
					</TableCell>
					<TableCell className="w-[120px] whitespace-nowrap text-center">
						<Badge className={getSeverityBadgeClassName(item.severity)}>
							{getSeverityText(item.severity)}
						</Badge>
					</TableCell>
					<TableCell className="w-[110px] whitespace-nowrap text-center">
						<Badge className={getConfidenceBadgeClassName(item.confidence)}>
							{getConfidenceText(item.confidence)}
						</Badge>
					</TableCell>
					<TableCell className="w-[120px] whitespace-nowrap text-center">
						<Button
							asChild
							size="sm"
							variant="outline"
							className="cyber-btn-ghost h-8 px-3"
						>
							<Link to={appendReturnTo(item.route, returnTo)}>详情</Link>
						</Button>
					</TableCell>
				</TableRow>
			);
		});
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent
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
						      漏洞共 {filteredRows.length.toLocaleString()} 条
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
					<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
						<div>
							<p className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
								危害
							</p>
							<Select
								value={severityFilter}
								onValueChange={(value) => {
									setSeverityFilter(value as TaskFindingSeverityFilter);
									setPage(1);
								}}
							>
								<SelectTrigger className="h-9 text-sm">
									<SelectValue />
								</SelectTrigger>
								<SelectContent className="cyber-dialog border-border">
									<SelectItem value="ALL">全部</SelectItem>
									<SelectItem value="CRITICAL">严重</SelectItem>
									<SelectItem value="HIGH">高危</SelectItem>
									<SelectItem value="MEDIUM">中危</SelectItem>
									<SelectItem value="LOW">低危</SelectItem>
									<SelectItem value="UNKNOWN">未知</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div>
							<p className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
								置信度
							</p>
							<Select
								value={confidenceFilter}
								onValueChange={(value) => {
									setConfidenceFilter(value as TaskFindingConfidenceFilter);
									setPage(1);
								}}
							>
								<SelectTrigger className="h-9 text-sm">
									<SelectValue />
								</SelectTrigger>
								<SelectContent className="cyber-dialog border-border">
									<SelectItem value="ALL">全部</SelectItem>
									<SelectItem value="HIGH">高</SelectItem>
									<SelectItem value="MEDIUM">中</SelectItem>
									<SelectItem value="LOW">低</SelectItem>
									<SelectItem value="UNKNOWN">未知</SelectItem>
								</SelectContent>
							</Select>
						</div>
						
					</div>

					

					<div className="flex-1 min-h-0 border border-border rounded-md overflow-auto">
						<Table className="min-w-[980px] table-fixed">
							<TableHeader>
								<TableRow>
									<TableHead className="w-[72px]">序号</TableHead>
									<TableHead className="min-w-[280px]">漏洞类型</TableHead>
									<TableHead className="min-w-[260px]">位置</TableHead>
									<TableHead className="w-[120px] text-center">危害</TableHead>
									<TableHead className="w-[110px] text-center">
										置信度
									</TableHead>
									<TableHead className="w-[120px] text-center">操作</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>{renderBody()}</TableBody>
						</Table>
					</div>

					<div className="flex items-center justify-between gap-3 flex-wrap">
						<span className="text-xs text-muted-foreground">
							共 {filteredRows.length.toLocaleString()} 条
						</span>
						<div className="flex items-center gap-2">
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-ghost h-8 px-3"
								onClick={() => setPage((current) => Math.max(1, current - 1))}
								disabled={page <= 1 || filteredRows.length === 0}
							>
								上一页
							</Button>
							<span className="text-xs text-muted-foreground min-w-[90px] text-center">
								第 {paginationPage} / {pagination.totalPages} 页
							</span>
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-ghost h-8 px-3"
								onClick={() =>
									setPage((current) =>
										Math.min(pagination.totalPages, current + 1),
									)
								}
								disabled={
									page >= pagination.totalPages || filteredRows.length === 0
								}
							>
								下一页
							</Button>
						</div>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}
