import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectCardLanguageStats } from "@/features/projects/services/projectCardPreview";
import type { CreateProjectForm, Project } from "@/shared/types";
import {
	LANGUAGE_STATS_MAX_RETRIES,
	LANGUAGE_STATS_RETRY_INTERVAL_MS,
} from "../constants";
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
	const [projectLanguageStatsMap, setProjectLanguageStatsMap] = useState<
		Record<string, ProjectCardLanguageStats>
	>({});

	const projectTaskPoolLoadingRef = useRef<Record<string, boolean>>({});
	const languageStatsRetryCountRef = useRef<Record<string, number>>({});
	const languageStatsPollTimerRef = useRef<Record<string, number>>({});

	const clearLanguageStatsPollTimer = useCallback((projectId: string) => {
		const timer = languageStatsPollTimerRef.current[projectId];
		if (timer) {
			window.clearTimeout(timer);
			delete languageStatsPollTimerRef.current[projectId];
		}
	}, []);

	const clearAllLanguageStatsPollTimers = useCallback(() => {
		for (const timer of Object.values(languageStatsPollTimerRef.current)) {
			window.clearTimeout(timer);
		}
		languageStatsPollTimerRef.current = {};
		languageStatsRetryCountRef.current = {};
	}, []);

	const loadProjects = useCallback(async () => {
		try {
			setLoading(true);
			const nextProjects = await dataSource.listProjects({ includeDeleted: true });
			setProjects(nextProjects);
			setProjectTaskPoolsMap({});
			setProjectLanguageStatsMap({});
			projectTaskPoolLoadingRef.current = {};
			clearAllLanguageStatsPollTimers();
		} finally {
			setLoading(false);
		}
	}, [clearAllLanguageStatsPollTimers, dataSource]);

	useEffect(() => {
		void loadProjects();
	}, [loadProjects]);

	const fetchProjectLanguageStats = useCallback(
		async (projectId: string) => {
			try {
				const stats = await dataSource.getProjectLanguageStats(projectId);
				setProjectLanguageStatsMap((previous) => ({
					...previous,
					[projectId]: stats,
				}));

				if (stats.status === "pending") {
					const retryCount = languageStatsRetryCountRef.current[projectId] ?? 0;
					if (retryCount < LANGUAGE_STATS_MAX_RETRIES) {
						clearLanguageStatsPollTimer(projectId);
						languageStatsRetryCountRef.current[projectId] = retryCount + 1;
						languageStatsPollTimerRef.current[projectId] = window.setTimeout(
							() => {
								delete languageStatsPollTimerRef.current[projectId];
								void fetchProjectLanguageStats(projectId);
							},
							LANGUAGE_STATS_RETRY_INTERVAL_MS,
						);
						return;
					}

					setProjectLanguageStatsMap((previous) => ({
						...previous,
						[projectId]: {
							status: "failed",
							total: 0,
							totalFiles: 0,
							slices: [],
						},
					}));
				}

				languageStatsRetryCountRef.current[projectId] = 0;
				clearLanguageStatsPollTimer(projectId);
			} catch {
				setProjectLanguageStatsMap((previous) => ({
					...previous,
					[projectId]: {
						status: "failed",
						total: 0,
						totalFiles: 0,
						slices: [],
					},
				}));
				clearLanguageStatsPollTimer(projectId);
			}
		},
		[clearLanguageStatsPollTimer, dataSource],
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
				if (!projectLanguageStatsMap[projectId]) {
					setProjectLanguageStatsMap((previous) => ({
						...previous,
						[projectId]: {
							status: "loading",
							total: 0,
							totalFiles: 0,
							slices: [],
						},
					}));
					void fetchProjectLanguageStats(projectId);
				}
			}
		},
		[fetchProjectLanguageStats, loadProjectTaskPool, projectLanguageStatsMap],
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

			setProjectLanguageStatsMap((previous) => {
				const next = { ...previous };
				for (const projectId of projectIds) {
					delete next[projectId];
					clearLanguageStatsPollTimer(projectId);
					delete languageStatsRetryCountRef.current[projectId];
				}
				return next;
			});
		},
		[clearLanguageStatsPollTimer],
	);

	useEffect(() => {
		return () => {
			clearAllLanguageStatsPollTimers();
			projectTaskPoolLoadingRef.current = {};
		};
	}, [clearAllLanguageStatsPollTimers]);

	return {
		projects,
		loading,
		projectTaskPoolsMap,
		projectLanguageStatsMap,
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
		async disableProject(projectId: string) {
			await dataSource.disableProject(projectId);
			await loadProjects();
		},
		async enableProject(projectId: string) {
			await dataSource.enableProject(projectId);
			await loadProjects();
		},
	};
}
