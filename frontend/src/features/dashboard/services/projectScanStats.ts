import { getAgentTasks, type AgentTask } from "@/shared/api/agentTasks";
import {
	getOpengrepScanTasks,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import { getProjectFoundIssuesBreakdown } from "@/features/projects/services/projectCardPreview";
import {
	resolveSourceModeFromTaskMeta,
} from "@/features/tasks/services/taskActivities";

const AGENT_TASK_PAGE_LIMIT = 100;
const STATIC_TASK_PAGE_LIMIT = 200;
const TASK_POOL_MAX_TOTAL = 1000;

export interface ProjectScanRunsChartItem {
	projectId: string;
	projectName: string;
	staticRuns: number;
	intelligentRuns: number;
	totalRuns: number;
}

export interface ProjectVulnsChartItem {
	projectId: string;
	projectName: string;
	staticVulns: number;
	intelligentVulns: number;
	totalVulns: number;
}

export interface TaskPoolsData {
	projects: Project[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
}

function isCompletedStatus(status: string | null | undefined): boolean {
	return String(status || "").trim().toLowerCase() === "completed";
}

async function fetchAgentTasksWithPagination(maxTotal: number): Promise<AgentTask[]> {
	const tasks: AgentTask[] = [];
	let skip = 0;
	while (tasks.length < maxTotal) {
		const batch = await getAgentTasks({
			skip,
			limit: AGENT_TASK_PAGE_LIMIT,
		});
		if (!Array.isArray(batch) || batch.length === 0) break;
		tasks.push(...batch);
		if (batch.length < AGENT_TASK_PAGE_LIMIT) break;
		skip += batch.length;
	}
	return tasks.slice(0, maxTotal);
}

async function fetchOpengrepTasksWithPagination(
	maxTotal: number,
): Promise<OpengrepScanTask[]> {
	const tasks: OpengrepScanTask[] = [];
	let skip = 0;
	while (tasks.length < maxTotal) {
		const batch = await getOpengrepScanTasks({
			skip,
			limit: STATIC_TASK_PAGE_LIMIT,
		});
		if (!Array.isArray(batch) || batch.length === 0) break;
		tasks.push(...batch);
		if (batch.length < STATIC_TASK_PAGE_LIMIT) break;
		skip += batch.length;
	}
	return tasks.slice(0, maxTotal);
}

export async function fetchTaskPoolsWithPagination(
	maxTotal = TASK_POOL_MAX_TOTAL,
): Promise<TaskPoolsData> {
	const [projects, agentTasks, opengrepTasks] =
		await Promise.all([
		api.getProjects(),
		fetchAgentTasksWithPagination(maxTotal),
		fetchOpengrepTasksWithPagination(maxTotal),
	]);

	return {
		projects: Array.isArray(projects) ? projects : [],
		agentTasks,
		opengrepTasks,
	};
}

export function buildProjectScanRunsChartData(params: {
	projects: Project[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
}): ProjectScanRunsChartItem[] {
	const { projects, agentTasks, opengrepTasks } = params;
	const projectNameMap = new Map(
		projects.map((project) => [project.id, project.name || "未知项目"]),
	);

	const aggregateMap = new Map<string, ProjectScanRunsChartItem>();
	const ensureItem = (projectId: string): ProjectScanRunsChartItem => {
		const existing = aggregateMap.get(projectId);
		if (existing) return existing;
		const created: ProjectScanRunsChartItem = {
			projectId,
			projectName: projectNameMap.get(projectId) || "未知项目",
			staticRuns: 0,
			intelligentRuns: 0,
			totalRuns: 0,
		};
		aggregateMap.set(projectId, created);
		return created;
	};

	for (const task of opengrepTasks) {
		if (!isCompletedStatus(task.status)) continue;
		const item = ensureItem(task.project_id);
		item.staticRuns += 1;
	}

	for (const task of agentTasks) {
		if (!isCompletedStatus(task.status)) continue;
		const item = ensureItem(task.project_id);
		resolveSourceModeFromTaskMeta("intelligent_audit", task.name, task.description);
		item.intelligentRuns += 1;
	}

	return Array.from(aggregateMap.values())
		.map((item) => ({
			...item,
			totalRuns: item.staticRuns + item.intelligentRuns,
		}))
		.filter((item) => item.totalRuns > 0)
		.sort((a, b) => {
			if (b.totalRuns !== a.totalRuns) return b.totalRuns - a.totalRuns;
			return a.projectName.localeCompare(b.projectName, "zh-CN");
		});
}

export function buildProjectVulnsChartData(params: {
	projects: Project[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
}): ProjectVulnsChartItem[] {
	const { projects, agentTasks, opengrepTasks } = params;
	const projectNameMap = new Map(
		projects.map((project) => [project.id, project.name || "未知项目"]),
	);
	const projectIdSet = new Set<string>();
	for (const task of opengrepTasks) {
		projectIdSet.add(task.project_id);
	}
	for (const task of agentTasks) {
		projectIdSet.add(task.project_id);
	}

	return Array.from(projectIdSet)
		.map((projectId) => {
			const issueBreakdown = getProjectFoundIssuesBreakdown({
				projectId,
				agentTasks,
				opengrepTasks,
			});
			return {
				projectId,
				projectName: projectNameMap.get(projectId) || "未知项目",
				staticVulns: issueBreakdown.staticIssues,
				intelligentVulns: issueBreakdown.intelligentIssues,
				totalVulns: issueBreakdown.totalIssues,
			};
		})
		.filter((item) => item.totalVulns > 0)
		.sort((a, b) => {
			if (b.totalVulns !== a.totalVulns) return b.totalVulns - a.totalVulns;
			return a.projectName.localeCompare(b.projectName, "zh-CN");
		});
}

export function toTopNByField<T extends object, K extends keyof T>(
	items: T[],
	field: K,
	limit = 10,
): T[] {
	return [...items]
		.sort(
			(a, b) =>
				Number((b[field] as string | number | null | undefined) || 0) -
				Number((a[field] as string | number | null | undefined) || 0),
		)
		.slice(0, limit);
}
