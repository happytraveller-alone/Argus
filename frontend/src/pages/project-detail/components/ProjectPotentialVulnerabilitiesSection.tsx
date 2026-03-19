import { AlertTriangle, Bug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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
	const [page, setPage] = useState(1);

	useEffect(() => {
		setPage(1);
	}, [findings.length, status, pageSize]);

	const statusMessage = useMemo(() => getStatusMessage(status), [status]);

	const totalPages = Math.max(
		1,
		Math.ceil(Math.max(totalFindings, findings.length) / Math.max(1, pageSize)),
	);
	const safePage = Math.min(page, totalPages);
	const pageSizeToUse = Math.max(1, pageSize);

	const pagedFindings = useMemo(() => {
		if (findings.length === 0) return [];
		const start = (safePage - 1) * pageSizeToUse;
		return findings.slice(start, start + pageSizeToUse);
	}, [findings, safePage, pageSizeToUse]);

	const handlePrev = () => {
		setPage((previous) => Math.max(1, previous - 1));
	};

	const handleNext = () => {
		setPage((previous) => Math.min(totalPages, previous + 1));
	};

	return (
		<section className="space-y-3">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="space-y-2">
					<div className="flex items-center gap-2">
						<Bug className="h-4 w-4 text-amber-400" />
						<h3 className="text-sm font-semibold uppercase tracking-wider">
							潜在漏洞
						</h3>
						<Badge className="cyber-badge-muted">{totalFindings}</Badge>
					</div>
					<p className="text-xs text-muted-foreground">
						仅显示中/高置信度且中危及以上漏洞
					</p>
				</div>
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
					<div className="rounded-sm border border-border/60 bg-slate-950/20">
						<Table className="table-fixed">
							<TableHeader>
								<TableRow className="border-b border-border/60">
									<TableHead className="w-[24%] border-r border-border/50 text-center">
										漏洞ID
									</TableHead>
									<TableHead className="w-[22%] border-r border-border/50 text-center">
										漏洞
									</TableHead>
									<TableHead className="w-[14%] border-r border-border/50 text-center">
										任务
									</TableHead>
									<TableHead className="w-[10%] border-r border-border/50 text-center">
										严重度
									</TableHead>
									<TableHead className="w-[10%] border-r border-border/50 text-center">
										置信度
									</TableHead>
									<TableHead className="w-[16%] text-center">操作</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{pagedFindings.length > 0 ? (
									pagedFindings.map((finding) => (
										<TableRow
											key={`${finding.taskId}:${finding.id}`}
											className="border-b border-border/40"
										>
											<TableCell className="border-r border-border/30 text-center text-sm text-foreground whitespace-nowrap">
												#{finding.id}
											</TableCell>
											<TableCell className="border-r border-border/30 text-left">
												<div
													className="space-y-1 text-left"
													title={finding.cweTooltip || undefined}
												>
													<div className="text-sm font-semibold text-foreground">
														{finding.cweLabel}
													</div>
												</div>
											</TableCell>
											<TableCell className="border-r border-border/30 text-center">
												<div className="flex flex-col items-center gap-2">
													<Badge className={getTaskCategoryBadgeClassName(finding.taskCategory)}>
														{finding.taskLabel}
													</Badge>
													{/* <div className="text-xs text-muted-foreground" title={finding.taskName || finding.taskId}>
														{finding.taskName || `#${finding.taskId}`}
													</div> */}
												</div>
											</TableCell>
											<TableCell className="border-r border-border/30 text-center">
												<Badge className={getSeverityBadgeClassName(finding.severity)}>
													{getSeverityText(finding.severity)}
												</Badge>
											</TableCell>
											<TableCell className="border-r border-border/30 text-center">
												<Badge className={getConfidenceBadgeClassName(finding.confidence)}>
													{getConfidenceText(finding.confidence)}
												</Badge>
											</TableCell>
											<TableCell className="text-center">
												<Button
													asChild
													size="sm"
													variant="outline"
													className="cyber-btn-ghost h-7 px-3"
												>
													<Link to={appendReturnTo(finding.route, currentRoute)}>详情</Link>
												</Button>
											</TableCell>
										</TableRow>
									))
								) : (
									<TableRow>
										<TableCell
											colSpan={6}
											className="py-10 text-center text-sm text-muted-foreground"
										>
											暂无潜在漏洞
										</TableCell>
									</TableRow>
								)}
							</TableBody>
						</Table>
					</div>
					<div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
						<span>
							第 {safePage} / {totalPages} 页
						</span>
						<div className="flex items-center gap-2">
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-ghost h-7 px-3"
								onClick={handlePrev}
								disabled={safePage === 1}
							>
								上一页
							</Button>
							<Button
								type="button"
								variant="outline"
								size="sm"
								className="cyber-btn-ghost h-7 px-3"
								onClick={handleNext}
								disabled={safePage >= totalPages}
							>
								下一页
							</Button>
						</div>
					</div>
				</div>
			)}
		</section>
	);
}

export default ProjectPotentialVulnerabilitiesSection;
