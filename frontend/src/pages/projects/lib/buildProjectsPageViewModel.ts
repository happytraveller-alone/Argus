import {
	getProjectCardSummaryStats,
} from "@/features/projects/services/projectCardPreview";
import {
	buildStaticScanGroups,
	resolveStaticScanGroupStatus,
} from "@/features/tasks/services/taskActivities";
import type { Project } from "@/shared/types";
import type { ZipFileMeta } from "@/shared/utils/zipStorage";
import type {
	ProjectTaskPoolState,
	ProjectsPageViewModel,
} from "../types";
import { buildPaginationItems } from "./projectsPageSelectors";

function formatProjectArchiveSize(bytes: number) {
	if (bytes >= 1024 * 1024) {
		return `${(bytes / 1024 / 1024).toFixed(2)} Mb`;
	}
	if (bytes >= 1024) {
		return `${(bytes / 1024).toFixed(2)} Kb`;
	}
	return `${bytes} B`;
}

export function getProjectSizeText(
	sourceType?: Project["source_type"],
	zipMeta?: ZipFileMeta,
) {
	if (sourceType !== "zip") return "-";
	if (!zipMeta?.has_file || typeof zipMeta.file_size !== "number") return "-";
	return formatProjectArchiveSize(zipMeta.file_size);
}

export function getProjectExecutionStats(
	projectTaskPool?: Partial<ProjectTaskPoolState>,
) {
	const nonStaticStatuses = [
		...((projectTaskPool?.auditTasks || []).map((task) => task.status)),
		...((projectTaskPool?.agentTasks || []).map((task) => task.status)),
	].map((status) => String(status || "").trim().toLowerCase());

	const staticGroups = buildStaticScanGroups({
		opengrepTasks: projectTaskPool?.opengrepTasks || [],
		gitleaksTasks: projectTaskPool?.gitleaksTasks || [],
		banditTasks: projectTaskPool?.banditTasks || [],
		phpstanTasks: projectTaskPool?.phpstanTasks || [],
	});
	const staticStats = staticGroups.reduce(
		(accumulator, group) => {
			const status = resolveStaticScanGroupStatus(group);
			if (status === "completed") {
				accumulator.completed += 1;
			} else if (status === "running") {
				accumulator.running += 1;
			}
			return accumulator;
		},
		{ completed: 0, running: 0 },
	);

	return {
		completed:
			nonStaticStatuses.filter((status) => status === "completed").length +
			staticStats.completed,
		running:
			nonStaticStatuses.filter(
				(status) => status === "running" || status === "pending",
			).length + staticStats.running,
	};
}

interface BuildProjectsPageViewModelParams {
	loading: boolean;
	filteredProjects: Project[];
	pagedProjects: Project[];
	projectPage: number;
	totalProjectPages: number;
	projectTaskPoolsMap: Record<string, ProjectTaskPoolState>;
	projectZipMetaMap: Record<string, ZipFileMeta>;
	projectDetailFrom: string;
	searchTerm: string;
	searchPlaceholder: string;
}

export function buildProjectsPageViewModel(
	params: BuildProjectsPageViewModelParams,
): ProjectsPageViewModel {
	const {
		loading,
		filteredProjects,
		pagedProjects,
		projectPage,
		totalProjectPages,
		projectTaskPoolsMap,
		projectZipMetaMap,
		projectDetailFrom,
		searchTerm,
		searchPlaceholder,
	} = params;

	return {
		loading,
		rows: pagedProjects.map((project) => {
			const projectTaskPool = projectTaskPoolsMap[project.id];
			const summaryStats = getProjectCardSummaryStats({
				projectId: project.id,
				auditTasks: projectTaskPool?.auditTasks || [],
				agentTasks: projectTaskPool?.agentTasks || [],
				opengrepTasks: projectTaskPool?.opengrepTasks || [],
				gitleaksTasks: projectTaskPool?.gitleaksTasks || [],
				banditTasks: projectTaskPool?.banditTasks || [],
				phpstanTasks: projectTaskPool?.phpstanTasks || [],
			});
			return {
				id: project.id,
				name: project.name,
				detailPath: `/projects/${project.id}`,
				detailState: { from: projectDetailFrom },
				sizeText: getProjectSizeText(projectLanguageStatsMap[project.id]),
				statusLabel: "可用",
				statusClassName: "cyber-badge-success",
				totalIssues: summaryStats.totalIssues ?? 0,
				executionStats: getProjectExecutionStats(projectTaskPool),
				actions: {
					canCreateScan: true,
					canBrowseCode: project.source_type === "zip",
					browseCodePath: `/projects/${project.id}/code-browser`,
					browseCodeState: { from: projectDetailFrom },
					browseCodeDisabledReason:
						project.source_type === "zip"
							? null
							: "仅 ZIP 类型项目支持代码浏览",
				},
			};
		}),
		toolbar: {
			searchTerm,
			searchPlaceholder,
			createButtonLabel: "创建项目",
		},
		pagination: {
			currentPage: projectPage,
			totalPages: totalProjectPages,
			totalCount: filteredProjects.length,
			items: buildPaginationItems(projectPage, totalProjectPages),
		},
		emptyState: {
			hasSearchTerm: Boolean(searchTerm.trim()),
		},
	};
}
