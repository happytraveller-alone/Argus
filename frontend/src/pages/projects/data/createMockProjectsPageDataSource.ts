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
		total_tasks: overrides.total_tasks ?? 12,
		completed_tasks: overrides.completed_tasks ?? 9,
		running_tasks: overrides.running_tasks ?? 1,
		audit_tasks: overrides.audit_tasks ?? 3,
		agent_tasks: overrides.agent_tasks ?? 4,
		opengrep_tasks: overrides.opengrep_tasks ?? 2,
		gitleaks_tasks: overrides.gitleaks_tasks ?? 1,
		bandit_tasks: overrides.bandit_tasks ?? 1,
		phpstan_tasks: overrides.phpstan_tasks ?? 1,
		critical: overrides.critical ?? 2,
		high: overrides.high ?? 3,
		medium: overrides.medium ?? 5,
		low: overrides.low ?? 4,
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
		owner_id: overrides.owner_id || "mock-user",
		is_active: overrides.is_active ?? true,
		created_at: timestamp,
		updated_at: overrides.updated_at || timestamp,
		management_metrics:
			overrides.management_metrics || createMockMetrics(overrides.management_metrics ?? {}),
		owner: overrides.owner,
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
			name: "Mock Zip Worker",
			description: "Zip project kept for regression verification",
			source_type: "zip",
			repository_url: undefined,
			repository_type: "other",
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
				yasaTasks: [],
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
				yasaTasks: [],
			},
		],
	]);

	const languageRequestCount = new Map<string, number>();
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
					yasaTasks: [],
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

		async getProjectZipMeta(projectId) {
			await wait();
			if (projectId === "mock-project-2") {
				return {
					has_file: true,
					file_size: 2_621_440,
					original_filename: "mock-project-2.zip",
				};
			}
			return {
				has_file: false,
			};
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
			taskPools.set(created.id, {
				auditTasks: [],
				agentTasks: [],
				opengrepTasks: [],
				gitleaksTasks: [],
				banditTasks: [],
				phpstanTasks: [],
				yasaTasks: [],
			});
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
