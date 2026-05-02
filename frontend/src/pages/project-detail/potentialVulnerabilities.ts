import {
	type ProjectCardTaskFindingCategory,
	type ProjectCardVulnerabilityConfidence,
	type ProjectCardVulnerabilitySeverity,
} from "@/features/projects/services/projectCardPreview";
import type { AgentFinding, AgentTask } from "@/shared/api/agentTasks";
import type { OpengrepFinding, OpengrepScanTask } from "@/shared/api/opengrep";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import { buildFindingDetailPath } from "@/shared/utils/findingRoute";

export interface ProjectDetailPotentialFindingNode {
	type: "finding";
	nodeKey: string;
	id: string;
	title: string;
	cweLabel: string;
	cweTooltip?: string | null;
	severity: ProjectCardVulnerabilitySeverity;
	confidence: ProjectCardVulnerabilityConfidence;
	location: string;
	route: string | null;
	taskCategory: ProjectCardTaskFindingCategory;
	source: "static" | "agent";
	line: number | null;
}

export interface ProjectDetailPotentialFileNode {
	type: "file";
	nodeKey: string;
	name: string;
	path: string;
	count: number;
	children: ProjectDetailPotentialFindingNode[];
}

export interface ProjectDetailPotentialDirectoryNode {
	type: "directory";
	nodeKey: string;
	name: string;
	path: string;
	count: number;
	children: Array<
		ProjectDetailPotentialDirectoryNode | ProjectDetailPotentialFileNode
	>;
}

export interface ProjectDetailPotentialTaskNode {
	type: "task";
	nodeKey: string;
	taskId: string;
	taskCategory: ProjectCardTaskFindingCategory;
	taskLabel: string;
	taskName: string;
	createdAt: string;
	count: number;
	children: Array<
		ProjectDetailPotentialDirectoryNode | ProjectDetailPotentialFileNode
	>;
}

export interface ProjectDetailPotentialTree {
	totalFindings: number;
	tasks: ProjectDetailPotentialTaskNode[];
}

export interface ProjectDetailPotentialListItem {
	id: string;
	title: string;
	cweLabel: string;
	cweTooltip?: string | null;
	severity: ProjectCardVulnerabilitySeverity;
	confidence: ProjectCardVulnerabilityConfidence;
	taskId: string;
	taskCategory: ProjectCardTaskFindingCategory;
	taskLabel: string;
	taskName: string;
	taskCreatedAt: string;
	route: string | null;
	source: "static" | "agent";
}

type MutableDirectoryNode = {
	type: "directory";
	nodeKey: string;
	name: string;
	path: string;
	count: number;
	children: Array<MutableDirectoryNode | MutableFileNode>;
};

type MutableFileNode = {
	type: "file";
	nodeKey: string;
	name: string;
	path: string;
	count: number;
	children: ProjectDetailPotentialFindingNode[];
};

type CandidateFinding = ProjectDetailPotentialFindingNode & {
	taskId: string;
	taskCreatedAt: string;
	taskName: string;
	relativePath: string;
};

const SOURCE_ROOT_SEGMENTS = new Set([
	"src",
	"include",
	"lib",
	"app",
	"apps",
	"test",
	"tests",
]);

function normalizeTimestamp(value: string | null | undefined): number {
	const timestamp = new Date(String(value || "")).getTime();
	return Number.isFinite(timestamp) ? timestamp : 0;
}

function normalizeSeverity(
	severity: string | null | undefined,
): ProjectCardVulnerabilitySeverity {
	const normalized = String(severity || "").trim().toUpperCase();
	if (normalized.includes("CRITICAL")) return "CRITICAL";
	if (normalized.includes("HIGH") || normalized === "ERROR") return "HIGH";
	if (normalized.includes("MEDIUM") || normalized === "WARNING") return "MEDIUM";
	if (normalized.includes("LOW") || normalized === "INFO") return "LOW";
	return "UNKNOWN";
}

function normalizeStaticConfidence(
	confidence: string | null | undefined,
): ProjectCardVulnerabilityConfidence {
	const normalized = String(confidence || "").trim().toUpperCase();
	if (normalized === "HIGH") return "HIGH";
	if (normalized === "MEDIUM") return "MEDIUM";
	if (normalized === "LOW") return "LOW";
	return "UNKNOWN";
}

