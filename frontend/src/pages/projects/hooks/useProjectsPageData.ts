import { useCallback, useEffect, useState } from "react";
import type { CreateProjectForm, Project } from "@/shared/types";
import type { ProjectsPageDataSource } from "../data/projectsPageDataSource";

export function useProjectsPageData(dataSource: ProjectsPageDataSource) {
	const [projects, setProjects] = useState<Project[]>([]);
	const [loading, setLoading] = useState(true);

	const loadProjects = useCallback(async () => {
		setLoading(true);
		try {
			const nextProjects = await dataSource.listProjects();
			setProjects(nextProjects);
		} finally {
			setLoading(false);
		}
	}, [dataSource]);

	useEffect(() => {
		void loadProjects();
	}, [loadProjects]);

	return {
		projects,
		loading,
		loadProjects,
		async createProject(input: CreateProjectForm) {
			const createdProject = await dataSource.createProject(input);
			await loadProjects();
			return createdProject;
		},
		async createZipProject(input: CreateProjectForm, file: File) {
			const createdProject = await dataSource.createZipProject(input, file);
			await loadProjects();
			return createdProject;
		},
		async deleteProject(projectId: string) {
			await dataSource.deleteProject(projectId);
			await loadProjects();
		},
		async updateProject(
			projectId: string,
			input: Partial<CreateProjectForm>,
			zipFile?: File | null,
		) {
			const updatedProject = await dataSource.updateProject(projectId, input, zipFile);
			await loadProjects();
			return updatedProject;
		},
	};
}
