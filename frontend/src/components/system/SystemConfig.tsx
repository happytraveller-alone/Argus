/**
 * System Config Component
 * Multi-provider intelligent engine configuration table.
 */

import {
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
	type Dispatch,
	type SetStateAction,
} from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
	AlertCircle,
	ArrowDown,
	ArrowUp,
	CheckCircle2,

	Loader2,
	Plus,
	RotateCcw,
	Save,
	Settings,
	Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import { runSaveThenBatchValidateAction } from "@/components/scan-config/intelligentEngineActionFlow";
import {
	buildLlmProviderOptions,
	getDefaultBaseUrlForProvider as resolveDefaultBaseUrlForProvider,
	getDefaultModelForProvider as resolveDefaultModelForProvider,
	getLlmProviderInfo,
	normalizeLlmProviderId,
	shouldRequireApiKey as resolveShouldRequireApiKey,
	type LLMProviderItem,
} from "@/shared/llm/providerCatalog";
import {
	resolvePreferredModelStats,
	type LlmModelStatsSource,
	type LlmModelStatsStatus,
} from "@/components/system/llmModelStatsSummary";
import { parseLlmCustomHeadersInput } from "@/shared/llm/providerCatalog";

type ConfigSection = "llm" | "analysis" | "cubesandbox";
type LlmSecretSource = "saved" | "imported" | "entered" | "none";
type DialogMode = "create" | "edit";

interface LlmAdvancedConfig {
	llmCustomHeaders: string;
	llmTimeout: number;
	llmTemperature: number;
	llmMaxTokens: number;
	llmFirstTokenTimeout: number;
	llmStreamTimeout: number;
	agentTimeout: number;
	subAgentTimeout: number;
	toolTimeout: number;
}

interface LlmConfigRow {
	id: string;
	priority: number;
	enabled: boolean;
	provider: string;
	baseUrl: string;
	model: string;
	apiKey: string;
	hasApiKey: boolean;
	secretSource: LlmSecretSource;
	advanced: LlmAdvancedConfig;
	modelStatus: {
		available: boolean | null;
		lastCheckedAt: string | null;
		reasonCode: string | null;
	};
	preflight: {
		status: "untested" | "passed" | "failed" | "missing_fields" | string;
		reasonCode: string | null;
		message: string | null;
		checkedAt: string | null;
		fingerprint: string | null;
	};
}

interface LlmConfigEnvelope {
	schemaVersion: 2;
	rows: LlmConfigRow[];
	latestPreflightRun: {
		runId: string | null;
		checkedAt: string | null;
		attemptedRowIds: string[];
		winningRowId: string | null;
		winningFingerprint: string | null;
	};
	migration: {
		status: "not_needed" | "migrated" | "reset" | string;
		message: string | null;
		sourceSchemaVersion?: number | null;
	};
}

interface CubeSandboxConfigData {
	enabled: boolean;
	apiBaseUrl: string;
	dataPlaneBaseUrl: string;
	templateId: string;
	helperPath: string;
	workDir: string;
	autoStart: boolean;
	autoInstall: boolean;
	helperTimeoutSeconds: number;
	executionTimeoutSeconds: number;
	sandboxCleanupTimeoutSeconds: number;
	stdoutLimitBytes: number;
	stderrLimitBytes: number;
}

interface SystemConfigData {
	llmConfig: LlmConfigEnvelope;
	rawOtherConfig: Record<string, unknown>;
	cubeSandbox: CubeSandboxConfigData;
	maxAnalyzeFiles: number;
	llmConcurrency: number;
	llmGapMs: number;
}

export interface SystemConfigSharedDraftState {
	config: SystemConfigData | null;
	setConfig: Dispatch<SetStateAction<SystemConfigData | null>>;
	loading: boolean;
	setLoading: Dispatch<SetStateAction<boolean>>;
	hasChanges: boolean;
	setHasChanges: Dispatch<SetStateAction<boolean>>;
	llmProvidersFromBackend: LLMProviderItem[];
	setLlmProvidersFromBackend: Dispatch<SetStateAction<LLMProviderItem[]>>;
	reloadConfig: () => Promise<void>;
}

