import {
	normalizeProjectCardLanguageStats,
	type ProjectCardLanguageStats,
} from "@/features/projects/services/projectCardPreview";
import { getAgentTasks } from "@/shared/api/agentTasks";
import { getBanditScanTasks } from "@/shared/api/bandit";
import { getGitleaksScanTasks } from "@/shared/api/gitleaks";
import { getPhpstanScanTasks } from "@/shared/api/phpstan";
import { getYasaScanTasks } from "@/shared/api/yasa";
import { getOpengrepScanTasks } from "@/shared/api/opengrep";
import { apiClient } from "@/shared/api/serverClient";
import { api } from "@/shared/api/database";
import { getZipFileInfo, uploadZipFile } from "@/shared/utils/zipStorage";
import type { CreateProjectForm, Project } from "@/shared/types";
import {
	AGENT_TASK_PAGE_LIMIT,
	BANDIT_TASK_PAGE_LIMIT,
	GITLEAKS_TASK_PAGE_LIMIT,
	OPENGREP_TASK_PAGE_LIMIT,
	PHPSTAN_TASK_PAGE_LIMIT,
	PROJECT_FETCH_BATCH_SIZE,
	TASK_POOL_MAX_TOTAL,
	YASA_TASK_PAGE_LIMIT,
} from "../constants";
import type { ProjectTaskPool } from "../types";
import type { ProjectsPageDataSource } from "./projectsPageDataSource";
import {
	createZipProjectWorkflow,
	updateProjectWorkflow,
} from "./projectsPageWorkflows";

type ApiSurface = Pick<
	typeof api,
	| "getProjects"
	| "getAuditTasks"
	| "createProject"
	| "createProjectWithZip"
	| "updateProject"
>;

function sortProjectsByCreatedAt(projects: Project[]) {
	return [...projects].sort((a, b) => {
		const aTs = new Date(a.created_at).getTime();
		const bTs = new Date(b.created_at).getTime();
		if (Number.isNaN(aTs) || Number.isNaN(bTs)) {
			return String(b.created_at).localeCompare(String(a.created_at));
		}
		return bTs - aTs;
	});
}

async function collectPagedItems<T>({
	fetchPage,
	pageLimit,
	maxTotal,
}: {
	fetchPage: (skip: number, limit: number) => Promise<T[]>;
	pageLimit: number;
	maxTotal: number;
}): Promise<T[]> {
	const items: T[] = [];
	let skip = 0;

	while (items.length < maxTotal) {
		const batch = await fetchPage(skip, pageLimit);
		if (!Array.isArray(batch) || batch.length === 0) {
			break;
		}
		items.push(...batch);
		if (batch.length < pageLimit) {
			break;
		}
		skip += batch.length;
	}

	return items.slice(0, maxTotal);
}

interface CreateApiProjectsPageDataSourceOptions {
	api?: ApiSurface;
	projectFetchBatchSize?: number;
	taskPoolMaxTotal?: number;
	agentTaskPageLimit?: number;
	opengrepTaskPageLimit?: number;
	gitleaksTaskPageLimit?: number;
	banditTaskPageLimit?: number;
	phpstanTaskPageLimit?: number;
	yasaTaskPageLimit?: number;
	getAgentTasks?: typeof getAgentTasks;
	getOpengrepScanTasks?: typeof getOpengrepScanTasks;
	getGitleaksScanTasks?: typeof getGitleaksScanTasks;
	getBanditScanTasks?: typeof getBanditScanTasks;
	getPhpstanScanTasks?: typeof getPhpstanScanTasks;
	getYasaScanTasks?: typeof getYasaScanTasks;
	getProjectInfo?: (projectId: string) => Promise<unknown>;
	getZipFileInfo?: typeof getZipFileInfo;
	uploadZipFile?: typeof uploadZipFile;
}

