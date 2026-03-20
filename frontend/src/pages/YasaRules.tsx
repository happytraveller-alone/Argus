import { useEffect, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import { Copy, Database, Info, Shield, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  areDataTableQueryStatesEqual,
  DataTable,
  type AppColumnDef,
  type DataTableQueryState,
  type DataTableSelectionContext,
  useDataTableUrlState,
} from "@/components/data-table";
import { getYasaRules, type YasaRule } from "@/shared/api/yasa";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "yasa";

interface YasaRulesProps {
  showEngineSelector?: boolean;
  engineValue?: EngineTab;
  onEngineChange?: (value: EngineTab) => void;
}

interface YasaRuleRowViewModel {
  id: string;
  ruleName: string;
  languages: string[];
  source: "内置规则";
  confidence: "低";
  activeStatus: "已启用";
  verifyStatus: "✓ 可用";
  createdAt: "-";
  checkerPacks: string[];
  checkerPath: string;
  demoRuleConfigPath: string;
  description: string;
}

function toViewModel(rule: YasaRule): YasaRuleRowViewModel {
  return {
    id: rule.checker_id,
    ruleName: rule.checker_id,
    languages: rule.languages || [],
    source: "内置规则",
    confidence: "低",
    activeStatus: "已启用",
    verifyStatus: "✓ 可用",
    createdAt: "-",
    checkerPacks: rule.checker_packs || [],
    checkerPath: rule.checker_path || "-",
    demoRuleConfigPath: rule.demo_rule_config_path || "-",
    description: rule.description || "-",
  };
}

function buildColumns(
  onOpenDetail: (row: YasaRuleRowViewModel) => void,
  onCopyRule: (row: YasaRuleRowViewModel) => Promise<void>,
): AppColumnDef<YasaRuleRowViewModel, unknown>[] {
  return [
    {
      id: "rowNumber",
      header: "序号",
      enableSorting: false,
      meta: {
        label: "序号",
        align: "center",
        width: 64,
      },
      cell: ({ row, table }) =>
        table.getState().pagination.pageIndex * table.getState().pagination.pageSize +
        row.index +
        1,
    },
    {
      accessorKey: "ruleName",
      header: "规则名称",
      meta: {
        label: "规则名称",
        filterVariant: "text",
      },
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.ruleName}</span>,
    },
    {
      id: "languages",
      accessorFn: (row) => row.languages.join(","),
      header: "编程语言",
      meta: {
        label: "编程语言",
        filterVariant: "select",
        filterOptions: [
          { label: "python", value: "python" },
          { label: "javascript", value: "javascript" },
          { label: "typescript", value: "typescript" },
          { label: "golang", value: "golang" },
          { label: "java", value: "java" },
        ],
      },
      filterFn: (row, columnId, filterValue) => {
        if (!filterValue) return true;
        const languages = row.original.languages || [];
        return languages.includes(String(filterValue));
      },
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {row.original.languages.length > 0 ? (
            row.original.languages.map((language) => (
              <Badge key={`${row.original.id}-${language}`} className="cyber-badge-info">
                {language}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">未标注</span>
          )}
        </div>
      ),
    },
    {
      accessorKey: "source",
      header: "规则来源",
      meta: {
        label: "规则来源",
        filterVariant: "select",
        filterOptions: [{ label: "内置规则", value: "内置规则" }],
      },
      cell: ({ row }) => <Badge className="cyber-badge-info">{row.original.source}</Badge>,
    },
    {
      accessorKey: "confidence",
      header: "置信度",
      meta: {
        label: "置信度",
        filterVariant: "select",
        filterOptions: [{ label: "低", value: "低" }],
      },
      cell: ({ row }) => <Badge className="cyber-badge-info">{row.original.confidence}</Badge>,
    },
    {
      accessorKey: "activeStatus",
      header: "启用状态",
      meta: {
        label: "启用状态",
        filterVariant: "select",
        filterOptions: [{ label: "已启用", value: "已启用" }],
      },
      cell: ({ row }) => <Badge className="cyber-badge-success">{row.original.activeStatus}</Badge>,
    },
    {
      accessorKey: "verifyStatus",
      header: "验证状态",
      meta: {
        label: "验证状态",
      },
      cell: ({ row }) => <span className="text-emerald-400">{row.original.verifyStatus}</span>,
    },
    {
      accessorKey: "createdAt",
      header: "创建时间",
      meta: {
        label: "创建时间",
      },
    },
    {
      id: "checkerPack",
      accessorFn: (row) => row.checkerPacks.join(","),
      header: "CheckerPack",
      meta: {
        label: "CheckerPack",
        filterVariant: "select",
      },
      cell: ({ row }) => (
        <div className="flex flex-wrap gap-1">
          {row.original.checkerPacks.length > 0 ? (
            row.original.checkerPacks.map((pack) => (
              <Badge key={`${row.original.id}-${pack}`} className="cyber-badge-muted">
                {pack}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">-</span>
          )}
        </div>
      ),
    },
    {
      id: "actions",
      header: "操作",
      enableSorting: false,
      meta: {
        label: "操作",
        minWidth: 220,
      },
      cell: ({ row }) => (
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            className="text-primary hover:text-primary/80"
            onClick={() => onOpenDetail(row.original)}
          >
            详情
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-primary hover:text-primary/80"
            onClick={() => void onCopyRule(row.original)}
          >
            <Copy className="h-3 w-3" />
            复制
          </button>
          <span className="cursor-not-allowed text-muted-foreground/50">编辑</span>
          <span className="cursor-not-allowed text-muted-foreground/50">禁用</span>
          <span className="cursor-not-allowed text-muted-foreground/50">删除</span>
        </div>
      ),
    },
  ];
}

function buildSelectionSummary({
  selectedCount,
  filteredCount,
}: DataTableSelectionContext<YasaRuleRowViewModel>) {
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

export default function YasaRules({
  showEngineSelector = false,
  engineValue = "yasa",
  onEngineChange,
}: YasaRulesProps) {
  const [rules, setRules] = useState<YasaRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [detailRule, setDetailRule] = useState<YasaRuleRowViewModel | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const { initialState, syncStateToUrl } = useDataTableUrlState(true);
  const [tableState, setTableState] = useState<DataTableQueryState>(() =>
    createInitialTableState(initialState),
  );
  const resolvedUrlState = useMemo(
    () => createInitialTableState(initialState),
    [initialState],
  );

  const loadRules = async () => {
    try {
      setLoading(true);
      setLoadFailed(false);
      const data = await getYasaRules({ limit: 2000 });
      setRules(data);
    } catch (error: any) {
      setLoadFailed(true);
      const detail =
        error?.response?.data?.detail ||
        "未找到 YASA 资源目录，请检查 YASA_RESOURCE_DIR 或本机安装";
      toast.error(String(detail));
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

  const rows = useMemo(() => rules.map(toViewModel), [rules]);
  const checkerPackOptions = useMemo(
    () =>
      Array.from(
        new Set(
          rows.flatMap((rule) => rule.checkerPacks).filter((item) => item && item.trim()),
        ),
      ).sort(),
    [rows],
  );

  const stats = useMemo(() => {
    const languageCount = new Set(rows.flatMap((item) => item.languages)).size;
    return {
      total: rows.length,
      active: rows.length,
      checkerPackCount: checkerPackOptions.length,
      languageCount,
    };
  }, [rows, checkerPackOptions.length]);

  const columns = useMemo<ColumnDef<YasaRuleRowViewModel>[]>(
    () => buildColumns(
      (row) => {
        setDetailRule(row);
        setShowDetail(true);
      },
      async (row) => {
        try {
          const text = JSON.stringify(
            {
              checker_id: row.id,
              checker_packs: row.checkerPacks,
              languages: row.languages,
              checker_path: row.checkerPath,
              demo_rule_config_path: row.demoRuleConfigPath,
            },
            null,
            2,
          );
          await navigator.clipboard.writeText(text);
          toast.success(`已复制规则: ${row.id}`);
        } catch {
          toast.error("复制失败，请手动复制");
        }
      },
    ),
    [],
  );

  const checkerPackFilterOptions = useMemo(
    () => checkerPackOptions.map((option) => ({ label: option, value: option })),
    [checkerPackOptions],
  );

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
      <div className="relative z-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
              <p className="stat-label">CheckerPack 数量</p>
              <p className="stat-value">{stats.checkerPackCount}</p>
            </div>
            <div className="stat-icon text-indigo-400">
              <Tag className="h-6 w-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">支持语言数量</p>
              <p className="stat-value">{stats.languageCount}</p>
            </div>
            <div className="stat-icon text-cyan-400">
              <Shield className="h-6 w-6" />
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-card p-4">
        <p className="text-sm text-muted-foreground">
          YASA 规则来自本机 yasa-engine 资源，当前为只读展示。
        </p>
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        <DataTable
          data={rows}
          columns={columns}
          state={tableState}
          onStateChange={setTableState}
          loading={loading}
          emptyState={{
            title: loadFailed ? "加载失败，请检查 YASA 资源目录配置" : "暂无符合条件的规则",
          }}
          toolbar={{
            searchPlaceholder: "搜索规则名称或ID...",
            filters: [
              {
                columnId: "languages",
                label: "编程语言",
                variant: "select",
                options: [
                  { label: "python", value: "python" },
                  { label: "javascript", value: "javascript" },
                  { label: "typescript", value: "typescript" },
                  { label: "golang", value: "golang" },
                  { label: "java", value: "java" },
                ],
              },
              {
                columnId: "source",
                label: "规则来源",
                variant: "select",
                options: [{ label: "内置规则", value: "内置规则" }],
              },
              {
                columnId: "confidence",
                label: "置信度",
                variant: "select",
                options: [{ label: "低", value: "低" }],
              },
              {
                columnId: "activeStatus",
                label: "启用状态",
                variant: "select",
                options: [{ label: "已启用", value: "已启用" }],
              },
              {
                columnId: "checkerPack",
                label: "CheckerPack",
                variant: "select",
                options: checkerPackFilterOptions,
              },
            ],
            leadingActions: engineSelector,
          }}
          selection={{
            enableRowSelection: true,
            summary: buildSelectionSummary,
            actions: () => (
              <>
                <Button type="button" size="sm" className="cyber-btn-primary h-8" disabled>
                  批量启用
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="cyber-btn-outline h-8"
                  disabled
                >
                  批量禁用
                </Button>
                <Button type="button" size="sm" variant="ghost" className="h-8 text-muted-foreground" disabled>
                  取消操作
                </Button>
              </>
            ),
          }}
          summary={
            <div className="flex items-center gap-1 text-xs text-amber-300">
              <Info className="h-3 w-3" />
              YASA 规则当前只读，暂不支持启停写回
            </div>
          }
          pagination={{
            enabled: true,
            pageSizeOptions: [10, 20, 50],
          }}
          tableClassName="min-w-[1240px]"
        />
      </div>

      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="cyber-dialog max-w-3xl border border-border">
          <DialogHeader>
            <DialogTitle>YASA 规则详情</DialogTitle>
          </DialogHeader>
          {detailRule ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <p className="text-muted-foreground">规则名称</p>
                  <p className="font-mono break-all">{detailRule.ruleName}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">规则来源</p>
                  <p>{detailRule.source}</p>
                </div>
              </div>
              <div>
                <p className="text-muted-foreground">语言映射</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {detailRule.languages.length > 0 ? (
                    detailRule.languages.map((language) => (
                      <Badge key={`detail-${detailRule.id}-${language}`} className="cyber-badge-info">
                        {language}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground">未标注</span>
                  )}
                </div>
              </div>
              <div>
                <p className="text-muted-foreground">CheckerPack</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {detailRule.checkerPacks.length > 0 ? (
                    detailRule.checkerPacks.map((pack) => (
                      <Badge key={`detail-${detailRule.id}-${pack}`} className="cyber-badge-muted">
                        {pack}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </div>
              </div>
              <div>
                <p className="text-muted-foreground">规则路径</p>
                <p className="font-mono break-all">{detailRule.checkerPath}</p>
              </div>
              <div>
                <p className="text-muted-foreground">demo rule config 路径</p>
                <p className="font-mono break-all">{detailRule.demoRuleConfigPath}</p>
              </div>
              <div>
                <p className="text-muted-foreground">规则描述</p>
                <p className="whitespace-pre-wrap">{detailRule.description}</p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function createInitialTableState(initialState: DataTableQueryState): DataTableQueryState {
  return {
    ...initialState,
    pagination: {
      pageIndex: initialState.pagination.pageIndex,
      pageSize: initialState.pagination.pageSize || 10,
    },
  };
}
