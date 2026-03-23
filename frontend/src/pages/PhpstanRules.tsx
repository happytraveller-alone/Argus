/**
 * PHPStan Rules Management Page
 *
 * 用途：在不改变现有页面布局的前提下，展示 PHPStan 规则并提供详情/编辑/启停/删除管理。
 * 说明：此处规则状态与编辑仅影响规则页展示，不影响 PHPStan 扫描执行命令。
 */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
// import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  type AppColumnDef,
  areDataTableQueryStatesEqual,
  createDefaultDataTableState,
  DataTable,
  type DataTableQueryState,
  type DataTableSelectionContext,
  useDataTableUrlState,
} from "@/components/data-table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertTriangle,
  Code,
  Database,
  Save,
  Shield,
} from "lucide-react";
import {
  batchDeletePhpstanRules,
  batchRestorePhpstanRules,
  batchUpdatePhpstanRulesEnabled,
  deletePhpstanRule,
  getPhpstanRule,
  getPhpstanRules,
  restorePhpstanRule,
  updatePhpstanRule,
  updatePhpstanRuleEnabled,
  type PhpstanRule,
} from "@/shared/api/phpstan";
import { resolveDeletedFilterValue } from "@/pages/rulesTableState";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa";
// type DeletedFilterValue = "false" | "true" | "all";

interface PhpstanRulesProps {
  showEngineSelector?: boolean;
  engineValue?: EngineTab;
  onEngineChange?: (value: EngineTab) => void;
}

const SOURCE_LABEL_MAP: Record<string, string> = {
  official_extension: "官方扩展",
  builtin: "内置规则",
};

const getSourceLabel = (source?: string) => {
  if (!source) return "未知来源";
  return SOURCE_LABEL_MAP[source] ?? source;
};
const DEFAULT_PAGE_SIZE = 10;

// function formatDate(value?: string | null) {
//   return value ? new Date(value).toLocaleString("zh-CN") : "-";
// }

function getColumnFilterValue(state: DataTableQueryState, columnId: string) {
  return state.columnFilters.find((filter) => filter.id === columnId)?.value;
}

function getStringColumnFilter(
  state: DataTableQueryState,
  columnId: string,
  fallback = "",
) {
  const value = getColumnFilterValue(state, columnId);
  return typeof value === "string" ? value : fallback;
}

function buildSelectionSummary({
  selectedCount,
  filteredCount,
}: DataTableSelectionContext<PhpstanRule>) {
  if (selectedCount > 0) {
    return (
      <>
        已选择 <span className="font-bold text-primary">{selectedCount}</span> 条规则
      </>
    );
  }
  return (
    <>
      将对全部 <span className="font-bold text-primary">{filteredCount}</span> 条规则进行操作
    </>
  );
}

function createInitialTableState(initialState: DataTableQueryState): DataTableQueryState {
  const nextState = createDefaultDataTableState({
    ...initialState,
    pagination: {
      pageIndex: initialState.pagination.pageIndex,
      pageSize: initialState.pagination.pageSize || DEFAULT_PAGE_SIZE,
    },
    columnVisibility: {
      ...initialState.columnVisibility,
      package: false,
    },
  });

  if (!nextState.columnFilters.some((filter) => filter.id === "deletedStatus")) {
    nextState.columnFilters.push({ id: "deletedStatus", value: "false" });
  }

  return nextState;
}

