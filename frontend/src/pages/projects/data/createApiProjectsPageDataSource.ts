import { api } from "@/shared/api/database";
import { uploadZipFile } from "@/shared/utils/zipStorage";
import type { CreateProjectForm, Project } from "@/shared/types";
import { PROJECT_FETCH_BATCH_SIZE } from "../constants";
import type { ProjectsPageDataSource } from "./projectsPageDataSource";
import {
	createZipProjectWorkflow,
	updateProjectWorkflow,
} from "./projectsPageWorkflows";

type ApiSurface = Pick<
	typeof api,
	| "getProjects"
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

interface CreateApiProjectsPageDataSourceOptions {
	api?: ApiSurface;
	projectFetchBatchSize?: number;
	uploadZipFile?: typeof uploadZipFile;
}

export function createApiProjectsPageDataSource(
	options: CreateApiProjectsPageDataSourceOptions = {},
): ProjectsPageDataSource {
	const apiSurface = options.api ?? api;
	const fetchBatchSize = options.projectFetchBatchSize ?? PROJECT_FETCH_BATCH_SIZE;
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
