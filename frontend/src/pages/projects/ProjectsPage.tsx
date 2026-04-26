import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import SilentLoadingState from "@/components/performance/SilentLoadingState";
import { useI18n } from "@/shared/i18n";
import { useLocation } from "react-router-dom";
import {
	MODULE_SCROLL_DELAY_MS,
	PROJECT_PAGE_SIZE,
	PROJECTS_TABLE_HEADER_HEIGHT,
	PROJECTS_TABLE_PAGINATION_HEIGHT,
	PROJECTS_TABLE_ROW_HEIGHT,
	SUPPORTED_PROJECT_LANGUAGES,
} from "./constants";
import type { ProjectsPageProps } from "./types";
import { useProjectsBrowserState } from "./hooks/useProjectsBrowserState";
import { useProjectsPageData } from "./hooks/useProjectsPageData";
import {
	buildProjectsPageViewModel,
} from "./lib/buildProjectsPageViewModel";
import {
	calculateResponsiveProjectsPageSize,
	filterProjects,
	paginateItems,
	resolveAnchoredProjectsPage,
	resolveProjectsFirstVisibleIndex,
} from "./lib/projectsPageSelectors";
import ProjectsToolbar from "./components/ProjectsToolbar";
import ProjectsTable from "./components/ProjectsTable";
import ProjectsPagination from "./components/ProjectsPagination";
import ProjectsEmptyState from "./components/ProjectsEmptyState";
import CreateProjectDialog from "./components/CreateProjectDialog";
import EditProjectDialog from "./components/EditProjectDialog";
import {
	createZipProjectsWorkflow,
	type BatchCreateZipProjectItem,
	type BatchCreateZipProjectsProgressEvent,
} from "./data/projectsPageWorkflows";

function scrollToProjectBrowser() {
	window.setTimeout(() => {
		document.getElementById("project-browser")?.scrollIntoView({
			behavior: "smooth",
			block: "start",
		});
	}, MODULE_SCROLL_DELAY_MS);
}

function pinToProjectBrowserHash() {
	const { pathname, search } = window.location;
	window.history.replaceState(
		window.history.state,
		"",
		`${pathname}${search}#project-browser`,
	);
}

async function logUserAction(action: string, payload: Record<string, unknown>) {
	const loggerModule = await import("@/shared/utils/logger");
	loggerModule.logger.logUserAction(action, payload);
}

function resolveResponsiveProjectPageSize(
	viewportNode: HTMLDivElement,
	paginationNode: HTMLDivElement | null,
) {
	const tableHeaderHeight =
		viewportNode
			.querySelector<HTMLElement>('[data-slot="table-header"]')
			?.getBoundingClientRect().height ?? PROJECTS_TABLE_HEADER_HEIGHT;
	const rowHeight =
		viewportNode
			.querySelector<HTMLElement>(
				'[data-slot="table-body"] [data-slot="table-row"]',
			)
			?.getBoundingClientRect().height ?? PROJECTS_TABLE_ROW_HEIGHT;
	const paginationHeight =
		paginationNode?.getBoundingClientRect().height ??
		PROJECTS_TABLE_PAGINATION_HEIGHT;

	return calculateResponsiveProjectsPageSize({
		containerHeight: viewportNode.clientHeight,
		tableHeaderHeight,
		paginationHeight,
		rowHeight,
	});
}

function getBatchZipCreationToast(
	successCount: number,
	failureCount: number,
	total: number,
) {
	if (failureCount === 0) {
		return {
			kind: "success" as const,
			title: `已创建 ${successCount} 个项目`,
			description: "所有压缩包都已成功导入，项目列表已刷新。",
		};
	}

	if (successCount === 0) {
		return {
			kind: "error" as const,
			title: "批量导入失败",
			description: `共 ${total} 个压缩包，均未创建成功。`,
		};
	}

	return {
		kind: "warning" as const,
		title: `批量导入完成：成功 ${successCount} / 失败 ${failureCount}`,
		description: "成功项目已保留，失败项可稍后重试。",
	};
}

