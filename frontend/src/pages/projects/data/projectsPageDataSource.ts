import type { CreateProjectForm, Project } from "@/shared/types";

export interface ProjectsPageDataSource {
	listProjects(): Promise<Project[]>;
	createProject(input: CreateProjectForm): Promise<Project>;
	createZipProject(input: CreateProjectForm, file: File): Promise<Project>;
	updateProject(
		projectId: string,
		input: Partial<CreateProjectForm>,
		zipFile?: File | null,
	): Promise<Project>;
}
