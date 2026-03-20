import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { Textarea } from "@/components/ui/textarea";
import { AlertTriangle, Database, Tag } from "lucide-react";
import {
  batchUpdateGitleaksRules,
  createGitleaksRule,
  deleteGitleaksRule,
  getGitleaksRules,
  type GitleaksRule,
  updateGitleaksRule,
} from "@/shared/api/gitleaks";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa";

interface GitleaksRulesProps {
  showEngineSelector?: boolean;
  engineValue?: EngineTab;
  onEngineChange?: (value: EngineTab) => void;
}

const SOURCE_LABEL_MAP: Record<string, string> = {
  builtin: "内置规则",
  custom: "自定义规则",
};

const DEFAULT_FORM = {
  name: "",
  description: "",
  rule_id: "",
  secret_group: "0",
  regex: "",
  keywords: "",
  path: "",
  tags: "",
  entropy: "",
  source: "custom",
  is_active: true,
};

const DEFAULT_PAGE_SIZE = 10;

function getSourceLabel(source?: string) {
  if (!source) return "未知来源";
  return SOURCE_LABEL_MAP[source] ?? source;
}

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleDateString("zh-CN") : "-";
}

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
}: DataTableSelectionContext<GitleaksRule>) {
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
  return createDefaultDataTableState({
    ...initialState,
    pagination: {
      pageIndex: initialState.pagination.pageIndex,
      pageSize: initialState.pagination.pageSize || DEFAULT_PAGE_SIZE,
    },
    columnVisibility: {
      isActiveFilter: false,
      entropyRange: false,
      ...initialState.columnVisibility,
    },
  });
}

function matchesEntropyRange(rule: GitleaksRule, filterValue: unknown) {
  if (!filterValue) return true;
  const entropy = rule.entropy;
  switch (String(filterValue)) {
    case "high":
      return entropy !== null && entropy !== undefined && entropy >= 4;
    case "medium":
      return entropy !== null && entropy !== undefined && entropy >= 3 && entropy < 4;
    case "low":
      return entropy !== null && entropy !== undefined && entropy > 0 && entropy < 3;
    case "none":
      return entropy === null || entropy === undefined;
    default:
      return true;
  }
}

