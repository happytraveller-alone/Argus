import type {
	CreateProjectForm,
	Project,
	ProjectManagementMetrics,
} from "@/shared/types";
import type { ProjectsPageDataSource } from "./projectsPageDataSource";

const DELAY_MS = 25;

function wait(ms = DELAY_MS) {
	return new Promise((resolve) => {
		setTimeout(resolve, ms);
	});
}

function createMockMetrics(
	overrides: Partial<ProjectManagementMetrics> = {},
): ProjectManagementMetrics {
	return {
		archive_size_bytes: overrides.archive_size_bytes ?? 2_621_440,
		archive_original_filename:
			overrides.archive_original_filename ?? "mock-project.zip",
		archive_uploaded_at:
			overrides.archive_uploaded_at ?? new Date().toISOString(),
		total_tasks: overrides.total_tasks ?? 9,
		completed_tasks: overrides.completed_tasks ?? 7,
		running_tasks: overrides.running_tasks ?? 1,
		agent_tasks: overrides.agent_tasks ?? 4,
		opengrep_tasks: overrides.opengrep_tasks ?? 2,
		gitleaks_tasks: overrides.gitleaks_tasks ?? 1,
		bandit_tasks: overrides.bandit_tasks ?? 1,
		phpstan_tasks: overrides.phpstan_tasks ?? 1,
		critical: overrides.critical ?? 2,
		high: overrides.high ?? 3,
		medium: overrides.medium ?? 5,
		low: overrides.low ?? 4,
		verified_critical: overrides.verified_critical ?? 1,
		verified_high: overrides.verified_high ?? 2,
		verified_medium: overrides.verified_medium ?? 1,
		verified_low: overrides.verified_low ?? 0,
		last_completed_task_at:
			overrides.last_completed_task_at ?? new Date().toISOString(),
		status: overrides.status ?? "ready",
		error_message: overrides.error_message ?? null,
		created_at: overrides.created_at ?? new Date().toISOString(),
		updated_at: overrides.updated_at ?? new Date().toISOString(),
	};
}

function createMockProject(overrides: Partial<Project> = {}): Project {
	const timestamp = overrides.created_at || new Date().toISOString();
	return {
		id: overrides.id || crypto.randomUUID(),
		name: overrides.name || "Mock Project",
		description: overrides.description || "Mock project for page development",
		source_type: overrides.source_type || "zip",
		repository_url: overrides.repository_url,
		repository_type: overrides.repository_type || "other",
		default_branch: overrides.default_branch || "main",
		programming_languages:
			typeof overrides.programming_languages === "string"
				? overrides.programming_languages
				: "TypeScript,Python",
		is_active: overrides.is_active ?? true,
		created_at: timestamp,
		updated_at: overrides.updated_at || timestamp,
		management_metrics:
			overrides.management_metrics || createMockMetrics(overrides.management_metrics ?? {}),
	};
}

export function createMockProjectsPageDataSource(
	initialProjects?: Project[],
): ProjectsPageDataSource {
	const projects =
		initialProjects && initialProjects.length > 0
			? [...initialProjects]
			: [
					createMockProject({
						id: "mock-project-1",
						name: "Mock Gateway",
						description: "Primary mock API gateway",
						created_at: "2026-03-10T09:00:00.000Z",
					}),
					createMockProject({
						id: "mock-project-2",
						name: "Mock Zip Worker",
						description: "Zip project kept for regression verification",
						source_type: "zip",
						repository_url: undefined,
						repository_type: "other",
						created_at: "2026-03-09T09:00:00.000Z",
					}),
			  ];

	function getProjectIndex(projectId: string) {
		return projects.findIndex((project) => project.id === projectId);
	}

	return {
		async listProjects() {
			await wait();
			return [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at));
		},

		async createProject(input: CreateProjectForm) {
			await wait();
			const created = createMockProject({
				id: crypto.randomUUID(),
				name: input.name,
				description: input.description,
				source_type: "zip",
				repository_url: undefined,
				repository_type: "other",
				default_branch: input.default_branch || "main",
				programming_languages: input.programming_languages.join(","),
				created_at: new Date().toISOString(),
			});
			projects.unshift(created);
			return created;
		},

		async createZipProject(input: CreateProjectForm, file: File) {
			console.debug("mock create zip project", input, file.name);
			return this.createProject(input);
		},

		async updateProject(projectId, input, zipFile) {
			await wait();
			const projectIndex = getProjectIndex(projectId);
			if (projectIndex < 0) {
				throw new Error("项目不存在");
			}
			const previous = projects[projectIndex];
			const updatedMetrics =
				previous.management_metrics?.status === "ready"
					? {
							...previous.management_metrics,
							updated_at: new Date().toISOString(),
					  }
					: previous.management_metrics;
			const updated: Project = {
				...previous,
				...input,
				id: previous.id,
				programming_languages: Array.isArray(input.programming_languages)
					? input.programming_languages.join(",")
					: previous.programming_languages,
				updated_at: new Date().toISOString(),
				management_metrics: updatedMetrics,
			};
			if (zipFile) {
				updated.management_metrics = {
					...(updated.management_metrics || createMockMetrics()),
					archive_original_filename: zipFile.name,
					archive_size_bytes: zipFile.size,
					updated_at: new Date().toISOString(),
				};
			}
			projects[projectIndex] = updated;
			return updated;
		},
	};
}
