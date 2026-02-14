/**
 * System Config Component
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCircle, Brain, CheckCircle2, Eye, EyeOff, PlayCircle, RotateCcw, Save, Settings, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";

const DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-5",
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
}

type ConfigSection = "llm" | "embedding" | "analysis";

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
};

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
  visibleSections = ["llm", "embedding", "analysis"],
  defaultSection = "llm",
  mergedView = false,
}: SystemConfigProps = {}) {
  const sections = visibleSections.length > 0 ? visibleSections : ["llm"];
  const forcedProvider = "openai";
  const [config, setConfig] = useState<SystemConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);
  const [llmModelSelectValue, setLlmModelSelectValue] =
    useState<string>("__default__");
  const [hasChanges, setHasChanges] = useState(false);
  const [testingLLM, setTestingLLM] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedAdvancedItemId, setSelectedAdvancedItemId] =
    useState<AdvancedConfigItemId>("llmTimeout");
  const [llmProvidersFromBackend, setLlmProvidersFromBackend] = useState<
    Array<{
      id: string;
      name: string;
      defaultModel: string;
      models: string[];
      defaultBaseUrl: string;
    }>
  >([]);
  const [llmTestResult, setLlmTestResult] = useState<{
    success: boolean;
    message: string;
    debug?: Record<string, unknown>;
  } | null>(null);
  const [showDebugInfo, setShowDebugInfo] = useState(true);
  const hasForcedProviderSavedRef = useRef(false);
  const llmModelSelectTouchedRef = useRef(false);

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
    return "grid-cols-3";
  }, [sections.length]);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const backendConfig = await api.getUserConfig();
      if (!backendConfig) {
        setConfig({ ...DEFAULT_CONFIG, llmProvider: forcedProvider });
        return;
      }

      const llmConfig = backendConfig.llmConfig || {};
      const otherConfig = backendConfig.otherConfig || {};

      const nextConfig: SystemConfigData = {
        llmProvider: forcedProvider,
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
      };

      setConfig(nextConfig);
      llmModelSelectTouchedRef.current = false;
      setLlmModelSelectValue(
        computeLlmModelSelectValue(
          nextConfig.llmModel,
          getModelsForProvider(forcedProvider),
        ),
      );

      // Force provider=openai and persist silently once.
      if (
        llmConfig.llmProvider !== forcedProvider &&
        !hasForcedProviderSavedRef.current
      ) {
        hasForcedProviderSavedRef.current = true;
        try {
          await api.updateUserConfig({
            llmConfig: {
              llmProvider: forcedProvider,
              llmApiKey: nextConfig.llmApiKey,
              llmModel: nextConfig.llmModel,
              llmBaseUrl: nextConfig.llmBaseUrl,
              llmTimeout: nextConfig.llmTimeout,
              llmTemperature: nextConfig.llmTemperature,
              llmMaxTokens: nextConfig.llmMaxTokens,
              llmFirstTokenTimeout: nextConfig.llmFirstTokenTimeout,
              llmStreamTimeout: nextConfig.llmStreamTimeout,
              agentTimeout: nextConfig.agentTimeout,
              subAgentTimeout: nextConfig.subAgentTimeout,
              toolTimeout: nextConfig.toolTimeout,
            },
            otherConfig: {
              maxAnalyzeFiles: nextConfig.maxAnalyzeFiles,
              llmConcurrency: nextConfig.llmConcurrency,
              llmGapMs: nextConfig.llmGapMs,
              outputLanguage: nextConfig.outputLanguage,
            },
          });
        } catch (error) {
          console.error("Failed to force llmProvider=openai:", error);
        }
      }
    } catch (error) {
      console.error("Failed to load config:", error);
      setConfig({ ...DEFAULT_CONFIG, llmProvider: forcedProvider });
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = (key: keyof SystemConfigData, value: string | number) => {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
    setHasChanges(true);
  };

  const computeLlmModelSelectValue = (model: string, models: string[]): string => {
    const current = (model || "").trim();
    if (!current) return "__default__";
    return models.includes(current) ? current : "__custom__";
  };

  const getDefaultModelForProvider = (providerId: string): string => {
    const backend = llmProvidersFromBackend.find((p) => p.id === providerId);
    return backend?.defaultModel || DEFAULT_MODELS[providerId] || "";
  };

  const getDefaultBaseUrlForProvider = (providerId: string): string => {
    const backend = llmProvidersFromBackend.find((p) => p.id === providerId);
    return backend?.defaultBaseUrl || "";
  };

  const getModelsForProvider = (providerId: string): string[] => {
    const backend = llmProvidersFromBackend.find((p) => p.id === providerId);
    return Array.isArray(backend?.models) ? backend!.models : [];
  };

  useEffect(() => {
    if (!config) return;
    const models = getModelsForProvider(forcedProvider);
    if (!models.length) return;
    if (llmModelSelectTouchedRef.current) return;
    setLlmModelSelectValue(computeLlmModelSelectValue(config.llmModel, models));
  }, [config, llmProvidersFromBackend]);

  const saveConfig = async () => {
    if (!config) return;

    try {
      const savedConfig = await api.updateUserConfig({
        llmConfig: {
          llmProvider: forcedProvider,
          llmApiKey: config.llmApiKey,
          llmModel: config.llmModel,
          llmBaseUrl: config.llmBaseUrl,
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
        const llmConfig = savedConfig.llmConfig || {};
        const otherConfig = savedConfig.otherConfig || {};
        const nextConfig: SystemConfigData = {
          llmProvider: forcedProvider,
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
        };
        setConfig(nextConfig);
        llmModelSelectTouchedRef.current = false;
        setLlmModelSelectValue(
          computeLlmModelSelectValue(
            nextConfig.llmModel,
            getModelsForProvider(forcedProvider),
          ),
        );
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
    if (!config.llmApiKey) {
      toast.error("请先配置 API Key");
      return;
    }

    setTestingLLM(true);
    setLlmTestResult(null);
    try {
      const result = await api.testLLMConnection({
        provider: forcedProvider,
        apiKey: config.llmApiKey,
        model: config.llmModel || undefined,
        baseUrl: config.llmBaseUrl || undefined,
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

  const isConfigured = config.llmApiKey !== "";

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
          </TabsList>
        )}

        {sections.includes("llm") && (
          <TabsContent value="llm" className="space-y-6">
            <div className="cyber-card p-6 space-y-6">
              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">API Key</Label>
                <div className="flex gap-2">
                  <Input
                    type={showApiKey ? "text" : "password"}
                    value={config.llmApiKey}
                    onChange={(event) => updateConfig("llmApiKey", event.target.value)}
                    placeholder="输入你的 API Key"
                    className="h-12 cyber-input"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setShowApiKey((prev) => !prev)}
                    className="h-12 w-12 cyber-btn-ghost"
                  >
                    {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">模型选择</Label>
                  {(() => {
                    const models = getModelsForProvider(forcedProvider);
                    const defaultModel = getDefaultModelForProvider(forcedProvider) || "auto";

                    if (!models.length) {
                      return (
                        <Input
                          value={config.llmModel}
                          onChange={(event) => updateConfig("llmModel", event.target.value)}
                          placeholder={`默认: ${defaultModel}`}
                          className="h-10 cyber-input"
                        />
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

                    return (
                      <div className="space-y-2">
                        <Select
                          value={selectValue}
                          onValueChange={(value) => {
                            llmModelSelectTouchedRef.current = true;
                            setLlmModelSelectValue(value);
                            if (value === "__default__") {
                              updateConfig("llmModel", "");
                              return;
                            }
                            if (value === "__custom__") {
                              // Switch to custom mode, and let user edit below.
                              return;
                            }
                            updateConfig("llmModel", value);
                          }}
                        >
                          <SelectTrigger className="h-10 cyber-input">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="cyber-dialog border-border">
                            <SelectItem value="__custom__" className="font-mono">
                              自定义模型...
                            </SelectItem>
                            <SelectItem value="__default__" className="font-mono">
                              默认（{defaultModel}）
                            </SelectItem>
                            {models.map((m) => (
                              <SelectItem key={m} value={m} className="font-mono">
                                {m}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>

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
                      </div>
                    );
                  })()}
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">API 站口</Label>
                  <Input
                    value={config.llmBaseUrl}
                    onChange={(event) => updateConfig("llmBaseUrl", event.target.value)}
                    placeholder={(() => {
                      const baseUrl = getDefaultBaseUrlForProvider(forcedProvider);
                      if (baseUrl) return `留空使用默认站口，例如：${baseUrl}`;
                      return "留空使用官方地址，或填入中转站地址";
                    })()}
                    className="h-10 cyber-input"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between">
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
