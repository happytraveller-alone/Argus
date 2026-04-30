import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/data-table/DataTable";
import type { AppColumnDef } from "@/components/data-table/types";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  api,
  type ExternalToolResourcePayload,
  type PromptSkillScopePayload,
} from "@/shared/api/database";
import PromptSkillEditorDialog from "./PromptSkillEditorDialog";
import {
  buildExternalToolListState,
  buildExternalToolResources,
  buildExternalToolRows,
  type ExternalToolRow,
  type ExternalToolStatusFilter,
  type ExternalToolTypeFilter,
} from "./externalToolsViewModel";
import {
  EXTERNAL_TOOLS_MAX_PAGE_SIZE,
  resolveAnchoredExternalToolsPage,
  resolveExternalToolsFirstVisibleIndex,
  resolveResponsiveExternalToolsLayout,
} from "./externalToolsResponsiveLayout";
import {
  mergeExternalToolsUrlState,
  parseExternalToolsUrlState,
} from "./externalToolsUrlState";
import {
  buildPromptSkillAgentOptions,
  DEFAULT_PROMPT_SKILL_FORM,
  extractPromptSkillErrorMessage,
  normalizePromptSkillCreatePayload,
  scopeLabel,
  type PromptSkillFormState,
} from "./promptSkillShared";

export interface SkillToolsPanelProps {
  initialResources?: ExternalToolResourcePayload[];
}

