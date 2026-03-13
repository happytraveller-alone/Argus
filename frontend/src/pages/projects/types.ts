import type { ReactNode } from "react";
import type { ScanCreateMode } from "@/components/scan/CreateProjectScanDialog";
import type { ProjectCardLanguageStats } from "@/features/projects/services/projectCardPreview";
import type { AgentTask } from "@/shared/api/agentTasks";
import type { BanditScanTask } from "@/shared/api/bandit";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { OpengrepScanTask } from "@/shared/api/opengrep";
import type { Project, AuditTask } from "@/shared/types";

export type ProjectTaskPoolStatus = "idle" | "loading" | "ready" | "failed";

export interface ProjectTaskPool {
	auditTasks: AuditTask[];
	agentTasks: AgentTask[];
	opengrepTasks: OpengrepScanTask[];
	gitleaksTasks: GitleaksScanTask[];
	banditTasks: BanditScanTask[];
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
	isActive: boolean;
	totalIssues: number;
	executionStats: {
		completed: number;
		running: number;
	};
	actions: {
		canCreateScan: boolean;
		canDisable: boolean;
		canEnable: boolean;
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
	dataSource: {
		listProjects: (params?: { includeDeleted?: boolean }) => Promise<Project[]>;
		getProjectTaskPool: (projectId: string) => Promise<ProjectTaskPool>;
		getProjectLanguageStats: (
			projectId: string,
		) => Promise<ProjectCardLanguageStats>;
		createProject: (input: import("@/shared/types").CreateProjectForm) => Promise<Project>;
		createZipProject: (
			input: import("@/shared/types").CreateProjectForm,
			file: File,
		) => Promise<Project>;
		updateProject: (
			projectId: string,
			input: Partial<import("@/shared/types").CreateProjectForm>,
			zipFile?: File | null,
		) => Promise<Project>;
		disableProject: (projectId: string) => Promise<void>;
		enableProject: (projectId: string) => Promise<void>;
	};
	renderCreateScanDialog?: (props: ProjectsPageScanDialogProps) => ReactNode;
}
