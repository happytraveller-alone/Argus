/**
 * 嵌入模型配置组件
 * Cyberpunk Terminal Aesthetic
 * 独立于 LLM 配置，专门用于 Agent 审计的 RAG 系统
 */

import { useEffect, useRef, useState } from "react";
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
import {
  Cpu,
  Loader2,
  Key,
  Info,
  CheckCircle2,
  AlertCircle,
  PlayCircle,
  Eye,
  EyeOff,
  RotateCcw,
  Save,
  Settings,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/shared/api/serverClient";

interface EmbeddingProvider {
  id: string;
  name: string;
  description: string;
  models: string[];
  requires_api_key: boolean;
  default_model: string;
}

interface EmbeddingConfig {
  provider: string;
  model: string;
  api_key: string | null;
  base_url: string | null;
  dimensions: number;
  batch_size: number;
}

interface TestResult {
  success: boolean;
  message: string;
  dimensions?: number;
  sample_embedding?: number[];
  latency_ms?: number;
}

export default function EmbeddingConfigPanel() {
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

  const handleSave = async () => {
    if (!selectedProvider) {
      toast.error("请选择提供商");
      return;
    }

    const provider = providers.find((p) => p.id === selectedProvider);
    if (!selectedModel) {
      toast.error("请选择或输入模型");
      return;
    }
    if (provider?.requires_api_key && !apiKey.trim()) {
      toast.error(`${provider.name} 需要 API Key`);
      return;
    }

    try {
      setSaving(true);
      await apiClient.put("/embedding/config", {
        provider: selectedProvider,
        model: selectedModel,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
        dimensions: customDimension || undefined,
        batch_size: batchSize,
      });

      toast.success("配置已保存");
      await loadData();
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!selectedProvider) {
      toast.error("请选择提供商");
      return;
    }
    if (!selectedModel) {
      toast.error("请选择或输入模型");
      return;
    }
    const provider = providers.find((p) => p.id === selectedProvider);
    if (provider?.requires_api_key && !apiKey.trim()) {
      toast.error(`${provider.name} 需要 API Key`);
      return;
    }

    try {
      setTesting(true);
      setTestResult(null);

      const response = await apiClient.post("/embedding/test", {
        provider: selectedProvider,
        model: selectedModel,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
        dimension: customDimension || undefined,
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
    } finally {
      setTesting(false);
    }
  };

  const selectedProviderInfo = providers.find((p) => p.id === selectedProvider);
  const requiresApiKey = Boolean(selectedProviderInfo?.requires_api_key);
  const isConfigured = !requiresApiKey || apiKey.trim().length > 0;

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
    <div className="space-y-6">
      {/* 配置表单 */}
      <div className="cyber-card p-6 space-y-6">
        {/* 提供商选择 */}
        <div className="space-y-2">
          <Label className="text-xs font-bold text-muted-foreground uppercase">提供商</Label>
          <Select value={selectedProvider} onValueChange={handleProviderChange}>
            <SelectTrigger className="h-12 cyber-input">
              <SelectValue placeholder="选择提供商" />
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

          {selectedProviderInfo && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Info className="w-3 h-3 text-sky-400" />
              {selectedProviderInfo.description}
            </p>
          )}
        </div>

        {/* API Key */}
        <div className="space-y-2">
          <Label className="text-xs font-bold text-muted-foreground uppercase">
            API Key
            {requiresApiKey ? <span className="text-rose-400 ml-1">*</span> : null}
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
              className="h-12 cyber-input"
              disabled={!requiresApiKey}
            />
            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowApiKey((prev) => !prev)}
              className="h-12 w-12 cyber-btn-ghost"
              disabled={!requiresApiKey}
              type="button"
            >
              {showApiKey ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </Button>
          </div>
          {requiresApiKey ? (
            <p className="text-xs text-muted-foreground">
              API Key 将安全存储，不会显示在页面上
            </p>
          ) : null}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 模型选择/输入 */}
          <div className="space-y-2">
            <Label className="text-xs font-bold text-muted-foreground uppercase">模型选择</Label>
            {selectedProviderInfo ? (
              (() => {
                const models = Array.isArray(selectedProviderInfo.models)
                  ? selectedProviderInfo.models
                  : [];
                const defaultModel = String(selectedProviderInfo.default_model || "").trim();
                const currentModel = String(selectedModel || "").trim();

                if (!models.length) {
                  return (
                    <Input
                      value={selectedModel}
                      onChange={(event) => {
                        setSelectedModel(event.target.value);
                        setHasChanges(true);
                      }}
                      placeholder={defaultModel ? `默认: ${defaultModel}` : "输入模型名称"}
                      className="h-10 cyber-input"
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
                      <SelectTrigger className="h-10 cyber-input">
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
                        className="h-10 cyber-input"
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
                placeholder="请先选择提供商"
                className="h-10 cyber-input"
                disabled
              />
            )}
          </div>

          {/* API 站口 */}
          <div className="space-y-2">
            <Label className="text-xs font-bold text-muted-foreground uppercase">
              API 站口 <span className="text-muted-foreground">(可选)</span>
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
              className="h-10 cyber-input"
            />
            <p className="text-xs text-muted-foreground">用于 API 代理或自托管服务</p>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            className="cyber-btn-ghost h-9"
            onClick={() => setAdvancedOpen((prev) => !prev)}
            type="button"
          >
            <Settings className="w-4 h-4 mr-2" />
            高级配置
          </Button>
        </div>

        {advancedOpen ? (
          <div className="pt-2 border-t border-border border-dashed space-y-6">
            {/* 自定义向量维度 */}
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
                className="h-10 cyber-input w-40"
              />
              <p className="text-xs text-muted-foreground">
                适用于 Ollama 等场景：同一模型不同参数规模可能有不同维度
                <br />
                例如 qwen3-embedding:0.6b=1024, qwen3-embedding:8b=4096
              </p>
            </div>

            {/* 批处理大小 */}
            <div className="space-y-2">
              <Label className="text-xs font-bold text-muted-foreground uppercase">批处理大小</Label>
              <Input
                type="number"
                value={batchSize}
                onChange={(e) => {
                  setBatchSize(parseInt(e.target.value) || 100);
                  setHasChanges(true);
                }}
                min={1}
                max={500}
                className="h-10 cyber-input w-32"
              />
              <p className="text-xs text-muted-foreground">每批嵌入的文本数量，建议 50-100</p>
            </div>
          </div>
        ) : null}

        {/* 测试结果 */}
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

        {/* 操作按钮（对齐 LLM） */}
        <div className="pt-4 border-t border-border border-dashed flex items-center justify-between flex-wrap gap-4">
          <div className="text-sm">
            <span className="font-bold text-foreground">测试连接</span>
            <span className="text-muted-foreground ml-2">验证配置是否正确</span>
          </div>

          <div className="flex items-center gap-2">
            <Button
              onClick={handleTest}
              disabled={testing || !selectedProvider || !selectedModel || !isConfigured}
              className="cyber-btn-primary h-10"
              type="button"
            >
              {testing ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
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
              onClick={handleSave}
              disabled={saving || !hasChanges}
              variant="outline"
              className="cyber-btn-outline h-10"
              type="button"
            >
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              保存
            </Button>

            <Button
              onClick={resetConfig}
              disabled={testing || saving}
              variant="ghost"
              className="cyber-btn-ghost h-10"
              type="button"
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              重置
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
