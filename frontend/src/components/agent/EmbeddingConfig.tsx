/**
 * 嵌入模型配置组件
 * Cyberpunk Terminal Aesthetic
 * 独立于 LLM 配置，专门用于 Agent 扫描的 RAG 系统
 */

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Cpu,
  Loader2,
  Key,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  RotateCcw,
  Save,
  Settings,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/shared/api/serverClient";
import { runSaveThenTestAction } from "@/components/scan-config/intelligentEngineActionFlow";

interface EmbeddingProvider {
  id: string;
  name: string;
  description: string;
  models: string[];
  requires_api_key: boolean;
  default_model: string;
}

interface TestResult {
  success: boolean;
  message: string;
  dimensions?: number;
  sample_embedding?: number[];
  latency_ms?: number;
}

interface EmbeddingConfigPanelProps {
  compact?: boolean;
}

export default function EmbeddingConfigPanel({ compact = false }: EmbeddingConfigPanelProps) {
  const [providers, setProviders] = useState<EmbeddingProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [loadedSnapshot, setLoadedSnapshot] = useState<{
    provider: string;
    model: string;
    apiKey: string;
    baseUrl: string;
    customDimension: number | null;
    batchSize: number;
  } | null>(null);

  // 表单状态
  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [customDimension, setCustomDimension] = useState<number | null>(null);
  const [batchSize, setBatchSize] = useState(100);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [modelSelectValue, setModelSelectValue] = useState<string>("__default__");
  const modelSelectTouchedRef = useRef(false);

  // 加载数据
  useEffect(() => {
    loadData();
  }, []);

  // 用户手动切换 provider 时更新为默认模型
  const handleProviderChange = (newProvider: string) => {
    setSelectedProvider(newProvider);
    // 切换 provider 时重置为该 provider 的默认模型
    const provider = providers.find((p) => p.id === newProvider);
    if (provider) {
      setSelectedModel(provider.default_model);
      modelSelectTouchedRef.current = true;
      setModelSelectValue(provider.default_model ? "__default__" : "__custom__");
    }
    setHasChanges(true);
    setTestResult(null);
  };

  const computeEmbeddingModelSelectValue = (
    provider: EmbeddingProvider | undefined,
    model: string,
  ): string => {
    const models = Array.isArray(provider?.models) ? provider!.models : [];
    const defaultModel = String(provider?.default_model || "").trim();
    const currentModel = String(model || "").trim();

    if (!models.length) return "__custom__";
    if (!currentModel && defaultModel) return "__default__";
    if (defaultModel && currentModel === defaultModel) return "__default__";
    return models.includes(currentModel) ? currentModel : "__custom__";
  };

  useEffect(() => {
    const provider = providers.find((p) => p.id === selectedProvider);
    if (!provider || !Array.isArray(provider.models) || provider.models.length === 0) return;
    if (modelSelectTouchedRef.current) return;
    setModelSelectValue(computeEmbeddingModelSelectValue(provider, selectedModel));
  }, [providers, selectedProvider, selectedModel]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [providersRes, configRes] = await Promise.all([
        apiClient.get("/embedding/providers"),
        apiClient.get("/embedding/config"),
      ]);

      setProviders(providersRes.data);

      // 设置表单默认值
      if (configRes.data) {
        const nextProvider = String(configRes.data.provider || "");
        const nextModel = String(configRes.data.model || "");
        const nextApiKey = String(configRes.data.api_key || "");
        const nextBaseUrl = String(configRes.data.base_url || "");
        const nextDimension =
          typeof configRes.data.dimensions === "number" ? configRes.data.dimensions : null;
        const nextBatchSize =
          typeof configRes.data.batch_size === "number" ? configRes.data.batch_size : 100;

        setSelectedProvider(nextProvider);
        setSelectedModel(nextModel);
        setApiKey(nextApiKey);
        setBaseUrl(nextBaseUrl);
        setCustomDimension(nextDimension);
        setBatchSize(nextBatchSize);
        modelSelectTouchedRef.current = false;
        const provider = (providersRes.data as EmbeddingProvider[]).find(
          (p) => p.id === nextProvider,
        );
        setModelSelectValue(computeEmbeddingModelSelectValue(provider, nextModel));

        setLoadedSnapshot({
          provider: nextProvider,
          model: nextModel,
          apiKey: nextApiKey,
          baseUrl: nextBaseUrl,
          customDimension: nextDimension,
          batchSize: nextBatchSize,
        });
        setHasChanges(false);
        setTestResult(null);
      }
    } catch (error) {
      toast.error("加载配置失败");
    } finally {
      setLoading(false);
    }
  };

  const resetConfig = async () => {
    if (loadedSnapshot) {
      setSelectedProvider(loadedSnapshot.provider);
      setSelectedModel(loadedSnapshot.model);
      setApiKey(loadedSnapshot.apiKey);
      setBaseUrl(loadedSnapshot.baseUrl);
      setCustomDimension(loadedSnapshot.customDimension);
      setBatchSize(loadedSnapshot.batchSize);
      modelSelectTouchedRef.current = false;
      const provider = providers.find((p) => p.id === loadedSnapshot.provider);
      setModelSelectValue(
        computeEmbeddingModelSelectValue(provider, loadedSnapshot.model),
      );
      setHasChanges(false);
      setTestResult(null);
      return;
    }
    await loadData();
  };

  const validateEmbeddingInputs = () => {
    if (!selectedProvider) {
      toast.error("请选择提供商");
      return null;
    }

    const provider = providers.find((p) => p.id === selectedProvider);
    if (!selectedModel) {
      toast.error("请选择或输入模型");
      return null;
    }
    if (provider?.requires_api_key && !apiKey.trim()) {
      toast.error(`${provider.name} 需要 API Key`);
      return null;
    }

    return {
      provider: selectedProvider,
      model: selectedModel,
      apiKey: apiKey || undefined,
      baseUrl: baseUrl || undefined,
      dimension: customDimension || undefined,
      batchSize,
    };
  };

  const saveEmbeddingConfig = async (payload: {
    provider: string;
    model: string;
    apiKey?: string;
    baseUrl?: string;
    dimension?: number;
    batchSize: number;
  }) => {
    try {
      await apiClient.put("/embedding/config", {
        provider: payload.provider,
        model: payload.model,
        api_key: payload.apiKey,
        base_url: payload.baseUrl,
        dimensions: payload.dimension,
        batch_size: payload.batchSize,
      });

      toast.success("配置已保存");
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "保存失败");
      throw error;
    }
  };

  const testEmbeddingConfig = async (payload: {
    provider: string;
    model: string;
    apiKey?: string;
    baseUrl?: string;
    dimension?: number;
  }) => {
    try {
      setTestResult(null);

      const response = await apiClient.post("/embedding/test", {
        provider: payload.provider,
        model: payload.model,
        api_key: payload.apiKey,
        base_url: payload.baseUrl,
        dimension: payload.dimension,
      });

      setTestResult(response.data);

      if (response.data.success) {
        toast.success("测试成功");
      } else {
        toast.error("测试失败");
      }
    } catch (error: any) {
      setTestResult({
        success: false,
        message: error.response?.data?.detail || "测试失败",
      });
      toast.error("测试失败");
      return {
        success: false,
        message: error.response?.data?.detail || "测试失败",
      };
    }
  };

  const handleSaveAndTest = async () => {
    const payload = validateEmbeddingInputs();
    if (!payload) return;

    setSaving(true);
    setTesting(true);
    try {
      await runSaveThenTestAction({
        save: () => saveEmbeddingConfig(payload),
        test: () =>
          testEmbeddingConfig({
            provider: payload.provider,
            model: payload.model,
            apiKey: payload.apiKey,
            baseUrl: payload.baseUrl,
            dimension: payload.dimension,
          }),
      });
      setLoadedSnapshot({
        provider: payload.provider,
        model: payload.model,
        apiKey: payload.apiKey || "",
        baseUrl: payload.baseUrl || "",
        customDimension: payload.dimension ?? null,
        batchSize: payload.batchSize,
      });
      setHasChanges(false);
    } finally {
      setSaving(false);
      setTesting(false);
    }
  };

  const selectedProviderInfo = providers.find((p) => p.id === selectedProvider);
  const requiresApiKey = Boolean(selectedProviderInfo?.requires_api_key);
  const isConfigured = !requiresApiKey || apiKey.trim().length > 0;
  const canSaveAndTest =
    Boolean(selectedProvider) && Boolean(selectedModel) && isConfigured;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <div className="text-center space-y-4">
          <div className="loading-spinner mx-auto" />
          <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">加载配置中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={compact ? "space-y-4" : "space-y-6"}>
      <div className={`cyber-card ${compact ? "p-4 space-y-4" : "p-6 space-y-6"}`}>
        <div
          className={`grid grid-cols-1 md:grid-cols-2 min-[1800px]:grid-cols-4 ${
            compact ? "gap-3" : "gap-4"
          }`}
        >
          <div className="space-y-2 min-w-0">
            <Label className="text-base font-bold text-muted-foreground uppercase">
              模型供应商
            </Label>
            <Select value={selectedProvider} onValueChange={handleProviderChange}>
              <SelectTrigger className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}>
                <SelectValue placeholder="选择模型供应商" />
              </SelectTrigger>
              <SelectContent className="cyber-dialog border-border">
                {providers.map((provider) => (
                  <SelectItem key={provider.id} value={provider.id} className="font-mono">
                    <div className="flex items-center gap-2">
                      <span>{provider.name}</span>
                      {provider.requires_api_key ? (
                        <Key className="w-3 h-3 text-amber-400" />
                      ) : (
                        <Cpu className="w-3 h-3 text-emerald-400" />
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 min-w-0">
            <Label className="text-base font-bold text-muted-foreground uppercase">
              地址
            </Label>
            <Input
              type="url"
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setHasChanges(true);
              }}
              placeholder={
                selectedProvider === "ollama"
                  ? "http://localhost:11434"
                  : selectedProvider === "huggingface"
                  ? "https://router.huggingface.co"
                  : selectedProvider === "cohere"
                  ? "https://api.cohere.com/v2"
                  : selectedProvider === "jina"
                  ? "https://api.jina.ai/v1"
                  : "https://api.openai.com/v1"
              }
              className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}
            />
          </div>

          <div className="space-y-2 min-w-0">
            <Label className="text-base font-bold text-muted-foreground uppercase">
              密钥
              {requiresApiKey ? <span className="text-rose-400 ml-1">*</span> : null}
              <Button
                variant="outline"
                size="icon"
                onClick={() => setShowApiKey((prev) => !prev)}
                className={compact ? "h-5 w-10 cyber-btn-ghost" : "h-6 w-12 cyber-btn-ghost"}
                disabled={!requiresApiKey}
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
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setHasChanges(true);
                }}
                placeholder={requiresApiKey ? "输入你的 API Key" : "该提供商无需 API Key"}
                className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}
                disabled={!requiresApiKey}
              />
              
            </div>
          </div>

          <div className="space-y-2 min-w-0">
            <Label className="text-base font-bold text-muted-foreground uppercase">模型</Label>
            {selectedProviderInfo ? (
              (() => {
                const models = Array.isArray(selectedProviderInfo.models)
                  ? selectedProviderInfo.models
                  : [];
                const defaultModel = String(selectedProviderInfo.default_model || "").trim();

                if (!models.length) {
                  return (
                    <Input
                      value={selectedModel}
                      onChange={(event) => {
                        setSelectedModel(event.target.value);
                        setHasChanges(true);
                      }}
                      placeholder={defaultModel ? `默认: ${defaultModel}` : "输入模型名称"}
                      className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}
                    />
                  );
                }

                const fallbackSelectValue = computeEmbeddingModelSelectValue(
                  selectedProviderInfo,
                  selectedModel,
                );
                const selectValue =
                  modelSelectValue === "__default__" ||
                  modelSelectValue === "__custom__" ||
                  models.includes(modelSelectValue)
                    ? modelSelectValue
                    : fallbackSelectValue;

                return (
                  <div className="space-y-2">
                    <Select
                      value={selectValue}
                      onValueChange={(value) => {
                        modelSelectTouchedRef.current = true;
                        setModelSelectValue(value);
                        if (value === "__default__") {
                          setSelectedModel(defaultModel);
                          setHasChanges(true);
                          return;
                        }
                        if (value === "__custom__") {
                          setSelectedModel("");
                          setHasChanges(true);
                          return;
                        }
                        setSelectedModel(value);
                        setHasChanges(true);
                      }}
                    >
                      <SelectTrigger className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="cyber-dialog border-border">
                        <SelectItem value="__custom__" className="font-mono">
                          自定义模型...
                        </SelectItem>
                        {defaultModel ? (
                          <SelectItem value="__default__" className="font-mono">
                            默认（{defaultModel}）
                          </SelectItem>
                        ) : null}
                        {models.map((m) => (
                          <SelectItem key={m} value={m} className="font-mono">
                            {m}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {selectValue === "__custom__" ? (
                      <Input
                        value={selectedModel}
                        onChange={(event) => {
                          modelSelectTouchedRef.current = true;
                          setModelSelectValue("__custom__");
                          setSelectedModel(event.target.value);
                          setHasChanges(true);
                        }}
                        placeholder="输入模型名称"
                        className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}
                      />
                    ) : null}
                  </div>
                );
              })()
            ) : (
              <Input
                value={selectedModel}
                onChange={(event) => {
                  setSelectedModel(event.target.value);
                  setHasChanges(true);
                }}
                placeholder="请先选择模型供应商"
                className={compact ? "h-10 cyber-input" : "h-12 cyber-input"}
                disabled
              />
            )}
          </div>
        </div>

        {testResult && (
          <div
            className={`p-4 rounded-lg ${
              testResult.success
                ? "bg-emerald-500/10 border border-emerald-500/30"
                : "bg-rose-500/10 border border-rose-500/30"
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              {testResult.success ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <AlertCircle className="w-5 h-5 text-rose-400" />
              )}
              <span
                className={`font-bold ${
                  testResult.success ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {testResult.success ? "测试成功" : "测试失败"}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">{testResult.message}</p>
            {testResult.success && (
              <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground space-y-1 font-mono">
                <div>向量维度: <span className="text-foreground">{testResult.dimensions}</span></div>
                <div>延迟: <span className="text-foreground">{testResult.latency_ms}ms</span></div>
                {testResult.sample_embedding && (
                  <div className="truncate">
                    示例向量: <span className="text-muted-foreground">[{testResult.sample_embedding.slice(0, 5).map((v) => v.toFixed(4)).join(", ")}...]</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div
          className={`${
            compact ? "pt-3" : "pt-4"
          } border-t border-border border-dashed flex justify-end flex-wrap gap-2`}
        >
          <Button
            onClick={handleSaveAndTest}
            disabled={saving || testing || !canSaveAndTest}
            className="cyber-btn-primary h-10"
            type="button"
          >
            {saving || testing ? (
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
            disabled={testing || saving || !hasChanges}
            variant="ghost"
            className="cyber-btn-ghost h-10"
            type="button"
          >
            <RotateCcw className="w-4 h-4 mr-2" />
            重置
          </Button>
        </div>

        <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
          <DialogContent className="!w-[min(92vw,720px)] !max-w-none p-0 gap-0 cyber-dialog border border-border rounded-lg">
            <DialogHeader className="px-5 py-4 border-b border-border bg-muted">
              <DialogTitle className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
                搜索增强高级配置
              </DialogTitle>
            </DialogHeader>

            <div className="px-5 py-5 space-y-5">
              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">
                  自定义向量维度 <span className="text-muted-foreground">(可选)</span>
                </Label>
                <Input
                  type="number"
                  value={customDimension || ""}
                  onChange={(e) => {
                    setCustomDimension(e.target.value ? parseInt(e.target.value) : null);
                    setHasChanges(true);
                  }}
                  placeholder="留空使用默认值"
                  min={64}
                  max={8192}
                  className="h-10 cyber-input max-w-xs"
                />
                <p className="text-xs text-muted-foreground">
                  适用于 Ollama 等场景：同一模型不同参数规模可能有不同维度
                  <br />
                  例如 qwen3-embedding:0.6b=1024, qwen3-embedding:8b=4096
                </p>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-bold text-muted-foreground uppercase">
                  批处理大小
                </Label>
                <Input
                  type="number"
                  value={batchSize}
                  onChange={(e) => {
                    setBatchSize(parseInt(e.target.value) || 100);
                    setHasChanges(true);
                  }}
                  min={1}
                  max={500}
                  className="h-10 cyber-input max-w-xs"
                />
                <p className="text-xs text-muted-foreground">
                  每批嵌入的文本数量，建议 50-100
                </p>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