function normalizeAgentConfidence(
	value: number | null | undefined,
): ProjectCardVulnerabilityConfidence {
	if (typeof value !== "number" || !Number.isFinite(value)) return "UNKNOWN";
	if (value >= 0.8) return "HIGH";
	if (value >= 0.5) return "MEDIUM";
	if (value > 0) return "LOW";
	return "UNKNOWN";
}

function severityRank(severity: ProjectCardVulnerabilitySeverity): number {
	if (severity === "CRITICAL") return 4;
	if (severity === "HIGH") return 3;
	if (severity === "MEDIUM") return 2;
	if (severity === "LOW") return 1;
	return 0;
}

function confidenceRank(confidence: ProjectCardVulnerabilityConfidence): number {
	if (confidence === "HIGH") return 3;
	if (confidence === "MEDIUM") return 2;
	if (confidence === "LOW") return 1;
	return 0;
}

function isFalsePositiveAgentFinding(finding: AgentFinding): boolean {
	return (
		String(finding.status || "").trim().toLowerCase() === "false_positive" ||
		String(finding.authenticity || "").trim().toLowerCase() === "false_positive"
	);
}

function shouldIncludeFinding(params: {
	severity: ProjectCardVulnerabilitySeverity;
	confidence: ProjectCardVulnerabilityConfidence;
}): boolean {
	const severityAllowed =
		params.severity === "CRITICAL" ||
		params.severity === "HIGH" ||
		params.severity === "MEDIUM";
	const confidenceAllowed =
		params.confidence === "HIGH" || params.confidence === "MEDIUM";
	return severityAllowed && confidenceAllowed;
}

export function getProjectDetailPotentialTaskCategoryText(
	category: ProjectCardTaskFindingCategory,
): string {
	if (category === "static") return "静态审计";
	return "智能审计";
}

