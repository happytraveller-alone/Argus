import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import { isZipProject } from "@/shared/utils/projectUtils";
import {
	createCodeqlScanTask,
	createOpengrepScanTask,
	getAllOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import { getZipFileInfo, uploadZipFile } from "@/shared/utils/zipStorage";
import { validateZipFile } from "@/features/projects/services/repoZipScan";
import { appendReturnTo } from "@/shared/utils/findingRoute";
import {
	appendStaticScanBatchMarker,
	createStaticScanBatchId,
} from "@/shared/utils/staticScanBatch";
import { normalizeCodeqlLanguages } from "@/shared/utils/programmingLanguages";
import type { StaticTool } from "@/components/agent/AgentModeSelector";
import CreateProjectScanDialogContent from "./create-project-scan/Content";
import { buildScanEngineConfigRoute } from "@/shared/constants/scanEngines";
import { hasSelectedPrimaryStaticEngine } from "@/shared/utils/staticEngineSelection";
import {
	paginateProjectCards,
	resolveProjectPageAfterSearchChange,
} from "./create-project-scan/llmGate";
import {
	buildCreateProjectStaticTaskRoute,
	extractCreateProjectScanApiErrorMessage,
	isSevereCreateProjectScanRule,
	stripCreateProjectScanArchiveSuffix,
} from "./create-project-scan/utils";

export type ScanCreateMode = "static" | "agent";

interface CreateProjectScanDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated?: () => void;
	initialMode?: ScanCreateMode;
	preselectedProjectId?: string;
	lockProjectSelection?: boolean;
	lockMode?: boolean;
	allowUploadProject?: boolean;
	navigateOnSuccess?: boolean;
	createButtonVariant?: "single" | "dual";
	primaryCreateLabel?: string;
	secondaryCreateLabel?: string;
	onSecondaryCreateSuccess?: () => void;
	showReturnButton?: boolean;
	onReturn?: () => void;
}

interface StaticTaskCreateResult {
	primaryTaskId: string;
	params: URLSearchParams;
}

