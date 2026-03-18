/**
 * System Config Component
 * Cyberpunk Terminal Aesthetic
 */

import {
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
	type Dispatch,
	type CSSProperties,
	type SetStateAction,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Command,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
} from "@/components/ui/command";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	AlertCircle,
	Brain,
	Check,
	CheckCircle2,
	ChevronsUpDown,
	Eye,
	EyeOff,
	Loader2,
	RotateCcw,
	Save,
	Settings,
	Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";
import { resolveProviderSwitchFieldValue } from "@/components/system/llmProviderSwitch";
import { runSaveThenTestAction } from "@/components/scan-config/intelligentEngineActionFlow";
import {
	buildLlmProviderOptions,
	getDefaultBaseUrlForProvider as resolveDefaultBaseUrlForProvider,
	getDefaultModelForProvider as resolveDefaultModelForProvider,
	getLlmCustomHeadersParseErrorMessage,
	getLlmProviderInfo,
	normalizeLlmProviderId,
	parseLlmCustomHeadersInput,
	shouldRequireApiKey as resolveShouldRequireApiKey,
	type LLMProviderItem,
} from "@/shared/llm/providerCatalog";
import {
	resolvePreferredModelStats,
	type LlmModelStatsCounts,
	type LlmModelStatsFetchState,
	type LlmModelStatsSource,
	type LlmModelStatsStatus,
} from "@/components/system/llmModelStatsSummary";

interface LLMModelMetadata {
	contextWindow?: number | null;
	maxOutputTokens?: number | null;
	recommendedMaxTokens?: number | null;
	source?: string;
}

type TokenRecommendation = {
	value: number;
	source: string;
};

const recommendTokensFromStaticRules = (modelName: string): number | null => {
	const normalized = String(modelName || "")
		.trim()
		.toLowerCase();
	if (!normalized) return null;

	const highReasoningHints = [
		"gpt-5",
		"o3",
		"o4",
		"claude-opus",
		"claude-sonnet",
		"deepseek-r1",
		"deepseek-v3",
		"qwen3-max",
		"qwen3-235b",
		"kimi-k2",
		"glm-4.6",
		"ernie-4.5",
		"minimax-m2",
		"doubao-1.6",
		"llama3.3-70b",
	];
	const mediumHints = [
		"mini",
		"haiku",
		"flash",
		"small",
		"3.5",
		"qwen3-4b",
		"qwen3-8b",
		"gemma",
	];

	if (highReasoningHints.some((hint) => normalized.includes(hint)))
		return 16384;
	if (mediumHints.some((hint) => normalized.includes(hint))) return 8192;
	return null;
};

interface SystemConfigData {
	llmProvider: string;
	llmApiKey: string;
	llmModel: string;
	llmBaseUrl: string;
	llmCustomHeaders: string;
	llmTimeout: number;
	llmTemperature: number;
	llmMaxTokens: number;
	llmFirstTokenTimeout: number;
	llmStreamTimeout: number;
	agentTimeout: number;
	subAgentTimeout: number;
	toolTimeout: number;
	maxAnalyzeFiles: number;
	llmConcurrency: number;
	llmGapMs: number;
	outputLanguage: string;
}

type ConfigSection = "llm" | "embedding" | "analysis";

export interface SystemConfigSharedDraftState {
	config: SystemConfigData | null;
	setConfig: Dispatch<SetStateAction<SystemConfigData | null>>;
	loading: boolean;
	setLoading: Dispatch<SetStateAction<boolean>>;
	hasChanges: boolean;
	setHasChanges: Dispatch<SetStateAction<boolean>>;
	llmProvidersFromBackend: LLMProviderItem[];
	setLlmProvidersFromBackend: Dispatch<SetStateAction<LLMProviderItem[]>>;
	fetchedModelsByProvider: Record<string, string[]>;
	setFetchedModelsByProvider: Dispatch<SetStateAction<Record<string, string[]>>>;
	fetchedModelMetadataByProvider: Record<string, Record<string, LLMModelMetadata>>;
	setFetchedModelMetadataByProvider: Dispatch<
		SetStateAction<Record<string, Record<string, LLMModelMetadata>>>
	>;
	reloadConfig: () => Promise<void>;
}

interface SystemConfigProps {
	visibleSections?: ConfigSection[];
	defaultSection?: ConfigSection;
	mergedView?: boolean;
	showLlmSummaryCards?: boolean;
	llmSummaryOnly?: boolean;
	showFloatingSaveButton?: boolean;
	compactLayout?: boolean;
	sharedDraftState?: SystemConfigSharedDraftState;
	onLlmSummaryChange?: (summary: {
		providerId: string;
		providerLabel: string;
		currentModelName: string;
		availableModelCount: number;
		availableModelMetadataCount: number;
		supportsModelFetch: boolean;
		modelStatsStatus: LlmModelStatsStatus;
		modelStatsSource: LlmModelStatsSource;
		shouldPreferOnlineStats: boolean;
	}) => void;
}

type AdvancedConfigItemId =
	| "llmCustomHeaders"
	| "llmTimeout"
	| "llmTemperature"
	| "llmMaxTokens"
	| "llmFirstTokenTimeout"
	| "llmStreamTimeout"
	| "agentTimeout"
	| "subAgentTimeout"
	| "toolTimeout"
	| "maxAnalyzeFiles"
	| "llmConcurrency"
	| "llmGapMs"
	| "outputLanguage";

const DEFAULT_CONFIG: SystemConfigData = {
	llmProvider: "openai",
	llmApiKey: "",
	llmModel: "",
	llmBaseUrl: "",
	llmCustomHeaders: "",
	llmTimeout: 300000,
	llmTemperature: 0.05,
	llmMaxTokens: 16384,
	llmFirstTokenTimeout: 180,
	llmStreamTimeout: 180,
	agentTimeout: 3600,
	subAgentTimeout: 1200,
	toolTimeout: 120,
	maxAnalyzeFiles: 0,
	llmConcurrency: 1,
	llmGapMs: 3000,
	outputLanguage: "zh-CN",
};

function buildSystemConfigDataFromBackendConfig(
	backendConfig:
		| {
				llmConfig?: Record<string, unknown>;
				otherConfig?: Record<string, unknown>;
			}
		| null
		| undefined,
): SystemConfigData {
	const llmConfig = (backendConfig?.llmConfig ?? {}) as Record<string, unknown>;
	const otherConfig = (backendConfig?.otherConfig ?? {}) as Record<string, unknown>;
	const normalizedProvider = normalizeLlmProviderId(
		typeof llmConfig.llmProvider === "string" ? llmConfig.llmProvider : "",
	);

	return {
		llmProvider: normalizedProvider || DEFAULT_CONFIG.llmProvider,
		llmApiKey: typeof llmConfig.llmApiKey === "string" ? llmConfig.llmApiKey : "",
		llmModel: typeof llmConfig.llmModel === "string" ? llmConfig.llmModel : "",
		llmBaseUrl:
			typeof llmConfig.llmBaseUrl === "string" ? llmConfig.llmBaseUrl : "",
		llmCustomHeaders:
			typeof llmConfig.llmCustomHeaders === "string"
				? llmConfig.llmCustomHeaders
				: "",
		llmTimeout:
			typeof llmConfig.llmTimeout === "number"
				? llmConfig.llmTimeout
				: DEFAULT_CONFIG.llmTimeout,
		llmTemperature:
			typeof llmConfig.llmTemperature === "number"
				? llmConfig.llmTemperature
				: DEFAULT_CONFIG.llmTemperature,
		llmMaxTokens:
			typeof llmConfig.llmMaxTokens === "number"
				? llmConfig.llmMaxTokens
				: DEFAULT_CONFIG.llmMaxTokens,
		llmFirstTokenTimeout:
			typeof llmConfig.llmFirstTokenTimeout === "number"
				? llmConfig.llmFirstTokenTimeout
				: DEFAULT_CONFIG.llmFirstTokenTimeout,
		llmStreamTimeout:
			typeof llmConfig.llmStreamTimeout === "number"
				? llmConfig.llmStreamTimeout
				: DEFAULT_CONFIG.llmStreamTimeout,
		agentTimeout:
			typeof llmConfig.agentTimeout === "number"
				? llmConfig.agentTimeout
				: DEFAULT_CONFIG.agentTimeout,
		subAgentTimeout:
			typeof llmConfig.subAgentTimeout === "number"
				? llmConfig.subAgentTimeout
				: DEFAULT_CONFIG.subAgentTimeout,
		toolTimeout:
			typeof llmConfig.toolTimeout === "number"
				? llmConfig.toolTimeout
				: DEFAULT_CONFIG.toolTimeout,
		maxAnalyzeFiles:
			typeof otherConfig.maxAnalyzeFiles === "number"
				? otherConfig.maxAnalyzeFiles
				: DEFAULT_CONFIG.maxAnalyzeFiles,
		llmConcurrency:
			typeof otherConfig.llmConcurrency === "number"
				? otherConfig.llmConcurrency
				: DEFAULT_CONFIG.llmConcurrency,
		llmGapMs:
			typeof otherConfig.llmGapMs === "number"
				? otherConfig.llmGapMs
				: DEFAULT_CONFIG.llmGapMs,
		outputLanguage:
			typeof otherConfig.outputLanguage === "string"
				? otherConfig.outputLanguage
				: DEFAULT_CONFIG.outputLanguage,
	};
}

