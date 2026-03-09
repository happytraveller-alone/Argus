import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Info, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/shared/api/database";
import { SKILL_TOOLS_CATALOG } from "./skillToolsCatalog";
import {
  DEFAULT_MCP_CATALOG,
  normalizeMcpCatalog,
  type McpCatalogItem,
} from "./mcpCatalog";
import {
  buildExternalToolDetailSections,
  buildExternalToolRows,
  type ExternalToolDetailSection,
  type ExternalToolRow,
  type McpToolItem,
  type McpVerifyResult,
  type SkillAvailabilityMap,
} from "./externalToolsViewModel";

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

function toObjectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function renderCapabilityBadges(capabilities: string[]) {
  const preview = capabilities.slice(0, 3);
  const overflow = capabilities.length - preview.length;

  return (
    <div className="flex flex-wrap gap-1.5">
      {preview.map((capability) => (
        <Badge key={capability} variant="secondary" className="text-[10px]">
          {capability}
        </Badge>
      ))}
      {overflow > 0 ? (
        <Badge variant="outline" className="text-[10px]">
          +{overflow}
        </Badge>
      ) : null}
      {capabilities.length === 0 ? (
        <span className="text-xs text-muted-foreground">-</span>
      ) : null}
    </div>
  );
}

function renderDetailSection(
  section: ExternalToolDetailSection,
  params: {
    selectedRow: ExternalToolRow;
    verifyingMcpId: string | null;
    onVerifyMcp: (mcpId: string) => void;
  },
) {
  if (section.kind === "properties") {
    return (
      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
        <div className="text-xs font-mono uppercase text-muted-foreground">{section.title}</div>
        <div className="space-y-2">
          {section.properties.map((item) => (
            <div key={`${section.title}-${item.label}`} className="space-y-1">
              <div className="text-xs font-semibold uppercase text-muted-foreground">{item.label}</div>
              <div className="text-sm text-foreground break-words leading-relaxed">{item.value || "-"}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (section.kind === "list") {
    return (
      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
        <div className="text-xs font-mono uppercase text-muted-foreground">{section.title}</div>
        {section.items.length ? (
          <ul className="space-y-1 text-sm text-foreground list-disc pl-4">
            {section.items.map((item) => (
              <li key={`${section.title}-${item}`} className="break-words">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-muted-foreground">暂无内容</div>
        )}
      </div>
    );
  }

  if (section.kind === "code") {
    return (
      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
        <div className="text-xs font-mono uppercase text-muted-foreground">{section.title}</div>
        <pre className="text-xs whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono leading-relaxed">
          {section.code || "-"}
        </pre>
      </div>
    );
  }

  if (section.kind === "mcp-tools") {
    return (
      <div className="rounded-md border border-border bg-card/70 p-3 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs font-mono uppercase text-muted-foreground">{section.title}</div>
          <Badge variant="outline" className="text-[10px] uppercase">
            工具 {section.tools.length}
          </Badge>
        </div>
        {section.error ? (
          <div className="text-xs text-amber-700 dark:text-amber-300 break-words">
            工具列表诊断：{section.error}
          </div>
        ) : null}
        {section.tools.length ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {section.tools.map((tool) => (
              <div
                key={`${params.selectedRow.id}-${tool.name}`}
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
          <div className="text-sm text-muted-foreground">暂无可用 Tool</div>
        )}
      </div>
    );
  }

  const verifyResult = section.result;
  const protocolSummary = verifyResult?.protocol_summary;

  return (
    <div className="rounded-md border border-border bg-card/70 p-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-mono uppercase text-muted-foreground">{section.title}</div>
        {params.selectedRow.type === "mcp" ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="cyber-btn-ghost h-8 px-3"
            disabled={params.verifyingMcpId === params.selectedRow.id}
            onClick={() => params.onVerifyMcp(params.selectedRow.id)}
          >
            {params.verifyingMcpId === params.selectedRow.id ? "验证中..." : "执行验证"}
          </Button>
        ) : null}
      </div>

      {section.error ? (
        <div className="text-xs text-rose-600 dark:text-rose-300 break-words">{section.error}</div>
      ) : null}

      {verifyResult ? (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className={`text-[10px] uppercase ${
                verifyResult.success
                  ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                  : "border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
              }`}
            >
              {verifyResult.success ? "验证通过" : "验证失败"}
            </Badge>
            {typeof protocolSummary?.called_count === "number" ? (
              <Badge variant="outline" className="text-[10px] uppercase">
                调用 {protocolSummary.called_count}
              </Badge>
            ) : null}
            {typeof protocolSummary?.call_success_count === "number" ? (
              <Badge variant="outline" className="text-[10px] uppercase">
                成功 {protocolSummary.call_success_count}
              </Badge>
            ) : null}
          </div>

          {Array.isArray(verifyResult.checks) && verifyResult.checks.length ? (
            <div className="space-y-2">
              {verifyResult.checks.map((check, index) => (
                <div
                  key={`${verifyResult.mcp_id}-${check.step}-${index}`}
                  className="rounded border border-border bg-muted/20 p-2 space-y-1"
                >
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-medium text-foreground">{check.step}</span>
                    <Badge variant="outline" className="text-[10px] uppercase">
                      {check.action}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={`text-[10px] uppercase ${
                        check.success
                          ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                          : "border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
                      }`}
                    >
                      {check.success ? "success" : "failed"}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground break-words">
                    {check.tool ? `tool: ${check.tool}` : "tool: -"}
                    {typeof check.duration_ms === "number" ? ` · ${check.duration_ms}ms` : ""}
                    {check.runtime_domain ? ` · domain: ${check.runtime_domain}` : ""}
                  </div>
                  {check.error ? (
                    <div className="text-xs text-rose-600 dark:text-rose-300 break-words">
                      {check.error}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">暂无验证结果</div>
          )}
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">尚未执行验证</div>
      )}
    </div>
  );
}

export default function SkillToolsPanel() {
  const [mcpCatalog, setMcpCatalog] = useState<McpCatalogItem[]>(DEFAULT_MCP_CATALOG);
  const [skillAvailability, setSkillAvailability] = useState<SkillAvailabilityMap>({});
  const [mcpCatalogLoading, setMcpCatalogLoading] = useState(false);
  const [mcpCatalogFallbackNotice, setMcpCatalogFallbackNotice] = useState<string | null>(null);
  const [verifyingMcpId, setVerifyingMcpId] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, McpVerifyResult>>({});
  const [verifyErrors, setVerifyErrors] = useState<Record<string, string>>({});
  const [mcpToolsById, setMcpToolsById] = useState<Record<string, McpToolItem[]>>({});
  const [mcpToolsLoading, setMcpToolsLoading] = useState<Record<string, boolean>>({});
  const [mcpToolsErrors, setMcpToolsErrors] = useState<Record<string, string>>({});
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    const loadRuntimeCatalog = async () => {
      setMcpCatalogLoading(true);
      try {
        const config = await api.getUserConfig();
        if (!mounted) return;

        const otherConfig = toObjectRecord(config?.otherConfig);
        const mcpConfig = toObjectRecord(otherConfig.mcpConfig);
        const runtimeSkillAvailability = mcpConfig.skillAvailability;
        if (runtimeSkillAvailability && typeof runtimeSkillAvailability === "object") {
          setSkillAvailability(runtimeSkillAvailability as SkillAvailabilityMap);
        } else {
          setSkillAvailability({});
        }

        const serverCatalog = mcpConfig.catalog;
        if (Array.isArray(serverCatalog) && serverCatalog.length > 0) {
          setMcpCatalog(normalizeMcpCatalog(serverCatalog));
          setMcpCatalogFallbackNotice(null);
        } else {
          setMcpCatalog(DEFAULT_MCP_CATALOG);
          setMcpCatalogFallbackNotice("后端未返回 MCP 目录，当前展示默认目录（非实时状态）。");
        }
      } catch {
        if (!mounted) return;
        setSkillAvailability({});
        setMcpCatalog(DEFAULT_MCP_CATALOG);
        setMcpCatalogFallbackNotice("MCP 目录加载失败，当前展示默认目录（非实时状态）。");
      } finally {
        if (mounted) {
          setMcpCatalogLoading(false);
        }
      }
    };

    void loadRuntimeCatalog();
    return () => {
      mounted = false;
    };
  }, []);

  const mcpServers = useMemo(
    () => mcpCatalog.filter((item) => item.type === "mcp-server"),
    [mcpCatalog],
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

        const resultMap = new Map((response?.results || []).map((item) => [item.mcp_id, item]));

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
                      tool?.inputSchema && typeof tool.inputSchema === "object" && !Array.isArray(tool.inputSchema)
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

        setMcpToolsErrors((prev) => {
          const next = { ...prev };
          for (const mcpId of normalizedIds) {
            const item = resultMap.get(mcpId);
            next[mcpId] = item?.success ? "" : String(item?.error || "工具列表拉取失败");
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
    if (mcpCatalogLoading || !mcpServers.length) {
      return;
    }
    void loadMcpTools(mcpServers.map((item) => item.id));
  }, [loadMcpTools, mcpCatalogLoading, mcpServers]);

  const handleVerifyMcp = useCallback(async (mcpId: string) => {
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
  }, [loadMcpTools]);

  const rows = useMemo(
    () =>
      buildExternalToolRows({
        mcpCatalog: mcpServers.map((item) => ({
          ...item,
          startup_error: formatMcpErrorMessage(item.startup_error, item.id) || item.startup_error,
        })),
        skillCatalog: SKILL_TOOLS_CATALOG,
        skillAvailability,
        mcpToolsById,
        mcpToolsErrors: Object.fromEntries(
          Object.entries(mcpToolsErrors).map(([id, value]) => [id, formatMcpErrorMessage(value, id) || value]),
        ),
        verifyResults,
        verifyErrors,
      }),
    [mcpServers, skillAvailability, mcpToolsById, mcpToolsErrors, verifyResults, verifyErrors],
  );

  const selectedRow = useMemo(
    () => rows.find((item) => `${item.type}:${item.id}` === selectedRowId) ?? null,
    [rows, selectedRowId],
  );

  const loadedCount = rows.filter((item) => item.isLoaded).length;
  const unloadedCount = rows.length - loadedCount;
  const mcpCount = rows.filter((item) => item.type === "mcp").length;
  const skillCount = rows.filter((item) => item.type === "skill").length;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border/70 bg-muted/20 p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-xs">外部工具总数 {rows.length}</Badge>
          <Badge variant="outline" className="text-xs">MCP {mcpCount}</Badge>
          <Badge variant="outline" className="text-xs">SKILL {skillCount}</Badge>
          <Badge
            variant="outline"
            className="text-xs border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
          >
            已加载 {loadedCount}
          </Badge>
          <Badge
            variant="outline"
            className="text-xs border-zinc-500/40 text-zinc-600 dark:text-zinc-300 bg-zinc-500/10"
          >
            未加载 {unloadedCount}
          </Badge>
          {mcpCatalogLoading ? (
            <Badge variant="secondary" className="text-xs">目录加载中</Badge>
          ) : null}
        </div>
        <div className="text-sm text-muted-foreground leading-relaxed">
          外部工具列表统一展示 MCP 与 SKILL 的名称、可执行功能、加载状态与详情入口；运行时策略继续由后端统一托管。
        </div>
        {mcpCatalogFallbackNotice ? (
          <div className="text-xs text-amber-700 dark:text-amber-300 break-words">
            {mcpCatalogFallbackNotice}
          </div>
        ) : null}
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[80px] text-center">序号</TableHead>
              <TableHead className="min-w-[280px]">名称</TableHead>
              <TableHead className="min-w-[260px]">可执行功能</TableHead>
              <TableHead className="w-[150px] text-center">是否加载</TableHead>
              <TableHead className="w-[120px] text-center">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={`${row.type}:${row.id}`}>
                <TableCell className="text-center text-muted-foreground">{index + 1}</TableCell>
                <TableCell>
                  <div className="max-w-[320px] space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-semibold text-foreground break-all">{row.name}</div>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {row.type === "mcp" ? "MCP" : "SKILL"}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground font-mono break-all">{row.id}</div>
                  </div>
                </TableCell>
                <TableCell>{renderCapabilityBadges(row.capabilities)}</TableCell>
                <TableCell className="text-center">
                  <Badge
                    className={
                      row.isLoaded
                        ? "cyber-badge cyber-badge-success"
                        : "cyber-badge cyber-badge-muted"
                    }
                  >
                    {row.isLoaded ? "已加载" : "未加载"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex items-center justify-center">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="cyber-btn-ghost h-8 px-3"
                      onClick={() => {
                        setSelectedRowId(`${row.type}:${row.id}`);
                        setDetailOpen(true);
                      }}
                    >
                      详情
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent
          showCloseButton={false}
          className="!w-[min(96vw,1100px)] !max-w-none max-h-[88vh] overflow-hidden flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
        >
          <DialogHeader className="px-6 py-4 border-b border-border flex-shrink-0">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 space-y-1 text-left">
                <DialogTitle className="flex items-center gap-2 text-base">
                  <Wrench className="w-4 h-4 text-primary" />
                  {selectedRow?.name || "外部工具详情"}
                </DialogTitle>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{selectedRow?.id || "-"}</span>
                  {selectedRow ? (
                    <Badge variant="outline" className="text-[10px] uppercase">
                      {selectedRow.type === "mcp" ? "MCP" : "SKILL"}
                    </Badge>
                  ) : null}
                  {selectedRow ? (
                    <Badge
                      className={
                        selectedRow.isLoaded
                          ? "cyber-badge cyber-badge-success"
                          : "cyber-badge cyber-badge-muted"
                      }
                    >
                      {selectedRow.isLoaded ? "已加载" : "未加载"}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="cyber-btn-ghost h-8 px-3"
                onClick={() => setDetailOpen(false)}
              >
                <ArrowLeft className="w-4 h-4" />
                返回
              </Button>
            </div>
          </DialogHeader>

          <div className="flex-1 min-h-0 overflow-auto px-6 py-4 space-y-4">
            {selectedRow
              ? buildExternalToolDetailSections(selectedRow).map((section) => (
                  <div key={`${selectedRow.type}:${selectedRow.id}:${section.title}`}>
                    {renderDetailSection(section, {
                      selectedRow,
                      verifyingMcpId,
                      onVerifyMcp: (mcpId) => {
                        void handleVerifyMcp(mcpId);
                      },
                    })}
                  </div>
                ))
              : (
                <div className="text-sm text-muted-foreground">暂无详情</div>
              )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