export default function CreateProjectScanDialog({
	open,
	onOpenChange,
	onTaskCreated,
	initialMode: _initialMode = "static",
	preselectedProjectId,
	lockProjectSelection = false,
	lockMode = false,
	allowUploadProject = false,
	navigateOnSuccess = true,
	createButtonVariant = "single",
	primaryCreateLabel = "创建扫描任务",
	secondaryCreateLabel = "创建并返回",
	onSecondaryCreateSuccess,
	showReturnButton = false,
	onReturn,
}: CreateProjectScanDialogProps) {
	const navigate = useNavigate();
	const location = useLocation();
	const currentRoute = `${location.pathname}${location.search}`;
	const [projects, setProjects] = useState<Project[]>([]);
	const [loadingProjects, setLoadingProjects] = useState(false);
	const [creating, setCreating] = useState(false);
	const [searchTerm, setSearchTerm] = useState("");
	const [projectPage, setProjectPage] = useState(1);
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">(
		"existing",
	);
	const [selectedProjectId, setSelectedProjectId] = useState("");
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const [opengrepEnabled, setOpengrepEnabled] = useState(true);
	const [codeqlEnabled, setCodeqlEnabled] = useState(false);
	const [configEngine, setConfigEngine] = useState<StaticTool | null>(null);
	const [activeRules, setActiveRules] = useState<OpengrepRule[]>([]);
	const previousSearchTermRef = useRef("");

	const activeProjects = useMemo(
		() =>
			projects.filter((project) => project.is_active && isZipProject(project)),
		[projects],
	);

	const filteredProjects = useMemo(() => {
		if (!searchTerm.trim()) return activeProjects;
		const keyword = searchTerm.trim().toLowerCase();
		return activeProjects.filter(
			(project) =>
				project.name.toLowerCase().includes(keyword) ||
				(project.description || "").toLowerCase().includes(keyword),
		);
	}, [activeProjects, searchTerm]);

	const paginatedProjects = useMemo(
		() => paginateProjectCards(filteredProjects, projectPage),
		[filteredProjects, projectPage],
	);

	const selectedProject = activeProjects.find(
		(project) => project.id === selectedProjectId,
	);

	const dialogTitle = useMemo(() => {
		if (!lockMode) return "创建扫描";
		return "创建静态审计";
	}, [lockMode]);

	useEffect(() => {
		if (!open) return;
		setSearchTerm("");
		setProjectPage(1);
		previousSearchTermRef.current = "";
		setSourceMode("existing");
		setSelectedProjectId(preselectedProjectId || "");
		setNewProjectName("");
		setNewProjectFile(null);
		setOpengrepEnabled(true);
		setCodeqlEnabled(false);
		setConfigEngine(null);

		const loadProjects = async () => {
			try {
				setLoadingProjects(true);
				const data = await api.getProjects();
				setProjects(data);
			} catch (error) {
				console.error("加载项目失败:", error);
				toast.error("加载项目失败");
			} finally {
				setLoadingProjects(false);
			}
		};

		const loadRules = async () => {
			try {
				const rules = await getAllOpengrepRules({
					is_active: true,
					severity: "ERROR",
				});
				setActiveRules(rules.filter(isSevereCreateProjectScanRule));
			} catch (error) {
				console.error("加载启用规则失败:", error);
				toast.error("加载启用规则失败");
			}
		};

		void loadProjects();
		void loadRules();
	}, [open, preselectedProjectId]);

	useEffect(() => {
		if (!open) return;
		if (selectedProjectId) return;
		if (lockProjectSelection && preselectedProjectId) return;
		if (activeProjects.length === 0) return;
		setSelectedProjectId(activeProjects[0].id);
	}, [
		open,
		selectedProjectId,
		activeProjects,
		lockProjectSelection,
		preselectedProjectId,
	]);

	useEffect(() => {
		if (!open) return;
		if (!lockProjectSelection) return;
		if (!preselectedProjectId) return;
		if (selectedProjectId === preselectedProjectId) return;
		setSelectedProjectId(preselectedProjectId);
	}, [open, lockProjectSelection, preselectedProjectId, selectedProjectId]);

	useEffect(() => {
		if (!open) return;
		setProjectPage((currentPage) =>
			resolveProjectPageAfterSearchChange({
				currentPage,
				previousSearchTerm: previousSearchTermRef.current,
				nextSearchTerm: searchTerm,
			}),
		);
		previousSearchTermRef.current = searchTerm;
	}, [open, searchTerm]);

	useEffect(() => {
		if (projectPage === paginatedProjects.currentPage) return;
		setProjectPage(paginatedProjects.currentPage);
	}, [projectPage, paginatedProjects.currentPage]);

	const canCreate = useMemo(() => {
		const hasStaticEngine = hasSelectedPrimaryStaticEngine({
			opengrep: opengrepEnabled,
			codeql: codeqlEnabled,
		});
		if (sourceMode === "upload") {
			if (!newProjectName.trim() || !newProjectFile) return false;
			return hasStaticEngine;
		} else {
			if (!selectedProject) return false;
			if (!hasStaticEngine) return false;
			return isZipProject(selectedProject);
		}
	}, [
		sourceMode,
		newProjectName,
		newProjectFile,
		selectedProject,
		opengrepEnabled,
		codeqlEnabled,
	]);

	const createStaticTasksForProject = async (
		project: Project,
	): Promise<StaticTaskCreateResult> => {
		let opengrepTask: { id: string } | null = null;
		let codeqlTask: { id: string } | null = null;
		if (
			!hasSelectedPrimaryStaticEngine({
				opengrep: opengrepEnabled,
				codeql: codeqlEnabled,
			})
		) {
			throw new Error("请至少启用一个扫描引擎");
		}
		const taskNamePrefix = "静态分析";
		const staticBatchId = createStaticScanBatchId();

		if (opengrepEnabled) {
			const ruleIds = activeRules
				.filter(isSevereCreateProjectScanRule)
				.map((rule) => rule.id);
			if (ruleIds.length === 0) {
				throw new Error("当前没有启用严重规则，请先启用严重规则");
			}
			opengrepTask = await createOpengrepScanTask({
				project_id: project.id,
				name: appendStaticScanBatchMarker(
					`${taskNamePrefix}-Opengrep-${project.name}`,
					staticBatchId,
				),
				rule_ids: ruleIds,
				target_path: ".",
			});
		}
		if (codeqlEnabled) {
			const codeqlLanguages = normalizeCodeqlLanguages(
				project.programming_languages,
			);
			codeqlTask = await createCodeqlScanTask({
				project_id: project.id,
				name: appendStaticScanBatchMarker(
					`${taskNamePrefix}-CodeQL-${project.name}`,
					staticBatchId,
				),
				target_path: ".",
				languages: codeqlLanguages.length > 0 ? codeqlLanguages : undefined,
			});
		}
		const primaryTaskId = opengrepTask?.id ?? codeqlTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态审计任务创建失败");
		}

		const params = new URLSearchParams();
		if (opengrepTask) {
			params.set("opengrepTaskId", opengrepTask.id);
		}
		if (codeqlTask) {
			params.set("codeqlTaskId", codeqlTask.id);
			params.set("engine", "codeql");
		}
		return { primaryTaskId, params };
	};

	const handleNewProjectFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0] || null;
		if (!file) return;
		const validation = validateZipFile(file);
		if (!validation.valid) {
			toast.error(validation.error || "文件无效");
			event.target.value = "";
			return;
		}
		setNewProjectFile(file);
		const inferredName = stripCreateProjectScanArchiveSuffix(file.name).trim();
		if (inferredName) setNewProjectName(inferredName);
		event.target.value = "";
	};

	const handleCreate = async (action: "primary" | "secondary" = "primary") => {
		try {
			setCreating(true);
			if (sourceMode === "upload") {
				if (!newProjectName.trim() || !newProjectFile) {
					toast.error("请先上传项目并填写项目名");
					return;
				}

				let createdProject: Project | null = null;
				try {
					createdProject = await api.createProject({
						name: newProjectName.trim(),
						source_type: "zip",
						repository_type: "other",
						repository_url: undefined,
						default_branch: "main",
						programming_languages: [],
					} as any);

					const uploadResult = await uploadZipFile(
						createdProject.id,
						newProjectFile,
					);
					if (!uploadResult.success) {
						throw new Error(uploadResult.message || "压缩包上传失败");
					}

					const result = await createStaticTasksForProject(createdProject);
					onOpenChange(false);
					onTaskCreated?.();
					toast.success("静态审计任务已创建");
					if (action === "secondary") {
						onSecondaryCreateSuccess?.();
					} else if (navigateOnSuccess) {
						navigate(
							appendReturnTo(
								buildCreateProjectStaticTaskRoute(result),
								currentRoute,
							),
						);
					}
					return;
				} catch (error) {
					if (createdProject) {
						try {
							await api.deleteProject(createdProject.id);
						} catch (rollbackError) {
							console.error("回滚失败项目失败:", rollbackError);
						}
					}
					throw error;
				}
			}

			if (!selectedProject) {
				toast.error("请选择项目");
				return;
			}

			if (!isZipProject(selectedProject)) {
				toast.error("静态审计仅支持源码压缩包项目");
				return;
			}
			const zipInfo = await getZipFileInfo(selectedProject.id);
			if (!zipInfo.has_file) {
				toast.error("该项目未上传源码压缩包");
				return;
			}
			if (
				!hasSelectedPrimaryStaticEngine({
					opengrep: opengrepEnabled,
					codeql: codeqlEnabled,
				})
			) {
				toast.error("请至少启用一个扫描引擎");
				return;
			}

			const result = await createStaticTasksForProject(selectedProject);
			onOpenChange(false);
			onTaskCreated?.();
			toast.success("静态审计任务已创建");
			if (action === "secondary") {
				onSecondaryCreateSuccess?.();
			} else if (navigateOnSuccess) {
				navigate(
					appendReturnTo(
						buildCreateProjectStaticTaskRoute(result),
						currentRoute,
					),
				);
			}
		} catch (error) {
			const message = extractCreateProjectScanApiErrorMessage(error);
			toast.error(`创建失败: ${message}`);
		} finally {
			setCreating(false);
		}
	};

	const handleNavigateToEngineConfig = (engine: StaticTool) => {
		onOpenChange(false);
		navigate(buildScanEngineConfigRoute(engine));
	};
	const handleOpengrepEnabledChange = (enabled: boolean) => {
		setOpengrepEnabled(enabled);
		if (enabled) setCodeqlEnabled(false);
	};
	const handleCodeqlEnabledChange = (enabled: boolean) => {
		setCodeqlEnabled(enabled);
		if (enabled) setOpengrepEnabled(false);
	};
	return (
		<CreateProjectScanDialogContent
			open={open}
			onOpenChange={onOpenChange}
			dialogTitle={dialogTitle}
			allowUploadProject={allowUploadProject}
			sourceMode={sourceMode}
			setSourceMode={setSourceMode}
			creating={creating}
			lockMode={lockMode}
			loadingProjects={loadingProjects}
			lockProjectSelection={lockProjectSelection}
			searchTerm={searchTerm}
			setSearchTerm={setSearchTerm}
			filteredProjects={filteredProjects}
			visibleProjects={paginatedProjects.items}
			projectPage={paginatedProjects.currentPage}
			projectTotalPages={paginatedProjects.totalPages}
			setProjectPage={setProjectPage}
			selectedProject={selectedProject}
			selectedProjectId={selectedProjectId}
			setSelectedProjectId={setSelectedProjectId}
			newProjectName={newProjectName}
			setNewProjectName={setNewProjectName}
			newProjectFile={newProjectFile}
			handleNewProjectFileSelect={handleNewProjectFileSelect}
			opengrepEnabled={opengrepEnabled}
			setOpengrepEnabled={handleOpengrepEnabledChange}
			codeqlEnabled={codeqlEnabled}
			setCodeqlEnabled={handleCodeqlEnabledChange}
			showReturnButton={showReturnButton}
			onReturn={onReturn}
			primaryCreateLabel={primaryCreateLabel}
			secondaryCreateLabel={secondaryCreateLabel}
			createButtonVariant={createButtonVariant}
			canCreate={canCreate}
			handleCreate={handleCreate}
			configEngine={configEngine}
			setConfigEngine={setConfigEngine}
			onNavigateToEngineConfig={handleNavigateToEngineConfig}
		/>
	);
}