export function toProjectRelativePotentialPath(
	filePath: string,
	projectName: string,
): string {
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

export function toStaticRelativePotentialPath(
	filePath: string,
	projectName: string,
): string {
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

	const sourceRootIndex = segments.findIndex((segment) =>
		SOURCE_ROOT_SEGMENTS.has(segment.toLowerCase()),
	);
	if (sourceRootIndex >= 0) {
		return segments.slice(sourceRootIndex).join("/");
	}

	return trimmed || "-";
}

export function formatProjectDetailPotentialLocation(params: {
	filePath: string;
	line: number | null;
	projectName: string;
	source: "static" | "agent";
}): string {
	const relativePath =
		params.source === "static"
			? toStaticRelativePotentialPath(params.filePath, params.projectName)
			: toProjectRelativePotentialPath(params.filePath, params.projectName);
	if (
		typeof params.line === "number" &&
		Number.isFinite(params.line) &&
		params.line > 0
	) {
		return `${relativePath}:${params.line}`;
	}
	return relativePath;
}

function sortFindings(
	left: ProjectDetailPotentialFindingNode,
	right: ProjectDetailPotentialFindingNode,
): number {
	const bySeverity = severityRank(right.severity) - severityRank(left.severity);
	if (bySeverity !== 0) return bySeverity;
	const byConfidence =
		confidenceRank(right.confidence) - confidenceRank(left.confidence);
	if (byConfidence !== 0) return byConfidence;
	const leftLine = left.line ?? Number.MAX_SAFE_INTEGER;
	const rightLine = right.line ?? Number.MAX_SAFE_INTEGER;
	if (leftLine !== rightLine) return leftLine - rightLine;
	return left.title.localeCompare(right.title, "zh-CN");
}

function sortTreeNodes(
	nodes: Array<MutableDirectoryNode | MutableFileNode>,
): Array<ProjectDetailPotentialDirectoryNode | ProjectDetailPotentialFileNode> {
	return [...nodes]
		.sort((left, right) => {
			if (left.type !== right.type) {
				return left.type === "directory" ? -1 : 1;
			}
			return left.name.localeCompare(right.name, "zh-CN");
		})
		.map((node) => {
			if (node.type === "directory") {
				return {
					type: "directory",
					nodeKey: node.nodeKey,
					name: node.name,
					path: node.path,
					count: node.count,
					children: sortTreeNodes(node.children),
				};
			}

			return {
				type: "file",
				nodeKey: node.nodeKey,
				name: node.name,
				path: node.path,
				count: node.count,
				children: [...node.children].sort(sortFindings),
			};
		});
}

function buildTaskNode(params: {
	taskId: string;
	taskCategory: ProjectCardTaskFindingCategory;
	taskName: string;
	createdAt: string;
	findings: CandidateFinding[];
}): ProjectDetailPotentialTaskNode {
	const rootNodes: Array<MutableDirectoryNode | MutableFileNode> = [];
	const directoryMap = new Map<string, MutableDirectoryNode>();
	const fileMap = new Map<string, MutableFileNode>();
	const taskKey = `task:${params.taskCategory}:${params.taskId}`;

	for (const finding of params.findings) {
		const relativePath = String(finding.relativePath || "").trim() || "-";
		const segments = relativePath.split("/").filter(Boolean);
		const fileName = segments.at(-1) || relativePath;
		const directorySegments = segments.slice(0, -1);

		let currentChildren = rootNodes;
		let currentPath = "";

		for (const segment of directorySegments) {
			currentPath = currentPath ? `${currentPath}/${segment}` : segment;
			let directoryNode = directoryMap.get(currentPath);
			if (!directoryNode) {
				directoryNode = {
					type: "directory",
					nodeKey: `${taskKey}:dir:${currentPath}`,
					name: segment,
					path: currentPath,
					count: 0,
					children: [],
				};
				directoryMap.set(currentPath, directoryNode);
				currentChildren.push(directoryNode);
			}
			directoryNode.count += 1;
			currentChildren = directoryNode.children;
		}

		const filePath = relativePath;
		let fileNode = fileMap.get(filePath);
		if (!fileNode) {
			fileNode = {
				type: "file",
				nodeKey: `${taskKey}:file:${filePath}`,
				name: fileName,
				path: filePath,
				count: 0,
				children: [],
			};
			fileMap.set(filePath, fileNode);
			currentChildren.push(fileNode);
		}
		fileNode.count += 1;
		fileNode.children.push(finding);
	}

	return {
		type: "task",
		nodeKey: taskKey,
		taskId: params.taskId,
		taskCategory: params.taskCategory,
		taskLabel: getProjectDetailPotentialTaskCategoryText(params.taskCategory),
		taskName: params.taskName,
		createdAt: params.createdAt,
		count: params.findings.length,
		children: sortTreeNodes(rootNodes),
	};
}

function collectFindingLeaves(
	nodes: Array<
		ProjectDetailPotentialDirectoryNode | ProjectDetailPotentialFileNode
	>,
): ProjectDetailPotentialFindingNode[] {
	const leaves: ProjectDetailPotentialFindingNode[] = [];
	for (const node of nodes) {
		if (node.type === "file" || node.type === "directory") {
			for (const child of node.children) {
				if (child.type === "finding") {
					leaves.push(child);
				} else {
					leaves.push(...collectFindingLeaves([child]));
				}
			}
		}
	}
	return leaves;
}

export function sortProjectDetailPotentialFindings(
	left: ProjectDetailPotentialListItem,
	right: ProjectDetailPotentialListItem,
): number {
	const bySeverity = severityRank(right.severity) - severityRank(left.severity);
	if (bySeverity !== 0) return bySeverity;
	const byConfidence =
		confidenceRank(right.confidence) - confidenceRank(left.confidence);
	if (byConfidence !== 0) return byConfidence;
	const byTaskTime =
		normalizeTimestamp(right.taskCreatedAt) -
		normalizeTimestamp(left.taskCreatedAt);
	if (byTaskTime !== 0) return byTaskTime;
	return left.title.localeCompare(right.title, "zh-CN");
}

export function flattenProjectDetailPotentialFindings(
	tree: ProjectDetailPotentialTree,
): ProjectDetailPotentialListItem[] {
	const items: ProjectDetailPotentialListItem[] = [];

	for (const task of tree.tasks) {
		const leaves = collectFindingLeaves(task.children);
		for (const leaf of leaves) {
			items.push({
				id: leaf.id,
				title: leaf.title,
				cweLabel: leaf.cweLabel,
				cweTooltip: leaf.cweTooltip,
				severity: leaf.severity,
				confidence: leaf.confidence,
				taskId: task.taskId,
				taskCategory: task.taskCategory,
				taskLabel: task.taskLabel,
				taskName: task.taskName,
				taskCreatedAt: task.createdAt,
				route: leaf.route,
				source: leaf.source,
			});
		}
	}

	return items.sort(sortProjectDetailPotentialFindings);
}

export function buildProjectDetailPotentialTree(params: {
	projectName: string;
	agentTasks?: AgentTask[];
	opengrepTasks?: OpengrepScanTask[];
	agentFindings?: AgentFinding[];
	opengrepFindings?: OpengrepFinding[];
}): ProjectDetailPotentialTree {
	const projectName = String(params.projectName || "");
	const taskInfo = new Map<
		string,
		{
			taskId: string;
			taskCategory: ProjectCardTaskFindingCategory;
			taskName: string;
			createdAt: string;
		}
	>();

	for (const task of params.agentTasks || []) {
		const taskCategory: ProjectCardTaskFindingCategory = "intelligent";
		taskInfo.set(task.id, {
			taskId: task.id,
			taskCategory,
			taskName: String(task.name || "").trim(),
			createdAt: task.created_at,
		});
	}

	for (const task of params.opengrepTasks || []) {
		taskInfo.set(task.id, {
			taskId: task.id,
			taskCategory: "static",
			taskName: String(task.name || "").trim(),
			createdAt: task.created_at,
		});
	}

	const candidateFindings: CandidateFinding[] = [];

	// Agent findings removed - only static findings remain

	for (const finding of params.opengrepFindings || []) {
		const severity = normalizeSeverity(finding.severity);
		const confidence = normalizeStaticConfidence(finding.confidence);
		if (!shouldIncludeFinding({ severity, confidence })) continue;

		const task = taskInfo.get(String(finding.scan_task_id || "").trim());
		if (!task) continue;

		const line =
			typeof finding.start_line === "number" && Number.isFinite(finding.start_line)
				? finding.start_line
				: null;
		const title =
			String(finding.rule_name || "").trim() ||
			String(finding.description || "").trim() ||
			"潜在漏洞";
		const filePath = String(finding.file_path || "").trim() || "-";
		const relativePath = toStaticRelativePotentialPath(filePath, projectName);
		const cweDisplay = resolveCweDisplay({
			cwe: finding.cwe,
			fallbackLabel: title,
		});

		candidateFindings.push({
			type: "finding",
			nodeKey: `task:${task.taskCategory}:${task.taskId}:finding:${finding.id}`,
			id: finding.id,
			title,
			cweLabel: cweDisplay.label,
			cweTooltip: cweDisplay.tooltip,
			severity,
			confidence,
			location: formatProjectDetailPotentialLocation({
				filePath,
				line,
				projectName,
				source: "static",
			}),
			route: buildFindingDetailPath({
				source: "static",
				taskId: task.taskId,
				findingId: finding.id,
				engine: "opengrep",
			}),
			taskCategory: "static",
			source: "static",
			line,
			taskId: task.taskId,
			taskCreatedAt: task.createdAt,
			taskName: task.taskName,
			relativePath,
		});
	}

	const findingsByTask = new Map<string, CandidateFinding[]>();
	for (const finding of candidateFindings) {
		const group = findingsByTask.get(finding.taskId) || [];
		group.push(finding);
		findingsByTask.set(finding.taskId, group);
	}

	const tasks = [...findingsByTask.entries()]
		.map(([taskId, findings]) => {
			const first = findings[0];
			if (!first) return null;
			return buildTaskNode({
				taskId,
				taskCategory: first.taskCategory,
				taskName: first.taskName,
				createdAt: first.taskCreatedAt,
				findings,
			});
		})
		.filter(
			(task): task is ProjectDetailPotentialTaskNode => Boolean(task),
		)
		.sort((left, right) => {
			const byTime =
				normalizeTimestamp(right.createdAt) - normalizeTimestamp(left.createdAt);
			if (byTime !== 0) return byTime;
			return right.count - left.count;
		});

	return {
		totalFindings: candidateFindings.length,
		tasks,
	};
}