export function useSystemConfigDraftState(
	options?: { enabled?: boolean },
): SystemConfigSharedDraftState {
	const enabled = options?.enabled ?? true;
	const [config, setConfig] = useState<SystemConfigData | null>(null);
	const [loading, setLoading] = useState(true);
	const [hasChanges, setHasChanges] = useState(false);
	const [llmProvidersFromBackend, setLlmProvidersFromBackend] = useState<
		LLMProviderItem[]
	>([]);
	const [fetchedModelsByProvider, setFetchedModelsByProvider] = useState<
		Record<string, string[]>
	>({});
	const [fetchedModelMetadataByProvider, setFetchedModelMetadataByProvider] =
		useState<Record<string, Record<string, LLMModelMetadata>>>({});

	const reloadConfig = useCallback(async () => {
		if (!enabled) return;
		try {
			setLoading(true);
			const backendConfig = await api.getUserConfig();
			setConfig(
				backendConfig
					? buildSystemConfigDataFromBackendConfig(backendConfig)
					: { ...DEFAULT_CONFIG },
			);
			setHasChanges(false);
		} catch (error) {
			console.error("Failed to load config:", error);
			setConfig({ ...DEFAULT_CONFIG });
		} finally {
			setLoading(false);
		}
	}, [enabled]);

	useEffect(() => {
		if (!enabled) return;
		void reloadConfig();
		api
			.getLLMProviders()
			.then((res) => setLlmProvidersFromBackend(res.providers || []))
			.catch(() => setLlmProvidersFromBackend([]));
	}, [enabled, reloadConfig]);

	return {
		config,
		setConfig,
		loading,
		setLoading,
		hasChanges,
		setHasChanges,
		llmProvidersFromBackend,
		setLlmProvidersFromBackend,
		fetchedModelsByProvider,
		setFetchedModelsByProvider,
		fetchedModelMetadataByProvider,
		setFetchedModelMetadataByProvider,
		reloadConfig,
	};
}

