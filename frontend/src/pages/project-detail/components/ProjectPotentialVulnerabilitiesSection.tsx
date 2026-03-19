import {
	AlertTriangle,
	Bug,
	ChevronRight,
	FileCode2,
	Folder,
	Radar,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
	ProjectDetailPotentialDirectoryNode,
	ProjectDetailPotentialFileNode,
	ProjectDetailPotentialFindingNode,
	ProjectDetailPotentialTaskNode,
} from "@/pages/project-detail/potentialVulnerabilities";
import { appendReturnTo } from "@/shared/utils/findingRoute";

type PotentialStatus = "loading" | "ready" | "empty" | "failed";

interface ProjectPotentialVulnerabilitiesSectionProps {
	status: PotentialStatus;
	tree: ProjectDetailPotentialTaskNode[];
	totalFindings: number;
	currentRoute: string;
	initialExpandedKeys?: string[];
	formatDate?: (value: string) => string;
}

function getStatusMessage(status: PotentialStatus): string | null {
	if (status === "loading") return "加载中...";
	if (status === "failed") return "加载失败";
	if (status === "empty") return "暂无潜在漏洞";
	return null;
}

function getSeverityBadgeClassName(
	severity: ProjectDetailPotentialFindingNode["severity"],
): string {
	if (severity === "CRITICAL") return "cyber-badge-danger";
	if (severity === "HIGH") return "cyber-badge-warning";
	if (severity === "MEDIUM") return "cyber-badge-info";
	return "cyber-badge-muted";
}

function getSeverityText(
	severity: ProjectDetailPotentialFindingNode["severity"],
): string {
	if (severity === "CRITICAL") return "严重";
	if (severity === "HIGH") return "高危";
	if (severity === "MEDIUM") return "中危";
	if (severity === "LOW") return "低危";
	return "未知";
}

function getConfidenceBadgeClassName(
	confidence: ProjectDetailPotentialFindingNode["confidence"],
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
	confidence: ProjectDetailPotentialFindingNode["confidence"],
): string {
	if (confidence === "HIGH") return "高";
	if (confidence === "MEDIUM") return "中";
	if (confidence === "LOW") return "低";
	return "-";
}

function getTaskCategoryBadgeClassName(
	category: ProjectDetailPotentialTaskNode["taskCategory"],
): string {
	if (category === "static") {
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	}
	if (category === "intelligent") {
		return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
	}
	return "bg-amber-500/20 text-amber-300 border-amber-500/30";
}

function BranchContainer(props: {
	depth: number;
	children: React.ReactNode;
}) {
	return (
		<div
			className="space-y-2"
			style={{ paddingLeft: props.depth > 0 ? props.depth * 14 : 0 }}
		>
			{props.children}
		</div>
	);
}

function FindingLeaf(props: {
	node: ProjectDetailPotentialFindingNode;
	currentRoute: string;
}) {
	return (
		<div className="rounded-sm border border-border/60 bg-slate-950/40 px-3 py-3">
			<div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
				<div className="min-w-0 space-y-2">
					<div
						className="text-sm font-semibold text-foreground"
						title={[props.node.cweLabel, props.node.cweTooltip, props.node.title]
							.filter(Boolean)
							.join("\n")}
					>
						{props.node.title}
					</div>
					<div className="text-xs text-muted-foreground">
						{props.node.cweLabel}
					</div>
					<div className="text-xs text-slate-300/85">{props.node.location}</div>
				</div>
				<div className="flex flex-wrap items-center gap-2">
					<Badge className={getSeverityBadgeClassName(props.node.severity)}>
						{getSeverityText(props.node.severity)}
					</Badge>
					<Badge className={getConfidenceBadgeClassName(props.node.confidence)}>
						{getConfidenceText(props.node.confidence)}
					</Badge>
					<Button
						asChild
						size="sm"
						variant="outline"
						className="cyber-btn-ghost h-7 px-3"
					>
						<Link to={appendReturnTo(props.node.route, props.currentRoute)}>
							详情
						</Link>
					</Button>
				</div>
			</div>
		</div>
	);
}

