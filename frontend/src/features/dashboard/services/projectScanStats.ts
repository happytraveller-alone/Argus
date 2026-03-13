import { getAgentTasks, type AgentTask } from "@/shared/api/agentTasks";
import {
	getBanditScanTasks,
	type BanditScanTask,
} from "@/shared/api/bandit";
import {
	getGitleaksScanTasks,
	type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
	getOpengrepScanTasks,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api } from "@/shared/config/database";
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
	hybridRuns: number;
	totalRuns: number;
}

export interface ProjectVulnsChartItem {
	projectId: string;
	projectName: string;
	staticVulns: number;
	intelligentVulns: number;
	hybridVulns: number;
	totalVulns: number;
}

export interface TaskPoolsData {
	projects: Project[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
	gitleaksTasks: GitleaksScanTask[];
	banditTasks: BanditScanTask[];
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

async function fetchGitleaksTasksWithPagination(
	maxTotal: number,
): Promise<GitleaksScanTask[]> {
	const tasks: GitleaksScanTask[] = [];
	let skip = 0;
	while (tasks.length < maxTotal) {
		const batch = await getGitleaksScanTasks({
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

async function fetchBanditTasksWithPagination(
	maxTotal: number,
): Promise<BanditScanTask[]> {
	const tasks: BanditScanTask[] = [];
	let skip = 0;
	while (tasks.length < maxTotal) {
		const batch = await getBanditScanTasks({
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
	const [projects, agentTasks, opengrepTasks, gitleaksTasks, banditTasks] = await Promise.all([
		api.getProjects(),
		fetchAgentTasksWithPagination(maxTotal),
		fetchOpengrepTasksWithPagination(maxTotal),
		fetchGitleaksTasksWithPagination(maxTotal),
		fetchBanditTasksWithPagination(maxTotal),
	]);

	return {
		projects: Array.isArray(projects) ? projects : [],
		agentTasks,
		opengrepTasks,
		gitleaksTasks,
		banditTasks,
	};
}

export function buildProjectScanRunsChartData(params: {
	projects: Project[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
	gitleaksTasks?: GitleaksScanTask[];
	banditTasks?: BanditScanTask[];
}): ProjectScanRunsChartItem[] {
	const { projects, agentTasks, opengrepTasks } = params;
	const gitleaksTasks = params.gitleaksTasks || [];
	const banditTasks = params.banditTasks || [];
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
			hybridRuns: 0,
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
	for (const task of gitleaksTasks) {
		if (!isCompletedStatus(task.status)) continue;
		const item = ensureItem(task.project_id);
		item.staticRuns += 1;
	}
	for (const task of banditTasks) {
		if (!isCompletedStatus(task.status)) continue;
		const item = ensureItem(task.project_id);
		item.staticRuns += 1;
	}

	for (const task of agentTasks) {
		if (!isCompletedStatus(task.status)) continue;
		const item = ensureItem(task.project_id);
		const sourceMode = resolveSourceModeFromTaskMeta(
			"intelligent_audit",
			task.name,
			task.description,
		);
		if (sourceMode === "intelligent") {
			item.intelligentRuns += 1;
		} else {
			item.hybridRuns += 1;
		}
	}

	return Array.from(aggregateMap.values())
		.map((item) => ({
			...item,
			totalRuns: item.staticRuns + item.intelligentRuns + item.hybridRuns,
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
	gitleaksTasks?: GitleaksScanTask[];
	banditTasks?: BanditScanTask[];
}): ProjectVulnsChartItem[] {
	const { projects, agentTasks, opengrepTasks } = params;
	const gitleaksTasks = params.gitleaksTasks || [];
	const banditTasks = params.banditTasks || [];
	const projectNameMap = new Map(
		projects.map((project) => [project.id, project.name || "未知项目"]),
	);
	const projectIdSet = new Set<string>();
	for (const task of opengrepTasks) {
		projectIdSet.add(task.project_id);
	}
	for (const task of gitleaksTasks) {
		projectIdSet.add(task.project_id);
	}
	for (const task of banditTasks) {
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
				gitleaksTasks,
				banditTasks,
			});
			return {
				projectId,
				projectName: projectNameMap.get(projectId) || "未知项目",
				staticVulns: issueBreakdown.staticIssues,
				intelligentVulns: issueBreakdown.intelligentIssues,
				hybridVulns: issueBreakdown.hybridIssues,
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