export default function SkillToolsPanel({
  initialResources = [],
}: SkillToolsPanelProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const parsedUrlState = useMemo(
    () => parseExternalToolsUrlState(searchParams),
    [searchParams],
  );
  const [resources, setResources] = useState<ExternalToolResourcePayload[]>(
    initialResources,
  );
  const [supportedAgentKeys, setSupportedAgentKeys] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState(parsedUrlState.searchQuery);
  const [typeFilter, setTypeFilter] =
    useState<ExternalToolTypeFilter>(parsedUrlState.typeFilter);
  const [statusFilter, setStatusFilter] =
    useState<ExternalToolStatusFilter>(parsedUrlState.statusFilter);
  const [page, setPage] = useState(parsedUrlState.page);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<PromptSkillFormState>(DEFAULT_PROMPT_SKILL_FORM);
  const tableViewportRef = useRef<HTMLDivElement | null>(null);
  const pageSizeRef = useRef(EXTERNAL_TOOLS_MAX_PAGE_SIZE);
  const [pageSize, setPageSize] = useState(EXTERNAL_TOOLS_MAX_PAGE_SIZE);

  const agentOptions = useMemo(
    () =>
      buildPromptSkillAgentOptions({
        supportedAgentKeys,
        builtinAgentKeys: resources
          .filter((item) => item.tool_type === "prompt-builtin")
          .map((item) => item.agent_key || ""),
        customAgentKeys: resources
          .filter((item) => item.tool_type === "prompt-custom")
          .map((item) => item.agent_key),
      }),
    [resources, supportedAgentKeys],
  );

  const rows = useMemo(
    () =>
      buildExternalToolRows({
        resources,
      }),
    [resources],
  );

  const listState = useMemo(
    () =>
      buildExternalToolListState({
        rows,
        searchQuery,
        typeFilter,
        statusFilter,
        page,
        pageSize,
      }),
    [page, pageSize, rows, searchQuery, statusFilter, typeFilter],
  );

  const syncUrlState = (
    nextState: Partial<{
      page: number;
      searchQuery: string;
      typeFilter: ExternalToolTypeFilter;
      statusFilter: ExternalToolStatusFilter;
    }>,
  ) => {
    const nextParams = mergeExternalToolsUrlState(
      new URLSearchParams(searchParams),
      {
        page,
        searchQuery,
        typeFilter,
        statusFilter,
        ...nextState,
      },
    );
    setSearchParams(nextParams, { replace: true });
  };

  const detailSearch = useMemo(() => {
    const nextParams = mergeExternalToolsUrlState(
      new URLSearchParams(searchParams),
      {
        page,
        searchQuery,
        typeFilter,
        statusFilter,
      },
    );
    const serialized = nextParams.toString();
    return serialized ? `?${serialized}` : "";
  }, [page, searchParams, searchQuery, setSearchParams, statusFilter, typeFilter]);

  useEffect(() => {
    if (searchQuery !== parsedUrlState.searchQuery) {
      setSearchQuery(parsedUrlState.searchQuery);
    }
    if (typeFilter !== parsedUrlState.typeFilter) {
      setTypeFilter(parsedUrlState.typeFilter);
    }
    if (statusFilter !== parsedUrlState.statusFilter) {
      setStatusFilter(parsedUrlState.statusFilter);
    }
    if (page !== parsedUrlState.page) {
      setPage(parsedUrlState.page);
    }
  }, [
    page,
    parsedUrlState.page,
    parsedUrlState.searchQuery,
    parsedUrlState.statusFilter,
    parsedUrlState.typeFilter,
    searchQuery,
    statusFilter,
    typeFilter,
  ]);

  useEffect(() => {
    if (page !== listState.page) {
      setPage(listState.page);
      syncUrlState({ page: listState.page });
    }
  }, [listState.page, page]);

  useEffect(() => {
    if (!tableViewportRef.current) {
      return;
    }

    const viewportNode = tableViewportRef.current;
    const updateLayout = () => {
      const { width, height } = viewportNode.getBoundingClientRect();
      const nextLayout = resolveResponsiveExternalToolsLayout({
        width,
        height,
        minCardHeight: 72,
      });
      setPageSize((current) =>
        current === nextLayout.pageSize ? current : nextLayout.pageSize,
      );
    };

    updateLayout();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
          updateLayout();
        });
    observer?.observe(viewportNode);
    window.addEventListener("resize", updateLayout);
    window.visualViewport?.addEventListener("resize", updateLayout);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", updateLayout);
      window.visualViewport?.removeEventListener("resize", updateLayout);
    };
  }, []);

  useEffect(() => {
    setPage((current) => {
      const firstVisibleIndex = resolveExternalToolsFirstVisibleIndex({
        page: current,
        pageSize: pageSizeRef.current,
      });
      const nextPage = resolveAnchoredExternalToolsPage({
        firstVisibleIndex,
        nextPageSize: pageSize,
        totalRows: listState.totalRows,
      });
      return current === nextPage ? current : nextPage;
    });
    pageSizeRef.current = pageSize;
  }, [listState.totalRows, pageSize]);

  useEffect(() => {
    let cancelled = false;

    async function loadResources() {
      setLoading(true);
      try {
        const payload = await api.getExternalToolCatalog({
          limit: 200,
        }).catch(async () => {
          const [skillCatalog, promptSkills] = await Promise.all([
            api.getSkillCatalog({ limit: 200 }),
            api.getPromptSkills({ limit: 500 }),
          ]);
          return {
            supportedAgentKeys: promptSkills.supportedAgentKeys,
            items: buildExternalToolResources({
              skillCatalog,
              promptSkills,
            }),
          };
        });
        if (cancelled) {
          return;
        }
        setSupportedAgentKeys(payload.supportedAgentKeys);
        if (payload.items.length > 0 || initialResources.length === 0) {
          setResources(payload.items);
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(`加载外部工具失败：${extractPromptSkillErrorMessage(error)}`);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadResources();
    return () => {
      cancelled = true;
    };
  }, [initialResources.length]);

  const resetForm = () => {
    setForm({
      ...DEFAULT_PROMPT_SKILL_FORM,
      agent_key: agentOptions[0]?.key || "",
    });
  };

  const handleScopeChange = (nextScope: PromptSkillScopePayload) => {
    setForm((current) => ({
      ...current,
      scope: nextScope,
      agent_key:
        nextScope === "agent_specific"
          ? current.agent_key || agentOptions[0]?.key || ""
          : "",
    }));
  };

  const handleCreatePromptSkill = async () => {
    const name = form.name.trim();
    const content = form.content.trim();

    if (!name) {
      toast.error("请填写 Skill 名称");
      return;
    }
    if (!content) {
      toast.error("请填写 Skill 内容");
      return;
    }
    if (form.scope === "agent_specific" && !form.agent_key) {
      toast.error("请选择目标智能体");
      return;
    }

    setSaving(true);
    try {
      const created = await api.createPromptSkill(
        normalizePromptSkillCreatePayload(form),
      );
      toast.success("Prompt Skill 已创建");
      setDialogOpen(false);
      resetForm();
      navigate(
        `/scan-config/external-tools/prompt-custom/${encodeURIComponent(created.id)}${detailSearch}`,
      );
    } catch (error) {
      toast.error(`保存失败：${extractPromptSkillErrorMessage(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTogglePromptRow = async (row: ExternalToolResourcePayload) => {
    if (row.tool_type === "skill") {
      return;
    }
    try {
      if (row.tool_type === "prompt-builtin") {
        await api.updateBuiltinPromptSkill(row.tool_id, {
          is_active: !row.is_enabled,
        });
      } else {
        await api.updatePromptSkill(row.tool_id, {
          is_active: !row.is_enabled,
        });
      }
      const payload = await api.getExternalToolCatalog({ limit: 200 }).catch(async () => {
        const [skillCatalog, promptSkills] = await Promise.all([
          api.getSkillCatalog({ limit: 200 }),
          api.getPromptSkills({ limit: 500 }),
        ]);
        return {
          supportedAgentKeys: promptSkills.supportedAgentKeys,
          items: buildExternalToolResources({
            skillCatalog,
            promptSkills,
          }),
        };
      });
      setSupportedAgentKeys(payload.supportedAgentKeys);
      setResources(payload.items);
      toast.success(row.is_enabled ? "Prompt Skill 已停用" : "Prompt Skill 已启用");
    } catch (error) {
      toast.error(`更新状态失败：${extractPromptSkillErrorMessage(error)}`);
    }
  };

  const toolColumns = useMemo<AppColumnDef<ExternalToolRow>[]>(
    () => [
      {
        id: "order",
        header: "序号",
        cell: ({ row }) => (
          <span className="font-mono text-sm text-muted-foreground">
            {String(listState.startIndex + row.index + 1).padStart(2, "0")}
          </span>
        ),
        meta: {
          label: "序号",
          width: 72,
          minWidth: 72,
        },
      },
      {
        id: "name",
        accessorKey: "name",
        header: "名称",
        cell: ({ row }) => (
          <div className="space-y-1">
            <div className="text-sm font-semibold text-foreground">
              {row.original.name}
            </div>
            {row.original.agent_label ? (
              <div className="text-xs text-muted-foreground">
                {row.original.scope ? `${scopeLabel(row.original.scope)} · ` : ""}
                {row.original.agent_label}
              </div>
            ) : null}
          </div>
        ),
        meta: {
          label: "名称",
          minWidth: 220,
        },
      },
      {
        id: "type",
        accessorKey: "typeLabel",
        header: "类型",
        cell: ({ row }) => (
          <Badge variant="outline" className="text-[10px] uppercase">
            {row.original.typeLabel}
          </Badge>
        ),
        meta: {
          label: "类型",
          width: 150,
          minWidth: 150,
        },
      },
      {
        id: "capabilities",
        header: "执行功能",
        cell: ({ row }) => (
          <div
            className="max-w-[420px] overflow-hidden text-ellipsis whitespace-nowrap text-sm leading-6 text-foreground/90"
            title={row.original.capabilities.join("; ")}
          >
            {row.original.capabilities.join("; ")}
          </div>
        ),
        meta: {
          label: "执行功能",
          minWidth: 280,
        },
      },
      {
        id: "status",
        accessorKey: "status_label",
        header: "状态",
        cell: ({ row }) => (
          <Badge variant={row.original.is_enabled ? "default" : "secondary"}>
            {row.original.status_label}
          </Badge>
        ),
        meta: {
          label: "状态",
          width: 120,
          minWidth: 120,
        },
      },
      {
        id: "actions",
        header: "操作",
        cell: ({ row }) => (
          <div className="flex justify-end gap-2">
            {row.original.tool_type !== "skill" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="cyber-btn-ghost h-8 px-3"
                onClick={() => void handleTogglePromptRow(row.original)}
              >
                {row.original.is_enabled ? "停用" : "启用"}
              </Button>
            ) : null}
            <Button
              asChild
              size="sm"
              variant="outline"
              className="cyber-btn-ghost h-8 px-3"
            >
              <Link
                to={`/scan-config/external-tools/${row.original.tool_type}/${encodeURIComponent(row.original.tool_id)}${detailSearch}`}
              >
                详情
              </Link>
            </Button>
          </div>
        ),
        meta: {
          label: "操作",
          align: "right",
          width: 160,
          minWidth: 160,
          hideable: false,
        },
      },
    ],
    [detailSearch, handleTogglePromptRow, listState.startIndex],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_180px_180px_auto] xl:items-end">
        <Input
          type="search"
          value={searchQuery}
          onChange={(event) => {
            const nextValue = event.target.value;
            setSearchQuery(nextValue);
            setPage(1);
            syncUrlState({ searchQuery: nextValue, page: 1 });
          }}
          startIcon={<Search className="h-4 w-4" />}
          placeholder="搜索名称、摘要、智能体或作用域..."
          className="cyber-input h-11 border-border/60 bg-background/70"
          wrapperClassName="max-w-full"
          aria-label="搜索名称、摘要、智能体或作用域"
        />
        <Select
          value={typeFilter}
          onValueChange={(value) => {
            const nextValue = value as ExternalToolTypeFilter;
            setTypeFilter(nextValue);
            setPage(1);
            syncUrlState({ typeFilter: nextValue, page: 1 });
          }}
        >
          <SelectTrigger className="cyber-input h-11">
            <SelectValue placeholder="筛选资源类型" />
          </SelectTrigger>
          <SelectContent className="border-border cyber-dialog">
            <SelectItem value="all">全部类型</SelectItem>
            <SelectItem value="skill">Scan Core</SelectItem>
            <SelectItem value="prompt-builtin">Builtin Prompt Skill</SelectItem>
            <SelectItem value="prompt-custom">Custom Prompt Skill</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={statusFilter}
          onValueChange={(value) => {
            const nextValue = value as ExternalToolStatusFilter;
            setStatusFilter(nextValue);
            setPage(1);
            syncUrlState({ statusFilter: nextValue, page: 1 });
          }}
        >
          <SelectTrigger className="cyber-input h-11">
            <SelectValue placeholder="筛选状态" />
          </SelectTrigger>
          <SelectContent className="border-border cyber-dialog">
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="enabled">已启用</SelectItem>
            <SelectItem value="disabled">已停用</SelectItem>
          </SelectContent>
        </Select>
        <Button
          type="button"
          className="cyber-btn-primary h-11 px-4"
          onClick={() => {
            resetForm();
            setDialogOpen(true);
          }}
        >
          <Plus className="h-4 w-4" />
          新增 Prompt Skill
        </Button>
      </div>

      <div ref={tableViewportRef} className="flex min-h-[20rem] flex-1 flex-col">
        <DataTable
          data={listState.pageRows}
          columns={toolColumns}
          getRowId={(row) => `${row.tool_type}:${row.tool_id}`}
          toolbar={false}
          pagination={false}
          loading={loading}
          emptyState={{
            title: "未找到匹配的外部工具",
            description: "尝试更换搜索词或筛选条件。",
          }}
          className="min-h-full border-border/50 bg-background/20"
          containerClassName="overflow-x-auto"
          tableClassName="min-w-[980px] w-full border-collapse"
        />
      </div>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-4">
        <span className="text-xs font-mono text-muted-foreground">
          当前展示 {listState.pageRows.length} / {listState.totalRows} 条 ·
          每页 {listState.pageSize} 条
        </span>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="cyber-btn-ghost h-8 px-3"
            onClick={() =>
              setPage((current) => {
                const nextPage = Math.max(1, current - 1);
                syncUrlState({ page: nextPage });
                return nextPage;
              })
            }
            disabled={listState.page <= 1 || listState.totalRows === 0}
          >
            上一页
          </Button>
          <span className="min-w-[96px] text-center text-xs font-mono text-muted-foreground">
            第 {listState.page} / {listState.totalPages} 页
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="cyber-btn-ghost h-8 px-3"
            onClick={() =>
              setPage((current) => {
                const nextPage = Math.min(listState.totalPages, current + 1);
                syncUrlState({ page: nextPage });
                return nextPage;
              })
            }
            disabled={
              listState.page >= listState.totalPages || listState.totalRows === 0
            }
          >
            下一页
          </Button>
        </div>
      </div>

      <PromptSkillEditorDialog
        open={dialogOpen}
        saving={saving}
        title="新增 Prompt Skill"
        description="配置运行时注入的自定义 Prompt Skill，支持通用和智能体专属两种作用域。"
        submitLabel="创建 Skill"
        form={form}
        agentOptions={agentOptions}
        onOpenChange={setDialogOpen}
        onFormChange={(updater) => setForm((current) => updater(current))}
        onScopeChange={handleScopeChange}
        onSubmit={() => void handleCreatePromptSkill()}
      />
    </div>
  );
}
