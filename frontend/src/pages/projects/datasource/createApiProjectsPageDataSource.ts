import { getAgentTasks } from "@/shared/api/agentTasks";
import { getBanditScanTasks } from "@/shared/api/bandit";
import { apiClient } from "@/shared/api/serverClient";
import { getGitleaksScanTasks } from "@/shared/api/gitleaks";
import { getOpengrepScanTasks } from "@/shared/api/opengrep";
import { api } from "@/shared/config/database";
import { uploadZipFile } from "@/shared/utils/zipStorage";
import {
	normalizeProjectCardLanguageStats,
	type ProjectCardLanguageStats,
} from "@/features/projects/services/projectCardPreview";
import {
	AGENT_TASK_PAGE_LIMIT,
	BANDIT_TASK_PAGE_LIMIT,
	GITLEAKS_TASK_PAGE_LIMIT,
	OPENGREP_TASK_PAGE_LIMIT,
} from "../constants";
import type { ProjectsPageDataSource } from "./projectsPageDataSource";

async function getProjectLanguageStats(
	projectId: string,
): Promise<ProjectCardLanguageStats> {
	try {
		const response = await apiClient.get(`/projects/info/${projectId}`);
		return normalizeProjectCardLanguageStats(response.data);
	} catch {
		return {
			status: "failed",
			total: 0,
			totalFiles: 0,
			slices: [],
		};
	}
}

export function createApiProjectsPageDataSource(): ProjectsPageDataSource {
	return {
		async listProjects(params) {
			return api.getProjects({ includeDeleted: params?.includeDeleted });
		},

		async getProjectTaskPool(projectId) {
			const [auditTasks, agentTasks, opengrepTasks, gitleaksTasks, banditTasks] =
				await Promise.all([
					api.getAuditTasks(projectId),
					getAgentTasks({
						project_id: projectId,
						limit: AGENT_TASK_PAGE_LIMIT,
						skip: 0,
					}),
					getOpengrepScanTasks({
						projectId,
						limit: OPENGREP_TASK_PAGE_LIMIT,
						skip: 0,
					}),
					getGitleaksScanTasks({
						projectId,
						limit: GITLEAKS_TASK_PAGE_LIMIT,
						skip: 0,
					}),
					getBanditScanTasks({
						projectId,
						limit: BANDIT_TASK_PAGE_LIMIT,
						skip: 0,
					}),
				]);

			return {
				auditTasks,
				agentTasks,
				opengrepTasks,
				gitleaksTasks,
				banditTasks,
			};
		},

		getProjectLanguageStats,

		async createProject(input) {
			return api.createProject(input);
		},

		async createZipProject(input, file) {
			const createdProject = await api.createProject({
				...input,
				source_type: "zip",
				repository_type: "other",
				repository_url: undefined,
				default_branch: input.default_branch || "main",
			});
			const uploadResult = await uploadZipFile(createdProject.id, file);
			if (!uploadResult.success) {
				try {
					await api.deleteProject(createdProject.id);
				} catch {
					// ignore rollback failure
				}
				throw new Error(uploadResult.message || "压缩包上传失败");
			}
			return createdProject;
		},

		async updateProject(projectId, input, zipFile) {
			const updatedProject = await api.updateProject(projectId, input);
			if (zipFile) {
				const uploadResult = await uploadZipFile(projectId, zipFile);
				if (!uploadResult.success) {
					throw new Error(uploadResult.message || "压缩包上传失败");
				}
			}
			return updatedProject;
		},

		async disableProject(projectId) {
			await api.updateProject(projectId, { is_active: false } as any);
		},

		async enableProject(projectId) {
			await api.updateProject(projectId, { is_active: true } as any);
		},
	};
}

