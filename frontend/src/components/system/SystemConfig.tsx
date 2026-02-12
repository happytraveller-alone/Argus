/**
 * System Config Component
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCircle, Brain, CheckCircle2, Eye, EyeOff, Info, PlayCircle, RotateCcw, Save, Settings, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import EmbeddingConfig from "@/components/agent/EmbeddingConfig";

const LLM_PROVIDERS = [
  { value: "openai", label: "OpenAI GPT", icon: "🟢", category: "litellm", hint: "gpt-5, gpt-5-mini, o3 等" },
  { value: "claude", label: "Anthropic Claude", icon: "🟣", category: "litellm", hint: "claude-sonnet-4.5, claude-opus-4 等" },
  { value: "gemini", label: "Google Gemini", icon: "🔵", category: "litellm", hint: "gemini-3-pro, gemini-3-flash 等" },
  { value: "deepseek", label: "DeepSeek", icon: "🔷", category: "litellm", hint: "deepseek-v3.1-terminus, deepseek-v3 等" },
  { value: "qwen", label: "通义千问", icon: "🟠", category: "litellm", hint: "qwen3-max-instruct, qwen3-plus 等" },
  { value: "zhipu", label: "智谱AI (GLM)", icon: "🔴", category: "litellm", hint: "glm-4.6, glm-4.5-flash 等" },
  { value: "moonshot", label: "Moonshot (Kimi)", icon: "🌙", category: "litellm", hint: "kimi-k2, kimi-k1.5 等" },
  { value: "ollama", label: "Ollama 本地", icon: "🖥️", category: "litellm", hint: "llama3.3-70b, qwen3-8b 等" },
  { value: "baidu", label: "百度文心", icon: "📘", category: "native", hint: "ernie-4.5 (需要 API_KEY:SECRET_KEY)" },
  { value: "minimax", label: "MiniMax", icon: "⚡", category: "native", hint: "minimax-m2, minimax-m1 等" },
  { value: "doubao", label: "字节豆包", icon: "🎯", category: "native", hint: "doubao-1.6-pro, doubao-1.5-pro 等" },
] as const;

const DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-5",
  claude: "claude-sonnet-4.5",
  gemini: "gemini-3-pro",
  deepseek: "deepseek-v3.1-terminus",
  qwen: "qwen3-max-instruct",
  zhipu: "glm-4.6",
  moonshot: "kimi-k2",
  ollama: "llama3.3-70b",
  baidu: "ernie-4.5",
  minimax: "minimax-m2",
  doubao: "doubao-1.6-pro",
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

export function SystemConfig({
  visibleSections = ["llm", "embedding", "analysis"],
  defaultSection = "llm",
  mergedView = false,
}: SystemConfigProps = {}) {
  const sections = visibleSections.length > 0 ? visibleSections : ["llm"];
  const [config, setConfig] = useState<SystemConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showApiKey, setShowApiKey] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [testingLLM, setTestingLLM] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{
    success: boolean;
    message: string;
    debug?: Record<string, unknown>;
  } | null>(null);
  const [showDebugInfo, setShowDebugInfo] = useState(true);

  useEffect(() => {
    loadConfig();
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
        setConfig(DEFAULT_CONFIG);
        return;
      }

      const llmConfig = backendConfig.llmConfig || {};
      const otherConfig = backendConfig.otherConfig || {};

      setConfig({
        llmProvider: llmConfig.llmProvider || DEFAULT_CONFIG.llmProvider,
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
      });
    } catch (error) {
      console.error("Failed to load config:", error);
      setConfig(DEFAULT_CONFIG);
    } finally {
      setLoading(false);
    }
  };

  const updateConfig = (key: keyof SystemConfigData, value: string | number) => {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
    setHasChanges(true);
  };

  const saveConfig = async () => {
    if (!config) return;

    try {
      const savedConfig = await api.updateUserConfig({
        llmConfig: {
          llmProvider: config.llmProvider,
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
        setConfig({
          llmProvider: llmConfig.llmProvider || config.llmProvider,
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
        });
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
    if (!config.llmApiKey && config.llmProvider !== "ollama") {
      toast.error("请先配置 API Key");
      return;
    }

    setTestingLLM(true);
    setLlmTestResult(null);
    try {
      const result = await api.testLLMConnection({
        provider: config.llmProvider,
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

  const currentProvider = LLM_PROVIDERS.find((provider) => provider.value === config.llmProvider);
  const isConfigured = config.llmApiKey !== "" || config.llmProvider === "ollama";

  return (
    <div className="space-y-6">
      <div className={`cyber-card p-4 ${isConfigured ? "border-emerald-500/30" : "border-amber-500/30"}`}>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <Info className="h-5 w-5 text-sky-400" />
            <span className="font-mono text-sm">
              {isConfigured ? (
                <span className="text-emerald-400 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4" /> LLM 已配置 ({currentProvider?.label})
                </span>
              ) : (
                <span className="text-amber-400 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" /> 请配置 LLM API Key
                </span>
              )}
            </span>
          </div>
          <div className="flex gap-2">
            {hasChanges && (
              <Button onClick={saveConfig} size="sm" className="cyber-btn-primary h-8">
                <Save className="w-3 h-3 mr-2" /> 保存
              </Button>
            )}
            <Button onClick={resetConfig} variant="outline" size="sm" className="cyber-btn-ghost h-8">
              <RotateCcw className="w-3 h-3 mr-2" /> 重置
            </Button>
          </div>
        </div>
      </div>

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
                <Label className="text-xs font-bold text-muted-foreground uppercase">选择 LLM 提供商</Label>
                <Select value={config.llmProvider} onValueChange={(value) => updateConfig("llmProvider", value)}>
                  <SelectTrigger className="h-12 cyber-input">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <div className="px-2 py-1.5 text-xs font-bold text-muted-foreground uppercase">LiteLLM 统一适配 (推荐)</div>
                    {LLM_PROVIDERS.filter((item) => item.category === "litellm").map((provider) => (
                      <SelectItem key={provider.value} value={provider.value} className="font-mono">
                        <span className="flex items-center gap-2">
                          <span>{provider.icon}</span>
                          <span>{provider.label}</span>
                          <span className="text-xs text-muted-foreground">- {provider.hint}</span>
                        </span>
                      </SelectItem>
                    ))}
                    <div className="px-2 py-1.5 text-xs font-bold text-muted-foreground uppercase mt-2">原生适配器</div>
                    {LLM_PROVIDERS.filter((item) => item.category === "native").map((provider) => (
                      <SelectItem key={provider.value} value={provider.value} className="font-mono">
                        <span className="flex items-center gap-2">
                          <span>{provider.icon}</span>
                          <span>{provider.label}</span>
                          <span className="text-xs text-muted-foreground">- {provider.hint}</span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {config.llmProvider !== "ollama" && (
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">API Key</Label>
                  <div className="flex gap-2">
                    <Input
                      type={showApiKey ? "text" : "password"}
                      value={config.llmApiKey}
                      onChange={(event) => updateConfig("llmApiKey", event.target.value)}
                      placeholder={config.llmProvider === "baidu" ? "API_KEY:SECRET_KEY 格式" : "输入你的 API Key"}
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
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">模型名称 (可选)</Label>
                  <Input
                    value={config.llmModel}
                    onChange={(event) => updateConfig("llmModel", event.target.value)}
                    placeholder={`默认: ${DEFAULT_MODELS[config.llmProvider] || "auto"}`}
                    className="h-10 cyber-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-bold text-muted-foreground uppercase">API Base URL (可选)</Label>
                  <Input
                    value={config.llmBaseUrl}
                    onChange={(event) => updateConfig("llmBaseUrl", event.target.value)}
                    placeholder="留空使用官方地址，或填入中转站地址"
                    className="h-10 cyber-input"
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-border border-dashed flex items-center justify-between flex-wrap gap-4">
                <div className="text-sm">
                  <span className="font-bold text-foreground">测试连接</span>
                  <span className="text-muted-foreground ml-2">验证配置是否正确</span>
                </div>
                <Button
                  onClick={testLLMConnection}
                  disabled={testingLLM || (!isConfigured && config.llmProvider !== "ollama")}
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

              <details className="pt-4 border-t border-border border-dashed">
                <summary className="font-bold uppercase cursor-pointer hover:text-primary text-muted-foreground text-sm">高级参数</summary>

                <div className="mt-4 mb-2">
                  <span className="text-xs text-muted-foreground uppercase font-semibold">LLM 基础参数</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">请求超时 (毫秒)</Label>
                    <Input type="number" value={config.llmTimeout} onChange={(event) => updateConfig("llmTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">温度 (0-2)</Label>
                    <Input type="number" step="0.1" min="0" max="2" value={config.llmTemperature} onChange={(event) => updateConfig("llmTemperature", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">最大 Tokens</Label>
                    <Input type="number" value={config.llmMaxTokens} onChange={(event) => updateConfig("llmMaxTokens", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                </div>

                <div className="mt-6 mb-2">
                  <span className="text-xs text-muted-foreground uppercase font-semibold">Agent 超时配置</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">首Token超时 (秒)</Label>
                    <Input type="number" value={config.llmFirstTokenTimeout} onChange={(event) => updateConfig("llmFirstTokenTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">流式超时 (秒)</Label>
                    <Input type="number" value={config.llmStreamTimeout} onChange={(event) => updateConfig("llmStreamTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">工具超时 (秒)</Label>
                    <Input type="number" value={config.toolTimeout} onChange={(event) => updateConfig("toolTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">子Agent超时 (秒)</Label>
                    <Input type="number" value={config.subAgentTimeout} onChange={(event) => updateConfig("subAgentTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground uppercase">总超时 (秒)</Label>
                    <Input type="number" value={config.agentTimeout} onChange={(event) => updateConfig("agentTimeout", Number(event.target.value))} className="h-10 cyber-input" />
                  </div>
                </div>
              </details>
            </div>

            <div className="bg-muted border border-border p-4 rounded-lg text-xs space-y-2">
              <p className="font-bold uppercase text-muted-foreground flex items-center gap-2">
                <Info className="w-4 h-4 text-sky-400" />
                配置说明
              </p>
              <p className="text-muted-foreground">• <strong className="text-muted-foreground">LiteLLM 统一适配</strong>: 大多数提供商通过 LiteLLM 统一处理，支持自动重试和负载均衡</p>
              <p className="text-muted-foreground">• <strong className="text-muted-foreground">原生适配器</strong>: 百度、MiniMax、豆包因 API 格式特殊，使用专用适配器</p>
              <p className="text-muted-foreground">• <strong className="text-muted-foreground">API 中转站</strong>: 在 Base URL 填入中转站地址即可，API Key 填中转站提供的 Key</p>
            </div>

            {mergedView && (
              <details className="cyber-card p-4">
                <summary className="font-bold uppercase cursor-pointer hover:text-primary text-muted-foreground text-sm">
                  嵌入模型配置（高级）
                </summary>
                <div className="mt-4">
                  <EmbeddingConfig />
                </div>
              </details>
            )}

            {mergedView && (
              <details className="cyber-card p-4">
                <summary className="font-bold uppercase cursor-pointer hover:text-primary text-muted-foreground text-sm">
                  分析参数（高级）
                </summary>
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-6">
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
              </details>
            )}
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

      {hasChanges && (
        <div className="fixed bottom-6 right-6 cyber-card p-4 z-50">
          <Button onClick={saveConfig} className="cyber-btn-primary h-12">
            <Save className="w-4 h-4 mr-2" /> 保存所有更改
          </Button>
        </div>
      )}
    </div>
  );
}
