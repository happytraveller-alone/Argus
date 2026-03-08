import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
	Bot,
	CheckCircle2,
	Layers,
	Loader2,
	Shield,
	TerminalSquare,
	Upload,
	Zap,
} from "lucide-react";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";
import { isRepositoryProject, isZipProject } from "@/shared/utils/projectUtils";
import { createAgentTask } from "@/shared/api/agentTasks";
import { type PreflightMissingField } from "@/shared/api/agentPreflight";
import {
	createOpengrepScanTask,
	getOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import { createGitleaksScanTask } from "@/shared/api/gitleaks";
import { getZipFileInfo, uploadZipFile } from "@/shared/utils/zipStorage";
import { validateZipFile } from "@/features/projects/services/repoZipScan";
import {
	HYBRID_TASK_NAME_MARKER,
	INTELLIGENT_TASK_NAME_MARKER,
} from "@/features/tasks/services/taskActivities";
import { useI18n } from "@/shared/i18n";
import { appendReturnTo } from "@/shared/utils/findingRoute";

export type ScanCreateMode = "static" | "agent" | "hybrid";

interface CreateProjectScanDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated?: () => void;
	preselectedProjectId?: string;
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

interface LlmQuickConfig {
	provider: string;
	model: string;
	baseUrl: string;
	apiKey: string;
}

const PROVIDER_KEY_FIELD_MAP: Record<string, string> = {
	openai: "openaiApiKey",
	openrouter: "openaiApiKey",
	azure_openai: "openaiApiKey",
	custom: "openaiApiKey",
	anthropic: "claudeApiKey",
	claude: "claudeApiKey",
	gemini: "geminiApiKey",
	qwen: "qwenApiKey",
	deepseek: "deepseekApiKey",
	zhipu: "zhipuApiKey",
	moonshot: "moonshotApiKey",
	baidu: "baiduApiKey",
	minimax: "minimaxApiKey",
	doubao: "doubaoApiKey",
};

const normalizeProvider = (provider: string | undefined | null) => {
	const normalized = (provider || "").trim().toLowerCase();
	if (!normalized) return "openai";
	if (normalized === "claude") return "anthropic";
	return normalized;
};

const resolveEffectiveApiKey = (
	provider: string,
	llmConfig: Record<string, unknown>,
): string => {
	const directKey = String(llmConfig.llmApiKey || "").trim();
	if (directKey) return directKey;

	const providerKeyField = PROVIDER_KEY_FIELD_MAP[provider];
	if (!providerKeyField) return "";
	return String(llmConfig[providerKeyField] || "").trim();
};

const extractApiErrorMessage = (error: unknown): string => {
	if (error instanceof Error) {
		const detail = (error as any)?.response?.data?.detail;
		if (typeof detail === "string" && detail.trim()) return detail;
		return error.message || "未知错误";
	}
	const detail = (error as any)?.response?.data?.detail;
	if (typeof detail === "string" && detail.trim()) return detail;
	return "未知错误";
};

const isSevereRule = (rule: OpengrepRule) =>
	String(rule.severity || "").toUpperCase() === "ERROR";

const buildStaticTaskRoute = (result: StaticTaskCreateResult) =>
	`/static-analysis/${result.primaryTaskId}${
		result.params.toString() ? `?${result.params.toString()}` : ""
	}`;



export default function CreateProjectScanDialog({
	open,
	onOpenChange,
	onTaskCreated,
	preselectedProjectId,
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
	const { t } = useI18n();
	const [projects, setProjects] = useState<Project[]>([]);
	const [loadingProjects, setLoadingProjects] = useState(false);
	const [creating, setCreating] = useState(false);
	const [searchTerm, setSearchTerm] = useState("");
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">("existing");
	const [selectedProjectId, setSelectedProjectId] = useState("");
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const [mode, setMode] = useState<ScanCreateMode>("static");
	const [targetFilesInput, setTargetFilesInput] = useState("");
	const [branchName, setBranchName] = useState("main");
	const [opengrepEnabled, setOpengrepEnabled] = useState(true);
	const [gitleaksEnabled, setGitleaksEnabled] = useState(false);
	const [activeRules, setActiveRules] = useState<OpengrepRule[]>([]);
	const [loadingRules, setLoadingRules] = useState(false);

	const [showLlmQuickFixPanel, setShowLlmQuickFixPanel] = useState(false);
	const [llmQuickConfig, setLlmQuickConfig] = useState<LlmQuickConfig>({
		provider: "openai",
		model: "",
		baseUrl: "",
		apiKey: "",
	});
	const [quickFixMissingFields, setQuickFixMissingFields] = useState<
		PreflightMissingField[]
	>([]);
	const [quickFixTesting, setQuickFixTesting] = useState(false);
	const [quickFixSaving, setQuickFixSaving] = useState(false);
	const [quickFixPanelOpening, setQuickFixPanelOpening] = useState(false);
	const [quickFixTestResult, setQuickFixTestResult] = useState<{
		success: boolean;
		message: string;
		model?: string;
	} | null>(null);
	const [lastPreflightMessage, setLastPreflightMessage] = useState("");

	const activeProjects = useMemo(
		() => projects.filter((project) => project.is_active),
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
		if (initialMode === "agent") return "创建智能扫描";
		if (initialMode === "hybrid") return "创建混合扫描";
		return "创建静态扫描";
	}, [initialMode, lockMode]);

	useEffect(() => {
		if (!open) return;
		setSearchTerm("");
		setSourceMode("existing");
		setSelectedProjectId(preselectedProjectId || "");
		setNewProjectName("");
		setNewProjectFile(null);
		setMode(initialMode || "static");
		setTargetFilesInput("");
		setBranchName("main");
		setOpengrepEnabled(true);
		setGitleaksEnabled(false);
		setShowLlmQuickFixPanel(false);
		setQuickFixMissingFields([]);
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
				setLoadingRules(true);
				const rules = await getOpengrepRules({ is_active: true });
				setActiveRules(rules.filter(isSevereRule));
			} catch (error) {
				console.error("加载启用规则失败:", error);
				toast.error("加载启用规则失败");
			} finally {
				setLoadingRules(false);
			}
		};

		void loadProjects();
		void loadRules();
	}, [open, preselectedProjectId, initialMode]);

	useEffect(() => {
		if (!open) return;
		if (selectedProjectId) return;
		if (activeProjects.length === 0) return;
		setSelectedProjectId(activeProjects[0].id);
	}, [open, selectedProjectId, activeProjects]);

	useEffect(() => {
		if (!selectedProject) return;
		setBranchName(selectedProject.default_branch || "main");
	}, [selectedProject?.id]);

	const canCreate = useMemo(() => {
		if (sourceMode === "upload") {
			if (!newProjectName.trim() || !newProjectFile) return false;
			if (mode === "agent") return true;
			return opengrepEnabled || gitleaksEnabled;
		}

		if (!selectedProject) return false;
		if (mode === "static" || mode === "hybrid") {
			if (!opengrepEnabled && !gitleaksEnabled) return false;
		}
		if (mode === "agent" && isRepositoryProject(selectedProject)) {
			return Boolean(branchName.trim());
		}
		if (mode === "hybrid" && !isZipProject(selectedProject)) {
			return false;
		}
		return true;
	}, [
		sourceMode,
		newProjectName,
		newProjectFile,
		selectedProject,
		mode,
		opengrepEnabled,
		gitleaksEnabled,
		branchName,
	]);

	const createStaticTasksForProject = async (
		project: Project,
	): Promise<StaticTaskCreateResult> => {
		let opengrepTask: { id: string } | null = null;
		let gitleaksTask: { id: string } | null = null;
		const taskNamePrefix = "静态分析";

		if (opengrepEnabled) {
			const ruleIds = activeRules.filter(isSevereRule).map((rule) => rule.id);
			if (ruleIds.length === 0) {
				throw new Error("当前没有启用严重规则，请先启用严重规则");
			}
			opengrepTask = await createOpengrepScanTask({
				project_id: project.id,
				name: `${taskNamePrefix}-Opengrep-${project.name}`,
				rule_ids: ruleIds,
				target_path: ".",
			});
		}

		if (gitleaksEnabled) {
			gitleaksTask = await createGitleaksScanTask({
				project_id: project.id,
				name: `${taskNamePrefix}-Gitleaks-${project.name}`,
				target_path: ".",
				no_git: true,
			});
		}

		const primaryTaskId = opengrepTask?.id || gitleaksTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态扫描任务创建失败");
		}

		const params = new URLSearchParams();
		if (opengrepTask && gitleaksTask) {
			params.set("opengrepTaskId", opengrepTask.id);
			params.set("gitleaksTaskId", gitleaksTask.id);
		} else if (!opengrepTask && gitleaksTask) {
			params.set("tool", "gitleaks");
		}
		return { primaryTaskId, params };
	};

	const buildAgentTaskPayload = (
		project: Project,
		source: "agent" | "hybrid" = "agent",
	) => ({
		project_id: project.id,
		name:
			source === "hybrid"
				? `混合扫描-智能扫描-${project.name}`
				: `智能扫描-${project.name}`,
		description:
			source === "hybrid"
				? `${HYBRID_TASK_NAME_MARKER}混合扫描智能阶段任务`
				: `${INTELLIGENT_TASK_NAME_MARKER}智能扫描任务`,
		branch_name: isRepositoryProject(project)
			? branchName.trim() || project.default_branch || "main"
			: undefined,
		target_files: parsedTargetFiles.length > 0 ? parsedTargetFiles : undefined,
		audit_scope: {
			static_bootstrap:
				source === "hybrid"
					? {
							mode: "embedded" as const,
							opengrep_enabled: opengrepEnabled,
							gitleaks_enabled: gitleaksEnabled,
						}
					: {
							mode: "disabled" as const,
							opengrep_enabled: false,
							gitleaks_enabled: false,
						},
		},
		verification_level: "analysis_with_poc_plan" as const,
	});

	const loadQuickFixConfigFromUser = async () => {
		const userConfig = await api.getUserConfig();
		const llmConfig = (userConfig?.llmConfig || {}) as Record<string, unknown>;
		const provider = normalizeProvider(String(llmConfig.llmProvider || "openai"));
		setLlmQuickConfig({
			provider,
			model: String(llmConfig.llmModel || ""),
			baseUrl: String(llmConfig.llmBaseUrl || ""),
			apiKey: resolveEffectiveApiKey(provider, llmConfig),
		});
	};


	const openLlmQuickFixPanelManual = async () => {
		if (showLlmQuickFixPanel) {
			setShowLlmQuickFixPanel(false);
			setQuickFixTestResult(null);
			return;
		}

		setQuickFixPanelOpening(true);
		setQuickFixTestResult(null);
		setQuickFixMissingFields([]);
		setLastPreflightMessage("");
		try {
			await loadQuickFixConfigFromUser();
		} catch (error) {
			console.error("加载 LLM 快速补配配置失败:", error);
		} finally {
			setShowLlmQuickFixPanel(true);
			setQuickFixPanelOpening(false);
		}
	};


	const createHybridLiteAgentTaskForProject = async (
		project: Project,
		source: "agent" | "hybrid" = "agent",
	) => createAgentTask(buildAgentTaskPayload(project, source));

	const handleQuickFixConfigChange = (key: keyof LlmQuickConfig, value: string) => {
		setLlmQuickConfig((prev) => ({ ...prev, [key]: value }));
		if (key === "model") {
			setQuickFixMissingFields((prev) => prev.filter((field) => field !== "llmModel"));
		}
		if (key === "baseUrl") {
			setQuickFixMissingFields((prev) => prev.filter((field) => field !== "llmBaseUrl"));
		}
		if (key === "apiKey") {
			setQuickFixMissingFields((prev) => prev.filter((field) => field !== "llmApiKey"));
		}
	};

	const validateQuickFixFields = (): { ok: boolean; message?: string } => {
		const provider = normalizeProvider(llmQuickConfig.provider);
		const model = llmQuickConfig.model.trim();
		const baseUrl = llmQuickConfig.baseUrl.trim();
		const apiKey = llmQuickConfig.apiKey.trim();
		if (!model) {
			setQuickFixMissingFields((prev) => Array.from(new Set([...prev, "llmModel"])));
			return { ok: false, message: "请先填写模型" };
		}
		if (!baseUrl) {
			setQuickFixMissingFields((prev) => Array.from(new Set([...prev, "llmBaseUrl"])));
			return { ok: false, message: "请先填写 Base URL" };
		}
		if (provider !== "ollama" && !apiKey) {
			setQuickFixMissingFields((prev) => Array.from(new Set([...prev, "llmApiKey"])));
			return { ok: false, message: "请先填写 API Key" };
		}
		return { ok: true };
	};

	const handleQuickFixTest = async () => {
		const validation = validateQuickFixFields();
		if (!validation.ok) {
			if (validation.message) toast.error(validation.message);
			return;
		}

		const provider = normalizeProvider(llmQuickConfig.provider);
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
			if (result.success) {
				toast.success(`测试成功：${result.model || payload.model}`);
			} else {
				toast.error(`测试失败：${result.message || "未知错误"}`);
			}
		} catch (error) {
			const message = extractApiErrorMessage(error);
			setQuickFixTestResult({ success: false, message });
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
			const provider = normalizeProvider(llmQuickConfig.provider);
			const apiKey = llmQuickConfig.apiKey.trim();
			const providerKeyField = PROVIDER_KEY_FIELD_MAP[provider];

			const nextLlmConfig: Record<string, unknown> = {
				...currentLlmConfig,
				llmProvider: provider,
				llmModel: llmQuickConfig.model.trim(),
				llmBaseUrl: llmQuickConfig.baseUrl.trim(),
				llmApiKey: apiKey,
			};
			if (providerKeyField) {
				nextLlmConfig[providerKeyField] = apiKey;
			}

			await api.updateUserConfig({ llmConfig: nextLlmConfig });
			setShowLlmQuickFixPanel(false);
			setQuickFixMissingFields([]);
			setLastPreflightMessage("");
			toast.success("LLM 配置已保存，请重新创建任务");
		} catch (error) {
			toast.error(`保存失败：${extractApiErrorMessage(error)}`);
		} finally {
			setQuickFixSaving(false);
		}
	};

	const handleCreateHybridFullForProject = async (
		project: Project,
		action: "primary" | "secondary",
	) => {
		const agentTask = await createAgentTask(
			buildAgentTaskPayload(project, "hybrid"),
		);
		onOpenChange(false);
		onTaskCreated?.();
		toast.success("混合扫描任务已创建（内嵌静态预扫 + 智能扫描）");
		if (action === "secondary") {
			onSecondaryCreateSuccess?.();
		} else if (navigateOnSuccess) {
			navigate(`/agent-audit/${agentTask.id}`);
		}
	};

	const handleCreateHybridLiteAgentForProject = async (
		project: Project,
		action: "primary" | "secondary",
	) => {
		const agentTask = await createHybridLiteAgentTaskForProject(project, "agent");
		onOpenChange(false);
		onTaskCreated?.();
		toast.success("智能扫描任务已创建");
		if (action === "secondary") {
			onSecondaryCreateSuccess?.();
		} else if (navigateOnSuccess) {
			navigate(`/agent-audit/${agentTask.id}`);
		}
	};

	const stripArchiveSuffix = (fileName: string) =>
		fileName.replace(/\.(tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|zip|tar|7z|rar)$/i, "");

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
		const inferredName = stripArchiveSuffix(file.name).trim();
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

					const uploadResult = await uploadZipFile(createdProject.id, newProjectFile);
					if (!uploadResult.success) {
						throw new Error(uploadResult.message || "压缩包上传失败");
					}

					if (mode === "static") {
						const result = await createStaticTasksForProject(createdProject);
						onOpenChange(false);
						onTaskCreated?.();
						toast.success("静态扫描任务已创建");
						if (action === "secondary") {
							onSecondaryCreateSuccess?.();
						} else if (navigateOnSuccess) {
							navigate(appendReturnTo(buildStaticTaskRoute(result), currentRoute));
						}
						return;
					}

					if (mode === "hybrid") {
						await handleCreateHybridFullForProject(createdProject, action);
						return;
					}

					await handleCreateHybridLiteAgentForProject(createdProject, action);
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

			if (mode === "static" || mode === "hybrid") {
				if (!isZipProject(selectedProject)) {
					toast.error(
						mode === "hybrid"
							? "混合扫描当前仅支持源码压缩包项目"
							: "静态扫描仅支持源码压缩包项目",
					);
					return;
				}
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
				if (!opengrepEnabled && !gitleaksEnabled) {
					toast.error("请至少启用一个扫描引擎");
					return;
				}
			}

			if (mode === "static") {
				const result = await createStaticTasksForProject(selectedProject);
				onOpenChange(false);
				onTaskCreated?.();
				toast.success("静态扫描任务已创建");
				if (action === "secondary") {
					onSecondaryCreateSuccess?.();
				} else if (navigateOnSuccess) {
					navigate(appendReturnTo(buildStaticTaskRoute(result), currentRoute));
				}
				return;
			}

			if (mode === "hybrid") {
				await handleCreateHybridFullForProject(selectedProject, action);
				return;
			}

			if (isZipProject(selectedProject)) {
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
			}

			await handleCreateHybridLiteAgentForProject(selectedProject, action);
		} catch (error) {
			const message = extractApiErrorMessage(error);
			const failureText =
				mode === "agent" ? `智能扫描创建失败：${message}` : `创建失败: ${message}`;
			toast.error(failureText);
		} finally {
			setCreating(false);
		}
	};

	const missingFieldClass = (field: PreflightMissingField) =>
		quickFixMissingFields.includes(field)
			? "border-rose-500/60 focus-visible:ring-rose-500"
			: "";

	const shouldShowAgentPrecheckHint = mode === "agent" || mode === "hybrid";

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[min(92vw,760px)] !max-w-none max-h-[88vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg">
				<DialogHeader className="px-6 py-4 border-b border-border bg-muted">
					<DialogTitle className="flex items-center gap-3 font-mono">
						<div className="p-2 rounded border border-sky-500/30 bg-sky-500/10">
							<TerminalSquare className="w-5 h-5 text-sky-300" />
						</div>
						<div>
							<p className="text-base font-bold uppercase tracking-wider text-foreground">
								{dialogTitle}
							</p>
						</div>
					</DialogTitle>
				</DialogHeader>

				<div className="p-6 space-y-5 overflow-y-auto flex-1">
					{allowUploadProject && (
						<div className="space-y-2">
							<p className="text-xs uppercase tracking-wider text-muted-foreground">项目来源</p>
							<div className="grid grid-cols-2 gap-2">
								<Button
									type="button"
									variant={sourceMode === "existing" ? "default" : "outline"}
									className={
										sourceMode === "existing"
											? "cyber-btn-primary h-10"
											: "cyber-btn-outline h-10"
									}
									onClick={() => {
										setSourceMode("existing");
									}}
									disabled={creating}
								>
									选择已有项目
								</Button>
								<Button
									type="button"
									variant={sourceMode === "upload" ? "default" : "outline"}
									className={
										sourceMode === "upload"
											? "cyber-btn-primary h-10"
											: "cyber-btn-outline h-10"
									}
									onClick={() => {
										setSourceMode("upload");
									}}
									disabled={creating}
								>
									上传新项目
								</Button>
							</div>
						</div>
					)}

					{!lockMode && (
						<div className="space-y-2">
							<p className="text-xs uppercase tracking-wider text-muted-foreground">扫描方式</p>
							<div className="grid grid-cols-1 md:grid-cols-3 gap-2">
								<Button
									type="button"
									variant={mode === "static" ? "default" : "outline"}
									className={
										mode === "static"
											? "cyber-btn-primary h-10 justify-start"
											: "cyber-btn-outline h-10 justify-start"
									}
									onClick={() => setMode("static")}
									disabled={creating}
								>
									<Zap className="w-4 h-4 mr-2" />
									静态扫描
								</Button>
								<Button
									type="button"
									variant={mode === "agent" ? "default" : "outline"}
									className={
										mode === "agent"
											? "h-10 justify-start border border-violet-500/40 bg-violet-500/20 text-violet-100 hover:bg-violet-500/30"
											: "cyber-btn-outline h-10 justify-start"
									}
									onClick={() => setMode("agent")}
									disabled={creating}
								>
									<Bot className="w-4 h-4 mr-2" />
									智能扫描
								</Button>
								<Button
									type="button"
									variant={mode === "hybrid" ? "default" : "outline"}
									className={
										mode === "hybrid"
											? "h-10 justify-start border border-emerald-500/40 bg-emerald-500/20 text-emerald-100 hover:bg-emerald-500/30"
											: "cyber-btn-outline h-10 justify-start"
									}
									onClick={() => setMode("hybrid")}
									disabled={creating}
								>
									<Layers className="w-4 h-4 mr-2" />
									混合扫描
								</Button>
							</div>
						</div>
					)}

					{sourceMode === "existing" ? (
						<div className="space-y-3">
							<Input
								value={searchTerm}
								onChange={(event) => setSearchTerm(event.target.value)}
								placeholder="搜索项目..."
								className="h-9 cyber-input"
								disabled={creating}
							/>
							<div className="border border-border rounded-lg max-h-[280px] overflow-y-auto p-2 space-y-2">
								{loadingProjects ? (
									<div className="py-10 flex items-center justify-center text-sm text-muted-foreground">
										<Loader2 className="w-4 h-4 animate-spin mr-2" />
										加载项目中...
									</div>
								) : filteredProjects.length > 0 ? (
									filteredProjects.map((project) => (
										<button
											key={project.id}
											type="button"
											onClick={() => setSelectedProjectId(project.id)}
											className={`w-full text-left p-3 rounded border transition-colors ${
												project.id === selectedProjectId
													? "border-sky-500/50 bg-sky-500/10"
													: "border-border hover:border-sky-500/30 bg-background"
											}`}
											disabled={creating}
										>
											<div className="flex items-start justify-between gap-3">
												<div className="min-w-0">
													<p className="text-sm font-semibold text-foreground">{project.name}</p>
													{project.description && (
														<p className="text-xs text-muted-foreground mt-1 line-clamp-1">
															{project.description}
														</p>
													)}
												</div>
												<div className="flex items-center gap-2 shrink-0">
													<Badge
														className={
															project.source_type === "zip"
																? "cyber-badge-warning"
																: "cyber-badge-info"
														}
													>
														{project.source_type === "zip" ? "ZIP" : "仓库"}
													</Badge>
													{project.id === selectedProjectId && (
														<CheckCircle2 className="w-4 h-4 text-sky-400" />
													)}
												</div>
											</div>
										</button>
									))
								) : (
									<div className="py-10 text-center text-sm text-muted-foreground">
										未找到可用项目
									</div>
								)}
							</div>
						</div>
					) : (
						<div className="space-y-3 border border-border rounded-lg p-4">
							<div>
								<p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">项目名称</p>
								<Input
									value={newProjectName}
									onChange={(event) => setNewProjectName(event.target.value)}
									placeholder="请输入项目名称"
									className="h-9 cyber-input"
									disabled={creating}
								/>
							</div>
						<div className="rounded-lg border border-dashed border-sky-500/30 bg-sky-500/8 p-3">
							<p className="text-xs uppercase tracking-wider font-semibold text-sky-100 mb-1">
								自动生成简介
							</p>
							<p className="text-xs leading-5 text-sky-50/85">
								项目上传完成后，系统会自动生成 1-2 句使用场景简介，并同步展示到项目列表与详情页。
							</p>
						</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">源码压缩包</p>
								<label className="inline-flex">
									<input
										type="file"
										accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
										className="hidden"
										onChange={handleNewProjectFileSelect}
										disabled={creating}
									/>
									<span className="cyber-btn-outline h-9 px-3 inline-flex items-center cursor-pointer">
										<Upload className="w-4 h-4 mr-2" />
										选择压缩包
									</span>
								</label>
								{newProjectFile && (
									<p className="text-xs text-emerald-400 mt-2">{newProjectFile.name}</p>
								)}
							</div>
						</div>
					)}

					{mode === "static" || mode === "hybrid" ? (
						<div className="border border-border rounded-lg p-4 space-y-3">
							<div className="flex items-center justify-between">
								<p className="text-sm font-semibold text-foreground">
									{mode === "hybrid" ? "混合扫描 - 静态引擎" : "静态扫描引擎"}
								</p>
								<p className="text-xs text-muted-foreground">
									{loadingRules ? "规则加载中..." : `已启用规则 ${activeRules.length}`}
								</p>
							</div>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-2">
								<label className="border border-border rounded p-3 flex items-center gap-3 cursor-pointer hover:border-sky-500/30">
									<Checkbox
										checked={opengrepEnabled}
										onCheckedChange={(checked) =>
											setOpengrepEnabled(Boolean(checked))
										}
										disabled={creating}
										className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
									/>
									<div>
										<p className="text-sm text-foreground font-semibold">Opengrep</p>
										<p className="text-xs text-muted-foreground">规则扫描</p>
									</div>
								</label>
								<label className="border border-border rounded p-3 flex items-center gap-3 cursor-pointer hover:border-sky-500/30">
									<Checkbox
										checked={gitleaksEnabled}
										onCheckedChange={(checked) =>
											setGitleaksEnabled(Boolean(checked))
										}
										disabled={creating}
										className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
									/>
									<div>
										<p className="text-sm text-foreground font-semibold">Gitleaks</p>
										<p className="text-xs text-muted-foreground">密钥泄露扫描</p>
									</div>
								</label>
							</div>
							{mode === "hybrid" && selectedProject && !isZipProject(selectedProject) && (
								<p className="text-xs text-rose-300">
									混合扫描当前仅支持源码压缩包项目（静态 + 智能）。
								</p>
							)}
						</div>
					) : null}

					{shouldShowAgentPrecheckHint && (
						<div className="space-y-3">
							<div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
								<div className="flex items-start justify-between gap-3">
									<div>
										<p className="text-sm text-violet-200">
											{t(
												"task.llmPrecheckHint",
												"创建前会自动校验 LLM 配置。",
											)}
										</p>
										<p className="text-xs text-violet-300/80 mt-1">
											{t(
												"task.llmQuickFixDesc",
												"未通过时可在下方直接补配并测试连接。",
											)}
										</p>
									</div>
					<Button
						type="button"
						variant="outline"
						className="cyber-btn-outline h-8 shrink-0"
						onClick={openLlmQuickFixPanelManual}
						disabled={
							creating ||
							quickFixSaving ||
							quickFixTesting ||
							quickFixPanelOpening
										}
									>
										{quickFixPanelOpening ? (
											<>
												<Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
												加载中...
											</>
										) : showLlmQuickFixPanel ? (
											t("task.llmConfigCollapse", "收起配置")
										) : (
											t("task.llmConfigTest", "配置测试")
										)}
									</Button>
								</div>
							</div>

							{showLlmQuickFixPanel && (
								<div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
									<div className="flex items-start justify-between gap-2">
										<div className="space-y-1">
											<p className="text-sm font-semibold text-amber-100">
												{t("task.llmQuickFixTitle", "LLM 快速补配")}
											</p>
											<p className="text-xs text-amber-200/85 leading-relaxed">
												{lastPreflightMessage ||
													t(
														"task.llmQuickFixDesc",
														"未通过时可在下方直接补配并测试连接。",
													)}
											</p>
										</div>
										<Badge className="cyber-badge-info uppercase">
											{normalizeProvider(llmQuickConfig.provider)}
										</Badge>
									</div>

									<div className="grid grid-cols-1 gap-3">
										<div className="space-y-1">
											<p className="text-xs uppercase tracking-wider text-muted-foreground">
												模型
											</p>
											<Input
												value={llmQuickConfig.model}
												onChange={(event) =>
													handleQuickFixConfigChange("model", event.target.value)
												}
												placeholder="例如：gpt-5"
												className={`h-9 cyber-input ${missingFieldClass("llmModel")}`}
												disabled={creating || quickFixSaving || quickFixTesting}
											/>
										</div>

										<div className="space-y-1">
											<p className="text-xs uppercase tracking-wider text-muted-foreground">
												Base URL
											</p>
											<Input
												value={llmQuickConfig.baseUrl}
												onChange={(event) =>
													handleQuickFixConfigChange("baseUrl", event.target.value)
												}
												placeholder="例如：https://api.openai.com/v1"
												className={`h-9 cyber-input ${missingFieldClass("llmBaseUrl")}`}
												disabled={creating || quickFixSaving || quickFixTesting}
											/>
										</div>

										<div className="space-y-1">
											<p className="text-xs uppercase tracking-wider text-muted-foreground">
												Token
											</p>
											<Input
												type="password"
												value={llmQuickConfig.apiKey}
												onChange={(event) =>
													handleQuickFixConfigChange("apiKey", event.target.value)
												}
												placeholder={
													normalizeProvider(llmQuickConfig.provider) === "ollama"
														? "可选"
														: "请输入 API Key"
												}
												className={`h-9 cyber-input ${missingFieldClass("llmApiKey")}`}
												disabled={creating || quickFixSaving || quickFixTesting}
											/>
										</div>
									</div>

									{quickFixTestResult && (
										<p
											className={`text-xs ${
												quickFixTestResult.success
													? "text-emerald-300"
													: "text-rose-300"
											}`}
										>
											{quickFixTestResult.success
												? `测试成功：${quickFixTestResult.model || llmQuickConfig.model}`
												: `测试失败：${quickFixTestResult.message}`}
										</p>
									)}

									<div className="flex items-center justify-end gap-2">
										<Button
											type="button"
											variant="outline"
											className="cyber-btn-outline h-9"
											onClick={handleQuickFixTest}
											disabled={creating || quickFixSaving || quickFixTesting}
										>
											{quickFixTesting ? (
												<>
													<Loader2 className="w-4 h-4 animate-spin mr-2" />
													测试中...
												</>
											) : (
												"测试连接"
											)}
										</Button>
										<Button
											type="button"
											className="cyber-btn-primary h-9"
											onClick={handleQuickFixSave}
											disabled={creating || quickFixSaving || quickFixTesting}
										>
											{quickFixSaving ? (
												<>
													<Loader2 className="w-4 h-4 animate-spin mr-2" />
													保存中...
												</>
											) : (
												"保存配置"
											)}
										</Button>
									</div>
								</div>
							)}
						</div>
					)}

					{mode === "agent" && selectedProject && isRepositoryProject(selectedProject) && (
						<div className="space-y-2">
							<p className="text-xs uppercase tracking-wider text-muted-foreground">扫描分支</p>
							<Input
								value={branchName}
								onChange={(event) => setBranchName(event.target.value)}
								placeholder="main"
								className="h-9 cyber-input"
								disabled={creating}
							/>
						</div>
					)}
				</div>

				<div className="px-6 py-4 border-t border-border bg-muted flex justify-end gap-2">
					{showReturnButton && onReturn && (
						<Button
							type="button"
							variant="outline"
							className="cyber-btn-outline"
							onClick={onReturn}
							disabled={creating}
						>
							返回
						</Button>
					)}
					<Button
						type="button"
						variant="outline"
						className="cyber-btn-outline"
						onClick={() => onOpenChange(false)}
						disabled={creating}
					>
						取消
					</Button>
					<Button
						type="button"
						className="cyber-btn-primary"
						onClick={() => handleCreate("primary")}
						disabled={!canCreate || creating}
					>
						{creating ? (
							<>
								<Loader2 className="w-4 h-4 animate-spin mr-2" />
								创建中...
							</>
						) : (
							<>
								<Shield className="w-4 h-4 mr-2" />
								{primaryCreateLabel}
							</>
						)}
					</Button>
					{createButtonVariant === "dual" && (
						<Button
							type="button"
							className="cyber-btn-primary"
							onClick={() => handleCreate("secondary")}
							disabled={!canCreate || creating}
						>
							{creating ? (
								<>
									<Loader2 className="w-4 h-4 animate-spin mr-2" />
									创建中...
								</>
							) : (
								<>
									<Shield className="w-4 h-4 mr-2" />
									{secondaryCreateLabel}
								</>
							)}
						</Button>
					)}
				</div>
			</DialogContent>
		</Dialog>
	);
}
