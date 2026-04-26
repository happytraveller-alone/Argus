import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import { isZipProject } from "@/shared/utils/projectUtils";
import { createAgentTask } from "@/shared/api/agentTasks";
import {
	runAgentPreflightCheck,
	type AgentPreflightResult,
	type PreflightMissingField,
} from "@/shared/api/agentPreflight";
import {
	createOpengrepScanTask,
	getAllOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import { getZipFileInfo, uploadZipFile } from "@/shared/utils/zipStorage";
import { validateZipFile } from "@/features/projects/services/repoZipScan";
import {
	INTELLIGENT_TASK_NAME_MARKER,
} from "@/features/tasks/services/taskActivities";
import { appendReturnTo } from "@/shared/utils/findingRoute";
import {
	appendStaticScanBatchMarker,
	createStaticScanBatchId,
} from "@/shared/utils/staticScanBatch";
import type { StaticTool } from "@/components/agent/AgentModeSelector";
import CreateProjectScanDialogContent from "./create-project-scan/Content";
import { buildScanEngineConfigRoute } from "@/shared/constants/scanEngines";
import {
	buildLlmProviderOptions,
	type LLMProviderItem,
} from "@/shared/llm/providerCatalog";
import {
	getLlmQuickGateStatus,
	invalidateSuccessfulManualTest,
	paginateProjectCards,
	resolveProjectPageAfterSearchChange,
	resolveQuickConfigAfterProviderChange,
	type LlmQuickConfig,
} from "./create-project-scan/llmGate";
import {
	CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP,
	buildCreateProjectStaticTaskRoute,
	extractCreateProjectScanApiErrorMessage,
	isSevereCreateProjectScanRule,
	normalizeCreateProjectScanProvider,
	stripCreateProjectScanArchiveSuffix,
} from "./create-project-scan/utils";

export type ScanCreateMode = "static" | "agent";

interface CreateProjectScanDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated?: () => void;
	preselectedProjectId?: string;
	lockProjectSelection?: boolean;
	initialMode?: ScanCreateMode;
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
	preselectedProjectId,
	lockProjectSelection = false,
	initialMode = "static",
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
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">("existing");
	const [selectedProjectId, setSelectedProjectId] = useState("");
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const [mode, setMode] = useState<ScanCreateMode>("static");
	const [targetFilesInput, setTargetFilesInput] = useState("");
	const [opengrepEnabled, setOpengrepEnabled] = useState(true);
	const [configEngine, setConfigEngine] = useState<StaticTool | null>(null);
	const [activeRules, setActiveRules] = useState<OpengrepRule[]>([]);

	const [showLlmQuickFixPanel, setShowLlmQuickFixPanel] = useState(false);
	const [llmProviderOptions, setLlmProviderOptions] = useState<LLMProviderItem[]>(
		() => buildLlmProviderOptions({ backendProviders: [], currentProviderId: "openai" }),
	);
	const [llmQuickConfig, setLlmQuickConfig] = useState<LlmQuickConfig>({
		provider: "openai",
		model: "",
		baseUrl: "",
		apiKey: "",
	});
	const [savedLlmQuickConfig, setSavedLlmQuickConfig] =
		useState<LlmQuickConfig | null>(null);
	const [llmQuickInitialized, setLlmQuickInitialized] = useState(false);
	const [quickFixBaseUrlTouched, setQuickFixBaseUrlTouched] = useState(false);
	const [quickFixManualTestPassed, setQuickFixManualTestPassed] = useState(false);
	const [quickFixTesting, setQuickFixTesting] = useState(false);
	const [quickFixSaving, setQuickFixSaving] = useState(false);
	const [quickFixPanelOpening, setQuickFixPanelOpening] = useState(false);
	const [quickFixTestResult, setQuickFixTestResult] = useState<{
		success: boolean;
		message: string;
		model?: string;
	} | null>(null);
	const [lastPreflightMessage, setLastPreflightMessage] = useState("");
	const previousSearchTermRef = useRef("");

	const activeProjects = useMemo(
		() => projects.filter((project) => project.is_active && isZipProject(project)),
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

	const parsedTargetFiles = useMemo(
		() =>
			targetFilesInput
				.split(/\n|,/g)
				.map((item) => item.trim())
				.filter(Boolean),
		[targetFilesInput],
	);

	const dialogTitle = useMemo(() => {
		if (!lockMode) return "创建扫描";
		if (initialMode === "agent") return "创建智能审计";
		return "创建静态审计";
	}, [initialMode, lockMode]);

	const isLlmMode = mode === "agent";
	const llmGateStatus = useMemo(
		() =>
			getLlmQuickGateStatus({
				providerOptions: llmProviderOptions,
				currentConfig: llmQuickConfig,
				savedConfig: savedLlmQuickConfig,
				hasSuccessfulManualTest: quickFixManualTestPassed,
			}),
		[llmProviderOptions, llmQuickConfig, savedLlmQuickConfig, quickFixManualTestPassed],
	);

	const loadLlmProviderOptions = async (currentProviderId: string) => {
		const providerResponse = await api
			.getLLMProviders()
			.catch(() => ({ providers: [] as LLMProviderItem[] }));
		return buildLlmProviderOptions({
			backendProviders: providerResponse.providers || [],
			currentProviderId,
		});
	};

	const syncGateWithPreflightResult = async (
		preflightResult: AgentPreflightResult,
	) => {
		const providerOptions = await loadLlmProviderOptions(
			preflightResult.effectiveConfig.provider,
		);
		const effectiveQuickConfig: LlmQuickConfig = {
			provider: normalizeCreateProjectScanProvider(
				preflightResult.effectiveConfig.provider,
			),
			model: String(preflightResult.effectiveConfig.model || ""),
			baseUrl: String(preflightResult.effectiveConfig.baseUrl || ""),
			apiKey: String(preflightResult.effectiveConfig.apiKey || ""),
		};
		const savedQuickConfig = preflightResult.savedConfig
			? {
					provider: normalizeCreateProjectScanProvider(
						preflightResult.savedConfig.provider,
					),
					model: String(preflightResult.savedConfig.model || ""),
					baseUrl: String(preflightResult.savedConfig.baseUrl || ""),
					apiKey: String(preflightResult.savedConfig.apiKey || ""),
				}
			: null;

		setLlmProviderOptions(providerOptions);
		setLlmQuickConfig(effectiveQuickConfig);
		setSavedLlmQuickConfig(savedQuickConfig);
		setQuickFixBaseUrlTouched(false);
		setQuickFixManualTestPassed(preflightResult.ok);
		setQuickFixTestResult(null);
		setShowLlmQuickFixPanel(!preflightResult.ok);
		setLastPreflightMessage(preflightResult.message);
		return preflightResult;
	};

	useEffect(() => {
		if (!open) return;
		setSearchTerm("");
		setProjectPage(1);
		previousSearchTermRef.current = "";
		setSourceMode("existing");
		setSelectedProjectId(preselectedProjectId || "");
		setNewProjectName("");
		setNewProjectFile(null);
		setMode(initialMode || "static");
		setTargetFilesInput("");
		setOpengrepEnabled(true);
		setConfigEngine(null);
		setShowLlmQuickFixPanel(false);
		setLlmProviderOptions(
			buildLlmProviderOptions({ backendProviders: [], currentProviderId: "openai" }),
		);
		setLlmQuickConfig({
			provider: "openai",
			model: "",
			baseUrl: "",
			apiKey: "",
		});
		setSavedLlmQuickConfig(null);
		setLlmQuickInitialized(false);
		setQuickFixBaseUrlTouched(false);
		setQuickFixManualTestPassed(false);
		setQuickFixTestResult(null);
		setLastPreflightMessage("");

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
	}, [open, preselectedProjectId, initialMode]);

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

	useEffect(() => {
		if (!open || !isLlmMode || llmQuickInitialized) return;
		let cancelled = false;

		const initializeLlmGate = async () => {
			setQuickFixPanelOpening(true);
			setQuickFixTestResult(null);
			setQuickFixManualTestPassed(false);
			try {
				const preflightResult = await runAgentPreflightCheck();
				if (cancelled) return;
				await syncGateWithPreflightResult(preflightResult);
			} catch (error) {
				if (cancelled) return;
				console.error("加载 LLM 任务预检失败:", error);
				setShowLlmQuickFixPanel(true);
				setLastPreflightMessage("加载 LLM 配置失败，请在下方重新补配并测试连接。");
			} finally {
				if (cancelled) return;
				setLlmQuickInitialized(true);
				setQuickFixPanelOpening(false);
			}
		};

		void initializeLlmGate();
		return () => {
			cancelled = true;
		};
	}, [open, isLlmMode, llmQuickInitialized]);

	const canCreate = useMemo(() => {
		let baseCanCreate = false;
		if (sourceMode === "upload") {
			if (!newProjectName.trim() || !newProjectFile) return false;
			if (mode === "agent") {
				baseCanCreate = true;
			} else {
				baseCanCreate = opengrepEnabled;
			}
		} else {
			if (!selectedProject) return false;
			if (mode === "static" && !opengrepEnabled) return false;
			baseCanCreate = isZipProject(selectedProject);
		}
		if (!baseCanCreate) return false;
		if (!isLlmMode) return true;
		if (!llmQuickInitialized || quickFixPanelOpening) return false;
		return llmGateStatus.canCreate;
	}, [
		sourceMode,
		newProjectName,
		newProjectFile,
		selectedProject,
		mode,
		opengrepEnabled,
		isLlmMode,
		llmQuickInitialized,
		quickFixPanelOpening,
		llmGateStatus.canCreate,
	]);

	const createStaticTasksForProject = async (
		project: Project,
	): Promise<StaticTaskCreateResult> => {
		let opengrepTask: { id: string } | null = null;
		if (!opengrepEnabled) {
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
		const primaryTaskId = opengrepTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态审计任务创建失败");
		}

		const params = new URLSearchParams();
		if (opengrepTask) {
			params.set("opengrepTaskId", opengrepTask.id);
		}
		return { primaryTaskId, params };
	};

	const buildAgentTaskPayload = (
		project: Project,
	) => ({
		project_id: project.id,
		name: `智能审计-${project.name}`,
		description: `${INTELLIGENT_TASK_NAME_MARKER}智能审计任务`,
		target_files: parsedTargetFiles.length > 0 ? parsedTargetFiles : undefined,
		use_prompt_skills: true,
		verification_level: "analysis_with_poc_plan" as const,
	});

	const openLlmQuickFixPanelManual = async () => {
		if (showLlmQuickFixPanel) {
			setShowLlmQuickFixPanel(false);
			return;
		}
		setShowLlmQuickFixPanel(true);
		if (!lastPreflightMessage) {
			setLastPreflightMessage("请先手动测试连接，测试成功后才能创建任务。");
		}
	};

	const createAgentTaskForProject = async (
		project: Project,
	) => createAgentTask(buildAgentTaskPayload(project));

	const handleQuickFixProviderChange = (nextProvider: string) => {
		const nextConfig = resolveQuickConfigAfterProviderChange({
			providerOptions: llmProviderOptions,
			currentConfig: llmQuickConfig,
			nextProvider,
			hasManualBaseUrlOverride: quickFixBaseUrlTouched,
		});
		setLlmQuickConfig(nextConfig);
		setQuickFixManualTestPassed(
			invalidateSuccessfulManualTest({
				previousConfig: llmQuickConfig,
				nextConfig,
				hasSuccessfulManualTest: quickFixManualTestPassed,
			}),
		);
		setQuickFixTestResult(null);
		setLastPreflightMessage("配置已修改，请先保存，再手动测试连接。");
	};

	const handleQuickFixConfigChange = (key: keyof LlmQuickConfig, value: string) => {
		const nextConfig = { ...llmQuickConfig, [key]: value };
		setLlmQuickConfig(nextConfig);
		if (key === "baseUrl") {
			setQuickFixBaseUrlTouched(true);
		}
		setQuickFixManualTestPassed(
			invalidateSuccessfulManualTest({
				previousConfig: llmQuickConfig,
				nextConfig,
				hasSuccessfulManualTest: quickFixManualTestPassed,
			}),
		);
		setQuickFixTestResult(null);
		setLastPreflightMessage("配置已修改，请先保存，再手动测试连接。");
	};

	const validateQuickFixFields = (): { ok: boolean; message?: string } => {
		if (!llmQuickInitialized && quickFixPanelOpening) {
			return { ok: false, message: "LLM 配置加载中，请稍候" };
		}
		if (llmGateStatus.missingFields.includes("llmModel")) {
			return { ok: false, message: "请先填写模型" };
		}
		if (llmGateStatus.missingFields.includes("llmBaseUrl")) {
			return { ok: false, message: "请先填写 Base URL" };
		}
		if (llmGateStatus.missingFields.includes("llmApiKey")) {
			return { ok: false, message: "请先填写 API Key" };
		}
		return { ok: true };
	};

	const handleQuickFixTest = async () => {
		const validation = validateQuickFixFields();
		if (!validation.ok) {
			const message = validation.message || "请先补全 LLM 必填配置";
			setLastPreflightMessage(`${message}。`);
			if (validation.message) toast.error(validation.message);
			return;
		}

		if (!llmGateStatus.canTest) {
			const message = llmGateStatus.testBlockMessage || "请先补全 LLM 必填配置。";
			setLastPreflightMessage(message);
			toast.error(message);
			return;
		}

		const provider = normalizeCreateProjectScanProvider(llmQuickConfig.provider);
		const payload = {
			provider,
			apiKey: llmQuickConfig.apiKey.trim(),
			model: llmQuickConfig.model.trim(),
			baseUrl: llmQuickConfig.baseUrl.trim(),
		};

		setQuickFixTesting(true);
		setQuickFixTestResult(null);
		try {
			const result = await api.testLLMConnection(payload);
			setQuickFixTestResult(result);
			setQuickFixManualTestPassed(Boolean(result.success));
			setLastPreflightMessage(
				result.success
					? "LLM 配置测试通过，现在可以创建任务。"
					: `LLM 测试失败：${result.message || "未知错误"}`,
			);
			if (result.success) {
				toast.success(`测试成功：${result.model || payload.model}`);
				// 测试通过后自动保存配置到后端，确保创建任务时使用已验证的配置
				try {
					const currentUserConfig = await api.getUserConfig();
					const currentLlmConfig =
						(currentUserConfig?.llmConfig as Record<string, unknown>) || {};
					const normalizedQuickConfig: LlmQuickConfig = {
						provider,
						model: payload.model,
						baseUrl: payload.baseUrl,
						apiKey: payload.apiKey,
					};
					const providerKeyField =
						CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP[provider];
					const nextLlmConfig: Record<string, unknown> = {
						...currentLlmConfig,
						llmProvider: provider,
						llmModel: normalizedQuickConfig.model,
						llmBaseUrl: normalizedQuickConfig.baseUrl,
						llmApiKey: normalizedQuickConfig.apiKey,
					};
					if (providerKeyField) {
						nextLlmConfig[providerKeyField] = normalizedQuickConfig.apiKey;
					}
					await api.updateUserConfig({ llmConfig: nextLlmConfig });
					setLlmQuickConfig(normalizedQuickConfig);
					setSavedLlmQuickConfig(normalizedQuickConfig);
				} catch (saveError) {
					console.error("测试通过后自动保存配置失败:", saveError);
				}
			} else {
				toast.error(`测试失败：${result.message || "未知错误"}`);
			}
		} catch (error) {
			const message = extractCreateProjectScanApiErrorMessage(error);
			setQuickFixTestResult({ success: false, message });
			setQuickFixManualTestPassed(false);
			setLastPreflightMessage(`LLM 测试失败：${message}`);
			toast.error(`测试失败：${message}`);
		} finally {
			setQuickFixTesting(false);
		}
	};

	const handleQuickFixSave = async () => {
		const validation = validateQuickFixFields();
		if (!validation.ok) {
			if (validation.message) toast.error(validation.message);
			return;
		}

		setQuickFixSaving(true);
		try {
			const currentConfig = await api.getUserConfig();
			const currentLlmConfig =
				(currentConfig?.llmConfig as Record<string, unknown>) || {};
			const provider = normalizeCreateProjectScanProvider(llmQuickConfig.provider);
			const normalizedQuickConfig: LlmQuickConfig = {
				provider,
				model: llmQuickConfig.model.trim(),
				baseUrl: llmQuickConfig.baseUrl.trim(),
				apiKey: llmQuickConfig.apiKey.trim(),
			};
			const apiKey = normalizedQuickConfig.apiKey;
			const providerKeyField =
				CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP[provider];

			const nextLlmConfig: Record<string, unknown> = {
				...currentLlmConfig,
				llmProvider: provider,
				llmModel: normalizedQuickConfig.model,
				llmBaseUrl: normalizedQuickConfig.baseUrl,
				llmApiKey: apiKey,
			};
			if (providerKeyField) {
				nextLlmConfig[providerKeyField] = apiKey;
			}

			await api.updateUserConfig({ llmConfig: nextLlmConfig });
			setLlmQuickConfig(normalizedQuickConfig);
			setSavedLlmQuickConfig(normalizedQuickConfig);
			setQuickFixManualTestPassed(true);
			setQuickFixTestResult(null);
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage(
				"LLM 配置已保存，请手动测试连接；测试成功后才能创建任务。",
			);
			toast.success("LLM 配置已保存，请继续测试连接");
		} catch (error) {
			setLastPreflightMessage(
				`保存失败：${extractCreateProjectScanApiErrorMessage(error)}`,
			);
			toast.error(
				`保存失败：${extractCreateProjectScanApiErrorMessage(error)}`,
			);
		} finally {
			setQuickFixSaving(false);
		}
	};

	const handleCreateAgentTaskForProject = async (
		project: Project,
		action: "primary" | "secondary",
	) => {
		const agentTask = await createAgentTaskForProject(project);
		onOpenChange(false);
		onTaskCreated?.();
		toast.success("智能审计任务已创建");
		if (action === "secondary") {
			onSecondaryCreateSuccess?.();
		} else if (navigateOnSuccess) {
			navigate(`/agent-audit/${agentTask.id}`);
		}
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

	const ensureAgentGatePassed = async () => {
		if (!isLlmMode) return true;
		if (!llmQuickInitialized || quickFixPanelOpening) {
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage("LLM 配置加载中，请稍候后重试。");
			return false;
		}
		if (llmGateStatus.missingFields.length > 0) {
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage("LLM 缺少必填配置，请先补全并保存，再手动测试连接。");
			return false;
		}
		if (llmGateStatus.hasUnsavedChanges) {
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage("当前 LLM 配置有未保存改动，请先保存，再手动测试连接。");
			return false;
		}
		if (!quickFixManualTestPassed) {
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage("请先手动测试连接，测试成功后才能创建任务。");
			return false;
		}

		const preflightResult = await runAgentPreflightCheck();
		await syncGateWithPreflightResult(preflightResult);
		if (!preflightResult.ok) {
			setShowLlmQuickFixPanel(true);
			return false;
		}
		return true;
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

					const uploadResult = await uploadZipFile(createdProject.id, newProjectFile);
					if (!uploadResult.success) {
						throw new Error(uploadResult.message || "压缩包上传失败");
					}

					if (mode === "static") {
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
					}

					if (!(await ensureAgentGatePassed())) {
						return;
					}

					await handleCreateAgentTaskForProject(createdProject, action);
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

			if (mode === "static") {
				if (!isZipProject(selectedProject)) {
					toast.error("静态审计仅支持源码压缩包项目");
					return;
				}
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
				if (!opengrepEnabled) {
					toast.error("请至少启用一个扫描引擎");
					return;
				}
			}

			if (mode === "static") {
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
				return;
			}

			if (!(await ensureAgentGatePassed())) {
				return;
			}

			if (isZipProject(selectedProject)) {
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
			}

			await handleCreateAgentTaskForProject(selectedProject, action);
		} catch (error) {
			const message = extractCreateProjectScanApiErrorMessage(error);
			const failureText =
				mode === "agent" ? `智能审计创建失败：${message}` : `创建失败: ${message}`;
			toast.error(failureText);
		} finally {
			setCreating(false);
		}
	};

	const missingFieldClass = (field: PreflightMissingField) =>
			llmGateStatus.missingFields.includes(field)
				? "border-rose-500/60 focus-visible:border-rose-500/70"
				: "";
	const handleNavigateToEngineConfig = (engine: StaticTool) => {
		onOpenChange(false);
		navigate(buildScanEngineConfigRoute(engine));
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
			mode={mode}
			setMode={setMode}
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
			setOpengrepEnabled={setOpengrepEnabled}
			gitleaksEnabled={false}
			setGitleaksEnabled={() => {}}
			banditEnabled={false}
			setBanditEnabled={() => {}}
			phpstanEnabled={false}
			setPhpstanEnabled={() => {}}
			pmdEnabled={false}
			setPmdEnabled={() => {}}
			isPmdBlockedProject={false}
			pmdBlockedMessage=""
			showLlmQuickFixPanel={showLlmQuickFixPanel}
			openLlmQuickFixPanelManual={openLlmQuickFixPanelManual}
			quickFixSaving={quickFixSaving}
				quickFixTesting={quickFixTesting}
				quickFixPanelOpening={quickFixPanelOpening}
				lastPreflightMessage={lastPreflightMessage}
				llmProviderOptions={llmProviderOptions}
				llmQuickConfig={llmQuickConfig}
				missingFieldClass={missingFieldClass}
				handleQuickFixProviderChange={handleQuickFixProviderChange}
				handleQuickFixConfigChange={handleQuickFixConfigChange}
				quickFixTestResult={quickFixTestResult}
				disableQuickFixTest={quickFixPanelOpening}
				llmTestBlockedMessage={llmGateStatus.testBlockMessage}
				handleQuickFixTest={handleQuickFixTest}
				handleQuickFixSave={handleQuickFixSave}
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
