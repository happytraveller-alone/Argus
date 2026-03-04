import { useCallback, useEffect, useMemo, useState } from "react";
import { Info } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/shared/api/database";
import {
  SKILL_TOOLS_CATALOG,
  SKILL_TOOL_CATEGORY_ORDER,
  type SkillToolCategory,
  buildSkillToolPrompt,
} from "./skillToolsCatalog";
import {
  DEFAULT_MCP_CATALOG,
  normalizeMcpCatalog,
  type McpCatalogItem,
} from "./mcpCatalog";

const CATEGORY_DESC: Partial<Record<SkillToolCategory, string>> = {
  "模型基础增强类": "用于提供模型基础能力增强模板，包括 MCP/Skill 设计、文件规划与策略协作。",
  "代码读取与定位": "用于读取代码、检索关键位置、提取函数上下文，形成后续分析证据链起点。",
  "候选发现与模式扫描": "用于快速拉取候选风险点，缩小审计范围并为验证阶段提供高优先级线索。",
  "可达性与逻辑分析": "用于验证漏洞链路是否真实可达，识别控制条件、授权边界与业务约束。",
  "报告与协作编排": "用于审计过程编排、结论沉淀与最终报告输出，保障任务可交付性。",
  "漏洞验证与 PoC 规划": "用于非武器化漏洞验证，收集可复现实验信号与证明链。",
};

const MCP_ERROR_TEXT: Record<string, string> = {
  missing_endpoint: "未配置 MCP 端点 URL",
  invalid_endpoint: "MCP 端点 URL 非法（需 http/https）",
  disabled: "已禁用",
  command_not_found: "命令不存在或不可执行",
  missing_command: "未配置启动命令",
  adapter_unavailable: "适配器不可用",
};

const MCP_NAME_MAP: Record<string, string> = {
  filesystem: "Filesystem MCP",
  code_index: "Code Index MCP",
  sequentialthinking: "Sequential Thinking MCP",
};

function toMcpName(mcpId?: string): string {
  const normalized = String(mcpId || "").trim().toLowerCase();
  return MCP_NAME_MAP[normalized] || normalized || "MCP";
}

function formatMcpErrorToken(rawToken: string, mcpId?: string): string {
  const token = String(rawToken || "").trim();
  if (!token) return "";

  if (token.startsWith("mcp_adapter_unavailable:")) {
    const unavailableMcpId = token.split(":", 2)[1];
    return `${toMcpName(unavailableMcpId || mcpId)} 适配器不可用`;
  }

  if (token === "mcp_adapter_unavailable") {
    return `${toMcpName(mcpId)} 适配器不可用`;
  }

  if (token.startsWith("healthcheck_failed:")) {
    const detail = token.slice("healthcheck_failed:".length);
    if (!detail) return "健康检查失败";
    const [reason] = detail.split("@", 2);
    return `健康检查失败（${reason}）`;
  }

  if (token.startsWith("tools_list_failed:")) {
    return "tools/list 调用异常";
  }

  if (token.startsWith("mcp_list_tools_failed:")) {
    return "tools/list 调用失败";
  }

  if (MCP_ERROR_TEXT[token]) {
    return MCP_ERROR_TEXT[token];
  }

  const [prefix, ...rest] = token.split(":");
  if (prefix && MCP_ERROR_TEXT[prefix]) {
    if (!rest.length) return MCP_ERROR_TEXT[prefix];
    return `${MCP_ERROR_TEXT[prefix]}（${rest.join(":")}）`;
  }

  return token;
}

function formatMcpErrorMessage(errorValue?: string | null, mcpId?: string): string {
  const parts = String(errorValue || "")
    .split(";")
    .map((part) => formatMcpErrorToken(part, mcpId))
    .filter((part) => part.length > 0);
  return parts.join("；");
}

