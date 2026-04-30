import type { Project, ProjectManagementMetrics } from "@/shared/types";
import type { ProjectsPageViewModel } from "../types";
import { buildPaginationItems } from "./projectsPageSelectors";

function formatArchiveSize(bytes?: number | null) {
	if (!Number.isFinite(bytes) || !bytes) {
		return "-";
	}
	if (bytes >= 1024 * 1024) {
		return `${(bytes / 1024 / 1024).toFixed(2)} Mb`;
	}
	if (bytes >= 1024) {
		return `${(bytes / 1024).toFixed(2)} Kb`;
	}
	return `${bytes} B`;
}

function buildExecutionStats(metrics?: ProjectManagementMetrics | null) {
	if (!isMetricsReady(metrics)) {
		return {
			completed: 0,
			running: 0,
		};
	}
	return {
		completed: metrics.completed_tasks,
		running: metrics.running_tasks,
	};
}

type SeverityStats = {
	critical: number;
	high: number;
	medium: number;
	low: number;
	total: number;
};

type SeverityValues = Omit<SeverityStats, "total">;

const EMPTY_SEVERITY_VALUES: SeverityValues = {
	critical: 0,
	high: 0,
	medium: 0,
	low: 0,
};

function isMetricsReady(
	metrics?: ProjectManagementMetrics | null,
): metrics is ProjectManagementMetrics {
	return metrics?.status === "ready";
}

function buildSeverityStats(values: SeverityValues): SeverityStats {
	return {
		...values,
		total: values.critical + values.high + values.medium + values.low,
	};
}

function hasSourceSeverityBreakdown(metrics: ProjectManagementMetrics) {
	return (
		metrics.static_critical !== undefined ||
		metrics.static_high !== undefined ||
		metrics.static_medium !== undefined ||
		metrics.static_low !== undefined ||
		metrics.intelligent_critical !== undefined ||
		metrics.intelligent_high !== undefined ||
		metrics.intelligent_medium !== undefined ||
		metrics.intelligent_low !== undefined
	);
}

function buildVulnerabilityStats(metrics?: ProjectManagementMetrics | null) {
	if (!isMetricsReady(metrics)) {
		return buildSeverityStats(EMPTY_SEVERITY_VALUES);
	}
	if (!hasSourceSeverityBreakdown(metrics)) {
		return buildSeverityStats({
			critical: metrics.critical ?? 0,
			high: metrics.high ?? 0,
			medium: metrics.medium ?? 0,
			low: metrics.low ?? 0,
		});
	}
	return buildSeverityStats({
		critical:
			(metrics.static_critical ?? 0) + (metrics.intelligent_critical ?? 0),
		high: (metrics.static_high ?? 0) + (metrics.intelligent_high ?? 0),
		medium: (metrics.static_medium ?? 0) + (metrics.intelligent_medium ?? 0),
		low: (metrics.static_low ?? 0) + (metrics.intelligent_low ?? 0),
	});
}

function buildAiVerifiedStats(metrics?: ProjectManagementMetrics | null) {
	if (!isMetricsReady(metrics)) {
		return buildSeverityStats(EMPTY_SEVERITY_VALUES);
	}
	return buildSeverityStats({
		critical: metrics.verified_critical ?? 0,
		high: metrics.verified_high ?? 0,
		medium: metrics.verified_medium ?? 0,
		low: metrics.verified_low ?? 0,
	});
}

function getMetricsStatusMessage(metrics?: ProjectManagementMetrics | null) {
	if (!metrics || metrics.status === "pending") {
		return "指标同步中...";
	}
	if (metrics.status === "failed") {
		return metrics.error_message || "指标刷新失败";
	}
	return null;
}

interface BuildProjectsPageViewModelParams {
	loading: boolean;
	filteredProjects: Project[];
	pagedProjects: Project[];
	projectPage: number;
	totalProjectPages: number;
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
		projectDetailFrom,
		searchTerm,
		searchPlaceholder,
	} = params;

	return {
		loading,
		rows: pagedProjects.map((project) => {
			const metrics = project.management_metrics;
			const metricsStatus = metrics?.status ?? "pending";
			const metricsStatusMessage = getMetricsStatusMessage(metrics);
			return {
				id: project.id,
				serialNumber:
					filteredProjects.findIndex(
						(candidate) => candidate.id === project.id,
					) + 1,
				name: project.name,
				detailPath: `/projects/${project.id}`,
				detailState: { from: projectDetailFrom },
				sizeText: formatArchiveSize(metrics?.archive_size_bytes),
				sizeBytes: metrics?.archive_size_bytes ?? 0,
				vulnerabilityStats: buildVulnerabilityStats(metrics),
				aiVerifiedStats: buildAiVerifiedStats(metrics),
				executionStats: buildExecutionStats(metrics),
				metricsStatus,
				metricsStatusMessage,
				actions: {
					canCreateScan: true,
					canBrowseCode: project.source_type === "zip",
					canDelete: true,
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
