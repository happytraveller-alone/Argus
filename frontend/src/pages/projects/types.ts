import type { ReactNode } from "react";
import type { ScanCreateMode } from "@/components/scan/CreateProjectScanDialog";
import type { AgentTask } from "@/shared/api/agentTasks";
import type { BanditScanTask } from "@/shared/api/bandit";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { PhpstanScanTask } from "@/shared/api/phpstan";
import type { OpengrepScanTask } from "@/shared/api/opengrep";
import type { Project, AuditTask } from "@/shared/types";
import type { ProjectsPageDataSource } from "./data/projectsPageDataSource";
import type { ProjectStatusToggleAction } from "./viewModel";

export type ProjectTaskPoolStatus = "idle" | "loading" | "ready" | "failed";

export interface ProjectTaskPool {
	auditTasks: AuditTask[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
	gitleaksTasks: GitleaksScanTask[];
	banditTasks: BanditScanTask[];
	phpstanTasks: PhpstanScanTask[];
}

export interface ProjectTaskPoolState extends ProjectTaskPool {
	status: ProjectTaskPoolStatus;
}

export interface ProjectsPageRowViewModel {
	id: string;
	rowNumber: number;
	name: string;
	detailPath: string;
	detailState: { from: string };
	sizeText: string;
	statusLabel: "启用" | "禁用";
	statusClassName: string;
	statusToggle: ProjectStatusToggleAction & {
		disabled: boolean;
	};
	isActive: boolean;
	totalIssues: number;
	executionStats: {
		completed: number;
		running: number;
	};
	actions: {
		canCreateScan: boolean;
		canBrowseCode: boolean;
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

export interface ProjectsSelectionViewModel {
	selectedProjectIds: Set<string>;
	currentPageProjectIds: string[];
	isAllCurrentPageSelected: boolean;
	isSomeCurrentPageSelected: boolean;
	selectedCount: number;
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
	disableProject: {
		open: boolean;
		project: Project | null;
	};
}

export interface ProjectsPageViewModel {
	loading: boolean;
	rows: ProjectsPageRowViewModel[];
	toolbar: ProjectsToolbarViewModel;
	pagination: ProjectsPaginationViewModel;
	selection: ProjectsSelectionViewModel;
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