interface SystemConfigProps {
	visibleSections?: ConfigSection[];
	defaultSection?: ConfigSection;
	mergedView?: boolean;
	showLlmSummaryCards?: boolean;
	llmSummaryOnly?: boolean;
	showFloatingSaveButton?: boolean;
	showInlineSaveButtons?: boolean;
	compactLayout?: boolean;
	cardClassName?: string;
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

const DEFAULT_ADVANCED: LlmAdvancedConfig = {
	llmCustomHeaders: "",
	llmTimeout: 300000,
	llmTemperature: 0.05,
	llmMaxTokens: 16384,
	llmFirstTokenTimeout: 180,
	llmStreamTimeout: 180,
	agentTimeout: 3600,
	subAgentTimeout: 1200,
	toolTimeout: 120,
};

const DEFAULT_CONFIG: SystemConfigData = {
	llmConfig: {
		schemaVersion: 2,
		rows: [],
		latestPreflightRun: {
			runId: null,
			checkedAt: null,
			attemptedRowIds: [],
			winningRowId: null,
			winningFingerprint: null,
		},
		migration: { status: "not_needed", message: null, sourceSchemaVersion: null },
	},
	rawOtherConfig: {},
	cubeSandbox: {
		enabled: false,
		apiBaseUrl: "http://127.0.0.1:23000",
		dataPlaneBaseUrl: "https://127.0.0.1:21443",
		templateId: "",
		helperPath: "scripts/cubesandbox-quickstart.sh",
		workDir: ".cubesandbox",
		autoStart: true,
		autoInstall: false,
		helperTimeoutSeconds: 600,
		executionTimeoutSeconds: 120,
		sandboxCleanupTimeoutSeconds: 30,
		stdoutLimitBytes: 65536,
		stderrLimitBytes: 65536,
	},
	maxAnalyzeFiles: 0,
	llmConcurrency: 1,
	llmGapMs: 3000,
};

const REDACTED_API_KEY_PLACEHOLDER = "***configured***";

const newRowId = () => `llmcfg_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

const normalizeSecretSource = (value: unknown, hasKey: boolean): LlmSecretSource => {
	const source = String(value || "").toLowerCase();
	if (source === "saved" || source === "imported" || source === "entered") return source;
	return hasKey ? "saved" : "none";
};

const normalizeNumber = (value: unknown, fallback: number) =>
	typeof value === "number" && Number.isFinite(value) ? value : fallback;

const normalizeBoolean = (value: unknown, fallback: boolean) =>
	typeof value === "boolean" ? value : fallback;

const normalizeString = (value: unknown, fallback: string) =>
	typeof value === "string" ? value : fallback;

const normalizeCubeSandboxConfig = (raw: unknown): CubeSandboxConfigData => {
	const value = (raw || {}) as Record<string, unknown>;
	return {
		enabled: normalizeBoolean(value.enabled, DEFAULT_CONFIG.cubeSandbox.enabled),
		apiBaseUrl: normalizeString(value.apiBaseUrl, DEFAULT_CONFIG.cubeSandbox.apiBaseUrl),
		dataPlaneBaseUrl: normalizeString(value.dataPlaneBaseUrl, DEFAULT_CONFIG.cubeSandbox.dataPlaneBaseUrl),
		templateId: normalizeString(value.templateId, DEFAULT_CONFIG.cubeSandbox.templateId),
		helperPath: normalizeString(value.helperPath, DEFAULT_CONFIG.cubeSandbox.helperPath),
		workDir: normalizeString(value.workDir, DEFAULT_CONFIG.cubeSandbox.workDir),
		autoStart: normalizeBoolean(value.autoStart, DEFAULT_CONFIG.cubeSandbox.autoStart),
		autoInstall: normalizeBoolean(value.autoInstall, DEFAULT_CONFIG.cubeSandbox.autoInstall),
		helperTimeoutSeconds: normalizeNumber(value.helperTimeoutSeconds, DEFAULT_CONFIG.cubeSandbox.helperTimeoutSeconds),
		executionTimeoutSeconds: normalizeNumber(value.executionTimeoutSeconds, DEFAULT_CONFIG.cubeSandbox.executionTimeoutSeconds),
		sandboxCleanupTimeoutSeconds: normalizeNumber(value.sandboxCleanupTimeoutSeconds, DEFAULT_CONFIG.cubeSandbox.sandboxCleanupTimeoutSeconds),
		stdoutLimitBytes: normalizeNumber(value.stdoutLimitBytes, DEFAULT_CONFIG.cubeSandbox.stdoutLimitBytes),
		stderrLimitBytes: normalizeNumber(value.stderrLimitBytes, DEFAULT_CONFIG.cubeSandbox.stderrLimitBytes),
	};
};

const normalizeRow = (raw: Record<string, unknown>, index: number): LlmConfigRow => {
	const advanced = (raw.advanced || {}) as Record<string, unknown>;
	const apiKey = String(raw.apiKey || "").trim() === REDACTED_API_KEY_PLACEHOLDER ? "" : String(raw.apiKey || "");
	const hasApiKey = Boolean(raw.hasApiKey) || apiKey.trim().length > 0;
	const preflight = (raw.preflight || {}) as Record<string, unknown>;
	const modelStatus = (raw.modelStatus || {}) as Record<string, unknown>;
	return {
		id: String(raw.id || newRowId()),
		priority: normalizeNumber(raw.priority, index + 1),
		enabled: typeof raw.enabled === "boolean" ? raw.enabled : true,
		provider: normalizeLlmProviderId(String(raw.provider || "openai_compatible")),
		baseUrl: String(raw.baseUrl || ""),
		model: String(raw.model || ""),
		apiKey,
		hasApiKey,
		secretSource: normalizeSecretSource(raw.secretSource, hasApiKey),
		advanced: {
			llmCustomHeaders: String(advanced.llmCustomHeaders || ""),
			llmTimeout: normalizeNumber(advanced.llmTimeout, DEFAULT_ADVANCED.llmTimeout),
			llmTemperature: normalizeNumber(advanced.llmTemperature, DEFAULT_ADVANCED.llmTemperature),
			llmMaxTokens: normalizeNumber(advanced.llmMaxTokens, DEFAULT_ADVANCED.llmMaxTokens),
			llmFirstTokenTimeout: normalizeNumber(advanced.llmFirstTokenTimeout, DEFAULT_ADVANCED.llmFirstTokenTimeout),
			llmStreamTimeout: normalizeNumber(advanced.llmStreamTimeout, DEFAULT_ADVANCED.llmStreamTimeout),
			agentTimeout: normalizeNumber(advanced.agentTimeout, DEFAULT_ADVANCED.agentTimeout),
			subAgentTimeout: normalizeNumber(advanced.subAgentTimeout, DEFAULT_ADVANCED.subAgentTimeout),
			toolTimeout: normalizeNumber(advanced.toolTimeout, DEFAULT_ADVANCED.toolTimeout),
		},
		modelStatus: {
			available: typeof modelStatus.available === "boolean" ? modelStatus.available : null,
			lastCheckedAt: typeof modelStatus.lastCheckedAt === "string" ? modelStatus.lastCheckedAt : null,
			reasonCode: typeof modelStatus.reasonCode === "string" ? modelStatus.reasonCode : null,
		},
		preflight: {
			status: typeof preflight.status === "string" ? preflight.status : "untested",
			reasonCode: typeof preflight.reasonCode === "string" ? preflight.reasonCode : null,
			message: typeof preflight.message === "string" ? preflight.message : null,
			checkedAt: typeof preflight.checkedAt === "string" ? preflight.checkedAt : null,
			fingerprint: typeof preflight.fingerprint === "string" ? preflight.fingerprint : null,
		},
	};
};

const renumberRows = (rows: LlmConfigRow[]) => rows.map((row, index) => ({ ...row, priority: index + 1 }));

const createEmptyRow = (providers: LLMProviderItem[], priority: number): LlmConfigRow => {
	const provider = normalizeLlmProviderId(providers[0]?.id || "openai_compatible");
	return normalizeRow(
		{
			id: newRowId(),
			priority,
			enabled: true,
			provider,
			baseUrl: resolveDefaultBaseUrlForProvider(providers, provider) || "",
			model: "",
			apiKey: "",
			hasApiKey: false,
			secretSource: "none",
			advanced: DEFAULT_ADVANCED,
		},
		priority - 1,
	);
};

function buildSystemConfigDataFromBackendConfig(
	backendConfig: { llmConfig?: Record<string, unknown>; otherConfig?: Record<string, unknown> } | null | undefined,
): SystemConfigData {
	const rawLlm = (backendConfig?.llmConfig ?? {}) as Record<string, unknown>;
	const otherConfig = (backendConfig?.otherConfig ?? {}) as Record<string, unknown>;
	const rows = Array.isArray(rawLlm.rows)
		? rawLlm.rows.map((row, index) => normalizeRow((row || {}) as Record<string, unknown>, index))
		: [normalizeRow(rawLlm, 0)];
	return {
		llmConfig: {
			schemaVersion: 2,
			rows: renumberRows(rows),
			latestPreflightRun: {
				runId: typeof (rawLlm.latestPreflightRun as Record<string, unknown> | undefined)?.runId === "string" ? String((rawLlm.latestPreflightRun as Record<string, unknown>).runId) : null,
				checkedAt: typeof (rawLlm.latestPreflightRun as Record<string, unknown> | undefined)?.checkedAt === "string" ? String((rawLlm.latestPreflightRun as Record<string, unknown>).checkedAt) : null,
				attemptedRowIds: Array.isArray((rawLlm.latestPreflightRun as Record<string, unknown> | undefined)?.attemptedRowIds) ? ((rawLlm.latestPreflightRun as Record<string, unknown>).attemptedRowIds as unknown[]).map(String) : [],
				winningRowId: typeof (rawLlm.latestPreflightRun as Record<string, unknown> | undefined)?.winningRowId === "string" ? String((rawLlm.latestPreflightRun as Record<string, unknown>).winningRowId) : null,
				winningFingerprint: typeof (rawLlm.latestPreflightRun as Record<string, unknown> | undefined)?.winningFingerprint === "string" ? String((rawLlm.latestPreflightRun as Record<string, unknown>).winningFingerprint) : null,
			},
			migration: {
				status: String((rawLlm.migration as Record<string, unknown> | undefined)?.status || "not_needed"),
				message: typeof (rawLlm.migration as Record<string, unknown> | undefined)?.message === "string" ? String((rawLlm.migration as Record<string, unknown>).message) : null,
				sourceSchemaVersion: normalizeNumber((rawLlm.migration as Record<string, unknown> | undefined)?.sourceSchemaVersion, 2),
			},
		},
		rawOtherConfig: otherConfig,
		cubeSandbox: normalizeCubeSandboxConfig(otherConfig.cubeSandbox),
		maxAnalyzeFiles: normalizeNumber(otherConfig.maxAnalyzeFiles, DEFAULT_CONFIG.maxAnalyzeFiles),
		llmConcurrency: normalizeNumber(otherConfig.llmConcurrency, DEFAULT_CONFIG.llmConcurrency),
		llmGapMs: normalizeNumber(otherConfig.llmGapMs, DEFAULT_CONFIG.llmGapMs),
	};
}

export function useSystemConfigDraftState(options?: { enabled?: boolean }): SystemConfigSharedDraftState {
	const enabled = options?.enabled ?? true;
	const [config, setConfig] = useState<SystemConfigData | null>(null);
	const [loading, setLoading] = useState(true);
	const [hasChanges, setHasChanges] = useState(false);
	const [llmProvidersFromBackend, setLlmProvidersFromBackend] = useState<LLMProviderItem[]>([]);
	const reloadConfig = useCallback(async () => {
		if (!enabled) return;
		try {
			setLoading(true);
			const backendConfig = await api.getUserConfig();
			setConfig(backendConfig ? buildSystemConfigDataFromBackendConfig(backendConfig) : { ...DEFAULT_CONFIG, llmConfig: { ...DEFAULT_CONFIG.llmConfig, rows: [] } });
			setHasChanges(false);
		} catch (error) {
			console.error("Failed to load config:", error);
			setConfig({ ...DEFAULT_CONFIG, llmConfig: { ...DEFAULT_CONFIG.llmConfig, rows: [] } });
		} finally {
			setLoading(false);
		}
	}, [enabled]);

	useEffect(() => {
		if (!enabled) return;
		void reloadConfig();
		api.getLLMProviders().then((res) => setLlmProvidersFromBackend(res.providers || [])).catch(() => setLlmProvidersFromBackend([]));
	}, [enabled, reloadConfig]);

	return { config, setConfig, loading, setLoading, hasChanges, setHasChanges, llmProvidersFromBackend, setLlmProvidersFromBackend, reloadConfig };
}

function RowConfigDialog({
	open,
	mode,
	row,
	providers,
	onOpenChange,
	onSave,
}: {
	open: boolean;
	mode: DialogMode;
	row: LlmConfigRow | null;
	providers: LLMProviderItem[];
	onOpenChange: (open: boolean) => void;
	onSave: (row: LlmConfigRow) => void;
}) {
	const [draft, setDraft] = useState<LlmConfigRow | null>(row);
	useEffect(() => setDraft(row), [row]);
	if (!draft) return null;
	const providerOptions = buildLlmProviderOptions({ backendProviders: providers, currentProviderId: draft.provider });
	const update = <K extends keyof LlmConfigRow>(key: K, value: LlmConfigRow[K]) => setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
	const updateAdvanced = <K extends keyof LlmAdvancedConfig>(key: K, value: LlmAdvancedConfig[K]) => setDraft((prev) => (prev ? { ...prev, advanced: { ...prev.advanced, [key]: value } } : prev));

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent aria-describedby={undefined} className="!w-[min(92vw,980px)] !max-w-none max-h-[88vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
				<DialogHeader className="px-8 pt-6 pb-4 border-b border-border flex-shrink-0">
					<DialogTitle className="font-mono text-lg font-bold uppercase tracking-wider text-foreground">
						{mode === "create" ? "新增模型配置" : "编辑模型配置"}
					</DialogTitle>
				</DialogHeader>
				<div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
					<div className="space-y-4">
						<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">基本配置</h3>
						<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
							<div className="space-y-2">
								<Label className="font-mono text-xs font-bold uppercase text-muted-foreground">模型供应商</Label>
								<Select value={draft.provider} onValueChange={(provider) => update("provider", normalizeLlmProviderId(provider))}>
									<SelectTrigger className="cyber-input h-10"><SelectValue /></SelectTrigger>
									<SelectContent className="cyber-dialog border-border">
										{providerOptions.map((provider) => <SelectItem key={provider.id} value={provider.id}>{provider.name}</SelectItem>)}
									</SelectContent>
								</Select>
							</div>
							<div className="space-y-2">
								<Label className="font-mono text-xs font-bold uppercase text-muted-foreground">状态</Label>
								<Select value={draft.enabled ? "enabled" : "disabled"} onValueChange={(value) => update("enabled", value === "enabled")}>
									<SelectTrigger className="cyber-input h-10"><SelectValue /></SelectTrigger>
									<SelectContent><SelectItem value="enabled">启用</SelectItem><SelectItem value="disabled">禁用</SelectItem></SelectContent>
								</Select>
							</div>
							<div className="space-y-2 md:col-span-2">
								<Label className="font-mono text-xs font-bold uppercase text-muted-foreground">地址</Label>
								<Input className="cyber-input h-10" value={draft.baseUrl} onChange={(event) => update("baseUrl", event.target.value)} placeholder={resolveDefaultBaseUrlForProvider(providerOptions, draft.provider)} />
							</div>
							<div className="space-y-2">
								<Label className="font-mono text-xs font-bold uppercase text-muted-foreground">模型</Label>
								<Input className="cyber-input h-10" value={draft.model} onChange={(event) => update("model", event.target.value)} placeholder={resolveDefaultModelForProvider(providerOptions, draft.provider)} />
							</div>
							<div className="space-y-2">
								<Label className="font-mono text-xs font-bold uppercase text-muted-foreground">API Key{draft.hasApiKey ? <span className="ml-2 normal-case tracking-normal text-emerald-300">已保存密钥，留空将保留</span> : null}</Label>
								<Input type="password" className="cyber-input h-10" value={draft.apiKey} onChange={(event) => update("apiKey", event.target.value)} placeholder={draft.hasApiKey ? "留空保留已保存密钥，输入则替换" : "输入 API Key"} />
							</div>
						</div>
					</div>
					<div className="space-y-4">
						<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2 flex items-center gap-2"><Settings className="h-4 w-4" /> 高级配置</h3>
						<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
							<label className="space-y-1.5 md:col-span-3"><span className="font-mono text-xs font-bold uppercase text-muted-foreground">自定义请求头 (JSON)</span><Textarea className="cyber-input min-h-24 font-mono" value={draft.advanced.llmCustomHeaders} onChange={(e) => updateAdvanced("llmCustomHeaders", e.target.value)} /></label>
							{([
								["llmTimeout", "请求超时 (毫秒)"],
								["llmTemperature", "温度"],
								["llmMaxTokens", "最大 Tokens"],
								["llmFirstTokenTimeout", "首 Token 超时 (秒)"],
								["llmStreamTimeout", "流式超时 (秒)"],
								["agentTimeout", "Agent 总超时 (秒)"],
								["subAgentTimeout", "子 Agent 超时 (秒)"],
								["toolTimeout", "工具超时 (秒)"],
							] as Array<[keyof LlmAdvancedConfig, string]>).map(([key, label]) => (
								<label key={key} className="space-y-1.5"><span className="font-mono text-xs font-bold uppercase text-muted-foreground">{label}</span><Input type="number" className="cyber-input h-10" value={draft.advanced[key] as number} onChange={(e) => updateAdvanced(key, Number(e.target.value) as never)} /></label>
							))}
						</div>
					</div>
				</div>
				<div className="flex-shrink-0 flex justify-end gap-3 px-8 py-4 bg-muted border-t border-border">
					<Button variant="outline" className="cyber-btn-ghost" onClick={() => onOpenChange(false)}>取消</Button>
					<Button className="cyber-btn-primary" onClick={() => onSave({ ...draft, apiKey: draft.apiKey.trim(), hasApiKey: draft.hasApiKey || draft.apiKey.trim().length > 0, secretSource: draft.apiKey.trim() ? "saved" : draft.secretSource })}>保存</Button>
				</div>
			</DialogContent>
		</Dialog>
	);
}

const rowStatusText = (row: LlmConfigRow, latestWinningRowId?: string | null) => {
	const parts = [row.enabled ? "启用" : "禁用"];
	if (!row.hasApiKey) parts.push("缺少密钥");
	if (row.preflight.status === "passed") {
		parts.push("预检通过");
	} else if (row.preflight.status === "missing_fields" || row.preflight.reasonCode === "missing_fields") {
		parts.push("字段不完整");
	} else if (row.preflight.status === "failed" || row.preflight.reasonCode) {
		parts.push("预检不通过");
	}
	if (row.preflight.checkedAt) {
		parts.push(`上次验证 ${formatCheckedAt(row.preflight.checkedAt)}`);
	}
	if (latestWinningRowId === row.id) parts.push("当前命中");
	return parts;
};

const formatCheckedAt = (value: string) => {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return value;
	}
	return date.toLocaleString("zh-CN", { hour12: false });
};

export function SystemConfig({
	visibleSections = ["llm", "analysis", "cubesandbox"],
	defaultSection = "llm",
	mergedView = false,
	showLlmSummaryCards = true,
	llmSummaryOnly = false,
	showFloatingSaveButton = true,
	showInlineSaveButtons = true,
	compactLayout = false,
	cardClassName,
	sharedDraftState,
	onLlmSummaryChange,
}: SystemConfigProps = {}) {
	const sections = visibleSections.length > 0 ? visibleSections : ["llm"];
	const internalDraftState = useSystemConfigDraftState({ enabled: sharedDraftState == null });
	const { config, setConfig, loading, hasChanges, setHasChanges, llmProvidersFromBackend, reloadConfig } = sharedDraftState ?? internalDraftState;
	const [savingLLM, setSavingLLM] = useState(false);
	const [testingLLM, setTestingLLM] = useState(false);
	const [dialogOpen, setDialogOpen] = useState(false);
	const [dialogMode, setDialogMode] = useState<DialogMode>("create");
	const [editingRow, setEditingRow] = useState<LlmConfigRow | null>(null);
	const [llmTestResult, setLlmTestResult] = useState<{ success: boolean; message: string } | null>(null);
	const latestConfigRef = useRef<SystemConfigData | null>(config);

	useEffect(() => { latestConfigRef.current = config; }, [config]);

	const providerOptions = useMemo(() => buildLlmProviderOptions({ backendProviders: llmProvidersFromBackend, currentProviderId: config?.llmConfig.rows[0]?.provider || "openai_compatible" }), [llmProvidersFromBackend, config?.llmConfig.rows]);
	const rows = config?.llmConfig.rows ?? [];
	const activeRow = rows.find((row) => row.id === config?.llmConfig.latestPreflightRun.winningRowId) || rows.find((row) => row.enabled) || rows[0];
	const activeProviderInfo = getLlmProviderInfo(providerOptions, activeRow?.provider || "openai_compatible");
	const supportsModelFetch = Boolean(activeProviderInfo?.supportsModelFetch);
	const availableModelCount = activeProviderInfo?.models.length ?? 0;
	const preferredModelStats = resolvePreferredModelStats({
		shouldPreferOnlineStats: false,
		staticStats: { availableModelCount, availableModelMetadataCount: availableModelCount },
		cachedOnlineStats: null,
		fetchState: "idle",
	});

	useEffect(() => {
		if (!onLlmSummaryChange) return;
		onLlmSummaryChange({
			providerId: activeRow?.provider || "openai_compatible",
			providerLabel: activeProviderInfo?.name || activeRow?.provider || "--",
			currentModelName: activeRow?.model || "--",
			availableModelCount: preferredModelStats.availableModelCount,
			availableModelMetadataCount: preferredModelStats.availableModelMetadataCount,
			supportsModelFetch,
			modelStatsStatus: preferredModelStats.modelStatsStatus,
			modelStatsSource: preferredModelStats.modelStatsSource,
			shouldPreferOnlineStats: false,
		});
	}, [onLlmSummaryChange, activeRow?.provider, activeRow?.model, activeProviderInfo?.name, preferredModelStats.availableModelCount, preferredModelStats.availableModelMetadataCount, preferredModelStats.modelStatsStatus, preferredModelStats.modelStatsSource, supportsModelFetch]);

	const updateRows = (nextRows: LlmConfigRow[]) => {
		setConfig((prev) => prev ? { ...prev, llmConfig: { ...prev.llmConfig, rows: renumberRows(nextRows) } } : prev);
		setHasChanges(true);
		setLlmTestResult(null);
	};

	const persistConfig = async () => {
		if (!config) return null;
		const parseErrorRow = config.llmConfig.rows.find((row) => !parseLlmCustomHeadersInput(row.advanced.llmCustomHeaders).ok);
		if (parseErrorRow) {
			const message = `第 ${parseErrorRow.priority} 行自定义请求头格式不正确`;
			toast.error(message);
			throw new Error(message);
		}
		setSavingLLM(true);
		try {
			const savedConfig = await api.updateUserConfig({
				llmConfig: { ...config.llmConfig, rows: config.llmConfig.rows.map((row) => ({ ...row, apiKey: row.apiKey.trim() })) },
				otherConfig: { ...config.rawOtherConfig, cubeSandbox: config.cubeSandbox, maxAnalyzeFiles: config.maxAnalyzeFiles, llmConcurrency: config.llmConcurrency, llmGapMs: config.llmGapMs },
			});
			const nextConfig = buildSystemConfigDataFromBackendConfig(savedConfig);
			setConfig(nextConfig);
			setHasChanges(false);
			toast.success("配置已保存！");
			return nextConfig;
		} catch (error) {
			toast.error(`保存失败: ${error instanceof Error ? error.message : "未知错误"}`);
			throw error;
		} finally {
			setSavingLLM(false);
		}
	};

	const runLlmConnectionTest = async (row: LlmConfigRow) => {
		setTestingLLM(true);
		try {
			const result = await api.testLLMConnection({
				rowId: row.id,
				provider: row.provider,
				apiKey: row.apiKey || undefined,
				secretSource: row.apiKey ? "entered" : row.secretSource,
				useSavedApiKey: !row.apiKey && row.hasApiKey,
				model: row.model,
				baseUrl: row.baseUrl,
				customHeaders: row.advanced.llmCustomHeaders,
			});
			setLlmTestResult(result);
			if (result.success) {
				toast.success(`连接成功！模型: ${result.model || row.model}`);
				await reloadConfig();
			} else {
				toast.error(`连接失败: ${result.message}`);
			}
			return result;
		} finally {
			setTestingLLM(false);
		}
	};

	const handleSaveAndTest = async () => {
		setTestingLLM(true);
		try {
			const { batchValidationResult } = await runSaveThenBatchValidateAction({
				save: persistConfig,
				batchValidate: () => api.batchTestLLMConnections(),
			});
			setLlmTestResult({ success: batchValidationResult.success, message: batchValidationResult.message });
			if (batchValidationResult.success) {
				toast.success(batchValidationResult.message || "批量验证通过");
			} else {
				toast.error(batchValidationResult.message || "批量验证未全部通过");
			}
			await reloadConfig();
		} finally {
			setTestingLLM(false);
		}
	};

	const handleSaveAndTestRow = async (targetRow: LlmConfigRow) => {
		const saved = await persistConfig();
		const savedRow = saved?.llmConfig.rows.find((r) => r.id === targetRow.id);
		if (savedRow) await runLlmConnectionTest(savedRow);
	};

	const openCreateDialog = () => {
		setDialogMode("create");
		setEditingRow(createEmptyRow(providerOptions, rows.length + 1));
		setDialogOpen(true);
	};
	const openEditDialog = (row: LlmConfigRow) => {
		setDialogMode("edit");
		setEditingRow({ ...row, advanced: { ...row.advanced }, apiKey: "" });
		setDialogOpen(true);
	};
	const saveDialogRow = (row: LlmConfigRow) => {
		if (dialogMode === "create") updateRows([...rows, row]);
		else updateRows(rows.map((item) => item.id === row.id ? { ...row, hasApiKey: row.hasApiKey || item.hasApiKey, secretSource: row.apiKey ? "saved" : item.secretSource } : item));
		setDialogOpen(false);
	};
	const deleteRow = (row: LlmConfigRow) => {
		if (row.enabled && rows.filter((item) => item.enabled).length <= 1) {
			toast.error("至少保留一条启用的模型配置");
			return;
		}
		if (!window.confirm(`确定删除第 ${row.priority} 行模型配置吗？`)) return;
		updateRows(rows.filter((item) => item.id !== row.id));
	};
	const moveRow = (row: LlmConfigRow, direction: -1 | 1) => {
		const index = rows.findIndex((item) => item.id === row.id);
		const nextIndex = index + direction;
		if (index < 0 || nextIndex < 0 || nextIndex >= rows.length) return;
		const nextRows = [...rows];
		[nextRows[index], nextRows[nextIndex]] = [nextRows[nextIndex], nextRows[index]];
		updateRows(nextRows);
	};

	if (loading || !config) {
		return <div className="flex items-center justify-center min-h-[400px]"><div className="loading-spinner mx-auto" /><p className="ml-3 text-muted-foreground font-mono text-sm uppercase">加载配置中...</p></div>;
	}

	const tabsGridClass = sections.length <= 1 ? "grid-cols-1" : sections.length === 2 ? "grid-cols-2" : "grid-cols-3";
	const isConfigured = rows.some((row) => row.enabled && row.model.trim() && row.baseUrl.trim() && (row.apiKey.trim() || row.hasApiKey || !resolveShouldRequireApiKey(providerOptions, row.provider)));

	return (
		<div className="space-y-6">
			<Tabs defaultValue={sections.includes(defaultSection) ? defaultSection : sections[0]} className="w-full">
				{!mergedView && sections.length > 1 && (
					<TabsList className={`grid w-full ${tabsGridClass} bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6`}>
						{sections.includes("llm") && <TabsTrigger value="llm" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"><Zap className="w-3 h-3" /> LLM 配置</TabsTrigger>}
						{sections.includes("analysis") && <TabsTrigger value="analysis" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"><Settings className="w-3 h-3" /> 分析参数</TabsTrigger>}
						{sections.includes("cubesandbox") && <TabsTrigger value="cubesandbox" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2"><Settings className="w-3 h-3" /> CubeSandbox</TabsTrigger>}
					</TabsList>
				)}
				{sections.includes("llm") && (
					<TabsContent value="llm" className={compactLayout ? "space-y-4" : "space-y-6"}>
						<div className={cn("cyber-card !overflow-visible", compactLayout ? "p-4 space-y-4" : "p-6 space-y-6", cardClassName)}>
							{showLlmSummaryCards ? <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><div className="cyber-card p-4"><p className="stat-label">模型提供商</p><p className="stat-value text-2xl break-all">{activeProviderInfo?.name || activeRow?.provider || "--"}</p></div><div className="cyber-card p-4"><p className="stat-label">当前采用模型</p><p className="stat-value text-2xl break-all">{activeRow?.model || "--"}</p></div><div className="cyber-card p-4"><p className="stat-label">支持模型数量</p><p className="stat-value text-2xl break-all">{availableModelCount}</p></div></div> : null}
							{!llmSummaryOnly ? <>
								<div className="flex items-center justify-between">
								<div className="flex items-center gap-2">
									{(() => {
										const availableCount = rows.filter((r) => r.enabled && r.hasApiKey && r.preflight.status === "passed").length;
										const abnormalCount = rows.length - availableCount;
										return <>
											<span className="rounded border border-emerald-500/40 text-emerald-300 px-2.5 py-1 text-sm font-medium">可用 {availableCount}</span>
											<span className="rounded border border-rose-500/40 text-rose-300 px-2.5 py-1 text-sm font-medium">异常 {abnormalCount}</span>
										</>;
									})()}
								</div>
								<div className="flex items-center gap-2">
									<Button onClick={handleSaveAndTest} disabled={savingLLM || testingLLM || !isConfigured} className="cyber-btn-primary h-9">{savingLLM || testingLLM ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />批量验证中...</> : <><Save className="h-4 w-4 mr-2" />保存并验证</>}</Button>
									<Button onClick={openCreateDialog} className="cyber-btn-primary h-9"><Plus className="h-4 w-4 mr-2" />新增配置</Button>
								</div>
							</div>
								<div className="overflow-x-auto rounded-lg border border-border">
									<Table className="table-fixed text-base" containerClassName="overflow-x-auto rounded-lg">
										<TableHeader>
											<TableRow className="border-b border-border/70 bg-muted/40 text-sm font-bold uppercase tracking-[0.12em] text-muted-foreground">
												<TableHead className="w-16 px-3 py-2 text-left font-bold whitespace-nowrap border-r border-border/30">序号</TableHead>
												<TableHead className="w-[120px] px-3 py-2 text-left font-bold whitespace-nowrap border-r border-border/30">模型供应商</TableHead>
												<TableHead className="w-[200px] px-3 py-2 text-left font-bold whitespace-nowrap border-r border-border/30">地址</TableHead>
												<TableHead className="w-[200px] px-3 py-2 text-left font-bold whitespace-nowrap border-r border-border/30">模型</TableHead>
												<TableHead className="w-[240px] px-3 py-2 text-left font-bold whitespace-nowrap border-r border-border/30">状态</TableHead>
												<TableHead className="w-[320px] px-3 py-2 text-center font-bold whitespace-nowrap">操作</TableHead>
											</TableRow>
										</TableHeader>
										<TableBody>
											{rows.map((row) => {
												const status = rowStatusText(row, config.llmConfig.latestPreflightRun.winningRowId);
												return <TableRow key={row.id} className="border-b border-border/70">
													<TableCell className="px-3 py-3 text-left font-mono text-base whitespace-nowrap border-r border-border/30">{row.priority}</TableCell>
													<TableCell className="px-3 py-3 text-left text-base whitespace-nowrap border-r border-border/30">{(getLlmProviderInfo(providerOptions, row.provider)?.name || row.provider).replace(" 兼容", "")}</TableCell>
													<TableCell className="px-3 py-3 text-left font-mono text-base break-all border-r border-border/30" title={row.baseUrl}>{row.baseUrl || "--"}</TableCell>
													<TableCell className="px-3 py-3 text-left font-mono text-base whitespace-nowrap border-r border-border/30" title={row.model}>{row.model || "--"}</TableCell>
													<TableCell className="px-3 py-3 text-left border-r border-border/30"><div className="flex flex-wrap gap-1">{status.map((item) => <span key={item} className={cn("rounded border px-2 py-0.5 text-xs whitespace-nowrap", item.includes("失败") || item.includes("缺少") ? "border-rose-500/40 text-rose-300" : item.includes("通过") || item.includes("命中") || item.includes("已配置") ? "border-emerald-500/40 text-emerald-300" : "border-border text-muted-foreground")}>{item}</span>)}</div></TableCell>
													<TableCell className="px-3 py-3"><div className="flex flex-nowrap gap-1 justify-center"><Button type="button" variant="outline" size="sm" className="cyber-btn-ghost h-8" disabled={savingLLM || testingLLM} onClick={() => handleSaveAndTestRow(row)}>验证</Button><Button type="button" variant="outline" size="sm" className="cyber-btn-ghost h-8" onClick={() => openEditDialog(row)}>编辑</Button><Button type="button" variant="outline" size="sm" className={cn("cyber-btn-ghost h-8", row.enabled ? "border-emerald-500/40 text-emerald-300" : "border-amber-500/40 text-amber-300")} onClick={() => updateRows(rows.map((r) => r.id === row.id ? { ...r, enabled: !r.enabled } : r))}>{row.enabled ? "禁用" : "启用"}</Button><Button type="button" variant="outline" size="sm" className="cyber-btn-ghost h-8 border-rose-500/40 text-rose-300" onClick={() => deleteRow(row)}>删除</Button><Button type="button" variant="outline" size="sm" className="cyber-btn-ghost h-8" disabled={row.priority === 1} onClick={() => moveRow(row, -1)}><ArrowUp className="h-3 w-3" /></Button><Button type="button" variant="outline" size="sm" className="cyber-btn-ghost h-8" disabled={row.priority === rows.length} onClick={() => moveRow(row, 1)}><ArrowDown className="h-3 w-3" /></Button></div></TableCell>
												</TableRow>;
											})}
										</TableBody>
									</Table>
								</div>
								{showInlineSaveButtons && <div className="pt-4 border-t border-border border-dashed flex justify-end flex-wrap gap-2"><Button onClick={handleSaveAndTest} disabled={savingLLM || testingLLM || !isConfigured} className="cyber-btn-primary h-10">{savingLLM || testingLLM ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />保存并测试中...</> : <><Save className="w-4 h-4 mr-2" />保存并测试</>}</Button><Button onClick={persistConfig} disabled={savingLLM} variant="outline" className="cyber-btn-ghost h-10"><Save className="w-4 h-4 mr-2" />保存</Button><Button onClick={async () => { if (!window.confirm("确定要重置为默认配置吗？")) return; await api.deleteUserConfig(); await reloadConfig(); setHasChanges(false); }} disabled={savingLLM || testingLLM} variant="ghost" className="cyber-btn-ghost h-10"><RotateCcw className="w-4 h-4 mr-2" />重置</Button></div>}
								{llmTestResult && <div className={`p-3 rounded-lg ${llmTestResult.success ? "bg-emerald-500/10 border border-emerald-500/30" : "bg-rose-500/10 border border-rose-500/30"}`}><div className="flex items-center gap-2 text-sm">{llmTestResult.success ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <AlertCircle className="h-4 w-4 text-rose-400" />}<span>{llmTestResult.message}</span></div></div>}
							</> : null}
						</div>
						<RowConfigDialog open={dialogOpen} mode={dialogMode} row={editingRow} providers={llmProvidersFromBackend} onOpenChange={setDialogOpen} onSave={saveDialogRow} />
					</TabsContent>
				)}
				{!mergedView && sections.includes("analysis") && (
					<TabsContent value="analysis" className="space-y-6"><div className="cyber-card p-6 space-y-6"><div className="grid grid-cols-1 md:grid-cols-3 gap-6">{([["maxAnalyzeFiles", "最大分析文件数"], ["llmConcurrency", "LLM 并发数"], ["llmGapMs", "请求间隔 (毫秒)"]] as Array<[keyof Pick<SystemConfigData, "maxAnalyzeFiles" | "llmConcurrency" | "llmGapMs">, string]>).map(([key, label]) => <label key={key} className="space-y-2"><span className="text-xs font-bold text-muted-foreground uppercase">{label}</span><Input type="number" value={config[key]} onChange={(event) => { setConfig((prev) => prev ? { ...prev, [key]: Number(event.target.value) } : prev); setHasChanges(true); }} className="h-10 cyber-input" /></label>)}</div></div></TabsContent>
				)}
				{!mergedView && sections.includes("cubesandbox") && (
					<TabsContent value="cubesandbox" className="space-y-6">
						<div className="cyber-card p-6 space-y-6">
							<div className="space-y-1">
								<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground">CubeSandbox 运行时</h3>
								<p className="text-xs text-muted-foreground">保存到 otherConfig.cubeSandbox；CUBESANDBOX_DATA_PLANE_BASE_URL 只作为默认种子。</p>
							</div>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
								<label className="space-y-2"><span className="text-xs font-bold text-muted-foreground uppercase">启用</span><Select value={config.cubeSandbox.enabled ? "enabled" : "disabled"} onValueChange={(value) => { setConfig((prev) => prev ? { ...prev, cubeSandbox: { ...prev.cubeSandbox, enabled: value === "enabled" } } : prev); setHasChanges(true); }}><SelectTrigger className="cyber-input h-10"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="enabled">启用</SelectItem><SelectItem value="disabled">禁用</SelectItem></SelectContent></Select></label>
								<label className="space-y-2"><span className="text-xs font-bold text-muted-foreground uppercase">自动启动 VM</span><Select value={config.cubeSandbox.autoStart ? "enabled" : "disabled"} onValueChange={(value) => { setConfig((prev) => prev ? { ...prev, cubeSandbox: { ...prev.cubeSandbox, autoStart: value === "enabled" } } : prev); setHasChanges(true); }}><SelectTrigger className="cyber-input h-10"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="enabled">启用</SelectItem><SelectItem value="disabled">禁用</SelectItem></SelectContent></Select></label>
								{([
									["apiBaseUrl", "CubeAPI 控制面地址"],
									["dataPlaneBaseUrl", "CubeProxy/envd 数据面地址"],
									["templateId", "模板 ID"],
									["helperPath", "生命周期 Helper"],
									["workDir", "工作目录"],
								] as Array<[keyof Pick<CubeSandboxConfigData, "apiBaseUrl" | "dataPlaneBaseUrl" | "templateId" | "helperPath" | "workDir">, string]>).map(([key, label]) => <label key={key} className="space-y-2"><span className="text-xs font-bold text-muted-foreground uppercase">{label}</span><Input value={config.cubeSandbox[key]} onChange={(event) => { setConfig((prev) => prev ? { ...prev, cubeSandbox: { ...prev.cubeSandbox, [key]: event.target.value } } : prev); setHasChanges(true); }} className="h-10 cyber-input" /></label>)}
								{([
									["helperTimeoutSeconds", "Helper 超时 (秒)"],
									["executionTimeoutSeconds", "执行超时 (秒)"],
									["sandboxCleanupTimeoutSeconds", "清理超时 (秒)"],
									["stdoutLimitBytes", "stdout 上限 (字节)"],
									["stderrLimitBytes", "stderr 上限 (字节)"],
								] as Array<[keyof Pick<CubeSandboxConfigData, "helperTimeoutSeconds" | "executionTimeoutSeconds" | "sandboxCleanupTimeoutSeconds" | "stdoutLimitBytes" | "stderrLimitBytes">, string]>).map(([key, label]) => <label key={key} className="space-y-2"><span className="text-xs font-bold text-muted-foreground uppercase">{label}</span><Input type="number" value={config.cubeSandbox[key]} onChange={(event) => { setConfig((prev) => prev ? { ...prev, cubeSandbox: { ...prev.cubeSandbox, [key]: Number(event.target.value) } } : prev); setHasChanges(true); }} className="h-10 cyber-input" /></label>)}
							</div>
						</div>
					</TabsContent>
				)}
			</Tabs>
			{hasChanges && !dialogOpen && showFloatingSaveButton && <div className="fixed bottom-6 right-6 cyber-card p-4 z-50"><Button onClick={persistConfig} className="cyber-btn-primary h-12"><Save className="w-4 h-4 mr-2" /> 保存所有更改</Button></div>}
		</div>
	);
}