function getErrorDetail(error: unknown, fallback: string): string {
  if (error && typeof error === "object") {
    const err = error as {
      response?: {
        data?: {
          detail?: unknown;
        };
      };
      message?: unknown;
    };
    if (typeof err.response?.data?.detail === "string" && err.response.data.detail.trim()) {
      return err.response.data.detail;
    }
    if (typeof err.message === "string" && err.message.trim()) {
      return err.message;
    }
  }
  return fallback;
}

type SkillToolsPanelMode = "all" | "skill" | "mcp";

type SkillAvailabilityMap = Record<
  string,
  {
    enabled?: boolean;
    reason?: string;
  }
>;

type McpVerifyResult = {
  success: boolean;
  mcp_id: string;
  checks: Array<{
    step: string;
    action: "tools/list" | "tools/call" | "policy/skip" | string;
    success: boolean;
    tool?: string | null;
    runtime_domain?: string | null;
    duration_ms: number;
    error?: string | null;
  }>;
  verification_tools: string[];
  discovered_tools?: Array<{
    name: string;
    description?: string;
    inputSchema?: Record<string, unknown>;
  }>;
  protocol_summary?: {
    list_tools_success?: boolean;
    discovered_count?: number;
    called_count?: number;
    call_success_count?: number;
    call_failed_count?: number;
    arg_failed_count?: number;
    skipped_unsupported_count?: number;
    required_gate?: string[];
    [key: string]: unknown;
  };
  project_context?: {
    project_name?: string;
    fallback_used?: boolean;
  };
};

type McpToolItem = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
};

type SkillCategorySummary = {
  category: SkillToolCategory;
  count: number;
  description: string;
};

type McpSummaryItem = {
  id: string;
  name: string;
  enabled: boolean;
  required: boolean;
  startupReady: boolean;
  toolCount: number | null;
  executionFunctions: string[];
};

