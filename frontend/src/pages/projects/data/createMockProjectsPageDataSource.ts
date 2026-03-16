import type { CreateProjectForm, Project } from "@/shared/types";
import type { ProjectsPageDataSource } from "./projectsPageDataSource";
import type { ProjectTaskPool } from "../types";

const DELAY_MS = 25;

function wait(ms = DELAY_MS) {
	return new Promise((resolve) => {
		setTimeout(resolve, ms);
	});
}

function createMockProject(overrides: Partial<Project> = {}): Project {
	const timestamp = overrides.created_at || new Date().toISOString();
	return {
		id: overrides.id || crypto.randomUUID(),
		name: overrides.name || "Mock Project",
		description: overrides.description || "Mock project for page development",
		source_type: overrides.source_type || "repository",
		repository_url: overrides.repository_url || "https://example.com/mock.git",
		repository_type: overrides.repository_type || "github",
		default_branch: overrides.default_branch || "main",
		programming_languages:
			typeof overrides.programming_languages === "string"
				? overrides.programming_languages
				: "TypeScript,Python",
		owner_id: overrides.owner_id || "mock-user",
		is_active: overrides.is_active ?? true,
		created_at: timestamp,
		updated_at: overrides.updated_at || timestamp,
	};
}

export function createMockProjectsPageDataSource(): ProjectsPageDataSource {
	const projects = [
		createMockProject({
			id: "mock-project-1",
			name: "Mock Gateway",
			description: "Primary mock API gateway",
			created_at: "2026-03-10T09:00:00.000Z",
		}),
		createMockProject({
			id: "mock-project-2",
			name: "Disabled Legacy Worker",
			description: "Legacy worker kept for regression verification",
			source_type: "zip",
			repository_url: undefined,
			repository_type: "other",
			is_active: false,
			created_at: "2026-03-09T09:00:00.000Z",
		}),
	];

	const taskPools = new Map<string, ProjectTaskPool>([
		[
			"mock-project-1",
			{
				auditTasks: [
					{
						id: "audit-1",
						project_id: "mock-project-1",
						task_type: "repository",
						status: "completed",
						exclude_patterns: "",
						scan_config: "",
						total_files: 20,
						scanned_files: 20,
						total_lines: 1000,
						issues_count: 3,
						quality_score: 88,
						created_by: "mock-user",
						created_at: "2026-03-10T10:00:00.000Z",
					},
				],
				agentTasks: [],
				opengrepTasks: [],
				gitleaksTasks: [],
				banditTasks: [],
				phpstanTasks: [],
			},
		],
		[
			"mock-project-2",
			{
				auditTasks: [],
				agentTasks: [],
				opengrepTasks: [],
				gitleaksTasks: [],
				banditTasks: [],
				phpstanTasks: [],
			},
		],
	]);

	const languageRequestCount = new Map<string, number>();

	function getProjectIndex(projectId: string) {
		return projects.findIndex((project) => project.id === projectId);
	}

	return {
		async listProjects() {
			await wait();
			return [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at));
		},

		async getProjectTaskPool(projectId) {
			await wait();
			return (
				taskPools.get(projectId) || {
					auditTasks: [],
					agentTasks: [],
					opengrepTasks: [],
					gitleaksTasks: [],
					banditTasks: [],
					phpstanTasks: [],
				}
			);
		},

		async getProjectLanguageStats(projectId) {
			await wait();
			const requestCount = (languageRequestCount.get(projectId) || 0) + 1;
			languageRequestCount.set(projectId, requestCount);
			if (requestCount === 1) {
				return {
					status: "pending" as const,
					total: 0,
					totalFiles: 0,
					slices: [],
				};
			}
			return {
				status: "ready" as const,
				total: 2000,
				totalFiles: 48,
				slices: [
					{ name: "TypeScript", proportion: 0.7, loc: 1400, files: 30 },
					{ name: "Python", proportion: 0.3, loc: 600, files: 18 },
				],
			};
		},

		async createProject(input: CreateProjectForm) {
			await wait();
			const created = createMockProject({
				id: crypto.randomUUID(),
				name: input.name,
				description: input.description,
				source_type: input.source_type || "repository",
				repository_url: input.repository_url,
				repository_type: input.repository_type || "github",
				default_branch: input.default_branch || "main",
				programming_languages: input.programming_languages.join(","),
				created_at: new Date().toISOString(),
			});
			projects.unshift(created);
			taskPools.set(created.id, {
				auditTasks: [],
				agentTasks: [],
				opengrepTasks: [],
				gitleaksTasks: [],
				banditTasks: [],
				phpstanTasks: [],
			});
			return created;
		},

		async createZipProject(input: CreateProjectForm) {
			return this.createProject({
				...input,
				source_type: "zip",
				repository_type: "other",
				repository_url: undefined,
			});
		},

		async updateProject(projectId, input) {
			await wait();
			const projectIndex = getProjectIndex(projectId);
			if (projectIndex < 0) {
				throw new Error("项目不存在");
			}
			const previous = projects[projectIndex];
			const updated = {
				...previous,
				...input,
				programming_languages: Array.isArray(input.programming_languages)
					? input.programming_languages.join(",")
					: previous.programming_languages,
				updated_at: new Date().toISOString(),
			};
			projects.splice(projectIndex, 1, updated);
			return updated;
		},

		async disableProject(projectId) {
			await wait();
			const projectIndex = getProjectIndex(projectId);
			if (projectIndex >= 0) {
				projects[projectIndex] = {
					...projects[projectIndex],
					is_active: false,
				};
			}
		},

		async enableProject(projectId) {
			await wait();
			const projectIndex = getProjectIndex(projectId);
			if (projectIndex >= 0) {
				projects[projectIndex] = {
					...projects[projectIndex],
					is_active: true,
				};
			}
		},
	};
}