export default function GitleaksRules({
  showEngineSelector = false,
  engineValue = "gitleaks",
  onEngineChange,
}: GitleaksRulesProps) {
  const [rules, setRules] = useState<GitleaksRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [batchOperating, setBatchOperating] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editingRule, setEditingRule] = useState<GitleaksRule | null>(null);
  const [savingRule, setSavingRule] = useState(false);
  const [formData, setFormData] = useState(DEFAULT_FORM);
  const { initialState, syncStateToUrl } = useDataTableUrlState(true);
  const [tableState, setTableState] = useState<DataTableQueryState>(() =>
    createInitialTableState(initialState),
  );
  const resolvedUrlState = useMemo(
    () => createInitialTableState(initialState),
    [initialState],
  );

  const sourceFilter = getStringColumnFilter(tableState, "source");
  const activeFilter = getStringColumnFilter(tableState, "isActiveFilter");
  const entropyFilter = getStringColumnFilter(tableState, "entropyRange");

  const loadRules = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const data = await getGitleaksRules({ limit: 2000 });
      setRules(data);
    } catch (error) {
      console.error("Failed to load gitleaks rules:", error);
      setLoadError("加载 gitleaks 规则失败");
      toast.error("加载 gitleaks 规则失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRules();
  }, []);

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
    const sources = new Set(rules.map((rule) => rule.source).filter(Boolean));
    const highEntropyCount = rules.filter(
      (rule) =>
        rule.entropy !== null &&
        rule.entropy !== undefined &&
        rule.entropy >= 3,
    ).length;
    return {
      total: rules.length,
      active,
      inactive: Math.max(rules.length - active, 0),
      sourceCount: sources.size,
      highEntropyCount,
    };
  }, [rules]);

  const sourceOptions = useMemo(
    () =>
      Array.from(new Set(rules.map((rule) => rule.source).filter(Boolean)))
        .sort()
        .map((source) => ({
          label: getSourceLabel(source),
          value: source,
        })),
    [rules],
  );

  const columns = useMemo<AppColumnDef<GitleaksRule, unknown>[]>(
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
        id: "ruleName",
        accessorFn: (row) =>
          [row.name, row.rule_id, row.regex, row.id].filter(Boolean).join(" "),
        header: "规则名称",
        meta: { label: "规则名称", minWidth: 320, filterVariant: "text" },
        cell: ({ row }) => (
          <div className="space-y-1">
            <div className="font-semibold text-foreground break-all">{row.original.name}</div>
            <div className="font-mono text-xs text-muted-foreground break-all">
              {row.original.rule_id}
            </div>
            <div className="line-clamp-2 font-mono text-[11px] text-muted-foreground/90 break-all">
              {row.original.regex}
            </div>
          </div>
        ),
      },
      {
        id: "keywords",
        accessorFn: (row) => row.keywords?.length ?? 0,
        header: "关键词数",
        meta: { label: "关键词数", align: "center", width: 120 },
        cell: ({ row }) => (
          <span className="font-mono tabular-nums text-sm text-muted-foreground">
            {row.original.keywords?.length || 0}
          </span>
        ),
      },
      {
        id: "secretGroup",
        accessorFn: (row) => row.secret_group ?? 0,
        header: "密钥分组",
        meta: { label: "密钥分组", align: "center", width: 120 },
        cell: ({ row }) => (
          <span className="font-mono tabular-nums text-sm text-muted-foreground">
            {row.original.secret_group ?? 0}
          </span>
        ),
      },
      {
        id: "entropy",
        accessorFn: (row) => row.entropy ?? -1,
        header: "熵值",
        meta: { label: "熵值", align: "center", width: 120 },
        cell: ({ row }) => (
          <span className="font-mono tabular-nums text-sm text-muted-foreground">
            {row.original.entropy === null || row.original.entropy === undefined
              ? "-"
              : row.original.entropy}
          </span>
        ),
      },
      {
        id: "source",
        accessorFn: (row) => row.source || "",
        header: "来源",
        meta: {
          label: "规则来源",
          width: 120,
          filterVariant: "select",
          filterOptions: sourceOptions,
        },
        cell: ({ row }) => (
          <Badge
            className={
              row.original.source === "builtin"
                ? "cyber-badge cyber-badge-info"
                : "cyber-badge cyber-badge-warning"
            }
          >
            {getSourceLabel(row.original.source)}
          </Badge>
        ),
      },
      {
        id: "status",
        accessorFn: (row) => (row.is_active ? "已启用" : "已禁用"),
        header: "启用状态",
        meta: { label: "启用状态", width: 120 },
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
      {
        id: "isActiveFilter",
        accessorFn: (row) => String(row.is_active),
        header: "启用筛选",
        enableHiding: false,
        meta: {
          label: "启用状态",
          filterVariant: "select",
          filterOptions: [
            { label: "已启用", value: "true" },
            { label: "已禁用", value: "false" },
          ],
        },
      },
      {
        id: "entropyRange",
        accessorFn: (row) => row.entropy ?? null,
        header: "熵值筛选",
        enableHiding: false,
        meta: {
          label: "熵值区间",
          filterVariant: "select",
          filterOptions: [
            { label: "高熵 (≥ 4)", value: "high" },
            { label: "中熵 (3 - 4)", value: "medium" },
            { label: "低熵 (0 - 3)", value: "low" },
            { label: "未设置熵值", value: "none" },
          ],
        },
        filterFn: (row, _columnId, filterValue) =>
          matchesEntropyRange(row.original, filterValue),
      },
      {
        id: "createdAt",
        accessorFn: (row) => row.created_at || "",
        header: "创建时间",
        meta: { label: "创建时间", width: 160 },
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">
            {formatDate(row.original.created_at)}
          </span>
        ),
      },
      {
        id: "actions",
        header: "操作",
        enableSorting: false,
        enableHiding: false,
        meta: { label: "操作", minWidth: 320 },
        cell: ({ row }) => {
          const builtinLocked = row.original.source === "builtin";
          return (
            <div className="flex flex-wrap items-center gap-2">
              {builtinLocked ? (
                <Badge className="cyber-badge cyber-badge-muted h-8 inline-flex items-center">
                  内置只读
                </Badge>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openEditDialog(row.original)}
                    className="cyber-btn-outline h-8 text-xs"
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (window.confirm(`确认删除规则「${row.original.name}」？`)) {
                        void handleDeleteRule(row.original);
                      }
                    }}
                    className="cyber-btn-outline h-8 text-xs"
                  >
                    删除
                  </Button>
                </>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleToggleRule(row.original)}
                className={row.original.is_active ? "cyber-btn-outline h-8 text-xs" : "cyber-btn-primary h-8 text-xs"}
              >
                {row.original.is_active ? "禁用" : "启用"}
              </Button>
            </div>
          );
        },
      },
    ],
    [sourceOptions],
  );

  const resetForm = () => {
    setFormData(DEFAULT_FORM);
    setEditingRule(null);
  };

  const openCreateDialog = () => {
    resetForm();
    setShowEditDialog(true);
  };

  const openEditDialog = (rule: GitleaksRule) => {
    setEditingRule(rule);
    setFormData({
      name: rule.name,
      description: rule.description || "",
      rule_id: rule.rule_id,
      secret_group: String(rule.secret_group ?? 0),
      regex: rule.regex,
      keywords: (rule.keywords || []).join(", "),
      path: rule.path || "",
      tags: (rule.tags || []).join(", "),
      entropy:
        rule.entropy !== null && rule.entropy !== undefined
          ? String(rule.entropy)
          : "",
      source: rule.source || "custom",
      is_active: rule.is_active,
    });
    setShowEditDialog(true);
  };

  const submitRule = async () => {
    if (editingRule?.source === "builtin") {
      toast.error("内置规则不支持直接编辑，请复制后创建自定义规则");
      return;
    }
    if (!formData.name.trim() || !formData.rule_id.trim() || !formData.regex.trim()) {
      toast.error("请填写规则名称、规则ID、正则表达式");
      return;
    }

    const payload = {
      name: formData.name.trim(),
      description: formData.description.trim() || undefined,
      rule_id: formData.rule_id.trim(),
      secret_group: Number(formData.secret_group || 0),
      regex: formData.regex.trim(),
      keywords: formData.keywords
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      path: formData.path.trim() || undefined,
      tags: formData.tags
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
      entropy: formData.entropy.trim() ? Number(formData.entropy) : undefined,
      source: formData.source.trim() || "custom",
      is_active: formData.is_active,
    };

    try {
      setSavingRule(true);
      if (editingRule) {
        await updateGitleaksRule(editingRule.id, payload);
        toast.success("规则更新成功");
      } else {
        await createGitleaksRule(payload);
        toast.success("规则创建成功");
      }
      setShowEditDialog(false);
      resetForm();
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "保存规则失败");
    } finally {
      setSavingRule(false);
    }
  };

  const handleDeleteRule = async (rule: GitleaksRule) => {
    if (rule.source === "builtin") {
      toast.error("内置规则不允许删除");
      return;
    }
    try {
      await deleteGitleaksRule(rule.id);
      toast.success(`规则「${rule.name}」已删除`);
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "删除规则失败");
    }
  };

  const handleToggleRule = async (rule: GitleaksRule) => {
    try {
      await updateGitleaksRule(rule.id, { is_active: !rule.is_active });
      await loadRules();
      toast.success(`规则已${rule.is_active ? "禁用" : "启用"}`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "更新规则失败");
    }
  };

  const handleBatchUpdate = async (
    selectedRows: GitleaksRule[],
    filteredRows: GitleaksRule[],
    isActive: boolean,
  ) => {
    const targetRows = selectedRows.length > 0 ? selectedRows : filteredRows;
    if (targetRows.length === 0) {
      toast.error("当前没有可操作的规则");
      return;
    }

    try {
      setBatchOperating(true);
      const result = await batchUpdateGitleaksRules({
        rule_ids: targetRows.map((row) => row.id),
        is_active: isActive,
      });
      toast.success(result.message);
      setTableState((current) => ({ ...current, rowSelection: {} }));
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量操作失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const engineSelector = showEngineSelector ? (
    <div className="min-w-[150px]">
      <Select
        value={engineValue}
        onValueChange={(value) => {
          if (
            value === "opengrep" ||
            value === "gitleaks" ||
            value === "bandit" ||
            value === "phpstan" ||
            value === "yasa"
          ) {
            onEngineChange?.(value);
          }
        }}
      >
        <SelectTrigger className="cyber-input h-9 min-w-[150px]">
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">有效规则总数</p>
              <div className="flex items-end gap-3">
                <p className="stat-value">{stats.total}</p>
                <p className="mb-1 flex items-center gap-3 text-sm">
                  <span className="inline-flex items-center gap-1 text-emerald-400">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                    已启用 {stats.active}
                  </span>
                </p>
              </div>
            </div>
            <div className="stat-icon text-primary">
              <Database className="h-6 w-6" />
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
              <AlertTriangle className="h-6 w-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">高熵规则数量</p>
              <p className="stat-value">{stats.highEntropyCount}</p>
            </div>
            <div className="stat-icon text-cyan-400">
              <Tag className="h-6 w-6" />
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        <DataTable
          data={rules}
          columns={columns}
          state={tableState}
          onStateChange={setTableState}
          loading={loading}
          error={loadError || undefined}
          emptyState={{
            title: "未找到规则",
            description:
              tableState.globalFilter || sourceFilter || activeFilter || entropyFilter
                ? "调整筛选条件尝试"
                : "暂无规则数据（系统将自动同步内置规则）",
          }}
          toolbar={{
            searchPlaceholder: "搜索名称/ID/正则...",
            filters: [
              {
                columnId: "source",
                label: "规则来源",
                variant: "select",
                options: sourceOptions,
              },
              {
                columnId: "entropyRange",
                label: "熵值区间",
                variant: "select",
                options: [
                  { label: "高熵 (≥ 4)", value: "high" },
                  { label: "中熵 (3 - 4)", value: "medium" },
                  { label: "低熵 (0 - 3)", value: "low" },
                  { label: "未设置熵值", value: "none" },
                ],
              },
              {
                columnId: "isActiveFilter",
                label: "启用状态",
                variant: "select",
                options: [
                  { label: "已启用", value: "true" },
                  { label: "已禁用", value: "false" },
                ],
              },
            ],
            leadingActions: engineSelector,
            trailingActions: (
              <Button className="cyber-btn-primary h-9" onClick={openCreateDialog}>
                新建规则
              </Button>
            ),
          }}
          selection={
            !loading && rules.length > 0
              ? {
                  enableRowSelection: true,
                  summary: buildSelectionSummary,
                  actions: ({ selectedRows, table }) => {
                    const filteredRows = table
                      .getFilteredRowModel()
                      .rows.map((row) => row.original);
                    return (
                      <>
                        <Button
                          onClick={() => void handleBatchUpdate(selectedRows, filteredRows, true)}
                          disabled={batchOperating}
                          className="cyber-btn-primary h-8 text-sm"
                        >
                          {batchOperating ? "处理中..." : "批量启用"}
                        </Button>
                        <Button
                          onClick={() => void handleBatchUpdate(selectedRows, filteredRows, false)}
                          disabled={batchOperating}
                          className="cyber-btn-outline h-8 text-sm"
                        >
                          {batchOperating ? "处理中..." : "批量禁用"}
                        </Button>
                      </>
                    );
                  },
                }
              : undefined
          }
          pagination={{ enabled: true, pageSizeOptions: [10, 20, 50] }}
          tableClassName="min-w-[1380px]"
          getRowId={(row) => row.id}
        />
      </div>

      <Dialog
        open={showEditDialog}
        onOpenChange={(open) => {
          setShowEditDialog(open);
          if (!open) resetForm();
        }}
      >
        <DialogContent className="cyber-dialog max-w-3xl max-h-[90vh] overflow-y-auto border-border">
          <DialogHeader>
            <DialogTitle>{editingRule ? "编辑 Gitleaks 规则" : "新建 Gitleaks 规则"}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label>规则名称 *</Label>
              <Input
                value={formData.name}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, name: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>规则ID *</Label>
              <Input
                value={formData.rule_id}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, rule_id: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>密钥分组</Label>
              <Input
                value={formData.secret_group}
                onChange={(event) =>
                  setFormData((current) => ({
                    ...current,
                    secret_group: event.target.value,
                  }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>来源</Label>
              <Input
                value={
                  editingRule?.source === "builtin"
                    ? getSourceLabel(editingRule.source)
                    : formData.source
                }
                onChange={(event) =>
                  setFormData((current) => ({ ...current, source: event.target.value }))
                }
                className="cyber-input mt-1.5"
                disabled={editingRule?.source === "builtin"}
              />
            </div>
            <div className="md:col-span-2">
              <Label>规则正则 *</Label>
              <Textarea
                value={formData.regex}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, regex: event.target.value }))
                }
                className="cyber-input mt-1.5 min-h-24 font-mono text-xs"
              />
            </div>
            <div className="md:col-span-2">
              <Label>描述</Label>
              <Textarea
                value={formData.description}
                onChange={(event) =>
                  setFormData((current) => ({
                    ...current,
                    description: event.target.value,
                  }))
                }
                className="cyber-input mt-1.5 min-h-20"
              />
            </div>
            <div>
              <Label>关键词（逗号分隔）</Label>
              <Input
                value={formData.keywords}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, keywords: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>标签（逗号分隔）</Label>
              <Input
                value={formData.tags}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, tags: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>路径正则（可选）</Label>
              <Input
                value={formData.path}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, path: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div>
              <Label>熵值（可选）</Label>
              <Input
                value={formData.entropy}
                onChange={(event) =>
                  setFormData((current) => ({ ...current, entropy: event.target.value }))
                }
                className="cyber-input mt-1.5"
              />
            </div>
            <div className="md:col-span-2 flex items-center gap-2 pt-1">
              <Checkbox
                checked={formData.is_active}
                onCheckedChange={(checked) =>
                  setFormData((current) => ({ ...current, is_active: checked === true }))
                }
              />
              <span className="text-sm">创建后立即启用</span>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              variant="outline"
              className="cyber-btn-outline"
              onClick={() => setShowEditDialog(false)}
            >
              取消
            </Button>
            <Button
              className="cyber-btn-primary"
              onClick={() => void submitRule()}
              disabled={savingRule || editingRule?.source === "builtin"}
            >
              {savingRule ? "保存中..." : "保存规则"}
            </Button>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <AlertTriangle className="h-3.5 w-3.5" />
            规则会在扫描执行前渲染为临时 TOML，传递给 gitleaks CLI。
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