function AdvancedConfigDialog(props: {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	selectedItemId: AdvancedConfigItemId;
	onSelectItem: (id: AdvancedConfigItemId) => void;
	config: SystemConfigData;
	hasChanges: boolean;
	onSave: () => void;
	onUpdate: (key: keyof SystemConfigData, value: string | number) => void;
}) {
	const renderItemPanel = () => {
		const cfg = props.config;
		const update = props.onUpdate;
		const item = props.selectedItemId;

		const panelMeta: Record<
			AdvancedConfigItemId,
			{ label: string; desc: string; input?: React.ReactNode }
		> = {
			llmCustomHeaders: {
				label: "自定义请求头 (JSON)",
				desc: "用于 OpenAI 兼容网关的额外请求头，例如 HTTP-Referer 或 X-Title。",
				input: (
					<Textarea
						value={cfg.llmCustomHeaders}
						onChange={(e) => update("llmCustomHeaders", e.target.value)}
						placeholder='{"HTTP-Referer":"https://app.example.com","X-Title":"VulHunter"}'
						className="min-h-32 cyber-input font-mono"
					/>
				),
			},
			llmTimeout: {
				label: "请求超时 (毫秒)",
				desc: "单次 LLM 请求最大允许耗时。",
				input: (
					<Input
						type="number"
						value={cfg.llmTimeout}
						onChange={(e) => update("llmTimeout", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			llmTemperature: {
				label: "温度 (0-2)",
				desc: "数值越高越发散，越低越稳定。",
				input: (
					<Input
						type="number"
						step="0.1"
						min="0"
						max="2"
						value={cfg.llmTemperature}
						onChange={(e) => update("llmTemperature", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			llmMaxTokens: {
				label: "最大 Tokens",
				desc: "限制单次输出 token 上限。",
				input: (
					<Input
						type="number"
						value={cfg.llmMaxTokens}
						onChange={(e) => update("llmMaxTokens", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			llmFirstTokenTimeout: {
				label: "首 Token 超时 (秒)",
				desc: "等待 LLM 首个 token 的最大时长。",
				input: (
					<Input
						type="number"
						value={cfg.llmFirstTokenTimeout}
						onChange={(e) =>
							update("llmFirstTokenTimeout", Number(e.target.value))
						}
						className="h-10 cyber-input"
					/>
				),
			},
			llmStreamTimeout: {
				label: "流式超时 (秒)",
				desc: "流式输出期间的超时阈值。",
				input: (
					<Input
						type="number"
						value={cfg.llmStreamTimeout}
						onChange={(e) => update("llmStreamTimeout", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			agentTimeout: {
				label: "Agent 总超时 (秒)",
				desc: "智能扫描任务整体超时阈值。",
				input: (
					<Input
						type="number"
						value={cfg.agentTimeout}
						onChange={(e) => update("agentTimeout", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			subAgentTimeout: {
				label: "子 Agent 超时 (秒)",
				desc: "单个子智能体执行的超时阈值。",
				input: (
					<Input
						type="number"
						value={cfg.subAgentTimeout}
						onChange={(e) => update("subAgentTimeout", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			toolTimeout: {
				label: "工具超时 (秒)",
				desc: "工具调用最大允许耗时。",
				input: (
					<Input
						type="number"
						value={cfg.toolTimeout}
						onChange={(e) => update("toolTimeout", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			maxAnalyzeFiles: {
				label: "最大分析文件数",
				desc: "限制本次分析的文件数。0 表示不限制。",
				input: (
					<Input
						type="number"
						value={cfg.maxAnalyzeFiles}
						onChange={(e) => update("maxAnalyzeFiles", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			llmConcurrency: {
				label: "LLM 并发数",
				desc: "同时发送的 LLM 请求数量。",
				input: (
					<Input
						type="number"
						value={cfg.llmConcurrency}
						onChange={(e) => update("llmConcurrency", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			llmGapMs: {
				label: "请求间隔 (毫秒)",
				desc: "两次请求之间的间隔，用于降速与稳定性。",
				input: (
					<Input
						type="number"
						value={cfg.llmGapMs}
						onChange={(e) => update("llmGapMs", Number(e.target.value))}
						className="h-10 cyber-input"
					/>
				),
			},
			outputLanguage: {
				label: "输出语言",
				desc: "智能扫描输出语言。",
				input: (
					<Select
						value={cfg.outputLanguage}
						onValueChange={(value) => update("outputLanguage", value)}
					>
						<SelectTrigger className="h-10 cyber-input">
							<SelectValue />
						</SelectTrigger>
						<SelectContent className="cyber-dialog border-border">
							<SelectItem value="zh-CN" className="font-mono">
								🇨🇳 中文
							</SelectItem>
							<SelectItem value="en-US" className="font-mono">
								🇺🇸 English
							</SelectItem>
						</SelectContent>
					</Select>
				),
			},
		};

		const meta = panelMeta[item as AdvancedConfigItemId];
		if (!meta) return null;

		return (
			<div className="p-6">
				<div className="mb-6">
					<div className="text-sm font-bold uppercase text-foreground">
						{meta.label}
					</div>
					<div className="text-xs text-muted-foreground mt-1">{meta.desc}</div>
				</div>
				<div className="space-y-2">
					<Label className="text-xs font-bold text-muted-foreground uppercase">
						{meta.label}
					</Label>
					{meta.input}
				</div>
			</div>
		);
	};

	return (
		<Dialog open={props.open} onOpenChange={props.onOpenChange}>
			<DialogContent
				showCloseButton={false}
				className="!w-[min(92vw,980px)] !max-w-none h-[80vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg"
			>
				<DialogHeader className="px-5 py-4 border-b border-border flex-shrink-0 bg-muted">
					<div className="flex items-center justify-between gap-3">
						<DialogTitle className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
							高级配置
						</DialogTitle>
						<div className="flex items-center gap-2">
							{props.hasChanges ? (
								<Button
									onClick={props.onSave}
									size="sm"
									className="cyber-btn-primary h-8"
								>
									保存
								</Button>
							) : null}
							<Button
								variant="outline"
								size="sm"
								className="cyber-btn-ghost h-8"
								onClick={() => props.onOpenChange(false)}
							>
								关闭
							</Button>
						</div>
					</div>
				</DialogHeader>

				<div className="flex-1 min-h-0 flex">
					<div className="w-[260px] flex-shrink-0 border-r border-border bg-muted/40 overflow-y-auto">
						<div className="p-4 space-y-4">
							<div>
								<div className="text-[11px] font-mono font-bold uppercase text-muted-foreground mb-2">
									LLM 高级参数
								</div>
								<div className="space-y-1">
									{[
										["llmCustomHeaders", "自定义请求头"],
										["llmTimeout", "请求超时"],
										["llmTemperature", "温度"],
										["llmMaxTokens", "最大 Tokens"],
										["llmFirstTokenTimeout", "首 Token 超时"],
										["llmStreamTimeout", "流式超时"],
										["agentTimeout", "Agent 总超时"],
										["subAgentTimeout", "子 Agent 超时"],
										["toolTimeout", "工具超时"],
									].map(([id, label]) => (
										<button
											key={id}
											type="button"
											onClick={() =>
												props.onSelectItem(id as AdvancedConfigItemId)
											}
											className={`w-full text-left px-3 py-2 rounded-md text-xs font-mono border transition-colors ${
												props.selectedItemId === id
													? "bg-primary/15 text-primary border-primary/40"
													: "bg-background/40 text-muted-foreground border-border hover:text-foreground hover:border-border/80"
											}`}
										>
											{label}
										</button>
									))}
								</div>
							</div>

							<div>
								<div className="text-[11px] font-mono font-bold uppercase text-muted-foreground mb-2">
									分析参数
								</div>
								<div className="space-y-1">
									{[
										["maxAnalyzeFiles", "最大分析文件数"],
										["llmConcurrency", "LLM 并发数"],
										["llmGapMs", "请求间隔"],
										["outputLanguage", "输出语言"],
									].map(([id, label]) => (
										<button
											key={id}
											type="button"
											onClick={() =>
												props.onSelectItem(id as AdvancedConfigItemId)
											}
											className={`w-full text-left px-3 py-2 rounded-md text-xs font-mono border transition-colors ${
												props.selectedItemId === id
													? "bg-primary/15 text-primary border-primary/40"
													: "bg-background/40 text-muted-foreground border-border hover:text-foreground hover:border-border/80"
											}`}
										>
											{label}
										</button>
									))}
								</div>
							</div>
						</div>
					</div>

					<div className="flex-1 min-w-0 overflow-y-auto bg-background/20">
						{renderItemPanel()}
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function SystemConfig({
	visibleSections = ["llm", "embedding", "analysis"],
	defaultSection = "llm",
	mergedView = false,
	showLlmSummaryCards = true,
	llmSummaryOnly = false,
	showFloatingSaveButton = true,
	compactLayout = false,
	sharedDraftState,
	onLlmSummaryChange,
}: SystemConfigProps = {}) {
	const sections = visibleSections.length > 0 ? visibleSections : ["llm"];
	const internalDraftState = useSystemConfigDraftState({
		enabled: sharedDraftState == null,
	});
	const {
		config,
		setConfig,
		loading,
		hasChanges,
		setHasChanges,
		llmProvidersFromBackend,
		fetchedModelsByProvider,
		setFetchedModelsByProvider,
		fetchedModelMetadataByProvider,
		setFetchedModelMetadataByProvider,
		reloadConfig,
	} = sharedDraftState ?? internalDraftState;
	const [showApiKey, setShowApiKey] = useState(false);
	const [llmModelPopoverOpen, setLlmModelPopoverOpen] = useState(false);
	const [savingLLM, setSavingLLM] = useState(false);
	const [testingLLM, setTestingLLM] = useState(false);
	const [advancedOpen, setAdvancedOpen] = useState(false);
	const [selectedAdvancedItemId, setSelectedAdvancedItemId] =
		useState<AdvancedConfigItemId>("llmTimeout");
	const [fetchingModels, setFetchingModels] = useState(false);
	const [llmDropdownPanelStyle, setLlmDropdownPanelStyle] =
		useState<CSSProperties | null>(null);
	const [onlineModelStatsBySignature, setOnlineModelStatsBySignature] = useState<
		Record<string, LlmModelStatsCounts>
	>({});
	const [modelStatsFetchStateBySignature, setModelStatsFetchStateBySignature] =
		useState<Record<string, LlmModelStatsFetchState>>({});
	const [llmTestResult, setLlmTestResult] = useState<{
		success: boolean;
		message: string;
		debug?: Record<string, unknown>;
	} | null>(null);
	const [showDebugInfo, setShowDebugInfo] = useState(true);
	const llmBaseUrlTouchedRef = useRef(false);
	const llmModelTouchedRef = useRef(false);
	const llmMaxTokensTouchedRef = useRef(false);
	const autoFetchSignatureRef = useRef<string>("");
	const latestConfigRef = useRef<SystemConfigData | null>(config);
	const llmModelDropdownAreaRef = useRef<HTMLDivElement | null>(null);
	const llmModelDropdownPanelRef = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		latestConfigRef.current = config;
	}, [config]);

	useEffect(() => {
		if (!llmModelPopoverOpen) return;
		const updateDropdownPosition = () => {
			const anchor = llmModelDropdownAreaRef.current;
			if (!anchor) return;
			const rect = anchor.getBoundingClientRect();
			const viewportHeight = window.innerHeight;
			const top = rect.bottom + 6;
			const panelHeight = Math.max(220, Math.min(340, viewportHeight - top - 12));
			setLlmDropdownPanelStyle({
				position: "fixed",
				left: rect.left,
				top,
				width: rect.width,
				height: panelHeight,
				maxHeight: panelHeight,
				zIndex: 80,
			});
		};

		const handleMouseDown = (event: MouseEvent) => {
			const target = event.target as Node | null;
			if (!target) return;
			if (llmModelDropdownAreaRef.current?.contains(target)) return;
			if (llmModelDropdownPanelRef.current?.contains(target)) return;
			setLlmModelPopoverOpen(false);
		};
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") {
				setLlmModelPopoverOpen(false);
			}
		};
		updateDropdownPosition();
		document.addEventListener("mousedown", handleMouseDown);
		document.addEventListener("keydown", handleKeyDown);
		window.addEventListener("resize", updateDropdownPosition);
		window.addEventListener("scroll", updateDropdownPosition, true);
		return () => {
			document.removeEventListener("mousedown", handleMouseDown);
			document.removeEventListener("keydown", handleKeyDown);
			window.removeEventListener("resize", updateDropdownPosition);
			window.removeEventListener("scroll", updateDropdownPosition, true);
		};
	}, [llmModelPopoverOpen]);

	const tabsGridClass = useMemo(() => {
		if (sections.length <= 1) return "grid-cols-1";
		if (sections.length === 2) return "grid-cols-2";
		if (sections.length === 3) return "grid-cols-3";
		return "grid-cols-4";
	}, [sections.length]);

	const llmProviderOptions = useMemo(() => {
		return buildLlmProviderOptions({
			backendProviders: llmProvidersFromBackend,
			currentProviderId: config?.llmProvider || "",
		});
	}, [llmProvidersFromBackend, config?.llmProvider]);

	const loadConfig = reloadConfig;

	const updateConfig = (
		key: keyof SystemConfigData,
		value: string | number,
	) => {
		if (key === "llmModel") {
			llmModelTouchedRef.current = true;
		}
		if (key === "llmMaxTokens") {
			llmMaxTokensTouchedRef.current = true;
		}
		setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
		setHasChanges(true);
	};

	const getProviderInfo = (providerId: string): LLMProviderItem | undefined => {
		return getLlmProviderInfo(llmProviderOptions, providerId);
	};

	const getDefaultModelForProvider = (providerId: string): string => {
		return resolveDefaultModelForProvider(llmProviderOptions, providerId);
	};

	const getDefaultBaseUrlForProvider = (providerId: string): string => {
		return resolveDefaultBaseUrlForProvider(llmProviderOptions, providerId);
	};

	const getModelsForProvider = (providerId: string): string[] => {
		const fetchedModels = fetchedModelsByProvider[providerId];
		if (Array.isArray(fetchedModels) && fetchedModels.length > 0)
			return fetchedModels;
		const backend = getProviderInfo(providerId);
		return Array.isArray(backend?.models) ? backend.models : [];
	};

	const getModelMetadataForProvider = (
		providerId: string,
	): Record<string, LLMModelMetadata> => {
		const fetched = fetchedModelMetadataByProvider[providerId];
		if (fetched && typeof fetched === "object") return fetched;
		return {};
	};

	const getModelMetadata = (
		providerId: string,
		modelName: string,
	): LLMModelMetadata | undefined => {
		const metadata = getModelMetadataForProvider(providerId);
		if (metadata[modelName]) return metadata[modelName];
		const normalized = String(modelName || "")
			.trim()
			.toLowerCase();
		if (!normalized) return undefined;
		const matchedKey = Object.keys(metadata).find(
			(key) => key.trim().toLowerCase() === normalized,
		);
		if (!matchedKey) return undefined;
		return metadata[matchedKey];
	};

	const resolveCurrentModelName = (
		providerId: string,
		modelValue: string,
	): string => {
		const explicitModel = String(modelValue || "").trim();
		if (explicitModel) return explicitModel;
		return getDefaultModelForProvider(providerId);
	};

	const getRecommendedMaxTokens = (
		providerId: string,
		modelName: string,
	): TokenRecommendation => {
		const fallbackValue = DEFAULT_CONFIG.llmMaxTokens;
		const model = String(modelName || "").trim();
		if (!model) {
			return { value: fallbackValue, source: "default" };
		}

		const metadata = getModelMetadata(providerId, model);
		const metadataRecommendation =
			typeof metadata?.recommendedMaxTokens === "number" &&
			metadata.recommendedMaxTokens > 0
				? metadata.recommendedMaxTokens
				: null;
		if (metadataRecommendation !== null) {
			return {
				value: metadataRecommendation,
				source: String(metadata?.source || "online_metadata"),
			};
		}

		const staticRecommendation = recommendTokensFromStaticRules(model);
		if (typeof staticRecommendation === "number" && staticRecommendation > 0) {
			return { value: staticRecommendation, source: "static_mapping" };
		}

		return { value: fallbackValue, source: "default" };
	};

	const applyRecommendedMaxTokens = (
		providerId: string,
		modelName: string,
		options?: { force?: boolean; markChanges?: boolean },
	): TokenRecommendation => {
		const recommendation = getRecommendedMaxTokens(providerId, modelName);
		const shouldForce = Boolean(options?.force);
		const shouldMarkChanges = options?.markChanges !== false;
		if (!config) return recommendation;
		if (!shouldForce && llmMaxTokensTouchedRef.current) return recommendation;
		if (config.llmMaxTokens === recommendation.value) return recommendation;

		setConfig((prev) =>
			prev
				? {
						...prev,
						llmMaxTokens: recommendation.value,
					}
				: prev,
		);
		if (shouldMarkChanges) {
			setHasChanges(true);
		}
		return recommendation;
	};

	const shouldRequireApiKey = (providerId: string): boolean => {
		return resolveShouldRequireApiKey(llmProviderOptions, providerId);
	};

	type StrictLlmInputs = {
		providerId: string;
		apiKey: string;
		model: string;
		baseUrl: string;
		customHeaders: string;
	};

	const validateStrictLlmInputs = (
		source: "save" | "test",
	): {
		ok: boolean;
	} & StrictLlmInputs => {
		if (!config) {
			return {
				ok: false,
				providerId: "openai",
				apiKey: "",
				model: "",
				baseUrl: "",
				customHeaders: "",
			};
		}
		const providerId = normalizeLlmProviderId(config.llmProvider);
		const apiKey = String(config.llmApiKey || "").trim();
		const model = String(config.llmModel || "").trim();
		const baseUrl = String(config.llmBaseUrl || "").trim();
		const parsedCustomHeaders = parseLlmCustomHeadersInput(
			config.llmCustomHeaders,
		);
		if (!parsedCustomHeaders.ok) {
			const parseErrorMessage = getLlmCustomHeadersParseErrorMessage(
				parsedCustomHeaders,
			);
			toast.error(
				`无法${source === "save" ? "保存" : "测试"}：${parseErrorMessage || "自定义请求头格式不正确"}`,
			);
			return {
				ok: false,
				providerId,
				apiKey,
				model,
				baseUrl,
				customHeaders: "",
			};
		}

		if (!model) {
			toast.error(
				`无法${source === "save" ? "保存" : "测试"}：请先填写模型（llmModel）`,
			);
			return {
				ok: false,
				providerId,
				apiKey,
				model,
				baseUrl,
				customHeaders: parsedCustomHeaders.normalizedText,
			};
		}
		if (!baseUrl) {
			toast.error(
				`无法${source === "save" ? "保存" : "测试"}：请先填写 Base URL（llmBaseUrl）`,
			);
			return {
				ok: false,
				providerId,
				apiKey,
				model,
				baseUrl,
				customHeaders: parsedCustomHeaders.normalizedText,
			};
		}
		if (shouldRequireApiKey(providerId) && !apiKey) {
			toast.error(
				`无法${source === "save" ? "保存" : "测试"}：当前提供商必须配置 API Key`,
			);
			return {
				ok: false,
				providerId,
				apiKey,
				model,
				baseUrl,
				customHeaders: parsedCustomHeaders.normalizedText,
			};
		}
		return {
			ok: true,
			providerId,
			apiKey,
			model,
			baseUrl,
			customHeaders: parsedCustomHeaders.normalizedText,
		};
	};

	const handleProviderChange = (newProvider: string) => {
		const defaultModel = getDefaultModelForProvider(newProvider);
		const defaultBaseUrl = getDefaultBaseUrlForProvider(newProvider);
		const nextModel = resolveProviderSwitchFieldValue({
			currentValue: latestConfigRef.current?.llmModel,
			wasTouched: llmModelTouchedRef.current,
			nextDefaultValue: defaultModel,
		});
		setConfig((prev) => {
			if (!prev) return prev;
			return {
				...prev,
				llmProvider: newProvider,
				llmModel: resolveProviderSwitchFieldValue({
					currentValue: prev.llmModel,
					wasTouched: llmModelTouchedRef.current,
					nextDefaultValue: defaultModel,
				}),
				llmBaseUrl: resolveProviderSwitchFieldValue({
					currentValue: prev.llmBaseUrl,
					wasTouched: llmBaseUrlTouchedRef.current,
					nextDefaultValue: defaultBaseUrl,
					preserveExistingNonEmptyValue: true,
					allowExplicitEmptyOverride: true,
				}),
			};
		});
		setLlmModelPopoverOpen(false);
		applyRecommendedMaxTokens(newProvider, nextModel, {
			force: false,
			markChanges: true,
		});
		setHasChanges(true);
		setLlmTestResult(null);
	};

	const fetchModels = async (options?: {
		trigger?: "manual" | "auto";
		silent?: boolean;
	}) => {
		const configSnapshot = latestConfigRef.current;
		if (!configSnapshot) return;
		const trigger = options?.trigger || "manual";
		const silent = Boolean(options?.silent);
		const providerId = normalizeLlmProviderId(configSnapshot.llmProvider);
		const baseUrl = String(configSnapshot.llmBaseUrl || "").trim();
		const apiKey = String(configSnapshot.llmApiKey || "").trim();
		const parsedCustomHeaders = parseLlmCustomHeadersInput(
			configSnapshot.llmCustomHeaders,
		);
		const requiresApiKey = shouldRequireApiKey(providerId);
		const signature = `${providerId}|${baseUrl}|${requiresApiKey ? apiKey : ""}|${
			parsedCustomHeaders.ok ? parsedCustomHeaders.normalizedText : "invalid"
		}`;

		if (!providerId || !baseUrl) return;
		if (!parsedCustomHeaders.ok) {
			const parseErrorMessage = getLlmCustomHeadersParseErrorMessage(
				parsedCustomHeaders,
			);
			setModelStatsFetchStateBySignature((prev) => ({
				...prev,
				[signature]: "failed",
			}));
			if (!silent) {
				toast.error(parseErrorMessage || "自定义请求头格式不正确");
			}
			return;
		}
		if (requiresApiKey && !apiKey) {
			if (!silent) {
				toast.error("当前提供商需要 API Key，无法拉取模型");
			}
			return;
		}

		if (trigger === "manual") {
			autoFetchSignatureRef.current = signature;
		}

		setModelStatsFetchStateBySignature((prev) => ({
			...prev,
			[signature]: "loading",
		}));
		setFetchingModels(true);
		try {
			const result = await api.fetchLLMModels({
				provider: providerId,
				apiKey,
				baseUrl,
				customHeaders: parsedCustomHeaders.normalizedText,
			});
			const latestConfig = latestConfigRef.current;
			if (!latestConfig) return;
			const latestProviderId = normalizeLlmProviderId(latestConfig.llmProvider);
			const latestBaseUrl = String(latestConfig.llmBaseUrl || "").trim();
			const latestApiKey = String(latestConfig.llmApiKey || "").trim();
			const latestParsedCustomHeaders = parseLlmCustomHeadersInput(
				latestConfig.llmCustomHeaders,
			);
			const latestSignature = `${latestProviderId}|${latestBaseUrl}|${
				shouldRequireApiKey(latestProviderId) ? latestApiKey : ""
			}|${latestParsedCustomHeaders.ok ? latestParsedCustomHeaders.normalizedText : "invalid"}`;
			if (latestSignature !== signature) return;

			const normalizedModels = Array.isArray(result.models)
				? [
						...new Set(
							result.models.filter((m) => typeof m === "string" && m.trim()),
						),
					]
				: [];
			setFetchedModelsByProvider((prev) => ({
				...prev,
				[providerId]: normalizedModels,
			}));
			const normalizedMetadata: Record<string, LLMModelMetadata> = {};
			const rawMetadata = result.modelMetadata;
			if (rawMetadata && typeof rawMetadata === "object") {
				for (const [modelName, modelMeta] of Object.entries(rawMetadata)) {
					if (!modelMeta || typeof modelMeta !== "object") continue;
					normalizedMetadata[modelName] = {
						contextWindow:
							typeof modelMeta.contextWindow === "number"
								? modelMeta.contextWindow
								: null,
						maxOutputTokens:
							typeof modelMeta.maxOutputTokens === "number"
								? modelMeta.maxOutputTokens
								: null,
						recommendedMaxTokens:
							typeof modelMeta.recommendedMaxTokens === "number"
								? modelMeta.recommendedMaxTokens
								: null,
						source: modelMeta.source,
					};
				}
			}
			setFetchedModelMetadataByProvider((prev) => ({
				...prev,
				[providerId]: normalizedMetadata,
			}));
			if (result.source === "online") {
				setOnlineModelStatsBySignature((prev) => ({
					...prev,
					[signature]: {
						availableModelCount: normalizedModels.length,
						availableModelMetadataCount: Object.keys(normalizedMetadata).length,
					},
				}));
				setModelStatsFetchStateBySignature((prev) => ({
					...prev,
					[signature]: "online",
				}));
			} else {
				setModelStatsFetchStateBySignature((prev) => ({
					...prev,
					[signature]: "failed",
				}));
			}
			const latestModel = String(latestConfig.llmModel || "").trim();
			const effectiveModel =
				resolveCurrentModelName(providerId, latestModel) ||
				result.defaultModel ||
				getDefaultModelForProvider(providerId);
			applyRecommendedMaxTokens(providerId, effectiveModel, {
				force: false,
				markChanges: true,
			});
			if (!silent) {
				if (result.success) {
					const currentModel = String(latestConfig.llmModel || "").trim();
					const hasCurrentModel = Boolean(currentModel);
					const matched = hasCurrentModel
						? normalizedModels.includes(currentModel)
						: false;
					if (hasCurrentModel && matched) {
						toast.success("模型列表已更新，当前输入已匹配可选项");
					} else if (hasCurrentModel) {
						toast.success("模型列表已更新，当前输入可继续作为自定义模型");
					} else {
						toast.success(result.message || "模型列表已更新");
					}
				} else {
					toast.error(result.message || "模型拉取失败");
				}
			}
		} catch (error) {
			setModelStatsFetchStateBySignature((prev) => ({
				...prev,
				[signature]: "failed",
			}));
			if (!silent) {
				toast.error(
					`模型拉取失败: ${error instanceof Error ? error.message : "未知错误"}`,
				);
			}
		} finally {
			setFetchingModels(false);
		}
	};

	const handleFetchModels = async () => {
		await fetchModels({ trigger: "manual", silent: false });
	};

	useEffect(() => {
		if (!config) return;
		const providerId = normalizeLlmProviderId(config.llmProvider);
		const baseUrl = String(config.llmBaseUrl || "").trim();
		const apiKey = String(config.llmApiKey || "").trim();
		const parsedCustomHeaders = parseLlmCustomHeadersInput(config.llmCustomHeaders);
		const requiresApiKey = shouldRequireApiKey(providerId);
		const providerInfo = getProviderInfo(providerId);
		if (!providerId || !baseUrl) return;
		if (!parsedCustomHeaders.ok) return;
		if (!providerInfo?.supportsModelFetch) return;
		if (requiresApiKey && !apiKey) return;
		const signature = `${providerId}|${baseUrl}|${requiresApiKey ? apiKey : ""}|${parsedCustomHeaders.normalizedText}`;
		if (autoFetchSignatureRef.current === signature) return;
		setModelStatsFetchStateBySignature((prev) => ({
			...prev,
			[signature]: "loading",
		}));
		const timer = setTimeout(() => {
			autoFetchSignatureRef.current = signature;
			void fetchModels({ trigger: "auto", silent: true });
		}, 700);
		return () => clearTimeout(timer);
	}, [
		config?.llmProvider,
		config?.llmBaseUrl,
		config?.llmApiKey,
		config?.llmCustomHeaders,
		llmProvidersFromBackend,
	]);

	const handleLlmModelSelect = (value: string) => {
		if (!config) return;
		const providerId = normalizeLlmProviderId(config.llmProvider);
		const nextModel = String(value || "").trim();
		if (!nextModel) return;
		updateConfig("llmModel", nextModel);
		applyRecommendedMaxTokens(providerId, nextModel, {
			force: false,
			markChanges: true,
		});
		setLlmModelPopoverOpen(false);
	};

	const persistConfig = async (validated: StrictLlmInputs) => {
		if (!config) return null;
		try {
			const savedConfig = await api.updateUserConfig({
				llmConfig: {
					llmProvider: validated.providerId,
					llmApiKey: validated.apiKey,
					llmModel: validated.model,
					llmBaseUrl: validated.baseUrl,
					llmCustomHeaders: validated.customHeaders,
					llmTimeout: config.llmTimeout,
					llmTemperature: config.llmTemperature,
					llmMaxTokens: config.llmMaxTokens,
					llmFirstTokenTimeout: config.llmFirstTokenTimeout,
					llmStreamTimeout: config.llmStreamTimeout,
					agentTimeout: config.agentTimeout,
					subAgentTimeout: config.subAgentTimeout,
					toolTimeout: config.toolTimeout,
				},
				otherConfig: {
					maxAnalyzeFiles: config.maxAnalyzeFiles,
					llmConcurrency: config.llmConcurrency,
					llmGapMs: config.llmGapMs,
					outputLanguage: config.outputLanguage,
				},
			});

			if (savedConfig) {
				const nextConfig = buildSystemConfigDataFromBackendConfig(savedConfig);
				setConfig(nextConfig);
				llmBaseUrlTouchedRef.current = false;
				llmModelTouchedRef.current = false;
				llmMaxTokensTouchedRef.current = false;
			}

			setHasChanges(false);
			toast.success("配置已保存！");
			return savedConfig;
		} catch (error) {
			toast.error(
				`保存失败: ${error instanceof Error ? error.message : "未知错误"}`,
			);
			throw error;
		}
	};

	const saveConfig = async () => {
		if (!config) return null;
		const validated = validateStrictLlmInputs("save");
		if (!validated.ok) return null;
		setSavingLLM(true);
		try {
			return await persistConfig(validated);
		} finally {
			setSavingLLM(false);
		}
	};

	const resetConfig = async () => {
		if (!window.confirm("确定要重置为默认配置吗？")) return;
		try {
			await api.deleteUserConfig();
			await loadConfig();
			llmBaseUrlTouchedRef.current = false;
			llmModelTouchedRef.current = false;
			llmMaxTokensTouchedRef.current = false;
			setHasChanges(false);
			toast.success("已重置为默认配置");
		} catch (error) {
			toast.error(
				`重置失败: ${error instanceof Error ? error.message : "未知错误"}`,
			);
		}
	};

	const runLlmConnectionTest = async (validated: StrictLlmInputs) => {
		setLlmTestResult(null);
		try {
			const result = await api.testLLMConnection({
				provider: validated.providerId,
				apiKey: validated.apiKey,
				model: validated.model,
				baseUrl: validated.baseUrl,
				customHeaders: validated.customHeaders,
			});
			setLlmTestResult(result);
			if (result.success) {
				toast.success(`连接成功！模型: ${result.model}`);
			} else {
				toast.error(`连接失败: ${result.message}`);
			}
		} catch (error) {
			const message = error instanceof Error ? error.message : "未知错误";
			setLlmTestResult({ success: false, message });
			toast.error(`测试失败: ${message}`);
			return { success: false, message };
		}
	};


	const handleSaveAndTestLLM = async () => {
		if (!config) return;
		const validated = validateStrictLlmInputs("save");
		if (!validated.ok) return;

		setSavingLLM(true);
		setTestingLLM(true);
		try {
			await runSaveThenTestAction({
				save: () => persistConfig(validated),
				test: () => runLlmConnectionTest(validated),
			});
		} finally {
			setSavingLLM(false);
			setTestingLLM(false);
		}
	};

	const normalizedProviderId = normalizeLlmProviderId(config?.llmProvider || "");
	const selectedProviderInfo = getProviderInfo(normalizedProviderId);
	const currentModelName = config
		? resolveCurrentModelName(normalizedProviderId, config.llmModel)
		: "";
	const availableModelCount = config
		? getModelsForProvider(normalizedProviderId).length
		: 0;
	const availableModelMetadataCount = config
		? Object.keys(getModelMetadataForProvider(normalizedProviderId)).length
		: 0;
	const statsBaseUrl = String(config?.llmBaseUrl || "").trim();
	const statsApiKey = String(config?.llmApiKey || "").trim();
	const statsRequiresApiKey = shouldRequireApiKey(normalizedProviderId);
	const supportsModelFetch = Boolean(selectedProviderInfo?.supportsModelFetch);
	const shouldPreferOnlineStats = Boolean(
		config &&
			supportsModelFetch &&
			normalizedProviderId !== "custom" &&
			statsBaseUrl &&
			(!statsRequiresApiKey || statsApiKey),
	);
	const currentStatsSignature = shouldPreferOnlineStats
		? `${normalizedProviderId}|${statsBaseUrl}|${statsRequiresApiKey ? statsApiKey : ""}`
		: null;
	const preferredModelStats = resolvePreferredModelStats({
		shouldPreferOnlineStats,
		staticStats: {
			availableModelCount,
			availableModelMetadataCount,
		},
		cachedOnlineStats: currentStatsSignature
			? onlineModelStatsBySignature[currentStatsSignature] || null
			: null,
		fetchState: currentStatsSignature
			? modelStatsFetchStateBySignature[currentStatsSignature] || "idle"
			: "idle",
	});

	useEffect(() => {
		if (!onLlmSummaryChange) return;
		onLlmSummaryChange({
			providerId: normalizedProviderId,
			providerLabel: selectedProviderInfo?.name || normalizedProviderId || "--",
			currentModelName: currentModelName || "--",
			availableModelCount: preferredModelStats.availableModelCount,
			availableModelMetadataCount:
				preferredModelStats.availableModelMetadataCount,
			supportsModelFetch,
			modelStatsStatus: preferredModelStats.modelStatsStatus,
			modelStatsSource: preferredModelStats.modelStatsSource,
			shouldPreferOnlineStats,
		});
	}, [
		onLlmSummaryChange,
		normalizedProviderId,
		selectedProviderInfo?.name,
		currentModelName,
		preferredModelStats.availableModelCount,
		preferredModelStats.availableModelMetadataCount,
		preferredModelStats.modelStatsSource,
		preferredModelStats.modelStatsStatus,
		supportsModelFetch,
		shouldPreferOnlineStats,
	]);

	if (loading || !config) {
		return (
			<div className="flex items-center justify-center min-h-[400px]">
				<div className="text-center space-y-4">
					<div className="loading-spinner mx-auto" />
					<p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
						加载配置中...
					</p>
				</div>
			</div>
		);
	}

	const hasModelConfigured = String(config.llmModel || "").trim().length > 0;
	const hasBaseUrlConfigured =
		String(config.llmBaseUrl || "").trim().length > 0;

	const isConfigured =
		(!shouldRequireApiKey(config.llmProvider) ||
			config.llmApiKey.trim() !== "") &&
		hasModelConfigured &&
		hasBaseUrlConfigured;

	return (
		<div className="space-y-6">
			<Tabs
				defaultValue={
					sections.includes(defaultSection) ? defaultSection : sections[0]
				}
				className="w-full"
			>
				{!mergedView && sections.length > 1 && (
					<TabsList
						className={`grid w-full ${tabsGridClass} bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6`}
					>
						{sections.includes("llm") && (
							<TabsTrigger
								value="llm"
								className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
							>
								<Zap className="w-3 h-3" /> LLM 配置
							</TabsTrigger>
						)}
						{sections.includes("embedding") && (
							<TabsTrigger
								value="embedding"
								className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
							>
								<Brain className="w-3 h-3" /> 嵌入模型
							</TabsTrigger>
						)}
						{sections.includes("analysis") && (
							<TabsTrigger
								value="analysis"
								className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"
							>
								<Settings className="w-3 h-3" /> 分析参数
							</TabsTrigger>
						)}
					</TabsList>
				)}

					{sections.includes("llm") && (
						<TabsContent
							value="llm"
							className={compactLayout ? "space-y-4" : "space-y-6"}
						>
							<div
								className={cn(
									"cyber-card !overflow-visible",
									compactLayout ? "p-4 space-y-4" : "p-6 space-y-6",
								)}
							>
							{showLlmSummaryCards ? (
								<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
									<div className="cyber-card p-4">
										<div className="flex items-center justify-between">
											<div>
												<p className="stat-label">模型提供商</p>
												<p className="stat-value text-2xl break-all">
													{selectedProviderInfo?.name || normalizedProviderId}
												</p>
											</div>
											<div className="stat-icon text-primary">
												<Settings className="w-6 h-6" />
											</div>
										</div>
									</div>

										<div className="cyber-card p-4">
											<div className="flex items-center justify-between">
												<div>
													<p className="stat-label">当前采用模型</p>
													<p className="stat-value text-2xl break-all">
														{currentModelName || "--"}
													</p>
												</div>
											<div className="stat-icon text-sky-400">
												<Brain className="w-6 h-6" />
											</div>
										</div>
									</div>

									<div className="cyber-card p-4">
										<div className="flex items-center justify-between">
											<div>
												<p className="stat-label">支持模型数量</p>
												<p className="stat-value text-2xl break-all">
													{availableModelCount}
												</p>
											</div>
											<div className="stat-icon text-emerald-400">
												<Zap className="w-6 h-6" />
											</div>
										</div>
									</div>
								</div>
							) : null}

							{!llmSummaryOnly ? (
								<>
									<div
										className={cn(
											"grid grid-cols-1 md:grid-cols-2 min-[1800px]:grid-cols-4",
											compactLayout ? "gap-3" : "gap-4",
										)}
									>
										<div className="space-y-2 min-w-0">
											<Label className="text-base font-bold text-muted-foreground uppercase">
												模型供应商
											</Label>
											<Select
												value={config.llmProvider}
												onValueChange={handleProviderChange}
											>
												<SelectTrigger
													className={cn(
														"cyber-input",
														compactLayout ? "h-10" : "h-12",
													)}
												>
													<SelectValue placeholder="选择模型供应商" />
												</SelectTrigger>
												<SelectContent className="cyber-dialog border-border">
													{llmProviderOptions.map((provider) => (
														<SelectItem
															key={provider.id}
															value={provider.id}
															className="font-mono"
														>
															{provider.name}
														</SelectItem>
													))}
												</SelectContent>
											</Select>
										</div>

										<div className="space-y-2 min-w-0">
											<Label className="text-base font-bold text-muted-foreground uppercase">
												地址
												<span className="text-rose-400 ml-1">*</span>
											</Label>
											<Input
												value={config.llmBaseUrl}
												onChange={(event) => {
													llmBaseUrlTouchedRef.current = true;
													updateConfig("llmBaseUrl", event.target.value);
												}}
												placeholder={(() => {
													const baseUrl = getDefaultBaseUrlForProvider(
														config.llmProvider,
													);
													if (baseUrl) return `必填，例如：${baseUrl}`;
													return "必填：请输入完整 Base URL";
												})()}
												className={cn(
													"cyber-input",
													compactLayout ? "h-10" : "h-12",
												)}
											/>
										</div>

										<div className="space-y-2 min-w-0">
											<Label className="text-base font-bold text-muted-foreground uppercase">
												密钥
												{shouldRequireApiKey(config.llmProvider) ? (
													<span className="text-rose-400 ml-1">*</span>
												) : null}
												<Button
													variant="outline"
													size="icon"
													onClick={() => setShowApiKey((prev) => !prev)}
													className={cn(
														"cyber-btn-ghost shrink-0",
														compactLayout ? "h-4 w-10" : "h-12 w-12",
													)}
													disabled={!shouldRequireApiKey(config.llmProvider)}
													type="button"
												>
													{showApiKey ? (
														<EyeOff className="h-4 w-4" />
													) : (
														<Eye className="h-4 w-4" />
													)}
												</Button>
											</Label>
											
											<div className="flex gap-2">
												<Input
													type={showApiKey ? "text" : "password"}
													value={config.llmApiKey}
													onChange={(event) =>
														updateConfig("llmApiKey", event.target.value)
													}
													placeholder={
														shouldRequireApiKey(config.llmProvider)
															? "输入你的 API Key"
															: "该提供商无需 API Key"
													}
													className={cn(
														"cyber-input",
														compactLayout ? "h-10" : "h-12",
													)}
													disabled={!shouldRequireApiKey(config.llmProvider)}
												/>
												
											</div>
										</div>

										<div className="space-y-2 min-w-0">
											<Label className="text-base font-bold text-muted-foreground uppercase">
												模型
												<span className="text-rose-400 ml-1">*</span>
												<Button
																type="button"
																variant="outline"
																className="h-4 cyber-btn-ghost text-xs"
																onClick={handleFetchModels}
																disabled={
																	fetchingModels ||
																	!config.llmProvider ||
																	!config.llmBaseUrl.trim() ||
																	(shouldRequireApiKey(config.llmProvider) &&
																		!config.llmApiKey.trim())
																}
															>
																{fetchingModels ? (
																	<>
																		<Loader2 className="w-3 h-3 mr-1 animate-spin" />
																		拉取中...
																	</>
																) : (
																	<>
																		<Zap className="w-3 h-3 mr-1" />
																		一键获取模型
																	</>
																)}
															</Button>
											</Label>
											{(() => {
												const providerId = config.llmProvider;
												const models = getModelsForProvider(providerId);
												const defaultModel =
													getDefaultModelForProvider(providerId) || "auto";
												const currentModel = String(config.llmModel || "");
												const normalizedCurrentModel = currentModel.trim();
												const normalizedQuery = normalizedCurrentModel
													.trim()
													.toLowerCase();
												const selectableModels = models
													.filter((model) => {
														if (!normalizedQuery) return true;
														return model.toLowerCase().includes(normalizedQuery);
													})
													.sort((a, b) => {
														const aStarts = normalizedQuery
															? a.toLowerCase().startsWith(normalizedQuery)
															: false;
														const bStarts = normalizedQuery
															? b.toLowerCase().startsWith(normalizedQuery)
															: false;
														if (aStarts !== bStarts) return aStarts ? -1 : 1;
														return a.localeCompare(b);
													})
													.slice(0, 80);

												return (
													<div className="space-y-2">
														<div
															className="relative"
															ref={llmModelDropdownAreaRef}
														>
															<div className="flex gap-2">
																<div className="relative flex-1 min-w-0">
																	<Input
																		value={currentModel}
																		onChange={(event) =>
																			updateConfig("llmModel", event.target.value)
																		}
																		onFocus={() => setLlmModelPopoverOpen(true)}
																		placeholder={`请输入模型名称，例如：${defaultModel}`}
																		className={cn(
																			"cyber-input font-mono",
																			compactLayout ? "h-10" : "h-12",
																		)}
																	/>
																	{llmModelPopoverOpen ? (
																		llmDropdownPanelStyle
																			? createPortal(
																					<div
																						ref={llmModelDropdownPanelRef}
																						style={llmDropdownPanelStyle}
																						className="border border-border rounded-md p-0 cyber-dialog shadow-lg overflow-hidden"
																					>
																						<Command className="bg-background h-full flex flex-col">
																							<CommandInput
																								placeholder="搜索模型..."
																								className="h-10 border-0 border-b border-border/60 rounded-none"
																							/>
																							<CommandList className="flex-1 overflow-y-auto custom-scrollbar">
																								<CommandEmpty>未找到匹配模型</CommandEmpty>
																								<CommandGroup>
																									{defaultModel ? (
																										<CommandItem
																											value={`默认模型 ${defaultModel}`}
																											onSelect={() =>
																												handleLlmModelSelect(defaultModel)
																											}
																											className="font-mono"
																										>
																											<Check
																												className={cn(
																													"mr-2 h-4 w-4",
																													normalizedCurrentModel ===
																														defaultModel
																														? "opacity-100"
																														: "opacity-0",
																												)}
																											/>
																											默认（{defaultModel}）
																										</CommandItem>
																									) : null}
																									{selectableModels.map((model) => (
																										<CommandItem
																											key={model}
																											value={model}
																											onSelect={() =>
																												handleLlmModelSelect(model)
																											}
																											className="font-mono"
																										>
																											<Check
																												className={cn(
																													"mr-2 h-4 w-4",
																													normalizedCurrentModel === model
																														? "opacity-100"
																														: "opacity-0",
																												)}
																											/>
																											<span className="truncate">
																												{model}
																											</span>
																										</CommandItem>
																									))}
																								</CommandGroup>
																							</CommandList>
																						</Command>
																					</div>,
																					document.body,
																				)
																			: null
																	) : null}
																</div>
																<Button
																	variant="outline"
																	role="combobox"
																	aria-expanded={llmModelPopoverOpen}
																	title="打开模型候选列表"
																	className={cn(
																		"px-0 cyber-btn-ghost shrink-0",
																		compactLayout ? "h-10 w-10" : "h-12 w-12",
																	)}
																	onClick={() =>
																		setLlmModelPopoverOpen((prev) => !prev)
																	}
																	type="button"
																>
																	<ChevronsUpDown className="h-4 w-4 opacity-70" />
																</Button>
															</div>
														</div>
														
													</div>
												);
											})()}
										</div>
									</div>

									<div className="pt-4 border-t border-border border-dashed flex justify-end flex-wrap gap-2">
										<Button
											onClick={handleSaveAndTestLLM}
											disabled={savingLLM || testingLLM || !isConfigured}
											className="cyber-btn-primary h-10"
											type="button"
										>
											{savingLLM || testingLLM ? (
												<>
													<Loader2 className="w-4 h-4 mr-2 animate-spin" />
													保存并测试中...
												</>
											) : (
												<>
													<Save className="w-4 h-4 mr-2" />
													保存并测试
												</>
											)}
										</Button>

										<Button
											variant="outline"
											className="cyber-btn-ghost h-10"
											onClick={() => setAdvancedOpen(true)}
											type="button"
										>
											<Settings className="w-4 h-4 mr-2" />
											高级配置
										</Button>

										<Button
											onClick={resetConfig}
											disabled={savingLLM || testingLLM}
											variant="ghost"
											className="cyber-btn-ghost h-10"
											type="button"
										>
											<RotateCcw className="w-4 h-4 mr-2" />
											重置
										</Button>
									</div>

									{llmTestResult && (
										<div
											className={`p-3 rounded-lg ${llmTestResult.success ? "bg-emerald-500/10 border border-emerald-500/30" : "bg-rose-500/10 border border-rose-500/30"}`}
										>
											<div className="flex items-center justify-between">
												<div className="flex items-center gap-2 text-sm">
													{llmTestResult.success ? (
														<CheckCircle2 className="h-4 w-4 text-emerald-400" />
													) : (
														<AlertCircle className="h-4 w-4 text-rose-400" />
													)}
													<span
														className={
															llmTestResult.success
																? "text-emerald-300/80"
																: "text-rose-300/80"
														}
													>
														{llmTestResult.message}
													</span>
												</div>
												{llmTestResult.debug && (
													<button
														onClick={() => setShowDebugInfo((prev) => !prev)}
														className="text-xs text-muted-foreground hover:text-foreground underline"
														type="button"
													>
														{showDebugInfo ? "隐藏调试信息" : "显示调试信息"}
													</button>
												)}
											</div>
											{showDebugInfo && llmTestResult.debug && (
												<pre className="mt-3 p-3 bg-background/50 rounded text-xs text-muted-foreground overflow-x-auto">
													{JSON.stringify(llmTestResult.debug, null, 2)}
												</pre>
											)}
										</div>
									)}
								</>
							) : null}
						</div>

						{!llmSummaryOnly ? (
							<AdvancedConfigDialog
								open={advancedOpen}
								onOpenChange={setAdvancedOpen}
								selectedItemId={selectedAdvancedItemId}
								onSelectItem={setSelectedAdvancedItemId}
								config={config}
								hasChanges={hasChanges}
								onSave={saveConfig}
								onUpdate={updateConfig}
							/>
						) : null}
					</TabsContent>
				)}

					{!mergedView && sections.includes("embedding") && (
						<TabsContent
							value="embedding"
							className={compactLayout ? "space-y-4" : "space-y-6"}
						>
							<EmbeddingConfig compact={compactLayout} />
						</TabsContent>
					)}

				{!mergedView && sections.includes("analysis") && (
					<TabsContent value="analysis" className="space-y-6">
						<div className="cyber-card p-6 space-y-6">
							<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
								<div className="space-y-2">
									<Label className="text-xs font-bold text-muted-foreground uppercase">
										最大分析文件数
									</Label>
									<Input
										type="number"
										value={config.maxAnalyzeFiles}
										onChange={(event) =>
											updateConfig(
												"maxAnalyzeFiles",
												Number(event.target.value),
											)
										}
										className="h-10 cyber-input"
									/>
								</div>
								<div className="space-y-2">
									<Label className="text-xs font-bold text-muted-foreground uppercase">
										LLM 并发数
									</Label>
									<Input
										type="number"
										value={config.llmConcurrency}
										onChange={(event) =>
											updateConfig("llmConcurrency", Number(event.target.value))
										}
										className="h-10 cyber-input"
									/>
								</div>
								<div className="space-y-2">
									<Label className="text-xs font-bold text-muted-foreground uppercase">
										请求间隔 (毫秒)
									</Label>
									<Input
										type="number"
										value={config.llmGapMs}
										onChange={(event) =>
											updateConfig("llmGapMs", Number(event.target.value))
										}
										className="h-10 cyber-input"
									/>
								</div>
								<div className="space-y-2">
									<Label className="text-xs font-bold text-muted-foreground uppercase">
										输出语言
									</Label>
									<Select
										value={config.outputLanguage}
										onValueChange={(value) =>
											updateConfig("outputLanguage", value)
										}
									>
										<SelectTrigger className="h-10 cyber-input">
											<SelectValue />
										</SelectTrigger>
										<SelectContent className="cyber-dialog border-border">
											<SelectItem value="zh-CN" className="font-mono">
												🇨🇳 中文
											</SelectItem>
											<SelectItem value="en-US" className="font-mono">
												🇺🇸 English
											</SelectItem>
										</SelectContent>
									</Select>
								</div>
							</div>
						</div>
					</TabsContent>
				)}

			</Tabs>

			{hasChanges && !advancedOpen && showFloatingSaveButton && (
				<div className="fixed bottom-6 right-6 cyber-card p-4 z-50">
					<Button onClick={saveConfig} className="cyber-btn-primary h-12">
						<Save className="w-4 h-4 mr-2" /> 保存所有更改
					</Button>
				</div>
			)}
		</div>
	);
}