export function createApiProjectsPageDataSource(
	options: CreateApiProjectsPageDataSourceOptions = {},
): ProjectsPageDataSource {
	const apiSurface = options.api ?? api;
	const fetchBatchSize = options.projectFetchBatchSize ?? PROJECT_FETCH_BATCH_SIZE;
	const taskPoolMaxTotal = options.taskPoolMaxTotal ?? TASK_POOL_MAX_TOTAL;
	const agentTaskPageLimit = options.agentTaskPageLimit ?? AGENT_TASK_PAGE_LIMIT;
	const opengrepTaskPageLimit =
		options.opengrepTaskPageLimit ?? OPENGREP_TASK_PAGE_LIMIT;
	const gitleaksTaskPageLimit =
		options.gitleaksTaskPageLimit ?? GITLEAKS_TASK_PAGE_LIMIT;
	const banditTaskPageLimit =
		options.banditTaskPageLimit ?? BANDIT_TASK_PAGE_LIMIT;
	const phpstanTaskPageLimit =
		options.phpstanTaskPageLimit ?? PHPSTAN_TASK_PAGE_LIMIT;
	const yasaTaskPageLimit =
		options.yasaTaskPageLimit ?? YASA_TASK_PAGE_LIMIT;
	const fetchAgentTasks = options.getAgentTasks ?? getAgentTasks;
	const fetchOpengrepTasks = options.getOpengrepScanTasks ?? getOpengrepScanTasks;
	const fetchGitleaksTasks =
		options.getGitleaksScanTasks ?? getGitleaksScanTasks;
	const fetchBanditTasks = options.getBanditScanTasks ?? getBanditScanTasks;
	const fetchPhpstanTasks = options.getPhpstanScanTasks ?? getPhpstanScanTasks;
	const fetchYasaTasks = options.getYasaScanTasks ?? getYasaScanTasks;
	const fetchProjectInfo =
		options.getProjectInfo ??
		(async (projectId: string) => {
			const response = await apiClient.get(`/projects/info/${projectId}`);
			return response.data;
		});
	const fetchProjectZipInfo = options.getZipFileInfo ?? getZipFileInfo;
	const uploadProjectZip = options.uploadZipFile ?? uploadZipFile;

	return {
		async listProjects() {
			const mergedProjects: Project[] = [];
			let skip = 0;

			while (true) {
				const batch = await apiSurface.getProjects({
					skip,
					limit: fetchBatchSize,
					includeMetrics: true,
				});
				const normalizedBatch = Array.isArray(batch) ? batch : [];
				mergedProjects.push(...normalizedBatch);
				if (normalizedBatch.length < fetchBatchSize) {
					break;
				}
				skip += fetchBatchSize;
			}

			return sortProjectsByCreatedAt(mergedProjects);
		},

		async getProjectTaskPool(projectId) {
			const [
				auditResult,
				agentResult,
				opengrepResult,
				gitleaksResult,
				banditResult,
				phpstanResult,
				yasaResult,
			] =
				await Promise.allSettled([
					apiSurface.getAuditTasks(projectId),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchAgentTasks({
								project_id: projectId,
								skip,
								limit,
							}),
						pageLimit: agentTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchOpengrepTasks({
								projectId,
								skip,
								limit,
							}),
						pageLimit: opengrepTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchGitleaksTasks({
								projectId,
								skip,
								limit,
							}),
						pageLimit: gitleaksTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchBanditTasks({
								projectId,
								skip,
								limit,
							}),
						pageLimit: banditTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchPhpstanTasks({
								projectId,
								skip,
								limit,
							}),
						pageLimit: phpstanTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
					collectPagedItems({
						fetchPage: (skip, limit) =>
							fetchYasaTasks({
								projectId,
								skip,
								limit,
							}),
						pageLimit: yasaTaskPageLimit,
						maxTotal: taskPoolMaxTotal,
					}),
				]);

			const taskPool: ProjectTaskPool = {
				auditTasks:
					auditResult.status === "fulfilled" && Array.isArray(auditResult.value)
						? auditResult.value
						: [],
				agentTasks:
					agentResult.status === "fulfilled" && Array.isArray(agentResult.value)
						? agentResult.value
						: [],
				opengrepTasks:
					opengrepResult.status === "fulfilled" &&
					Array.isArray(opengrepResult.value)
						? opengrepResult.value
						: [],
				gitleaksTasks:
					gitleaksResult.status === "fulfilled" &&
					Array.isArray(gitleaksResult.value)
						? gitleaksResult.value
						: [],
				banditTasks:
					banditResult.status === "fulfilled" &&
					Array.isArray(banditResult.value)
						? banditResult.value
						: [],
				phpstanTasks:
					phpstanResult.status === "fulfilled" &&
					Array.isArray(phpstanResult.value)
						? phpstanResult.value
						: [],
				yasaTasks:
					yasaResult.status === "fulfilled" &&
					Array.isArray(yasaResult.value)
						? yasaResult.value
						: [],
			};

			return taskPool;
		},

		async getProjectLanguageStats(projectId): Promise<ProjectCardLanguageStats> {
			try {
				const payload = await fetchProjectInfo(projectId);
				return normalizeProjectCardLanguageStats(payload as never);
			} catch (error) {
				if (getErrorStatusCode(error) === 202) {
					return {
						status: "pending",
						total: 0,
						totalFiles: 0,
						slices: [],
					};
				}

				return {
					status: "failed",
					total: 0,
					totalFiles: 0,
					slices: [],
				};
			}
		},

		async getProjectZipMeta(projectId) {
			return fetchProjectZipInfo(projectId);
		},

		async createProject(input: CreateProjectForm) {
			return apiSurface.createProject(input);
		},

		async createZipProject(input: CreateProjectForm, file: File) {
			return createZipProjectWorkflow({
				input,
				file,
				createProjectWithZip: (nextInput, nextFile) =>
					apiSurface.createProjectWithZip(nextInput, nextFile),
			});
		},

		async updateProject(projectId, input, zipFile) {
			return updateProjectWorkflow({
				projectId,
				input,
				zipFile,
				updateProject: (nextProjectId, nextInput) =>
					apiSurface.updateProject(nextProjectId, nextInput),
				uploadZipFile: uploadProjectZip,
			});
		},
	};
}