function NodeBranch(props: {
	node:
		| ProjectDetailPotentialTaskNode
		| ProjectDetailPotentialDirectoryNode
		| ProjectDetailPotentialFileNode;
	depth: number;
	expandedKeys: Set<string>;
	onToggle: (nodeKey: string) => void;
	currentRoute: string;
	formatDate: (value: string) => string;
}) {
	const isOpen = props.expandedKeys.has(props.node.nodeKey);
	const isTask = props.node.type === "task";
	const isDirectory = props.node.type === "directory";
	const icon = isTask ? (
		<Radar className="h-4 w-4 text-sky-300" />
	) : isDirectory ? (
		<Folder className="h-4 w-4 text-amber-300" />
	) : (
		<FileCode2 className="h-4 w-4 text-emerald-300" />
	);

	return (
		<BranchContainer depth={props.depth}>
			<div className="rounded-sm border border-border/60 bg-slate-950/35">
				<button
					type="button"
					className="flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-slate-900/50"
					onClick={() => props.onToggle(props.node.nodeKey)}
				>
					<ChevronRight
						className={`h-4 w-4 text-muted-foreground transition-transform ${
							isOpen ? "rotate-90" : ""
						}`}
					/>
					{icon}
					<div className="min-w-0 flex-1">
						<div className="flex flex-wrap items-center gap-2">
							<span className="text-sm font-semibold text-foreground">
								{isTask ? props.node.taskLabel : props.node.name}
							</span>
							{isTask ? (
								<Badge
									className={getTaskCategoryBadgeClassName(props.node.taskCategory)}
								>
									{props.node.taskLabel}
								</Badge>
							) : null}
							<Badge className="cyber-badge-muted">{props.node.count}</Badge>
						</div>
						{isTask ? (
							<div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
								{props.node.taskName ? <span>{props.node.taskName}</span> : null}
								<span>{props.formatDate(props.node.createdAt)}</span>
							</div>
						) : (
							<div className="mt-1 text-xs text-muted-foreground">
								{props.node.path}
							</div>
						)}
					</div>
				</button>
				{isOpen ? (
					<div className="space-y-2 border-t border-border/50 px-3 py-3">
						{props.node.children.map((child) =>
							child.type === "finding" ? (
								<FindingLeaf
									key={child.nodeKey}
									node={child}
									currentRoute={props.currentRoute}
								/>
							) : (
								<NodeBranch
									key={child.nodeKey}
									node={child}
									depth={props.depth + 1}
									expandedKeys={props.expandedKeys}
									onToggle={props.onToggle}
									currentRoute={props.currentRoute}
									formatDate={props.formatDate}
								/>
							),
						)}
					</div>
				) : null}
			</div>
		</BranchContainer>
	);
}

export function ProjectPotentialVulnerabilitiesSection({
	status,
	tree,
	totalFindings,
	currentRoute,
	initialExpandedKeys = [],
	formatDate = (value) =>
		new Date(value).toLocaleDateString("zh-CN", {
			year: "numeric",
			month: "short",
			day: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		}),
}: ProjectPotentialVulnerabilitiesSectionProps) {
	const [expandedKeys, setExpandedKeys] = useState<Set<string>>(
		() => new Set(initialExpandedKeys),
	);

	useEffect(() => {
		setExpandedKeys(new Set(initialExpandedKeys));
	}, [initialExpandedKeys]);

	const statusMessage = useMemo(() => getStatusMessage(status), [status]);

	const toggleNode = (nodeKey: string) => {
		setExpandedKeys((previous) => {
			const next = new Set(previous);
			if (next.has(nodeKey)) {
				next.delete(nodeKey);
			} else {
				next.add(nodeKey);
			}
			return next;
		});
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
					<p className="text-xs leading-5 text-muted-foreground">
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
				<div className="space-y-2">
					{tree.map((task) => (
						<NodeBranch
							key={task.nodeKey}
							node={task}
							depth={0}
							expandedKeys={expandedKeys}
							onToggle={toggleNode}
							currentRoute={currentRoute}
							formatDate={formatDate}
						/>
					))}
				</div>
			)}
		</section>
	);
}

export default ProjectPotentialVulnerabilitiesSection;