export default function SkillToolsPanel({
  mode = "all",
}: {
  mode?: SkillToolsPanelMode;
}) {
  const [mcpCatalog, setMcpCatalog] = useState<McpCatalogItem[]>(
    DEFAULT_MCP_CATALOG,
  );
  const [skillAvailability, setSkillAvailability] =
    useState<SkillAvailabilityMap>({});
  const [mcpCatalogLoading, setMcpCatalogLoading] = useState(false);
  const [mcpCatalogFallbackNotice, setMcpCatalogFallbackNotice] = useState<
    string | null
  >(null);
  const [verifyingMcpId, setVerifyingMcpId] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<
    Record<string, McpVerifyResult>
  >({});
  const [verifyErrors, setVerifyErrors] = useState<Record<string, string>>({});
  const [mcpToolsById, setMcpToolsById] = useState<
    Record<string, McpToolItem[]>
  >({});
  const [mcpToolsLoading, setMcpToolsLoading] = useState<
    Record<string, boolean>
  >({});
  const [mcpToolsErrors, setMcpToolsErrors] = useState<Record<string, string>>(
    {},
  );
  const [mcpToolCountById, setMcpToolCountById] = useState<
    Record<string, number | null>
  >({});

  const showSkillCatalog = mode === "all" || mode === "skill";
  const showMcpCatalog = mode === "all" || mode === "mcp";

  const visibleSkillTools = useMemo(
    () =>
      SKILL_TOOLS_CATALOG.filter((item) => {
        const runtimeState = skillAvailability[item.id];
        if (!runtimeState) return true;
        return runtimeState.enabled !== false;
      }),
    [skillAvailability],
  );

  const groupedTools = useMemo(() => {
    const grouped = new Map<SkillToolCategory, typeof SKILL_TOOLS_CATALOG>();
    for (const category of SKILL_TOOL_CATEGORY_ORDER) {
      grouped.set(
        category,
        visibleSkillTools.filter((item) => item.category === category),
      );
    }
    return grouped;
  }, [visibleSkillTools]);

  const skillCategorySummary = useMemo<SkillCategorySummary[]>(
    () =>
      SKILL_TOOL_CATEGORY_ORDER.map((category) => ({
        category,
        count: groupedTools.get(category)?.length ?? 0,
        description:
          CATEGORY_DESC[category] || "该分类用于智能审计流程中的关键步骤。",
      })),
    [groupedTools],
  );

  const visibleSkillToolsCount = visibleSkillTools.length;

  useEffect(() => {
    if (!showSkillCatalog && !showMcpCatalog) {
      return;
    }

    let mounted = true;
    const loadRuntimeCatalog = async () => {
      if (showMcpCatalog) {
        setMcpCatalogLoading(true);
      }
      try {
        const config = await api.getUserConfig();
        if (!mounted) return;

        const runtimeSkillAvailability =
          config?.otherConfig?.mcpConfig?.skillAvailability;
        if (
          runtimeSkillAvailability &&
          typeof runtimeSkillAvailability === "object"
        ) {
          setSkillAvailability(runtimeSkillAvailability as SkillAvailabilityMap);
        } else {
          setSkillAvailability({});
        }

        if (showMcpCatalog) {
          const serverCatalog = config?.otherConfig?.mcpConfig?.catalog;
          if (Array.isArray(serverCatalog) && serverCatalog.length > 0) {
            setMcpCatalog(normalizeMcpCatalog(serverCatalog));
            setMcpCatalogFallbackNotice(null);
          } else {
            setMcpCatalog(DEFAULT_MCP_CATALOG);
            setMcpCatalogFallbackNotice(
              "后端未返回 MCP 目录，当前展示默认目录（非实时状态）。",
            );
          }
        }
      } catch {
        if (!mounted) return;
        setSkillAvailability({});
        if (showMcpCatalog) {
          setMcpCatalog(DEFAULT_MCP_CATALOG);
          setMcpCatalogFallbackNotice(
            "MCP 目录加载失败，当前展示默认目录（非实时状态）。",
          );
        }
      } finally {
        if (mounted && showMcpCatalog) {
          setMcpCatalogLoading(false);
        }
      }
    };

    void loadRuntimeCatalog();
    return () => {
      mounted = false;
    };
  }, [showMcpCatalog, showSkillCatalog]);

  const mcpServers = useMemo(
    () => mcpCatalog.filter((item) => item.type === "mcp-server"),
    [mcpCatalog],
  );

  const mcpServerCount = mcpServers.length;

  const requiredNotReadyMcps = useMemo(
    () =>
      mcpServers.filter(
        (item) =>
          item.required !== false && item.enabled && item.startup_ready === false,
      ),
    [mcpServers],
  );

  const hasRequiredMcpNotReady = requiredNotReadyMcps.length > 0;

  const hasOptionalMcpNotReady = useMemo(
    () =>
      mcpServers.some(
        (item) =>
          item.required === false && item.enabled && item.startup_ready === false,
      ),
    [mcpServers],
  );

  const loadMcpTools = useCallback(
    async (mcpIds?: string[]) => {
      const targetIds =
        Array.isArray(mcpIds) && mcpIds.length
          ? mcpIds
          : mcpServers.map((item) => item.id);
      const normalizedIds = [
        ...new Set(
          targetIds
            .map((item) => String(item || "").trim())
            .filter((item) => item.length > 0),
        ),
      ];
      if (!normalizedIds.length) return;

      setMcpToolsLoading((prev) => {
        const next = { ...prev };
        for (const mcpId of normalizedIds) {
          next[mcpId] = true;
        }
        return next;
      });

      setMcpToolsErrors((prev) => {
        const next = { ...prev };
        for (const mcpId of normalizedIds) {
          next[mcpId] = "";
        }
        return next;
      });

      try {
        const response = await api.listMcpTools({
          mcp_ids: normalizedIds,
          include_internal: false,
        });

        const resultMap = new Map(
          (response?.results || []).map((item) => [item.mcp_id, item]),
        );

        setMcpToolsById((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            const item = resultMap.get(mcpId);
            if (item?.success) {
              next[mcpId] = Array.isArray(item.tools)
                ? item.tools.map((tool) => ({
                    name: String(tool?.name || ""),
                    description: String(tool?.description || ""),
                    inputSchema:
                      tool?.inputSchema &&
                      typeof tool.inputSchema === "object" &&
                      !Array.isArray(tool.inputSchema)
                        ? (tool.inputSchema as Record<string, unknown>)
                        : {},
                  }))
                : [];
            } else {
              next[mcpId] = [];
            }
          }
          return next;
        });

        setMcpToolCountById((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            const item = resultMap.get(mcpId);
            if (item?.success) {
              const visibleCount = Number.isFinite(item.visible_count)
                ? Math.max(Number(item.visible_count), 0)
                : Array.isArray(item.tools)
                  ? item.tools.length
                  : 0;
              next[mcpId] = visibleCount;
            } else {
              next[mcpId] = null;
            }
          }
          return next;
        });

        setMcpToolsErrors((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            const item = resultMap.get(mcpId);
            if (item?.success) {
              next[mcpId] = "";
            } else {
              next[mcpId] = String(item?.error || "工具列表拉取失败");
            }
          }
          return next;
        });
      } catch (error: unknown) {
        const detail = getErrorDetail(error, "工具列表拉取失败");

        setMcpToolsErrors((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            next[mcpId] = String(detail);
          }
          return next;
        });

        setMcpToolCountById((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            next[mcpId] = null;
          }
          return next;
        });
      } finally {
        setMcpToolsLoading((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            next[mcpId] = false;
          }
          return next;
        });
      }
    },
    [mcpServers],
  );

  useEffect(() => {
    if (!showMcpCatalog || mcpCatalogLoading || !mcpServers.length) {
      return;
    }
    void loadMcpTools(mcpServers.map((item) => item.id));
  }, [loadMcpTools, mcpCatalogLoading, mcpServers, showMcpCatalog]);

  const mcpSummaryItems = useMemo<McpSummaryItem[]>(
    () =>
      mcpServers.map((item) => ({
        id: item.id,
        name: item.name,
        enabled: Boolean(item.enabled),
        required: item.required !== false,
        startupReady: item.startup_ready !== false,
        toolCount:
          typeof mcpToolCountById[item.id] === "number"
            ? mcpToolCountById[item.id]
            : null,
        executionFunctions: Array.isArray(item.executionFunctions)
          ? item.executionFunctions
          : [],
      })),
    [mcpServers, mcpToolCountById],
  );

  const totalVisibleToolCount = useMemo(
    () =>
      mcpSummaryItems.reduce(
        (sum, item) => sum + (typeof item.toolCount === "number" ? item.toolCount : 0),
        0,
      ),
    [mcpSummaryItems],
  );

  const hasUnknownToolCount = useMemo(
    () =>
      mcpSummaryItems.some(
        (item) => item.enabled && item.toolCount === null && !mcpToolsLoading[item.id],
      ),
    [mcpSummaryItems, mcpToolsLoading],
  );

  const mcpCapabilityOverview = useMemo(() => {
    const capabilities = Array.from(
      new Set(
        mcpServers.flatMap((item) =>
          Array.isArray(item.executionFunctions)
            ? item.executionFunctions.filter((fn) => fn.trim().length > 0)
            : [],
        ),
      ),
    );
    return {
      preview: capabilities.slice(0, 10),
      overflow: Math.max(capabilities.length - 10, 0),
    };
  }, [mcpServers]);

  const handleVerifyMcp = async (mcpId: string) => {
    setVerifyingMcpId(mcpId);
    setVerifyErrors((prev) => ({ ...prev, [mcpId]: "" }));
    try {
      const result = await api.verifyMcp(mcpId);
      setVerifyResults((prev) => ({ ...prev, [mcpId]: result }));
      if (result?.success) {
        void loadMcpTools([mcpId]);
      }
    } catch (error: unknown) {
      const detail = getErrorDetail(error, "MCP 验证失败，请检查后端日志。");
      setVerifyErrors((prev) => ({ ...prev, [mcpId]: String(detail) }));
    } finally {
      setVerifyingMcpId(null);
    }
  };

  return (
    <div className="space-y-6">
      {showMcpCatalog ? (
        <Card className="cyber-card p-5 gap-3">
          <CardHeader className="border-b border-border pb-3">
            <CardTitle className="text-base">智能审计 MCP 目录（摘要）</CardTitle>
          </CardHeader>
          <CardContent className="pt-3 space-y-4">
            <p className="text-sm text-muted-foreground leading-relaxed">
              仅展示 MCP 数量、工具数量与可执行功能摘要。运行时策略由后端默认配置统一托管。
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-xs">
                MCP 数量 {mcpServerCount}
              </Badge>
              <Badge variant="outline" className="text-xs">
                工具总数 {totalVisibleToolCount}
                {hasUnknownToolCount ? "+" : ""}
              </Badge>
              {mcpCatalogLoading ? (
                <Badge variant="secondary" className="text-xs">
                  目录加载中
                </Badge>
              ) : null}
              {hasUnknownToolCount ? (
                <Badge
                  variant="outline"
                  className="text-xs border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10"
                >
                  部分 MCP 工具数未知
                </Badge>
              ) : null}
              {hasRequiredMcpNotReady ? (
                <Badge
                  variant="outline"
                  className="text-xs border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
                >
                  required MCP 未就绪，任务不可启动
                </Badge>
              ) : hasOptionalMcpNotReady ? (
                <Badge
                  variant="outline"
                  className="text-xs border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10"
                >
                  required MCP 已就绪，optional MCP 存在异常（不阻断）
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="text-xs border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                >
                  required MCP 已就绪，任务可启动
                </Badge>
              )}
            </div>

            <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
              <div className="text-xs font-mono uppercase text-muted-foreground">
                可执行功能概述
              </div>
              <div className="flex flex-wrap gap-1.5">
                {mcpCapabilityOverview.preview.map((capability) => (
                  <Badge key={capability} variant="secondary" className="text-[10px]">
                    {capability}
                  </Badge>
                ))}
                {mcpCapabilityOverview.overflow > 0 ? (
                  <Badge variant="outline" className="text-[10px]">
                    +{mcpCapabilityOverview.overflow}
                  </Badge>
                ) : null}
              </div>
            </div>

            {mcpCatalogFallbackNotice ? (
              <div className="text-xs text-amber-700 dark:text-amber-300">
                {mcpCatalogFallbackNotice}
              </div>
            ) : null}

            {hasRequiredMcpNotReady ? (
              <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs space-y-1">
                <div className="text-rose-700 dark:text-rose-300">
                  未就绪 required MCP: {requiredNotReadyMcps.map((item) => item.id).join(", ")}
                </div>
                {requiredNotReadyMcps.map((item) => (
                  <div
                    key={`required-error-${item.id}`}
                    className="text-rose-700/90 dark:text-rose-200/90 break-words"
                  >
                    {item.id}: {formatMcpErrorMessage(item.startup_error, item.id) || "启动未就绪"}
                  </div>
                ))}
              </div>
            ) : null}

            <Accordion type="multiple" className="w-full rounded-md border border-border bg-card/70 px-3">
              {mcpSummaryItems.map((item) => {
                const mcpData = mcpServers.find((server) => server.id === item.id);
                if (!mcpData) return null;

                return (
                  <AccordionItem key={item.id} value={item.id} className="border-border">
                    <AccordionTrigger className="py-3 text-sm hover:no-underline">
                      <div className="flex-1 min-w-0 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <code className="font-mono text-sm text-foreground">{item.id}</code>
                          <span className="text-sm text-foreground">{item.name}</span>
                          <Badge variant="outline" className="text-[10px] uppercase">
                            {item.required ? "required" : "optional"}
                          </Badge>
                          <Badge
                            variant="outline"
                            className={`text-[10px] uppercase ${
                              item.enabled
                                ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                                : "border-zinc-500/40 text-zinc-600 dark:text-zinc-300 bg-zinc-500/10"
                            }`}
                          >
                            {item.enabled ? "enabled" : "disabled"}
                          </Badge>
                          {item.enabled ? (
                            <Badge
                              variant="outline"
                              className={`text-[10px] uppercase ${
                                item.startupReady
                                  ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                                  : item.required
                                    ? "border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
                                    : "border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10"
                              }`}
                            >
                              {item.startupReady
                                ? "startup ready"
                                : item.required
                                  ? "required error"
                                  : "optional warning"}
                            </Badge>
                          ) : null}
                          {mcpToolsLoading[item.id] ? (
                            <Badge variant="secondary" className="text-[10px] uppercase">
                              工具数加载中
                            </Badge>
                          ) : typeof item.toolCount === "number" ? (
                            <Badge variant="outline" className="text-[10px] uppercase">
                              工具 {item.toolCount}
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="text-[10px] uppercase border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10"
                            >
                              工具数未知
                            </Badge>
                          )}
                        </div>

                        <div className="flex flex-wrap gap-1.5">
                          {item.executionFunctions.slice(0, 5).map((fn) => (
                            <Badge key={fn} variant="secondary" className="text-[10px]">
                              {fn}
                            </Badge>
                          ))}
                          {item.executionFunctions.length > 5 ? (
                            <Badge variant="outline" className="text-[10px]">
                              +{item.executionFunctions.length - 5}
                            </Badge>
                          ) : null}
                        </div>
                      </div>
                    </AccordionTrigger>

                    <AccordionContent className="space-y-3">
                      <div className="rounded-md border border-border bg-muted/20 p-3 space-y-1">
                        <div className="text-sm text-muted-foreground leading-relaxed">
                          {mcpData.description}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          runtime_mode: {mcpData.runtime_mode || "n/a"}
                        </div>
                        <div
                          className={`text-xs ${
                            mcpData.startup_ready === false
                              ? "text-rose-600 dark:text-rose-300"
                              : "text-emerald-600 dark:text-emerald-300"
                          }`}
                        >
                          启动诊断：
                          {mcpData.startup_ready === false
                            ? formatMcpErrorMessage(mcpData.startup_error, mcpData.id) || "启动未就绪"
                            : "启动正常"}
                        </div>
                        {mcpToolsErrors[mcpData.id] && !mcpToolsLoading[mcpData.id] ? (
                          <div className="text-xs text-amber-700 dark:text-amber-300 break-words">
                            工具列表诊断：
                            {formatMcpErrorMessage(mcpToolsErrors[mcpData.id], mcpData.id) || "工具列表拉取失败"}
                          </div>
                        ) : null}
                      </div>

                      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs font-mono uppercase text-muted-foreground">
                            可用工具明细
                          </div>
                          {mcpToolsLoading[mcpData.id] ? (
                            <Badge variant="outline" className="text-[10px] uppercase">
                              工具列表加载中
                            </Badge>
                          ) : null}
                        </div>

                        {mcpToolsLoading[mcpData.id] ? (
                          <div className="text-xs text-muted-foreground">工具列表加载中</div>
                        ) : mcpToolsErrors[mcpData.id] ? (
                          <div className="space-y-2">
                            <div className="text-xs text-rose-600 dark:text-rose-300 break-words">
                              工具列表拉取失败：
                              {formatMcpErrorMessage(mcpToolsErrors[mcpData.id], mcpData.id) || "工具列表拉取失败"}
                            </div>
                            <div className="text-xs text-muted-foreground break-words">
                              原始错误: {mcpToolsErrors[mcpData.id]}
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => void loadMcpTools([mcpData.id])}
                            >
                              重试加载
                            </Button>
                          </div>
                        ) : (mcpToolsById[mcpData.id] || []).length ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {(mcpToolsById[mcpData.id] || []).map((tool) => (
                              <div
                                key={`${mcpData.id}-tool-${tool.name}`}
                                className="rounded border border-border bg-muted/20 p-2 space-y-2 min-h-[84px]"
                              >
                                <div className="flex items-center gap-1.5">
                                  <code className="text-xs font-mono text-foreground">{tool.name}</code>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <button
                                        type="button"
                                        className="inline-flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                                        aria-label="查看工具说明"
                                      >
                                        <Info className="h-3.5 w-3.5" />
                                      </button>
                                    </TooltipTrigger>
                                    <TooltipContent
                                      side="top"
                                      sideOffset={6}
                                      className="max-w-xs px-3 py-2 text-xs leading-relaxed"
                                    >
                                      {tool.description || "暂无工具说明"}
                                    </TooltipContent>
                                  </Tooltip>
                                </div>
                                <details className="rounded border border-border bg-card/70 p-2">
                                  <summary className="cursor-pointer list-none text-xs text-primary">
                                    查看 Input Schema
                                  </summary>
                                  <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words rounded border border-border bg-muted/30 p-2 font-mono leading-relaxed">
                                    {JSON.stringify(tool.inputSchema || {}, null, 2)}
                                  </pre>
                                </details>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-muted-foreground">暂无可用 Tool</div>
                        )}

                        <div className="text-xs text-muted-foreground break-all">
                          Source: {mcpData.source}
                        </div>
                      </div>

                      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs font-mono uppercase text-muted-foreground">
                            执行验证
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={verifyingMcpId === mcpData.id}
                            onClick={() => void handleVerifyMcp(mcpData.id)}
                          >
                            {verifyingMcpId === mcpData.id ? "验证中..." : "执行验证"}
                          </Button>
                        </div>

                        {verifyErrors[mcpData.id] ? (
                          <div className="text-xs text-rose-600 dark:text-rose-300 break-words">
                            {verifyErrors[mcpData.id]}
                          </div>
                        ) : null}

                        {verifyResults[mcpData.id] ? (
                          <div className="space-y-2 text-xs">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge
                                variant="outline"
                                className={
                                  verifyResults[mcpData.id].success
                                    ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                                    : "border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
                                }
                              >
                                {verifyResults[mcpData.id].success ? "验证通过" : "验证失败"}
                              </Badge>
                              {verifyResults[mcpData.id].project_context?.project_name ? (
                                <span className="text-muted-foreground">
                                  项目: {verifyResults[mcpData.id].project_context?.project_name}
                                  {verifyResults[mcpData.id].project_context?.fallback_used
                                    ? "（fallback）"
                                    : ""}
                                </span>
                              ) : null}
                              {typeof verifyResults[mcpData.id].protocol_summary?.skipped_unsupported_count ===
                                "number" &&
                              verifyResults[mcpData.id].protocol_summary?.skipped_unsupported_count ? (
                                <Badge
                                  variant="outline"
                                  className="text-[10px] border-zinc-500/40 text-zinc-600 dark:text-zinc-300 bg-zinc-500/10"
                                >
                                  skip {verifyResults[mcpData.id].protocol_summary?.skipped_unsupported_count}
                                </Badge>
                              ) : null}
                            </div>

                            {verifyResults[mcpData.id].protocol_summary?.required_gate?.length ? (
                              <div className="text-muted-foreground">
                                required_gate: {verifyResults[mcpData.id].protocol_summary?.required_gate?.join(", ")}
                              </div>
                            ) : null}

                            <div className="space-y-1">
                              {verifyResults[mcpData.id].checks.map((check) => (
                                <div
                                  key={`${mcpData.id}-${check.step}`}
                                  className="rounded border border-border px-2 py-1"
                                >
                                  <span
                                    className={
                                      check.action === "policy/skip"
                                        ? "text-zinc-600 dark:text-zinc-300"
                                        : check.success
                                          ? "text-emerald-600 dark:text-emerald-300"
                                          : "text-rose-600 dark:text-rose-300"
                                    }
                                  >
                                    {check.action === "policy/skip" ? "○" : check.success ? "✓" : "✗"}
                                  </span>{" "}
                                  {check.step}
                                  {check.tool ? ` · ${check.tool}` : ""}
                                  {check.runtime_domain ? ` · ${check.runtime_domain}` : ""}
                                  {` · ${check.duration_ms}ms`}
                                  {check.error ? ` · ${check.error}` : ""}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
            </Accordion>
          </CardContent>
        </Card>
      ) : null}

      {showSkillCatalog ? (
        <>
          <Card className="cyber-card p-5 gap-3">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="text-base">智能审计 SKILL 目录（摘要）</CardTitle>
            </CardHeader>
            <CardContent className="pt-3 space-y-3">
              <p className="text-sm text-muted-foreground leading-relaxed">
                首屏仅展示 SKILL 总数与能力域分布。展开后可查看每个 SKILL 的用途与高级详情。
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  SKILL 总数 {visibleSkillToolsCount}
                </Badge>
                {skillCategorySummary
                  .filter((item) => item.count > 0)
                  .map((item) => (
                    <Badge key={`summary-${item.category}`} variant="secondary" className="text-[10px]">
                      {item.category} {item.count}
                    </Badge>
                  ))}
              </div>
            </CardContent>
          </Card>

          <Accordion type="multiple" className="w-full rounded-md border border-border bg-card/70 px-3">
            {skillCategorySummary
              .filter((item) => item.count > 0)
              .map((summaryItem) => {
                const tools = groupedTools.get(summaryItem.category) ?? [];
                return (
                  <AccordionItem key={summaryItem.category} value={summaryItem.category} className="border-border">
                    <AccordionTrigger className="py-3 text-sm hover:no-underline">
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm font-bold uppercase text-foreground">
                            {summaryItem.category}
                          </span>
                          <Badge variant="outline" className="text-[10px] uppercase">
                            {summaryItem.count} 个 SKILL
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {summaryItem.description}
                        </p>
                      </div>
                    </AccordionTrigger>

                    <AccordionContent className="space-y-3">
                      <div className="grid grid-cols-1 gap-3">
                        {tools.map((tool) => (
                          <Card key={tool.id} className="cyber-card p-4 gap-3">
                            <CardHeader className="pb-2 border-b border-border">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <code className="font-mono text-sm text-foreground">{tool.id}</code>
                                <Badge variant="outline" className="text-[10px] uppercase">
                                  skill tool
                                </Badge>
                              </div>
                              <p className="text-sm text-muted-foreground leading-relaxed">
                                {tool.summary}
                              </p>
                            </CardHeader>

                            <CardContent className="space-y-3 pt-1">
                              <div className="rounded-md border border-border bg-muted/30 p-3">
                                <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                  使用目标
                                </div>
                                <div className="text-sm text-foreground">{tool.goal}</div>
                              </div>

                              <details className="rounded-md border border-border bg-card/70 p-3">
                                <summary className="cursor-pointer list-none font-mono text-xs uppercase text-primary">
                                  高级详情（Prompt / 参数 / 误用）
                                </summary>
                                <div className="mt-3 space-y-3">
                                  <div>
                                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                      任务清单
                                    </div>
                                    <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                                      {tool.taskList.map((task) => (
                                        <li key={task}>{task}</li>
                                      ))}
                                    </ul>
                                  </div>

                                  <div>
                                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                      Prompt 模板
                                    </div>
                                    <pre className="text-xs whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono leading-relaxed">
                                      {buildSkillToolPrompt(tool)}
                                    </pre>
                                  </div>

                                  <div>
                                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                      示例输入
                                    </div>
                                    <pre className="text-xs whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono leading-relaxed">
                                      {tool.exampleInput}
                                    </pre>
                                  </div>

                                  <div>
                                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                      参数清单
                                    </div>
                                    <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                                      {tool.inputChecklist.map((input) => (
                                        <li key={input}>{input}</li>
                                      ))}
                                    </ul>
                                  </div>

                                  <div>
                                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                                      误用提示
                                    </div>
                                    <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                                      {tool.pitfalls.map((pitfall) => (
                                        <li key={pitfall}>{pitfall}</li>
                                      ))}
                                    </ul>
                                  </div>
                                </div>
                              </details>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
          </Accordion>
        </>
      ) : null}
    </div>
  );
}
