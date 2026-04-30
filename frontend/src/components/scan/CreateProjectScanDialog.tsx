import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import { isZipProject } from "@/shared/utils/projectUtils";
import { createAgentTask, startAgentTask } from "@/shared/api/agentTasks";
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
import { INTELLIGENT_TASK_NAME_MARKER } from "@/features/tasks/services/taskActivities";
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
	invalidatePassedAgentPreflight,
	isRedactedApiKeyPlaceholder,
	mergeRetainedProjectForRetry,
	normalizeSecretSource,
	paginateProjectCards,
	resolveProjectPageAfterSearchChange,
	resolveQuickConfigAfterProviderChange,
	type LlmQuickConfig,
	usesSavedOrImportedSecret,
} from "./create-project-scan/llmGate";
import {
	CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP,
	buildCreateProjectScanSystemConfigUpdate,
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
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">(
		"existing",
	);
	const [selectedProjectId, setSelectedProjectId] = useState("");
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const [mode, setMode] = useState<ScanCreateMode>("static");
	const [targetFilesInput, setTargetFilesInput] = useState("");
	const [opengrepEnabled, setOpengrepEnabled] = useState(true);
	const [configEngine, setConfigEngine] = useState<StaticTool | null>(null);
	const [activeRules, setActiveRules] = useState<OpengrepRule[]>([]);

	const [showLlmQuickFixPanel, setShowLlmQuickFixPanel] = useState(false);
	const [llmProviderOptions, setLlmProviderOptions] = useState<
		LLMProviderItem[]
	>(() =>
		buildLlmProviderOptions({
			backendProviders: [],
			currentProviderId: "openai_compatible",
		}),
	);
	const [llmQuickConfig, setLlmQuickConfig] = useState<LlmQuickConfig>({
		provider: "openai_compatible",
		model: "",
		baseUrl: "",
		apiKey: "",
		apiKeySource: "none",
		hasSavedApiKey: false,
	});
	const [savedLlmQuickConfig, setSavedLlmQuickConfig] =
		useState<LlmQuickConfig | null>(null);
	const [llmQuickInitialized, setLlmQuickInitialized] = useState(false);
	const [quickFixBaseUrlTouched, setQuickFixBaseUrlTouched] = useState(false);
	const [agentPreflightPassed, setAgentPreflightPassed] = useState(false);
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
				hasPassedAgentPreflight: agentPreflightPassed,
			}),
		[
			llmProviderOptions,
			llmQuickConfig,
			savedLlmQuickConfig,
			agentPreflightPassed,
		],
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

	const buildQuickConfigFromSnapshot = (snapshot: {
		provider?: string;
		model?: string;
		baseUrl?: string;
		apiKey?: string;
		hasSavedApiKey?: boolean;
		secretSource?: string;
	}): LlmQuickConfig => {
		const rawApiKey = String(snapshot.apiKey || "").trim();
		const hasSavedApiKey = Boolean(snapshot.hasSavedApiKey);
		const apiKeySource = normalizeSecretSource(
			snapshot.secretSource,
			hasSavedApiKey,
		);
		return {
			provider: normalizeCreateProjectScanProvider(snapshot.provider || ""),
			model: String(snapshot.model || ""),
			baseUrl: String(snapshot.baseUrl || ""),
			apiKey: isRedactedApiKeyPlaceholder(rawApiKey) ? "" : rawApiKey,
			apiKeySource,
			hasSavedApiKey,
		};
	};

	const syncGateWithPreflightResult = async (
		preflightResult: AgentPreflightResult,
	) => {
		const providerOptions = await loadLlmProviderOptions(
			preflightResult.effectiveConfig.provider,
		);
		const effectiveQuickConfig = buildQuickConfigFromSnapshot(
			preflightResult.effectiveConfig,
		);
		const savedQuickConfig = preflightResult.savedConfig
			? buildQuickConfigFromSnapshot(preflightResult.savedConfig)
			: null;

		setLlmProviderOptions(providerOptions);
		setLlmQuickConfig(effectiveQuickConfig);
		setSavedLlmQuickConfig(savedQuickConfig);
		setQuickFixBaseUrlTouched(false);
		const hasPassedPreflight = Boolean(preflightResult.ok);
		const nextMessage = preflightResult.message;
		setAgentPreflightPassed(hasPassedPreflight);
		setQuickFixTestResult(null);
		setShowLlmQuickFixPanel(!hasPassedPreflight);
		setLastPreflightMessage(nextMessage);
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
			buildLlmProviderOptions({
				backendProviders: [],
				currentProviderId: "openai_compatible",
			}),
		);
		setLlmQuickConfig({
			provider: "openai_compatible",
			model: "",
			baseUrl: "",
			apiKey: "",
			apiKeySource: "none",
			hasSavedApiKey: false,
		});
		setSavedLlmQuickConfig(null);
		setLlmQuickInitialized(false);
		setQuickFixBaseUrlTouched(false);
		setAgentPreflightPassed(false);
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
			setAgentPreflightPassed(false);
			try {
				const preflightResult = await runAgentPreflightCheck();
				if (cancelled) return;
				await syncGateWithPreflightResult(preflightResult);
			} catch (error) {
				if (cancelled) return;
				console.error("加载 LLM 任务预检失败:", error);
				setShowLlmQuickFixPanel(true);
				setLastPreflightMessage(
					"加载 LLM 预检失败，请在下方补配并保存配置后重新预检。",
				);
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

	const buildAgentTaskPayload = (project: Project) => ({
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
			setLastPreflightMessage("请先完成智能审计预检，预检通过后才能创建任务。");
		}
	};

	const createAgentTaskForProject = async (project: Project) =>
		createAgentTask(buildAgentTaskPayload(project));

	const handleQuickFixProviderChange = (nextProvider: string) => {
		const nextConfig = resolveQuickConfigAfterProviderChange({
			providerOptions: llmProviderOptions,
			currentConfig: llmQuickConfig,
			nextProvider,
			hasManualBaseUrlOverride: quickFixBaseUrlTouched,
		});
		setLlmQuickConfig(nextConfig);
		setAgentPreflightPassed(
			invalidatePassedAgentPreflight({
				previousConfig: llmQuickConfig,
				nextConfig,
				hasPassedAgentPreflight: agentPreflightPassed,
			}),
		);
		setQuickFixTestResult(null);
		setLastPreflightMessage("配置已修改，请点击重新预检，系统将先保存配置。");
	};

	const handleQuickFixConfigChange = (
		key: keyof LlmQuickConfig,
		value: string,
	) => {
		if (key === "baseUrl") {
			setQuickFixBaseUrlTouched(true);
		}
		setLlmQuickConfig((previousConfig) => {
			const nextConfig = { ...previousConfig, [key]: value };
			setAgentPreflightPassed(
				invalidatePassedAgentPreflight({
					previousConfig,
					nextConfig,
					hasPassedAgentPreflight: agentPreflightPassed,
				}),
			);
			return nextConfig;
		});
		setQuickFixTestResult(null);
		setLastPreflightMessage("配置已修改，请点击重新预检，系统将先保存配置。");
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
		if (isRedactedApiKeyPlaceholder(llmQuickConfig.apiKey)) {
			return {
				ok: false,
				message: "Redacted API Key 占位符不能作为真实密钥提交",
			};
		}
		return { ok: true };
	};

	const persistQuickFixConfig = async (): Promise<LlmQuickConfig> => {
		setQuickFixSaving(true);
		try {
			const currentConfig = await api.getUserConfig();
			const currentLlmConfig = {
				...((currentConfig?.llmConfig as Record<string, unknown>) || {}),
			};
			delete currentLlmConfig.llmApiKey;
			for (const keyField of Object.values(
				CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP,
			)) {
				if (keyField) delete currentLlmConfig[keyField];
			}
			const provider = normalizeCreateProjectScanProvider(
				llmQuickConfig.provider,
			);
			const normalizedQuickConfig: LlmQuickConfig = {
				provider,
				model: llmQuickConfig.model.trim(),
				baseUrl: llmQuickConfig.baseUrl.trim(),
				apiKey: isRedactedApiKeyPlaceholder(llmQuickConfig.apiKey)
					? ""
					: llmQuickConfig.apiKey.trim(),
				apiKeySource: llmQuickConfig.apiKey.trim()
					? "entered"
					: normalizeSecretSource(
							llmQuickConfig.apiKeySource,
							llmQuickConfig.hasSavedApiKey,
						),
				hasSavedApiKey: llmQuickConfig.hasSavedApiKey,
			};
			const apiKey = normalizedQuickConfig.apiKey;
			const useSavedApiKey =
				usesSavedOrImportedSecret(normalizedQuickConfig) && !apiKey;
			const secretSource = apiKey
				? "entered"
				: normalizeSecretSource(
						normalizedQuickConfig.apiKeySource,
						normalizedQuickConfig.hasSavedApiKey,
					);
			const providerKeyField =
				CREATE_PROJECT_SCAN_PROVIDER_KEY_FIELD_MAP[provider];

			const nextLlmConfig: Record<string, unknown> = {
				...currentLlmConfig,
				llmProvider: provider,
				llmModel: normalizedQuickConfig.model,
				llmBaseUrl: normalizedQuickConfig.baseUrl,
				secretSource,
				useSavedApiKey,
				...(apiKey ? { llmApiKey: apiKey } : {}),
			};
			if (providerKeyField && apiKey) {
				nextLlmConfig[providerKeyField] = apiKey;
			}

			await api.updateUserConfig(
				buildCreateProjectScanSystemConfigUpdate({
					currentConfig,
					nextLlmConfig,
				}),
			);
			setLlmQuickConfig(normalizedQuickConfig);
			setSavedLlmQuickConfig(normalizedQuickConfig);
			setAgentPreflightPassed(false);
			setQuickFixTestResult(null);
			setShowLlmQuickFixPanel(true);
			return normalizedQuickConfig;
		} finally {
			setQuickFixSaving(false);
		}
	};

	const handleQuickFixTest = async () => {
		const validation = validateQuickFixFields();
		if (!validation.ok) {
			const message = validation.message || "请先补全 LLM 必填配置";
			setLastPreflightMessage(`${message}。`);
			if (validation.message) toast.error(validation.message);
			return;
		}

		setQuickFixTesting(true);
		setQuickFixTestResult(null);
		try {
			if (llmGateStatus.hasUnsavedChanges) {
				setLastPreflightMessage("配置已修改，正在保存并重新预检。");
				await persistQuickFixConfig();
			}
			const preflightResult = await runAgentPreflightCheck();
			await syncGateWithPreflightResult(preflightResult);
			const success = Boolean(preflightResult.ok);
			const message = success
				? "智能审计预检通过，现在可以创建任务。"
				: preflightResult.message || "未知错误";
			setQuickFixTestResult({
				success,
				message,
				model: preflightResult.effectiveConfig.model,
			});
			setLastPreflightMessage(message);
			if (success) {
				toast.success(
					`智能审计预检通过：${preflightResult.effectiveConfig.model}`,
			);
			} else {
				toast.error(`智能审计预检失败：${message}`);
			}
		} catch (error) {
			const message = extractCreateProjectScanApiErrorMessage(error);
			setQuickFixTestResult({ success: false, message });
			setAgentPreflightPassed(false);
			setLastPreflightMessage(`智能审计预检失败：${message}`);
			toast.error(`智能审计预检失败：${message}`);
		} finally {
			setQuickFixTesting(false);
		}
	};

	const handleCreateAgentTaskForProject = async (
		project: Project,
		action: "primary" | "secondary",
	) => {
		const agentTask = await createAgentTaskForProject(project);
		startAgentTask(agentTask.id).catch(console.error);
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

	const retainUploadedProjectForAgentRetry = (
		project: Project,
		message: string,
	) => {
		setProjects((currentProjects) =>
			mergeRetainedProjectForRetry(currentProjects, project),
		);
		setSourceMode("existing");
		setSelectedProjectId(project.id);
		setSearchTerm("");
		setProjectPage(1);
		setNewProjectName("");
		setNewProjectFile(null);
		setLastPreflightMessage(message);
		setShowLlmQuickFixPanel(true);
		toast.error(message);
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
			setLastPreflightMessage("LLM 缺少必填配置，请先补全并保存，再重新预检。");
			return false;
		}
		if (llmGateStatus.hasUnsavedChanges) {
			setShowLlmQuickFixPanel(true);
			setLastPreflightMessage(
				"当前 LLM 配置有未保存改动，请先保存，再重新预检。",
			);
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
				let uploadSucceeded = false;
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
					uploadSucceeded = true;

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
						retainUploadedProjectForAgentRetry(
							createdProject,
							`项目“${createdProject.name}”已保留，智能审计预检未通过。请修复预检后重试。`,
						);
						return;
					}

					await handleCreateAgentTaskForProject(createdProject, action);
					return;
				} catch (error) {
					if (mode === "agent" && createdProject && uploadSucceeded) {
						const message = extractCreateProjectScanApiErrorMessage(error);
						retainUploadedProjectForAgentRetry(
							createdProject,
							`项目“${createdProject.name}”已保留，智能审计创建失败：${message}。请修复预检后重试。`,
						);
						return;
					}
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
				mode === "agent"
					? `智能审计创建失败：${message}`
					: `创建失败: ${message}`;
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
	const handleNavigateToAdvancedLlmConfig = () => {
		onOpenChange(false);
		navigate("/scan-config/intelligent-engine");
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
			onNavigateToAdvancedLlmConfig={handleNavigateToAdvancedLlmConfig}
		/>
	);
}
