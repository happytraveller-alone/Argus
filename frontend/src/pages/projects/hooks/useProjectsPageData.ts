import { useCallback, useEffect, useRef, useState } from "react";
import type { CreateProjectForm, Project } from "@/shared/types";
import type { ZipFileMeta } from "@/shared/utils/zipStorage";
import type { ProjectTaskPoolState } from "../types";
import type { ProjectsPageDataSource } from "../data/projectsPageDataSource";

function createEmptyTaskPoolState(
	status: ProjectTaskPoolState["status"] = "idle",
): ProjectTaskPoolState {
	return {
		status,
		auditTasks: [],
		agentTasks: [],
		opengrepTasks: [],
		gitleaksTasks: [],
		banditTasks: [],
		phpstanTasks: [],
	};
}

export function useProjectsPageData(dataSource: ProjectsPageDataSource) {
	const [projects, setProjects] = useState<Project[]>([]);
	const [loading, setLoading] = useState(true);
	const [projectTaskPoolsMap, setProjectTaskPoolsMap] = useState<
		Record<string, ProjectTaskPoolState>
	>({});
	const [projectZipMetaMap, setProjectZipMetaMap] = useState<
		Record<string, ZipFileMeta>
	>({});

	const projectTaskPoolLoadingRef = useRef<Record<string, boolean>>({});
	const projectZipMetaLoadingRef = useRef<Record<string, boolean>>({});

	const loadProjects = useCallback(async () => {
		try {
			setLoading(true);
			const nextProjects = await dataSource.listProjects();
			setProjects(nextProjects);
			setProjectTaskPoolsMap({});
			setProjectZipMetaMap({});
			projectTaskPoolLoadingRef.current = {};
			projectZipMetaLoadingRef.current = {};
		} finally {
			setLoading(false);
		}
	}, [dataSource]);

	useEffect(() => {
		void loadProjects();
	}, [loadProjects]);

	const loadProjectZipMeta = useCallback(
		async (projectId: string) => {
			if (projectZipMetaLoadingRef.current[projectId]) {
				return;
			}

			projectZipMetaLoadingRef.current[projectId] = true;
			try {
				const zipMeta = await dataSource.getProjectZipMeta(projectId);
				setProjectZipMetaMap((previous) => ({
					...previous,
					[projectId]: zipMeta,
				}));
			} catch {
				setProjectZipMetaMap((previous) => ({
					...previous,
					[projectId]: {
						has_file: false,
					},
				}));
			} finally {
				delete projectZipMetaLoadingRef.current[projectId];
			}
		},
		[dataSource],
	);

	const loadProjectTaskPool = useCallback(
		async (projectId: string) => {
			const existing = projectTaskPoolsMap[projectId];
			if (
				existing?.status === "ready" ||
				existing?.status === "loading" ||
				existing?.status === "failed"
			) {
				return;
			}
			if (projectTaskPoolLoadingRef.current[projectId]) {
				return;
			}

			projectTaskPoolLoadingRef.current[projectId] = true;
			setProjectTaskPoolsMap((previous) => ({
				...previous,
				[projectId]: {
					...createEmptyTaskPoolState("loading"),
					...previous[projectId],
				},
			}));

			try {
				const taskPool = await dataSource.getProjectTaskPool(projectId);
				setProjectTaskPoolsMap((previous) => ({
					...previous,
					[projectId]: {
						status: "ready",
						...taskPool,
					},
				}));
			} catch {
				setProjectTaskPoolsMap((previous) => ({
					...previous,
					[projectId]: createEmptyTaskPoolState("failed"),
				}));
			} finally {
				delete projectTaskPoolLoadingRef.current[projectId];
			}
		},
		[dataSource, projectTaskPoolsMap],
	);

	const ensureProjectData = useCallback(
		(projectIds: string[]) => {
			if (projectIds.length === 0) {
				return;
			}

			for (const projectId of projectIds) {
				void loadProjectTaskPool(projectId);
				if (!projectZipMetaMap[projectId]) {
					void loadProjectZipMeta(projectId);
				}
			}
		},
		[loadProjectTaskPool, loadProjectZipMeta, projectZipMetaMap],
	);

	const invalidateProjectMetrics = useCallback(
		(projectIds: string[]) => {
			if (projectIds.length === 0) {
				return;
			}

			setProjectTaskPoolsMap((previous) => {
				const next = { ...previous };
				for (const projectId of projectIds) {
					delete next[projectId];
					delete projectTaskPoolLoadingRef.current[projectId];
				}
				return next;
			});

			setProjectZipMetaMap((previous) => {
				const next = { ...previous };
				for (const projectId of projectIds) {
					delete next[projectId];
					delete projectZipMetaLoadingRef.current[projectId];
				}
				return next;
			});
		},
		[],
	);

	useEffect(() => {
		return () => {
			projectTaskPoolLoadingRef.current = {};
			projectZipMetaLoadingRef.current = {};
		};
	}, []);

	return {
		projects,
		loading,
		projectTaskPoolsMap,
		projectZipMetaMap,
		loadProjects,
		ensureProjectData,
		invalidateProjectMetrics,
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
