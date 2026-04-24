import type { ReactNode } from "react";
import type { ScanCreateMode } from "@/components/scan/CreateProjectScanDialog";
import type { ProjectSeverityBreakdown } from "@/features/projects/services/projectCardPreview";
import type { AgentTask } from "@/shared/api/agentTasks";
import type { OpengrepScanTask } from "@/shared/api/opengrep";
import type { Project, ProjectManagementMetrics } from "@/shared/types";
import type { ProjectsPageDataSource } from "./data/projectsPageDataSource";

export type ProjectTaskPoolStatus = "idle" | "loading" | "ready" | "failed";

export interface ProjectTaskPool {
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
}

export interface ProjectTaskPoolState extends ProjectTaskPool {
	status: ProjectTaskPoolStatus;
}

export type ProjectMetricsStatus = NonNullable<
	ProjectManagementMetrics["status"]
>;

export interface ProjectsPageRowViewModel {
	id: string;
	serialNumber: number;
	name: string;
	detailPath: string;
	detailState: { from: string };
	sizeText: string;
	sizeBytes: number;
	vulnerabilityStats: ProjectSeverityBreakdown;
	aiVerifiedStats: ProjectSeverityBreakdown;
	executionStats: {
		completed: number;
		running: number;
	};
	metricsStatus: ProjectMetricsStatus | "pending";
	metricsStatusMessage: string | null;
	actions: {
		canCreateScan: boolean;
		canBrowseCode: boolean;
		canDelete: boolean;
		browseCodePath: string;
		browseCodeState: { from: string };
		browseCodeDisabledReason: string | null;
	};
}

export interface ProjectsToolbarViewModel {
	searchTerm: string;
	searchPlaceholder: string;
	createButtonLabel: string;
}

export interface ProjectsPaginationViewModel {
	currentPage: number;
	totalPages: number;
	totalCount: number;
	items: Array<number | "ellipsis">;
}

export interface ProjectsDialogControllerState {
	createProjectOpen: boolean;
	createScan: {
		open: boolean;
		preselectedProjectId: string;
		initialMode: ScanCreateMode;
		navigateOnSuccess: boolean;
	};
	editProject: {
		open: boolean;
		project: Project | null;
	};
}

export interface ProjectsPageViewModel {
	loading: boolean;
	rows: ProjectsPageRowViewModel[];
	toolbar: ProjectsToolbarViewModel;
	pagination: ProjectsPaginationViewModel;
	emptyState: {
		hasSearchTerm: boolean;
	};
}

export interface ProjectsPageScanDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated: () => void;
	preselectedProjectId?: string;
	lockProjectSelection?: boolean;
	initialMode?: ScanCreateMode;
	navigateOnSuccess?: boolean;
}

export interface ProjectsPageProps {
	dataSource: ProjectsPageDataSource;
	renderCreateScanDialog?: (props: ProjectsPageScanDialogProps) => ReactNode;
}