export default function PhpstanRules({
  showEngineSelector = false,
  engineValue = "phpstan",
  onEngineChange,
}: PhpstanRulesProps) {
  const [rules, setRules] = useState<PhpstanRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [batchOperating, setBatchOperating] = useState(false);
  const [showRuleDetail, setShowRuleDetail] = useState(false);
  const [selectedRule, setSelectedRule] = useState<PhpstanRule | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [isEditingRule, setIsEditingRule] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  // PHPStan rules integration: 规则编辑表单仅用于规则页展示态，不影响扫描执行。
  const [editRuleForm, setEditRuleForm] = useState({
    package: "",
    repo: "",
    name: "",
      description_summary: "",
      source_file: "",
      source: "",
  });
  const { initialState, syncStateToUrl } = useDataTableUrlState(true);
  const defaultResetState = useMemo(
    () => createInitialTableState(createDefaultDataTableState()),
    [],
  );
  const [tableState, setTableState] = useState<DataTableQueryState>(() =>
    createInitialTableState(initialState),
  );
  const resolvedUrlState = useMemo(
    () => createInitialTableState(initialState),
    [initialState],
  );
  const deletedFilter = resolveDeletedFilterValue(tableState);
  const activeFilter = getStringColumnFilter(tableState, "status");

  const loadRules = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = await getPhpstanRules({
        deleted: deletedFilter,
        limit: 2000,
      });
      setRules(data);
    } catch (error) {
      console.error("Failed to load phpstan rules:", error);
      setLoadError("加载 PHPStan 规则失败");
      toast.error("加载 PHPStan 规则失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRules();
  }, [deletedFilter]);

  useEffect(() => {
    setTableState((current) =>
      areDataTableQueryStatesEqual(current, resolvedUrlState) ? current : resolvedUrlState,
    );
  }, [resolvedUrlState]);

  useEffect(() => {
    syncStateToUrl(tableState);
  }, [syncStateToUrl, tableState]);

  const stats = useMemo(() => {
    const active = rules.filter((rule) => rule.is_active).length;
    const deleted = rules.filter((rule) => rule.is_deleted).length;
    const sources = new Set(rules.map((rule) => rule.source).filter(Boolean));
    const packages = new Set(rules.map((rule) => rule.package).filter(Boolean));
    return {
      total: rules.length,
      active,
      inactive: Math.max(rules.length - active, 0),
      deleted,
      sourceCount: sources.size,
      packageCount: packages.size,
    };
  }, [rules]);

  const sourceOptions = useMemo(
    () =>
      Array.from(new Set(rules.map((rule) => rule.source).filter(Boolean)))
        .sort()
        .map((source) => ({ label: getSourceLabel(source), value: source })),
    [rules],
  );

  const columns = useMemo<AppColumnDef<PhpstanRule, unknown>[]>(
    () => [
      {
        id: "rowNumber",
        header: "序号",
        enableSorting: false,
        enableHiding: false,
        meta: { label: "序号", align: "center", width: 72 },
        cell: ({ row, table }) =>
          table.getState().pagination.pageIndex * table.getState().pagination.pageSize +
          row.index +
          1,
      },
      {
        id: "ruleInfo",
        accessorFn: (row) =>
          [
            row.name,
            row.rule_class,
            row.description_summary,
            row.package,
            row.repo,
            row.id,
          ]
            .filter(Boolean)
            .join(" "),
        header: "规则",
        enableSorting: false,
        enableHiding: false,
        meta: { label: "规则", minWidth: 200, filterVariant: "text" },
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="font-semibold text-foreground break-all">{row.original.name}</div>
            {/* <div className="font-mono text-xs text-muted-foreground break-all">
              {row.original.rule_class}
            </div> */}
            {/* {row.original.description_summary ? (
              <div className="text-xs text-muted-foreground break-all line-clamp-2">
                {row.original.description_summary}
              </div>
            ) : null} */}
          </div>
        ),
      },
      {
        id: "package",
        accessorFn: (row) => row.package || "",
        header: "扩展包",
        meta: { label: "扩展包", minWidth: 200 },
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground break-all">
            {row.original.package || "-"}
          </span>
        ),
      },
      {
        id: "source",
        accessorFn: (row) => row.source || "",
        header: "来源",
        enableSorting: false,
        enableHiding: false,
        meta: {
          label: "规则来源",
          width: 120,
          filterVariant: "select",
          filterOptions: sourceOptions,
        },
        cell: ({ row }) => (
          <Badge className="cyber-badge cyber-badge-info">
            {getSourceLabel(row.original.source)}
          </Badge>
        ),
      },
      {
        id: "status",
        accessorFn: (row) => String(row.is_active),
        header: "启用状态",
        enableSorting: false,
        enableHiding: false,
        meta: {
          label: "启用状态",
          width: 136,
          filterVariant: "select",
          filterOptions: [
            { label: "已启用", value: "true" },
            { label: "已禁用", value: "false" },
          ],
        },
        cell: ({ row }) => (
          <Badge
            className={
              row.original.is_active
                ? "cyber-badge cyber-badge-success"
                : "cyber-badge cyber-badge-muted"
            }
          >
            {row.original.is_active ? "已启用" : "已禁用"}
          </Badge>
        ),
      },
      // {
      //   id: "deletedStatus",
      //   accessorFn: (row) => String(row.is_deleted),
      //   header: "删除状态",
      //   meta: {
      //     label: "删除状态",
      //     width: 136,
      //     filterVariant: "select",
      //     filterOptions: [
      //       { label: "未删除", value: "false" },
      //       { label: "已删除", value: "true" },
      //     ],
      //   },
      //   filterFn: (row, _columnId, filterValue) => {
      //     if (!filterValue) return true;
      //     return String(row.original.is_deleted) === String(filterValue);
      //   },
      //   cell: ({ row }) => (
      //     <Badge
      //       className={
      //         row.original.is_deleted
      //           ? "cyber-badge cyber-badge-warning"
      //           : "cyber-badge cyber-badge-info"
      //       }
      //     >
      //       {row.original.is_deleted ? "已删除" : "未删除"}
      //     </Badge>
      //   ),
      // },
      // {
      //   id: "updatedAt",
      //   accessorFn: (row) => row.updated_at || "",
      //   header: "更新时间",
      //   meta: { label: "更新时间", width: 180 },
      //   cell: ({ row }) => (
      //     <span className="text-xs text-muted-foreground">
      //       {formatDate(row.original.updated_at)}
      //     </span>
      //   ),
      // },
      {
        id: "actions",
        header: "操作",
        enableSorting: false,
        enableHiding: false,
        meta: { label: "操作", minWidth: 280 },
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => handleViewRuleDetail(row.original)}
              className="cyber-btn-outline h-8 text-xs"
            >
              详情
            </Button>
            <Button
              onClick={() => handleViewRuleDetail(row.original, "edit")}
              className="cyber-btn-outline h-8 text-xs"
            >
              编辑
            </Button>
            <Button
              onClick={() => void handleToggleRule(row.original)}
              disabled={row.original.is_deleted}
              className={
                row.original.is_active
                  ? "cyber-btn-outline h-8 text-xs"
                  : "cyber-btn-primary h-8 text-xs"
              }
            >
              {row.original.is_active ? "禁用" : "启用"}
            </Button>
            {!row.original.is_deleted ? (
              <Button
                onClick={() => void handleDeleteRule(row.original)}
                className="cyber-btn-outline h-8 text-xs"
              >
                删除
              </Button>
            ) : (
              <Button
                onClick={() => void handleRestoreRule(row.original)}
                className="cyber-btn-primary h-8 text-xs"
              >
                恢复
              </Button>
            )}
          </div>
        ),
      },
    ],
    [sourceOptions],
  );

  const handleStartEditRule = (rule: PhpstanRule) => {
    setEditRuleForm({
      package: rule.package || "",
      repo: rule.repo || "",
      name: rule.name || "",
      description_summary: rule.description_summary || "",
      source_file: rule.source_file || "",
      source: rule.source || "",
    });
    setIsEditingRule(true);
  };

  const handleViewRuleDetail = async (rule: PhpstanRule, mode: "view" | "edit" = "view") => {
    setSelectedRule(rule);
    setShowRuleDetail(true);
    setIsEditingRule(mode === "edit");
    setLoadingDetail(true);
    try {
      const detail = await getPhpstanRule(rule.id);
      setSelectedRule(detail);
      if (mode === "edit") {
        handleStartEditRule(detail);
      }
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "加载规则详情失败");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleCancelEditRule = () => {
    setIsEditingRule(false);
    setSavingRule(false);
  };

  const handleSaveRule = async () => {
    if (!selectedRule) return;
    if (!editRuleForm.name.trim()) {
      toast.error("规则名称不能为空");
      return;
    }

    try {
      setSavingRule(true);
      const result = await updatePhpstanRule({
        ruleId: selectedRule.id,
        package: editRuleForm.package.trim(),
        repo: editRuleForm.repo.trim(),
        name: editRuleForm.name.trim(),
        description_summary: editRuleForm.description_summary.trim(),
        source_file: editRuleForm.source_file.trim(),
        source: editRuleForm.source.trim(),
      });
      const updatedRule = result.rule;
      setSelectedRule(updatedRule);
      setRules((prev) =>
        prev.map((item) => (item.id === updatedRule.id ? { ...item, ...updatedRule } : item)),
      );
      setIsEditingRule(false);
      toast.success(result.message || "规则更新成功");
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "更新规则失败");
    } finally {
      setSavingRule(false);
    }
  };

  const handleDeleteRule = async (rule: PhpstanRule) => {
    try {
      await deletePhpstanRule(rule.id);
      toast.success(`规则「${rule.id}」已删除`);
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "删除规则失败");
    }
  };

  const handleRestoreRule = async (rule: PhpstanRule) => {
    try {
      await restorePhpstanRule(rule.id);
      toast.success(`规则「${rule.id}」已恢复`);
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "恢复规则失败");
    }
  };

  const handleToggleRule = async (rule: PhpstanRule) => {
    if (rule.is_deleted) {
      toast.error("已删除规则请先恢复后再启用/禁用");
      return;
    }
    try {
      await updatePhpstanRuleEnabled({
        ruleId: rule.id,
        is_active: !rule.is_active,
      });
      await loadRules();
      toast.success(`规则已${rule.is_active ? "禁用" : "启用"}`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "更新规则失败");
    }
  };

  const handleBatchToggleEnabled = async (selectedRows: PhpstanRule[], isActive: boolean) => {
    try {
      setBatchOperating(true);
      const currentActiveFilter = getStringColumnFilter(tableState, "status");
      const payload =
        selectedRows.length > 0
          ? {
              rule_ids: selectedRows.map((row) => row.id),
              is_active: isActive,
            }
          : {
              source: getStringColumnFilter(tableState, "source") || undefined,
              keyword: tableState.globalFilter.trim() || undefined,
              current_is_active:
                currentActiveFilter === ""
                  ? undefined
                  : currentActiveFilter === "true",
              is_active: isActive,
            };
      const result = await batchUpdatePhpstanRulesEnabled(payload);
      toast.success(result.message);
      setTableState((current) => ({ ...current, rowSelection: {} }));
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量启停失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const handleBatchDelete = async (selectedRows: PhpstanRule[]) => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRows.length > 0
          ? { rule_ids: selectedRows.map((row) => row.id) }
          : {
              source: getStringColumnFilter(tableState, "source") || undefined,
              keyword: tableState.globalFilter.trim() || undefined,
              current_is_deleted: false,
            };
      const result = await batchDeletePhpstanRules(payload);
      toast.success(result.message);
      setTableState((current) => ({ ...current, rowSelection: {} }));
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量删除失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const handleBatchRestore = async (selectedRows: PhpstanRule[]) => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRows.length > 0
          ? { rule_ids: selectedRows.map((row) => row.id) }
          : {
              source: getStringColumnFilter(tableState, "source") || undefined,
              keyword: tableState.globalFilter.trim() || undefined,
              current_is_deleted: true,
            };
      const result = await batchRestorePhpstanRules(payload);
      toast.success(result.message);
      setTableState((current) => ({ ...current, rowSelection: {} }));
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量恢复失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const engineSelector = showEngineSelector ? (
    <div className="min-w-[150px]">
      <Select
        value={engineValue}
        onValueChange={(val) => {
          if (
            val === "opengrep" ||
            val === "gitleaks" ||
            val === "bandit" ||
            val === "phpstan" ||
            val === "yasa"
          ) {
            onEngineChange?.(val);
          }
        }}
      >
        <SelectTrigger className="cyber-input h-10 min-w-[150px]">
          <SelectValue placeholder="选择引擎" />
        </SelectTrigger>
        <SelectContent className="cyber-dialog border-border">
          <SelectItem value="opengrep">opengrep</SelectItem>
          <SelectItem value="gitleaks">gitleaks</SelectItem>
          <SelectItem value="bandit">bandit</SelectItem>
          <SelectItem value="phpstan">phpstan</SelectItem>
          <SelectItem value="yasa">yasa</SelectItem>
        </SelectContent>
      </Select>
    </div>
  ) : null;

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">有效规则总数</p>
              <div className="flex items-end gap-3">
                <p className="stat-value">{stats.total}</p>
                <p className="text-sm mb-1 flex items-center gap-3">
                  <span className="inline-flex items-center gap-1 text-emerald-400">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    已启用 {stats.active}
                  </span>
                </p>
              </div>
            </div>
            <div className="stat-icon text-primary">
              <Database className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">规则来源数量</p>
              <p className="stat-value">{stats.sourceCount}</p>
            </div>
            <div className="stat-icon text-indigo-400">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">扩展包数量</p>
              <p className="stat-value">{stats.packageCount}</p>
            </div>
            <div className="stat-icon text-cyan-400">
              <Shield className="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        <DataTable
          data={rules}
          columns={columns}
          state={tableState}
          resetState={defaultResetState}
          onStateChange={setTableState}
          loading={loading}
          error={loadError || undefined}
          emptyState={{
            title: "未找到规则",
            description:
              tableState.globalFilter || activeFilter || deletedFilter !== "false"
                ? "调整筛选条件尝试"
                : "暂无规则数据（请先生成并导入 phpstan 规则快照）",
          }}
          toolbar={{
            searchPlaceholder: "搜索名称/类名/包名...",
            leadingActions: engineSelector,
            showGlobalSearch: false,
            showColumnVisibility: false,
						showDensityToggle: false,
						showReset: false,
          }}
          selection={
            loading
              ? undefined
              : {
                  enableRowSelection: true,
                  summary: buildSelectionSummary,
                  actions: ({ selectedRows }) => (
                    <>
                      <Button
                        onClick={() => void handleBatchToggleEnabled(selectedRows, true)}
                        disabled={batchOperating}
                        className="cyber-btn-primary h-8 text-sm"
                      >
                        {batchOperating ? "处理中..." : "批量启用"}
                      </Button>
                      <Button
                        onClick={() => void handleBatchToggleEnabled(selectedRows, false)}
                        disabled={batchOperating}
                        className="cyber-btn-outline h-8 text-sm"
                      >
                        {batchOperating ? "处理中..." : "批量禁用"}
                      </Button>
                      <Button
                        onClick={() => void handleBatchDelete(selectedRows)}
                        disabled={batchOperating}
                        className="cyber-btn-outline h-8 text-sm"
                      >
                        {batchOperating ? "处理中..." : "批量删除"}
                      </Button>
                      <Button
                        onClick={() => void handleBatchRestore(selectedRows)}
                        disabled={batchOperating}
                        className="cyber-btn-outline h-8 text-sm"
                      >
                        {batchOperating ? "处理中..." : "批量恢复"}
                      </Button>
                    </>
                  ),
                }
          }
          pagination={{ enabled: true, pageSizeOptions: [10, 20, 50] }}
          tableClassName="min-w-[1400px]"
          getRowId={(row) => row.id}
        />
      </div>

      <Dialog
        open={showRuleDetail}
        onOpenChange={(open) => {
          setShowRuleDetail(open);
          if (!open) {
            setIsEditingRule(false);
            setSavingRule(false);
          }
        }}
      >
        <DialogContent className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
          <DialogHeader className="px-6 pt-4 flex-shrink-0">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Code className="w-5 h-5 text-primary" />
              {isEditingRule ? "编辑规则" : "规则详情"}
            </DialogTitle>
          </DialogHeader>

          {loadingDetail ? (
            <div className="flex items-center justify-center p-8">
              <div className="loading-spinner" />
            </div>
          ) : selectedRule ? (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="space-y-6">
                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    基本信息
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm font-mono">
                    <div>
                      <p className="text-muted-foreground">规则名称</p>
                      {isEditingRule ? (
                        <Input
                          value={editRuleForm.name}
                          onChange={(e) =>
                            setEditRuleForm((prev) => ({ ...prev, name: e.target.value }))
                          }
                          className="cyber-input mt-1.5 h-9"
                        />
                      ) : (
                        <p className="text-foreground font-bold mt-1 break-all">{selectedRule.name}</p>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则ID</p>
                      <p className="text-foreground font-bold mt-1 break-all">{selectedRule.id}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">扩展包</p>
                      {isEditingRule ? (
                        <Input
                          value={editRuleForm.package}
                          onChange={(e) =>
                            setEditRuleForm((prev) => ({ ...prev, package: e.target.value }))
                          }
                          className="cyber-input mt-1.5 h-9"
                        />
                      ) : (
                        <p className="text-foreground font-bold mt-1 break-all">{selectedRule.package || "-"}</p>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">仓库</p>
                      {isEditingRule ? (
                        <Input
                          value={editRuleForm.repo}
                          onChange={(e) =>
                            setEditRuleForm((prev) => ({ ...prev, repo: e.target.value }))
                          }
                          className="cyber-input mt-1.5 h-9"
                        />
                      ) : (
                        <p className="text-foreground font-bold mt-1 break-all">{selectedRule.repo || "-"}</p>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则类</p>
                      <p className="text-foreground font-bold mt-1 break-all">{selectedRule.rule_class}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">来源</p>
                      {isEditingRule ? (
                        <Input
                          value={editRuleForm.source}
                          onChange={(e) =>
                            setEditRuleForm((prev) => ({ ...prev, source: e.target.value }))
                          }
                          className="cyber-input mt-1.5 h-9"
                        />
                      ) : (
                        <Badge className="cyber-badge cyber-badge-info mt-1">
                          {getSourceLabel(selectedRule.source)}
                        </Badge>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">启用状态</p>
                      {selectedRule.is_deleted ? (
                        <Badge className="cyber-badge cyber-badge-muted mt-1">已删除</Badge>
                      ) : (
                        <Badge className={`mt-1 ${selectedRule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}`}>
                          {selectedRule.is_active ? "已启用" : "已禁用"}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    摘要
                  </h3>
                  {isEditingRule ? (
                    <Textarea
                      value={editRuleForm.description_summary}
                      onChange={(e) =>
                        setEditRuleForm((prev) => ({ ...prev, description_summary: e.target.value }))
                      }
                      className="cyber-input min-h-24"
                    />
                  ) : (
                    <div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
                      {selectedRule.description_summary || "-"}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    源文件
                  </h3>
                  {isEditingRule ? (
                    <Input
                      value={editRuleForm.source_file}
                      onChange={(e) =>
                        setEditRuleForm((prev) => ({ ...prev, source_file: e.target.value }))
                      }
                      className="cyber-input h-9"
                    />
                  ) : (
                    <div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words font-mono">
                      {selectedRule.source_file || "-"}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    规则文件内容
                  </h3>
                  <div className="rounded border border-border/50 p-3 text-xs whitespace-pre-wrap break-words font-mono max-h-[320px] overflow-auto">
                    {selectedRule.source_content || "未找到对应源码内容"}
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    元数据
                  </h3>
                  <div className="text-sm font-mono text-muted-foreground">
                    <p>创建时间: {selectedRule.created_at ? new Date(selectedRule.created_at).toLocaleString("zh-CN") : "-"}</p>
                    <p>更新时间: {selectedRule.updated_at ? new Date(selectedRule.updated_at).toLocaleString("zh-CN") : "-"}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
            <Button
              variant="outline"
              onClick={() => {
                if (isEditingRule) {
                  handleCancelEditRule();
                } else {
                  setShowRuleDetail(false);
                }
              }}
              className="cyber-btn-outline"
            >
              {isEditingRule ? "取消编辑" : "关闭"}
            </Button>
            {isEditingRule ? (
              <Button
                onClick={() => void handleSaveRule()}
                className="cyber-btn-primary"
                disabled={savingRule}
              >
                {savingRule ? (
                  <>
                    <div className="loading-spinner mr-2" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    保存规则
                  </>
                )}
              </Button>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