export default function ProjectsPage({
	dataSource,
	renderCreateScanDialog,
}: ProjectsPageProps) {
	const location = useLocation();
	const { t } = useI18n();
	const browser = useProjectsBrowserState();
	const data = useProjectsPageData(dataSource);
	const tableViewportRef = useRef<HTMLDivElement | null>(null);
	const paginationRef = useRef<HTMLDivElement | null>(null);
	const [projectPageSize, setProjectPageSize] = useState(PROJECT_PAGE_SIZE);
	const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
	const projectPageSizeRef = useRef(projectPageSize);

	const filteredProjects = useMemo(
		() => filterProjects(data.projects, browser.searchTerm),
		[data.projects, browser.searchTerm],
	);
	const totalProjectPages = Math.max(
		1,
		Math.ceil(filteredProjects.length / projectPageSize),
	);
	const pagedProjects = useMemo(
		() =>
			paginateItems(filteredProjects, browser.projectPage, projectPageSize),
		[filteredProjects, browser.projectPage, projectPageSize],
	);
	const projectDetailFrom = `${location.pathname}${location.search}${location.hash}`;

	useEffect(() => {
		if (browser.projectPage > totalProjectPages) {
			browser.setProjectPage(totalProjectPages);
		}
	}, [browser, totalProjectPages]);

	useEffect(() => {
		browser.setProjectPage((currentPage) => {
			const firstVisibleIndex = resolveProjectsFirstVisibleIndex({
				page: currentPage,
				pageSize: projectPageSizeRef.current,
			});
			const nextPage = resolveAnchoredProjectsPage({
				firstVisibleIndex,
				nextPageSize: projectPageSize,
				totalRows: filteredProjects.length,
			});
			return currentPage === nextPage ? currentPage : nextPage;
		});
		projectPageSizeRef.current = projectPageSize;
	}, [browser, filteredProjects.length, projectPageSize]);

	useEffect(() => {
		if (typeof ResizeObserver === "undefined" || !tableViewportRef.current) {
			return;
		}

		const viewportNode = tableViewportRef.current;
		const updatePageSize = () => {
			const nextPageSize = resolveResponsiveProjectPageSize(
				viewportNode,
				paginationRef.current,
			);
			setProjectPageSize((current) =>
				current === nextPageSize ? current : nextPageSize,
			);
		};

		updatePageSize();
		const observer = new ResizeObserver(() => {
			updatePageSize();
		});
		observer.observe(viewportNode);
		if (paginationRef.current) {
			observer.observe(paginationRef.current);
		}
		window.addEventListener("resize", updatePageSize);
		window.visualViewport?.addEventListener("resize", updatePageSize);
		return () => {
			observer.disconnect();
			window.removeEventListener("resize", updatePageSize);
			window.visualViewport?.removeEventListener("resize", updatePageSize);
		};
	}, [browser.projectPage, filteredProjects.length, totalProjectPages]);

	useEffect(() => {
		const hash = window.location.hash;
		if (hash !== "#project-browser") {
			return;
		}
		scrollToProjectBrowser();
	}, []);

	const viewModel = useMemo(
		() =>
			buildProjectsPageViewModel({
				loading: data.loading,
				filteredProjects,
				pagedProjects,
				projectPage: browser.projectPage,
				totalProjectPages,
				projectDetailFrom,
				searchTerm: browser.searchTerm,
				searchPlaceholder: t("projects.searchPlaceholder", "按项目名称/描述搜索"),
			}),
		[
			browser.projectPage,
			browser.searchTerm,
			data.loading,
			filteredProjects,
			pagedProjects,
			projectDetailFrom,
			t,
			totalProjectPages,
		],
	);

	async function handleCreateZipProjects(
		items: BatchCreateZipProjectItem[],
		sharedInput: Omit<Parameters<typeof data.createProject>[0], "name">,
		onProgress?: (event: BatchCreateZipProjectsProgressEvent) => void,
	) {
		const result = await createZipProjectsWorkflow({
			items,
			sharedInput,
			createZipProject: (input, file) => dataSource.createZipProject(input, file),
			onProgress,
		});

		await data.loadProjects();
		void logUserAction("批量上传ZIP文件创建项目", {
			total: result.total,
			successCount: result.successCount,
			failureCount: result.failureCount,
			projectNames: result.successes.map((project) => project.name),
			failedFiles: result.failures.map((failure) => failure.fileName),
		});

		const toastConfig = getBatchZipCreationToast(
			result.successCount,
			result.failureCount,
			result.total,
		);
		if (toastConfig.kind === "success") {
			toast.success(toastConfig.title, {
				description: toastConfig.description,
				duration: 4000,
			});
		} else if (toastConfig.kind === "error") {
			toast.error(toastConfig.title, {
				description: toastConfig.description,
				duration: 5000,
			});
		} else {
			toast.warning(toastConfig.title, {
				description: toastConfig.description,
				duration: 5000,
			});
		}

		if (result.successCount > 0) {
			pinToProjectBrowserHash();
			scrollToProjectBrowser();
		}

		return result;
	}

	async function handleUpdateProject(
		projectId: string,
		input: Partial<Parameters<typeof data.updateProject>[1]>,
		zipFile?: File | null,
	) {
		try {
			const project = await data.updateProject(projectId, input, zipFile);
			toast.success(`项目 "${project.name}" 已更新`);
		} catch (error) {
			console.error("Failed to update project:", error);
			toast.error("更新项目失败");
			throw error;
		}
	}

	async function handleDeleteProject(projectId: string, projectName: string) {
		if (
			typeof window !== "undefined" &&
			!window.confirm(
				`确认删除项目「${projectName}」？与该项目相关的扫描任务也会一并删除，且不可恢复。`,
			)
		) {
			return;
		}

		setDeletingProjectId(projectId);
		try {
			await data.deleteProject(projectId);
			toast.success(`项目 "${projectName}" 已删除`, {
				description: "与该项目相关的扫描任务已一并删除。",
				duration: 5000,
			});
			pinToProjectBrowserHash();
			scrollToProjectBrowser();
		} catch (error) {
			console.error("Failed to delete project:", error);
			toast.error("删除项目失败");
			throw error;
		} finally {
			setDeletingProjectId((current) =>
				current === projectId ? null : current,
			);
		}
	}

	function handleTaskCreated() {
		void data.loadProjects();
		toast.success("扫描任务已创建", {
			description:
				"因为网络和代码文件大小等因素，扫描时长通常至少需要1分钟，请耐心等待...",
			duration: 5000,
		});
	}

	return (
		<div className="p-6 bg-background min-h-screen font-mono relative flex flex-col gap-6">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			<CreateProjectDialog
				open={browser.showCreateDialog}
				supportedLanguages={SUPPORTED_PROJECT_LANGUAGES}
				onOpenChange={(open) => {
					browser.setShowCreateDialog(open);
					if (!open) {
						pinToProjectBrowserHash();
						scrollToProjectBrowser();
					}
				}}
				onCreateZipProjects={handleCreateZipProjects}
			/>

			<div
				id="project-browser"
				className="relative z-10 flex flex-col flex-1 min-h-[65vh]"
			>
				<ProjectsToolbar
					searchTerm={viewModel.toolbar.searchTerm}
					searchPlaceholder={viewModel.toolbar.searchPlaceholder}
					createButtonLabel={viewModel.toolbar.createButtonLabel}
					onSearchChange={browser.setSearchTerm}
					onCreateProjectClick={() => {
						pinToProjectBrowserHash();
						browser.setShowCreateDialog(true);
					}}
				/>

				{viewModel.loading && data.projects.length === 0 ? (
					<SilentLoadingState className="w-full" minHeight={240} />
				) : viewModel.rows.length > 0 ? (
					<div
						ref={tableViewportRef}
						className="flex min-h-0 flex-1 flex-col"
					>
						<ProjectsTable
							rows={viewModel.rows}
							onCreateScan={(projectId) => {
								pinToProjectBrowserHash();
								browser.openCreateScanDialog("agent", projectId, {
									navigateOnSuccess: true,
								});
							}}
							onDeleteProject={handleDeleteProject}
							deletingProjectId={deletingProjectId}
						/>
						<div ref={paginationRef}>
							<ProjectsPagination
								currentPage={viewModel.pagination.currentPage}
								totalPages={viewModel.pagination.totalPages}
								totalCount={viewModel.pagination.totalCount}
								items={viewModel.pagination.items}
								onPageChange={browser.setProjectPage}
							/>
						</div>
					</div>
				) : (
					<ProjectsEmptyState
						hasSearchTerm={viewModel.emptyState.hasSearchTerm}
						onCreateProjectClick={() => {
							pinToProjectBrowserHash();
							browser.setShowCreateDialog(true);
						}}
					/>
				)}
			</div>

			{renderCreateScanDialog
				? renderCreateScanDialog({
						open: browser.createScanState.open,
						onOpenChange: (open) => {
							if (!open) {
								browser.closeCreateScanDialog();
								pinToProjectBrowserHash();
								scrollToProjectBrowser();
								return;
							}
						},
						onTaskCreated: handleTaskCreated,
						preselectedProjectId:
							browser.createScanState.preselectedProjectId || undefined,
						lockProjectSelection: Boolean(
							browser.createScanState.preselectedProjectId,
						),
						initialMode: browser.createScanState.initialMode,
						navigateOnSuccess: browser.createScanState.navigateOnSuccess,
					})
				: null}

			<EditProjectDialog
				open={browser.editProjectState.open}
				project={browser.editProjectState.project}
				supportedLanguages={SUPPORTED_PROJECT_LANGUAGES}
				onOpenChange={(open) =>
					browser.setEditProjectState((previous) => ({
						open,
						project: open ? previous.project : null,
					}))
				}
				onSubmit={handleUpdateProject}
			/>
		</div>
	);
}
