/**
 * System Config Component
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/shared/utils/utils";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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
  PlayCircle,
  RotateCcw,
  Save,
  Settings,
  Shield,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";

const DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-5",
  anthropic: "claude-sonnet-4-20250514",
  gemini: "gemini-2.5-pro",
  deepseek: "deepseek-chat",
  ollama: "llama3.1",
  openrouter: "openai/gpt-5-mini",
};

type LLMFetchStyle =
  | "openai_compatible"
  | "anthropic"
  | "azure_openai"
  | "native_static";

interface LLMProviderItem {
  id: string;
  name: string;
  description: string;
  defaultModel: string;
  models: string[];
  defaultBaseUrl: string;
  requiresApiKey: boolean;
  supportsModelFetch: boolean;
  fetchStyle: LLMFetchStyle;
}

const BUILTIN_LLM_PROVIDERS: LLMProviderItem[] = [
  {
    id: "openai",
    name: "OpenAI",
    description: "OpenAI 官方模型服务",
    defaultModel: "gpt-5",
    models: ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
    defaultBaseUrl: "https://api.openai.com/v1",
    requiresApiKey: true,
    supportsModelFetch: true,
    fetchStyle: "openai_compatible",
  },
  {
    id: "anthropic",
    name: "Anthropic",
    description: "Claude 系列模型服务",
    defaultModel: "claude-sonnet-4-20250514",
    models: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-latest"],
    defaultBaseUrl: "https://api.anthropic.com",
    requiresApiKey: true,
    supportsModelFetch: true,
    fetchStyle: "anthropic",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    description: "Google Gemini 模型服务",
    defaultModel: "gemini-2.5-pro",
    models: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    requiresApiKey: true,
    supportsModelFetch: true,
    fetchStyle: "openai_compatible",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "DeepSeek 推理与对话模型",
    defaultModel: "deepseek-chat",
    models: ["deepseek-chat", "deepseek-reasoner"],
    defaultBaseUrl: "https://api.deepseek.com/v1",
    requiresApiKey: true,
    supportsModelFetch: true,
    fetchStyle: "openai_compatible",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    description: "统一多模型路由聚合服务",
    defaultModel: "openai/gpt-5-mini",
    models: ["openai/gpt-5-mini", "anthropic/claude-3.7-sonnet", "google/gemini-2.5-pro"],
    defaultBaseUrl: "https://openrouter.ai/api/v1",
    requiresApiKey: true,
    supportsModelFetch: true,
    fetchStyle: "openai_compatible",
  },
  {
    id: "ollama",
    name: "Ollama",
    description: "本地部署 LLM（无 API Key）",
    defaultModel: "llama3.1",
    models: ["llama3.1", "qwen2.5", "deepseek-r1:latest"],
    defaultBaseUrl: "http://localhost:11434/v1",
    requiresApiKey: false,
    supportsModelFetch: true,
    fetchStyle: "openai_compatible",
  },
];

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

const normalizeLlmProviderId = (provider: string | undefined | null): string => {
  const normalized = (provider || "").trim().toLowerCase();
  if (!normalized) return "openai";
  if (normalized === "claude") return "anthropic";
  return normalized;
};

const TOKEN_SOURCE_LABELS: Record<string, string> = {
  online_metadata: "在线元数据",
  static_mapping: "静态映射",
  default: "默认值",
};

const recommendTokensFromStaticRules = (modelName: string): number | null => {
  const normalized = String(modelName || "").trim().toLowerCase();
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

  if (highReasoningHints.some((hint) => normalized.includes(hint))) return 16384;
  if (mediumHints.some((hint) => normalized.includes(hint))) return 8192;
  return null;
};

interface SystemConfigData {
  llmProvider: string;
  llmApiKey: string;
  llmModel: string;
  llmBaseUrl: string;
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
  mcpConfig: {
    enabled: boolean;
    preferMcp: boolean;
    writePolicy: {
      all_agents_writable: boolean;
      max_writable_files_per_task: number;
      require_evidence_binding: boolean;
      forbid_project_wide_writes: boolean;
    };
  };
}

type ConfigSection = "llm" | "embedding" | "analysis" | "mcp";

interface SystemConfigProps {
  visibleSections?: ConfigSection[];
  defaultSection?: ConfigSection;
  mergedView?: boolean;
}

type AdvancedConfigItemId =
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
  llmTimeout: 150000,
  llmTemperature: 0.1,
  llmMaxTokens: 4096,
  llmFirstTokenTimeout: 90,
  llmStreamTimeout: 60,
  agentTimeout: 1800,
  subAgentTimeout: 600,
  toolTimeout: 60,
  maxAnalyzeFiles: 0,
  llmConcurrency: 3,
  llmGapMs: 2000,
  outputLanguage: "zh-CN",
  mcpConfig: {
    enabled: true,
    preferMcp: true,
    writePolicy: {
      all_agents_writable: true,
      max_writable_files_per_task: 50,
      require_evidence_binding: true,
      forbid_project_wide_writes: true,
    },
  },
};

function clampWritableFilesLimit(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_CONFIG.mcpConfig.writePolicy.max_writable_files_per_task;
  }
  return Math.min(50, Math.max(1, Math.floor(parsed)));
}

function normalizeMcpConfig(rawOtherConfig: Record<string, unknown>): SystemConfigData["mcpConfig"] {
  const rawMcp = (rawOtherConfig?.mcpConfig ?? {}) as Record<string, unknown>;
  const rawWritePolicy = (rawMcp?.writePolicy ?? {}) as Record<string, unknown>;
  return {
    enabled: rawMcp.enabled !== undefined ? Boolean(rawMcp.enabled) : DEFAULT_CONFIG.mcpConfig.enabled,
    preferMcp: rawMcp.preferMcp !== undefined ? Boolean(rawMcp.preferMcp) : DEFAULT_CONFIG.mcpConfig.preferMcp,
    writePolicy: {
      all_agents_writable: true,
      max_writable_files_per_task: clampWritableFilesLimit(
        rawWritePolicy.max_writable_files_per_task ??
          DEFAULT_CONFIG.mcpConfig.writePolicy.max_writable_files_per_task,
      ),
      require_evidence_binding:
        rawWritePolicy.require_evidence_binding !== undefined
          ? Boolean(rawWritePolicy.require_evidence_binding)
          : DEFAULT_CONFIG.mcpConfig.writePolicy.require_evidence_binding,
      forbid_project_wide_writes: true,
    },
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
            onChange={(e) => update("llmFirstTokenTimeout", Number(e.target.value))}
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
        desc: "智能审计任务整体超时阈值。",
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
        desc: "智能审计输出语言。",
        input: (
          <Select value={cfg.outputLanguage} onValueChange={(value) => update("outputLanguage", value)}>
            <SelectTrigger className="h-10 cyber-input">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="cyber-dialog border-border">
              <SelectItem value="zh-CN" className="font-mono">🇨🇳 中文</SelectItem>
              <SelectItem value="en-US" className="font-mono">🇺🇸 English</SelectItem>
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
          <div className="text-sm font-bold uppercase text-foreground">{meta.label}</div>
          <div className="text-xs text-muted-foreground mt-1">{meta.desc}</div>
        </div>
        <div className="space-y-2">
          <Label className="text-xs font-bold text-muted-foreground uppercase">{meta.label}</Label>
          {meta.input}
        </div>
      </div>
    );
  };

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="!w-[min(92vw,980px)] !max-w-none h-[80vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg">
        <DialogHeader className="px-5 py-4 border-b border-border flex-shrink-0 bg-muted">
          <div className="flex items-center justify-between gap-3">
            <DialogTitle className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
              高级配置
            </DialogTitle>
            <div className="flex items-center gap-2">
              {props.hasChanges ? (
                <Button onClick={props.onSave} size="sm" className="cyber-btn-primary h-8">
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
                      onClick={() => props.onSelectItem(id as AdvancedConfigItemId)}
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
                      onClick={() => props.onSelectItem(id as AdvancedConfigItemId)}
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
  visibleSections = ["llm", "embedding", "analysis", "mcp"],
  defaultSection = "llm",
  mergedView = false,
}: SystemConfigProps = {}) {
  const sections = visibleSections.length > 0 ? visibleSections : ["llm"];
  const [config, setConfig] = useState<SystemConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmModelSelectValue, setLlmModelSelectValue] =
    useState<string>("__default__");
  const [llmModelPopoverOpen, setLlmModelPopoverOpen] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [testingLLM, setTestingLLM] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedAdvancedItemId, setSelectedAdvancedItemId] =
    useState<AdvancedConfigItemId>("llmTimeout");
  const [llmProvidersFromBackend, setLlmProvidersFromBackend] = useState<LLMProviderItem[]>(
    [],
  );
  const [fetchedModelsByProvider, setFetchedModelsByProvider] = useState<Record<string, string[]>>(
    {},
  );
  const [fetchedModelMetadataByProvider, setFetchedModelMetadataByProvider] = useState<
    Record<string, Record<string, LLMModelMetadata>>
  >({});
  const [fetchingModels, setFetchingModels] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{
    success: boolean;
    message: string;
    debug?: Record<string, unknown>;
  } | null>(null);
  const [showDebugInfo, setShowDebugInfo] = useState(true);
  const llmModelSelectTouchedRef = useRef(false);
  const llmBaseUrlTouchedRef = useRef(false);
  const llmMaxTokensTouchedRef = useRef(false);

  useEffect(() => {
    loadConfig();
    api
      .getLLMProviders()
      .then((res) => setLlmProvidersFromBackend(res.providers || []))
      .catch(() => setLlmProvidersFromBackend([]));
  }, []);

  const tabsGridClass = useMemo(() => {
    if (sections.length <= 1) return "grid-cols-1";
    if (sections.length === 2) return "grid-cols-2";
    if (sections.length === 3) return "grid-cols-3";
    return "grid-cols-4";
  }, [sections.length]);

  const llmProviderOptions = useMemo(() => {
    const backendProviders = Array.isArray(llmProvidersFromBackend)
      ? llmProvidersFromBackend
      : [];
    const baseProviders =
      backendProviders.length > 0 ? backendProviders : BUILTIN_LLM_PROVIDERS;
    const currentProviderId = normalizeLlmProviderId(config?.llmProvider || "");
    if (!currentProviderId) return baseProviders;
    if (baseProviders.some((provider) => provider.id === currentProviderId)) {
      return baseProviders;
    }
    return [
      ...baseProviders,
      {
        id: currentProviderId,
        name: currentProviderId,
        description: "自定义模型提供商",
        defaultModel: "",
        models: [],
        defaultBaseUrl: "",
        requiresApiKey: true,
        supportsModelFetch: false,
        fetchStyle: "openai_compatible",
      },
    ];
  }, [llmProvidersFromBackend, config?.llmProvider]);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const backendConfig = await api.getUserConfig();
      if (!backendConfig) {
        setConfig({ ...DEFAULT_CONFIG });
        return;
      }

      const llmConfig = backendConfig.llmConfig || {};
      const otherConfig = backendConfig.otherConfig || {};
      const normalizedProvider = normalizeLlmProviderId(llmConfig.llmProvider);

      const nextConfig: SystemConfigData = {
        llmProvider: normalizedProvider || DEFAULT_CONFIG.llmProvider,
        llmApiKey: llmConfig.llmApiKey || "",
        llmModel: llmConfig.llmModel || "",
        llmBaseUrl: llmConfig.llmBaseUrl || "",
        llmTimeout: llmConfig.llmTimeout || DEFAULT_CONFIG.llmTimeout,
        llmTemperature: llmConfig.llmTemperature ?? DEFAULT_CONFIG.llmTemperature,
        llmMaxTokens: llmConfig.llmMaxTokens || DEFAULT_CONFIG.llmMaxTokens,
        llmFirstTokenTimeout: llmConfig.llmFirstTokenTimeout || DEFAULT_CONFIG.llmFirstTokenTimeout,
        llmStreamTimeout: llmConfig.llmStreamTimeout || DEFAULT_CONFIG.llmStreamTimeout,
        agentTimeout: llmConfig.agentTimeout || DEFAULT_CONFIG.agentTimeout,
        subAgentTimeout: llmConfig.subAgentTimeout || DEFAULT_CONFIG.subAgentTimeout,
        toolTimeout: llmConfig.toolTimeout || DEFAULT_CONFIG.toolTimeout,
        maxAnalyzeFiles: otherConfig.maxAnalyzeFiles ?? DEFAULT_CONFIG.maxAnalyzeFiles,
        llmConcurrency: otherConfig.llmConcurrency || DEFAULT_CONFIG.llmConcurrency,
        llmGapMs: otherConfig.llmGapMs || DEFAULT_CONFIG.llmGapMs,
        outputLanguage: otherConfig.outputLanguage || DEFAULT_CONFIG.outputLanguage,
        mcpConfig: normalizeMcpConfig(otherConfig as Record<string, unknown>),
      };

      setConfig(nextConfig);
      llmModelSelectTouchedRef.current = false;
      llmBaseUrlTouchedRef.current = false;
      llmMaxTokensTouchedRef.current = false;
      setLlmModelSelectValue(
        computeLlmModelSelectValue(
          nextConfig.llmModel,
          getModelsForProvider(nextConfig.llmProvider),
        ),
      );
    } catch (error) {
      console.error("Failed to load config:", error);
      setConfig({ ...DEFAULT_CONFIG });
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = (key: keyof SystemConfigData, value: string | number) => {
    if (key === "llmMaxTokens") {
      llmMaxTokensTouchedRef.current = true;
    }
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
    setHasChanges(true);
  };

  const updateMcpConfig = (
    key: "enabled" | "preferMcp",
    value: boolean,
  ) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        mcpConfig: {
          ...prev.mcpConfig,
          [key]: value,
        },
      };
    });
    setHasChanges(true);
  };

  const updateMcpWritePolicy = (
    key: "max_writable_files_per_task" | "require_evidence_binding",
    value: number | boolean,
  ) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        mcpConfig: {
          ...prev.mcpConfig,
          writePolicy: {
            ...prev.mcpConfig.writePolicy,
            [key]:
              key === "max_writable_files_per_task"
                ? clampWritableFilesLimit(value)
                : Boolean(value),
            all_agents_writable: true,
            forbid_project_wide_writes: true,
          },
        },
      };
    });
    setHasChanges(true);
  };

  const computeLlmModelSelectValue = (model: string, models: string[]): string => {
    const current = (model || "").trim();
    if (!current) return "__default__";
    return models.includes(current) ? current : "__custom__";
  };

  const getProviderInfo = (providerId: string): LLMProviderItem | undefined => {
    return llmProviderOptions.find((p) => p.id === providerId);
  };

  const getDefaultModelForProvider = (providerId: string): string => {
    const backend = getProviderInfo(providerId);
    return backend?.defaultModel || DEFAULT_MODELS[providerId] || "";
  };

  const getDefaultBaseUrlForProvider = (providerId: string): string => {
    const backend = getProviderInfo(providerId);
    return backend?.defaultBaseUrl || "";
  };

  const getModelsForProvider = (providerId: string): string[] => {
    const fetchedModels = fetchedModelsByProvider[providerId];
    if (Array.isArray(fetchedModels) && fetchedModels.length > 0) return fetchedModels;
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
    const normalized = String(modelName || "").trim().toLowerCase();
    if (!normalized) return undefined;
    const matchedKey = Object.keys(metadata).find(
      (key) => key.trim().toLowerCase() === normalized,
    );
    if (!matchedKey) return undefined;
    return metadata[matchedKey];
  };

  const resolveCurrentModelName = (providerId: string, modelValue: string): string => {
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
      typeof metadata?.recommendedMaxTokens === "number" && metadata.recommendedMaxTokens > 0
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
    const provider = getProviderInfo(providerId);
    if (provider) return Boolean(provider.requiresApiKey);
    return providerId !== "ollama";
  };

  const validateStrictLlmInputs = (source: "save" | "test"): {
    ok: boolean;
    providerId: string;
    apiKey: string;
    model: string;
    baseUrl: string;
  } => {
    if (!config) {
      return { ok: false, providerId: "openai", apiKey: "", model: "", baseUrl: "" };
    }
    const providerId = normalizeLlmProviderId(config.llmProvider);
    const apiKey = String(config.llmApiKey || "").trim();
    const model = String(config.llmModel || "").trim();
    const baseUrl = String(config.llmBaseUrl || "").trim();

    if (!model) {
      toast.error(`无法${source === "save" ? "保存" : "测试"}：请先填写模型（llmModel）`);
      return { ok: false, providerId, apiKey, model, baseUrl };
    }
    if (!baseUrl) {
      toast.error(`无法${source === "save" ? "保存" : "测试"}：请先填写 Base URL（llmBaseUrl）`);
      return { ok: false, providerId, apiKey, model, baseUrl };
    }
    if (shouldRequireApiKey(providerId) && !apiKey) {
      toast.error(`无法${source === "save" ? "保存" : "测试"}：当前提供商必须配置 API Key`);
      return { ok: false, providerId, apiKey, model, baseUrl };
    }
    return { ok: true, providerId, apiKey, model, baseUrl };
  };

  const applyLongReasoningPreset = () => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        llmTemperature: 0.05,
        llmTimeout: 300000,
        llmMaxTokens: 16384,
        llmFirstTokenTimeout: 180,
        llmStreamTimeout: 180,
        agentTimeout: 3600,
        subAgentTimeout: 1200,
        toolTimeout: 120,
        llmConcurrency: 1,
        llmGapMs: 3000,
      };
    });
    llmMaxTokensTouchedRef.current = true;
    setHasChanges(true);
    toast.success("已应用漏洞挖掘-长推理预设，可继续微调。");
  };

  const handleProviderChange = (newProvider: string) => {
    const defaultModel = getDefaultModelForProvider(newProvider);
    setConfig((prev) => {
      if (!prev) return prev;
      const defaultBaseUrl = getDefaultBaseUrlForProvider(newProvider);
      const shouldUpdateBaseUrl =
        !llmBaseUrlTouchedRef.current || !(prev.llmBaseUrl || "").trim();
      return {
        ...prev,
        llmProvider: newProvider,
        llmModel: defaultModel || prev.llmModel,
        llmBaseUrl: shouldUpdateBaseUrl ? defaultBaseUrl : prev.llmBaseUrl,
      };
    });
    llmModelSelectTouchedRef.current = true;
    setLlmModelSelectValue("__default__");
    applyRecommendedMaxTokens(newProvider, defaultModel, {
      force: false,
      markChanges: true,
    });
    setHasChanges(true);
    setLlmTestResult(null);
  };

  const handleFetchModels = async () => {
    if (!config) return;
    const providerId = normalizeLlmProviderId(config.llmProvider);
    const requiresApiKey = shouldRequireApiKey(providerId);
    if (requiresApiKey && !config.llmApiKey.trim()) {
      toast.error("当前提供商需要 API Key，无法拉取模型");
      return;
    }

    setFetchingModels(true);
    try {
      const result = await api.fetchLLMModels({
        provider: providerId,
        apiKey: config.llmApiKey,
        baseUrl: config.llmBaseUrl || undefined,
      });
      const normalizedModels = Array.isArray(result.models)
        ? [...new Set(result.models.filter((m) => typeof m === "string" && m.trim()))]
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
      llmModelSelectTouchedRef.current = false;
      setLlmModelSelectValue(
        computeLlmModelSelectValue(config.llmModel, normalizedModels),
      );
      const effectiveModel =
        resolveCurrentModelName(providerId, config.llmModel) ||
        result.defaultModel ||
        getDefaultModelForProvider(providerId);
      const recommendation = applyRecommendedMaxTokens(providerId, effectiveModel, {
        force: false,
        markChanges: true,
      });
      if (result.success) {
        const sourceLabel =
          TOKEN_SOURCE_LABELS[result.tokenRecommendationSource || recommendation.source] ||
          "默认值";
        toast.success(`${result.message || "模型列表已更新"}（max tokens: ${recommendation.value}，${sourceLabel}）`);
      } else {
        toast.error(result.message || "模型拉取失败");
      }
    } catch (error) {
      toast.error(`模型拉取失败: ${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setFetchingModels(false);
    }
  };

  useEffect(() => {
    if (!config) return;
    const models = getModelsForProvider(config.llmProvider);
    if (!models.length) return;
    if (llmModelSelectTouchedRef.current) return;
    setLlmModelSelectValue(computeLlmModelSelectValue(config.llmModel, models));
  }, [config, llmProvidersFromBackend, fetchedModelsByProvider]);

  const handleLlmModelSelect = (value: string) => {
    if (!config) return;
    llmModelSelectTouchedRef.current = true;
    setLlmModelSelectValue(value);
    const providerId = normalizeLlmProviderId(config.llmProvider);
    const defaultModel = getDefaultModelForProvider(providerId);

    if (value === "__default__") {
      updateConfig("llmModel", defaultModel);
      applyRecommendedMaxTokens(providerId, defaultModel, {
        force: false,
        markChanges: true,
      });
      return;
    }
    if (value === "__custom__") {
      return;
    }

    updateConfig("llmModel", value);
    applyRecommendedMaxTokens(providerId, value, {
      force: false,
      markChanges: true,
    });
  };

  const applyCurrentModelRecommendation = () => {
    if (!config) return;
    const providerId = normalizeLlmProviderId(config.llmProvider);
    const effectiveModel = resolveCurrentModelName(providerId, config.llmModel);
    llmMaxTokensTouchedRef.current = false;
    const recommendation = applyRecommendedMaxTokens(providerId, effectiveModel, {
      force: true,
      markChanges: true,
    });
    const sourceLabel = TOKEN_SOURCE_LABELS[recommendation.source] || "默认值";
    toast.success(`已应用模型推荐 max tokens: ${recommendation.value}（${sourceLabel}）`);
  };

  const currentModelRecommendation = useMemo(() => {
    if (!config) return null;
    const providerId = normalizeLlmProviderId(config.llmProvider);
    const effectiveModel = resolveCurrentModelName(providerId, config.llmModel);
    if (!effectiveModel) return null;
    return getRecommendedMaxTokens(providerId, effectiveModel);
  }, [config, llmProvidersFromBackend, fetchedModelsByProvider, fetchedModelMetadataByProvider]);

  const saveConfig = async () => {
    if (!config) return;
    const validated = validateStrictLlmInputs("save");
    if (!validated.ok) return;

    try {
      const savedConfig = await api.updateUserConfig({
        llmConfig: {
          llmProvider: validated.providerId,
          llmApiKey: validated.apiKey,
          llmModel: validated.model,
          llmBaseUrl: validated.baseUrl,
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
          mcpConfig: {
            enabled: Boolean(config.mcpConfig.enabled),
            preferMcp: Boolean(config.mcpConfig.preferMcp),
            writePolicy: {
              all_agents_writable: true,
              max_writable_files_per_task: clampWritableFilesLimit(
                config.mcpConfig.writePolicy.max_writable_files_per_task,
              ),
              require_evidence_binding: Boolean(
                config.mcpConfig.writePolicy.require_evidence_binding,
              ),
              forbid_project_wide_writes: true,
            },
          },
        },
      });

      if (savedConfig) {
        const llmConfig = savedConfig.llmConfig || {};
        const otherConfig = savedConfig.otherConfig || {};
        const normalizedProvider = normalizeLlmProviderId(llmConfig.llmProvider);
        const nextConfig: SystemConfigData = {
          llmProvider: normalizedProvider || DEFAULT_CONFIG.llmProvider,
          llmApiKey: llmConfig.llmApiKey || "",
          llmModel: llmConfig.llmModel || "",
          llmBaseUrl: llmConfig.llmBaseUrl || "",
          llmTimeout: llmConfig.llmTimeout || DEFAULT_CONFIG.llmTimeout,
          llmTemperature: llmConfig.llmTemperature ?? DEFAULT_CONFIG.llmTemperature,
          llmMaxTokens: llmConfig.llmMaxTokens || DEFAULT_CONFIG.llmMaxTokens,
          llmFirstTokenTimeout: llmConfig.llmFirstTokenTimeout || DEFAULT_CONFIG.llmFirstTokenTimeout,
          llmStreamTimeout: llmConfig.llmStreamTimeout || DEFAULT_CONFIG.llmStreamTimeout,
          agentTimeout: llmConfig.agentTimeout || DEFAULT_CONFIG.agentTimeout,
          subAgentTimeout: llmConfig.subAgentTimeout || DEFAULT_CONFIG.subAgentTimeout,
          toolTimeout: llmConfig.toolTimeout || DEFAULT_CONFIG.toolTimeout,
          maxAnalyzeFiles: otherConfig.maxAnalyzeFiles ?? DEFAULT_CONFIG.maxAnalyzeFiles,
          llmConcurrency: otherConfig.llmConcurrency || DEFAULT_CONFIG.llmConcurrency,
          llmGapMs: otherConfig.llmGapMs || DEFAULT_CONFIG.llmGapMs,
          outputLanguage: otherConfig.outputLanguage || DEFAULT_CONFIG.outputLanguage,
          mcpConfig: normalizeMcpConfig(otherConfig as Record<string, unknown>),
        };
        setConfig(nextConfig);
        llmModelSelectTouchedRef.current = false;
        setLlmModelSelectValue(
          computeLlmModelSelectValue(
            nextConfig.llmModel,
            getModelsForProvider(nextConfig.llmProvider),
          ),
        );
        llmBaseUrlTouchedRef.current = false;
      }

      setHasChanges(false);
      toast.success("配置已保存！");
    } catch (error) {
      toast.error(`保存失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  const resetConfig = async () => {
    if (!window.confirm("确定要重置为默认配置吗？")) return;
    try {
      await api.deleteUserConfig();
      await loadConfig();
      setHasChanges(false);
      toast.success("已重置为默认配置");
    } catch (error) {
      toast.error(`重置失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  const testLLMConnection = async () => {
    if (!config) return;
    const validated = validateStrictLlmInputs("test");
    if (!validated.ok) return;

    setTestingLLM(true);
    setLlmTestResult(null);
    try {
      const result = await api.testLLMConnection({
        provider: validated.providerId,
        apiKey: validated.apiKey,
        model: validated.model,
        baseUrl: validated.baseUrl,
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
    } finally {
      setTestingLLM(false);
    }
  };

  if (loading || !config) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-4">
          <div className="loading-spinner mx-auto" />
          <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">加载配置中...</p>
        </div>
      </div>
    );
  }

  const normalizedProviderId = normalizeLlmProviderId(config.llmProvider);
  const selectedProviderInfo = getProviderInfo(normalizedProviderId);
  const currentModelName = resolveCurrentModelName(
    normalizedProviderId,
    config.llmModel,
  );
  const availableModelCount = getModelsForProvider(normalizedProviderId).length;
  const availableModelMetadataCount = Object.keys(
    getModelMetadataForProvider(normalizedProviderId),
  ).length;
  const hasModelConfigured = String(config.llmModel || "").trim().length > 0;
  const hasBaseUrlConfigured = String(config.llmBaseUrl || "").trim().length > 0;
  const isConfigured =
    (!shouldRequireApiKey(config.llmProvider) || config.llmApiKey.trim() !== "") &&
    hasModelConfigured &&
    hasBaseUrlConfigured;

  return (
    <div className="space-y-6">
      <Tabs defaultValue={sections.includes(defaultSection) ? defaultSection : sections[0]} className="w-full">
        {!mergedView && sections.length > 1 && (
          <TabsList className={`grid w-full ${tabsGridClass} bg-muted border border-border p-1 h-auto gap-1 rounded-lg mb-6`}>
            {sections.includes("llm") && (
              <TabsTrigger value="llm" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2">
                <Zap className="w-3 h-3" /> LLM 配置
              </TabsTrigger>
            )}
            {sections.includes("embedding") && (
              <TabsTrigger value="embedding" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2">
                <Brain className="w-3 h-3" /> 嵌入模型
              </TabsTrigger>
            )}
            {sections.includes("analysis") && (
              <TabsTrigger value="analysis" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2">
                <Settings className="w-3 h-3" /> 分析参数
              </TabsTrigger>
            )}
            {sections.includes("mcp") && (
              <TabsTrigger value="mcp" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2.5 text-muted-foreground transition-all rounded text-xs flex items-center gap-2">
                <Shield className="w-3 h-3" /> MCP 配置
              </TabsTrigger>
            )}
          </TabsList>
        )}

        {sections.includes("llm") && (
          <TabsContent value="llm" className="space-y-6">
            <div className="cyber-card p-6 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="cyber-card p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="stat-label">模型提供商</p>
                      <p className="stat-value text-2xl break-all">
                        {selectedProviderInfo?.name || normalizedProviderId}
                      </p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {selectedProviderInfo?.supportsModelFetch
                          ? "支持在线拉取"
                          : "静态模型列表"}
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
                      <p className="text-sm text-muted-foreground mt-1">
                        推荐 max tokens：{currentModelRecommendation?.value ?? config.llmMaxTokens}
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
                      <p className="stat-label">模型统计</p>
                      <p className="stat-value">{availableModelCount} 个模型</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        元数据 {availableModelMetadataCount} ·
                        {selectedProviderInfo?.supportsModelFetch ? " 支持在线拉取" : " 使用静态列表"}
                      </p>
                    </div>
                    <div className="stat-icon text-emerald-400">
                      <Zap className="w-6 h-6" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">提供商</Label>
                <Select value={config.llmProvider} onValueChange={handleProviderChange}>
                  <SelectTrigger className="h-12 cyber-input">
                    <SelectValue placeholder="选择提供商" />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    {llmProviderOptions.map((provider) => (
                      <SelectItem key={provider.id} value={provider.id} className="font-mono">
                        {provider.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedProviderInfo?.description ? (
                  <p className="text-xs text-muted-foreground">{selectedProviderInfo.description}</p>
                ) : null}
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">
                  API Key
                  {shouldRequireApiKey(config.llmProvider) ? (
                    <span className="text-rose-400 ml-1">*</span>
                  ) : null}
                </Label>
                <div className="flex gap-2">
                  <Input
                    type={showApiKey ? "text" : "password"}
                    value={config.llmApiKey}
                    onChange={(event) => updateConfig("llmApiKey", event.target.value)}
                    placeholder={
                      shouldRequireApiKey(config.llmProvider)
                        ? "输入你的 API Key"
                        : "该提供商无需 API Key"
                    }
                    className="h-12 cyber-input"
                    disabled={!shouldRequireApiKey(config.llmProvider)}
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setShowApiKey((prev) => !prev)}
                    className="h-12 w-12 cyber-btn-ghost"
                    disabled={!shouldRequireApiKey(config.llmProvider)}
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">
                  API 站口
                  <span className="text-rose-400 ml-1">*</span>
                </Label>
                <Input
                  value={config.llmBaseUrl}
                  onChange={(event) => {
                    llmBaseUrlTouchedRef.current = true;
                    updateConfig("llmBaseUrl", event.target.value);
                  }}
                  placeholder={(() => {
                    const baseUrl = getDefaultBaseUrlForProvider(config.llmProvider);
                    if (baseUrl) return `必填，例如：${baseUrl}`;
                    return "必填：请输入完整 Base URL";
                  })()}
                  className="h-10 cyber-input"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    模型选择
                    <span className="text-rose-400 ml-1">*</span>
                  </Label>
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 cyber-btn-ghost text-xs"
                    onClick={handleFetchModels}
                    disabled={
                      fetchingModels ||
                      !config.llmProvider ||
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
                      "一键获取模型"
                    )}
                  </Button>
                </div>
                {(() => {
                  const providerId = config.llmProvider;
                  const models = getModelsForProvider(providerId);
                  const defaultModel = getDefaultModelForProvider(providerId) || "auto";

                  if (!models.length) {
                    return (
                      <div className="space-y-2">
                        <Input
                          value={config.llmModel}
                          onChange={(event) => updateConfig("llmModel", event.target.value)}
                          placeholder={`请输入模型名称，例如：${defaultModel}`}
                          className="h-10 cyber-input"
                        />
                        {currentModelRecommendation ? (
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>
                              推荐 max tokens: {currentModelRecommendation.value}（
                              {TOKEN_SOURCE_LABELS[currentModelRecommendation.source] || "默认值"}）
                            </span>
                            {llmMaxTokensTouchedRef.current ? (
                              <Button
                                type="button"
                                variant="outline"
                                className="h-7 px-2 text-xs cyber-btn-ghost"
                                onClick={applyCurrentModelRecommendation}
                              >
                                跟随模型建议
                              </Button>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  }

                  const fallbackSelectValue = computeLlmModelSelectValue(
                    config.llmModel,
                    models,
                  );
                  const selectValue =
                    llmModelSelectValue === "__default__" ||
                    llmModelSelectValue === "__custom__" ||
                    models.includes(llmModelSelectValue)
                      ? llmModelSelectValue
                      : fallbackSelectValue;
                  const displayLabel =
                    selectValue === "__default__"
                      ? `默认（${defaultModel}）`
                      : selectValue === "__custom__"
                        ? config.llmModel?.trim()
                          ? `自定义：${config.llmModel.trim()}`
                          : "自定义模型..."
                        : selectValue;

                  return (
                    <div className="space-y-2">
                      <Popover open={llmModelPopoverOpen} onOpenChange={setLlmModelPopoverOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            role="combobox"
                            aria-expanded={llmModelPopoverOpen}
                            className="h-10 w-full justify-between cyber-input font-mono text-sm"
                          >
                            <span className="truncate text-left">{displayLabel}</span>
                            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent
                          className="w-[--radix-popover-trigger-width] p-0 cyber-dialog border-border"
                          align="start"
                        >
                          <Command className="bg-background">
                            <CommandInput placeholder="搜索模型..." />
                            <CommandList className="max-h-[280px]">
                              <CommandEmpty>未找到匹配模型</CommandEmpty>
                              <CommandGroup>
                                <CommandItem
                                  value={`自定义模型 ${config.llmModel || ""}`}
                                  onSelect={() => {
                                    handleLlmModelSelect("__custom__");
                                    setLlmModelPopoverOpen(false);
                                  }}
                                  className="font-mono"
                                >
                                  <Check
                                    className={cn(
                                      "mr-2 h-4 w-4",
                                      selectValue === "__custom__" ? "opacity-100" : "opacity-0",
                                    )}
                                  />
                                  自定义模型...
                                </CommandItem>
                                {defaultModel ? (
                                  <CommandItem
                                    value={`默认模型 ${defaultModel}`}
                                    onSelect={() => {
                                      handleLlmModelSelect("__default__");
                                      setLlmModelPopoverOpen(false);
                                    }}
                                    className="font-mono"
                                  >
                                    <Check
                                      className={cn(
                                        "mr-2 h-4 w-4",
                                        selectValue === "__default__" ? "opacity-100" : "opacity-0",
                                      )}
                                    />
                                    默认（{defaultModel}）
                                  </CommandItem>
                                ) : null}
                                {models.map((model) => (
                                  <CommandItem
                                    key={model}
                                    value={model}
                                    onSelect={() => {
                                      handleLlmModelSelect(model);
                                      setLlmModelPopoverOpen(false);
                                    }}
                                    className="font-mono"
                                  >
                                    <Check
                                      className={cn(
                                        "mr-2 h-4 w-4",
                                        selectValue === model ? "opacity-100" : "opacity-0",
                                      )}
                                    />
                                    <span className="truncate">{model}</span>
                                  </CommandItem>
                                ))}
                              </CommandGroup>
                            </CommandList>
                          </Command>
                        </PopoverContent>
                      </Popover>

                      {selectValue === "__custom__" ? (
                        <Input
                          value={config.llmModel}
                          onChange={(event) => {
                            llmModelSelectTouchedRef.current = true;
                            setLlmModelSelectValue("__custom__");
                            updateConfig("llmModel", event.target.value);
                          }}
                          placeholder="输入模型名称"
                          className="h-10 cyber-input"
                        />
                      ) : null}

                      {currentModelRecommendation ? (
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            推荐 max tokens: {currentModelRecommendation.value}（
                            {TOKEN_SOURCE_LABELS[currentModelRecommendation.source] || "默认值"}）
                          </span>
                          {llmMaxTokensTouchedRef.current ? (
                            <Button
                              type="button"
                              variant="outline"
                              className="h-7 px-2 text-xs cyber-btn-ghost"
                              onClick={applyCurrentModelRecommendation}
                            >
                              跟随模型建议
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })()}
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    className="cyber-btn-ghost h-9"
                    onClick={applyLongReasoningPreset}
                    type="button"
                  >
                    <Zap className="w-4 h-4 mr-2" />
                    漏洞挖掘-长推理预设
                  </Button>
                  <Button
                    variant="outline"
                    className="cyber-btn-ghost h-9"
                    onClick={() => setAdvancedOpen(true)}
                    type="button"
                  >
                    <Settings className="w-4 h-4 mr-2" />
                    高级配置
                  </Button>
                </div>
              </div>

              <div className="pt-4 border-t border-border border-dashed flex items-center justify-between flex-wrap gap-4">
                <div className="text-sm">
                  <span className="font-bold text-foreground">测试连接</span>
                  <span className="text-muted-foreground ml-2">验证配置是否正确</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={testLLMConnection}
                    disabled={testingLLM || !isConfigured}
                    className="cyber-btn-primary h-10"
                  >
                    {testingLLM ? (
                      <>
                        <div className="loading-spinner w-4 h-4 mr-2" />
                        测试中...
                      </>
                    ) : (
                      <>
                        <PlayCircle className="w-4 h-4 mr-2" />
                        测试
                      </>
                    )}
                  </Button>

                  <Button
                    onClick={saveConfig}
                    disabled={!hasChanges}
                    variant="outline"
                    className="cyber-btn-outline h-10"
                    type="button"
                  >
                    <Save className="w-4 h-4 mr-2" />
                    保存
                  </Button>

                  <Button
                    onClick={resetConfig}
                    disabled={testingLLM}
                    variant="ghost"
                    className="cyber-btn-ghost h-10"
                    type="button"
                  >
                    <RotateCcw className="w-4 h-4 mr-2" />
                    重置
                  </Button>
                </div>
              </div>

              {llmTestResult && (
                <div className={`p-3 rounded-lg ${llmTestResult.success ? "bg-emerald-500/10 border border-emerald-500/30" : "bg-rose-500/10 border border-rose-500/30"}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm">
                      {llmTestResult.success ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <AlertCircle className="h-4 w-4 text-rose-400" />
                      )}
                      <span className={llmTestResult.success ? "text-emerald-300/80" : "text-rose-300/80"}>
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
            </div>

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
          </TabsContent>
        )}

        {!mergedView && sections.includes("embedding") && (
          <TabsContent value="embedding" className="space-y-6">
            <EmbeddingConfig />
          </TabsContent>
        )}

        {!mergedView && sections.includes("analysis") && (
          <TabsContent value="analysis" className="space-y-6">
            <div className="cyber-card p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">最大分析文件数</Label>
                  <Input type="number" value={config.maxAnalyzeFiles} onChange={(event) => updateConfig("maxAnalyzeFiles", Number(event.target.value))} className="h-10 cyber-input" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">LLM 并发数</Label>
                  <Input type="number" value={config.llmConcurrency} onChange={(event) => updateConfig("llmConcurrency", Number(event.target.value))} className="h-10 cyber-input" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">请求间隔 (毫秒)</Label>
                  <Input type="number" value={config.llmGapMs} onChange={(event) => updateConfig("llmGapMs", Number(event.target.value))} className="h-10 cyber-input" />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">输出语言</Label>
                  <Select value={config.outputLanguage} onValueChange={(value) => updateConfig("outputLanguage", value)}>
                    <SelectTrigger className="h-10 cyber-input">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="zh-CN" className="font-mono">🇨🇳 中文</SelectItem>
                      <SelectItem value="en-US" className="font-mono">🇺🇸 English</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </TabsContent>
        )}

        {!mergedView && sections.includes("mcp") && (
          <TabsContent value="mcp" className="space-y-6">
            <div className="cyber-card p-6 space-y-6">
              <div className="space-y-1">
                <div className="font-mono font-bold uppercase text-sm text-foreground">
                  MCP 运行时策略
                </div>
                <div className="text-xs text-muted-foreground">
                  全部 Agent 可写已启用；项目全量写入永久禁用；单任务可写文件数后端硬上限为 50。
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    MCP 开关
                  </Label>
                  <Select
                    value={config.mcpConfig.enabled ? "enabled" : "disabled"}
                    onValueChange={(value) => updateMcpConfig("enabled", value === "enabled")}
                  >
                    <SelectTrigger className="h-10 cyber-input">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="enabled" className="font-mono">
                        启用
                      </SelectItem>
                      <SelectItem value="disabled" className="font-mono">
                        禁用
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    MCP 优先执行
                  </Label>
                  <Select
                    value={config.mcpConfig.preferMcp ? "enabled" : "disabled"}
                    onValueChange={(value) => updateMcpConfig("preferMcp", value === "enabled")}
                  >
                    <SelectTrigger className="h-10 cyber-input">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="enabled" className="font-mono">
                        启用
                      </SelectItem>
                      <SelectItem value="disabled" className="font-mono">
                        禁用
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    全部 Agent 可写
                  </Label>
                  <Input
                    value="已启用（受写入白名单与上限约束）"
                    disabled
                    className="h-10 cyber-input opacity-80"
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    项目全量写入
                  </Label>
                  <Input
                    value="永久禁用（不可关闭）"
                    disabled
                    className="h-10 cyber-input opacity-80"
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    单任务最多可写文件数（1-50）
                  </Label>
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={config.mcpConfig.writePolicy.max_writable_files_per_task}
                    onChange={(event) =>
                      updateMcpWritePolicy(
                        "max_writable_files_per_task",
                        Number(event.target.value || 0),
                      )
                    }
                    className="h-10 cyber-input"
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">
                    需要证据绑定
                  </Label>
                  <Select
                    value={config.mcpConfig.writePolicy.require_evidence_binding ? "enabled" : "disabled"}
                    onValueChange={(value) =>
                      updateMcpWritePolicy("require_evidence_binding", value === "enabled")
                    }
                  >
                    <SelectTrigger className="h-10 cyber-input">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="enabled" className="font-mono">
                        启用
                      </SelectItem>
                      <SelectItem value="disabled" className="font-mono">
                        禁用
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </TabsContent>
        )}
      </Tabs>

      {hasChanges && !advancedOpen && (
        <div className="fixed bottom-6 right-6 cyber-card p-4 z-50">
          <Button onClick={saveConfig} className="cyber-btn-primary h-12">
            <Save className="w-4 h-4 mr-2" /> 保存所有更改
          </Button>
        </div>
      )}
    </div>
  );
}
