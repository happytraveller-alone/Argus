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
import { Textarea } from "@/components/ui/textarea";
import {
  areDataTableQueryStatesEqual,
  createDefaultDataTableState,
  DataTable,
  type AppColumnDef,
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
import { Code2, Copy, Database, FileCode2, Shield, Upload } from "lucide-react";
import {
  importPmdRuleConfig,
  type PmdPreset,
  type PmdRuleConfig,
  type PmdRulesetSummary,
} from "@/shared/api/pmd";
import {
  PMD_CUSTOM_RULE_CONFIGS_LOAD_ERROR_FALLBACK,
  PMD_PRESETS_LOAD_ERROR_FALLBACK,
  loadPmdRulesPageData,
  type PmdRulesLoaderResult,
} from "@/pages/pmdRulesLoader";
import {
  isScanEngineTab,
  SCAN_ENGINE_SELECTOR_OPTIONS,
  type ScanEngineTab,
} from "@/shared/constants/scanEngines";

interface PmdRulesProps {
  showEngineSelector?: boolean;
  engineValue?: ScanEngineTab;
  onEngineChange?: (value: ScanEngineTab) => void;
}

type PmdRulesRow = PmdRulesetSummary | PmdRuleConfig;

export interface PmdImportDialogContentProps {
  importName: string;
  importDescription: string;
  importing: boolean;
  onImportNameChange: (value: string) => void;
  onImportDescriptionChange: (value: string) => void;
  onImportFileChange: (file: File | null) => void;
  onImport: () => void | Promise<void>;
}

const DEFAULT_PAGE_SIZE = 10;

function createInitialTableState(initialState: DataTableQueryState): DataTableQueryState {
  return createDefaultDataTableState({
    ...initialState,
    pagination: {
      pageIndex: initialState.pagination.pageIndex,
      pageSize: initialState.pagination.pageSize || DEFAULT_PAGE_SIZE,
    },
  });
}


function getSourceLabel(source: string) {
  return source === "custom" ? "自定义 ruleset" : "内置 ruleset";
}

function DetailSectionTitle({ children }: { children: string }) {
  return (
    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
      {children}
    </h3>
  );
}

function DetailInfoCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-md border border-border/60 bg-muted/30 p-3">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className={`mt-2 text-sm text-foreground break-all ${mono ? "font-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function buildSelectionSummary({
  selectedCount,
  filteredCount,
}: DataTableSelectionContext<PmdRulesRow>) {
  if (selectedCount > 0) {
    return (
      <>
        已选择 <span className="font-bold text-primary">{selectedCount}</span> 个 ruleset
      </>
    );
  }

  return (
    <>
      将对全部 <span className="font-bold text-primary">{filteredCount}</span> 个 ruleset 进行操作
    </>
  );
}

export function PmdImportDialogContent({
  importName,
  importDescription,
  importing,
  onImportNameChange,
  onImportDescriptionChange,
  onImportFileChange,
  onImport,
}: PmdImportDialogContentProps) {
  return (
    <div className="space-y-4 text-sm">
      <div>
        <h2 className="text-lg font-semibold">导入自定义规则</h2>
        <p className="text-sm text-muted-foreground">
          上传自定义 PMD XML ruleset，并复用后端共享解析结果。
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_1fr]">
        <Input
          value={importName}
          onChange={(event) => onImportNameChange(event.target.value)}
          placeholder="输入 ruleset 名称"
          className="cyber-input"
        />
        <Input
          type="file"
          accept=".xml,text/xml,application/xml"
          className="cyber-input"
          onChange={(event) => onImportFileChange(event.target.files?.[0] || null)}
        />
      </div>
      <Textarea
        value={importDescription}
        onChange={(event) => onImportDescriptionChange(event.target.value)}
        placeholder="可选：填写 ruleset 描述"
        className="cyber-input min-h-[96px]"
      />
      <div className="flex justify-end">
        <Button
          type="button"
          className="cyber-btn-primary h-9"
          onClick={() => void onImport()}
          disabled={importing}
        >
          {importing ? "导入中..." : "导入 XML ruleset"}
        </Button>
      </div>
    </div>
  );
}

export function PmdRulesetDetailPanel({
  ruleset,
  onCopyRawXml,
}: {
  ruleset: PmdRulesRow;
  onCopyRawXml: () => void | Promise<void>;
}) {
  const languages = (ruleset.languages || []).filter((language) => language && language.trim());
  const description = ruleset.description?.trim() || "暂无 ruleset 说明";
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="space-y-6">
        <div className="rounded-md border border-border/60 bg-muted/30 p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <p className="font-mono text-xs uppercase tracking-[0.22em] text-primary">
                Ruleset Overview
              </p>
              <div>
                <h3 className="text-xl font-semibold break-all text-foreground">
                  {ruleset.name}
                </h3>
                <p className="mt-1 font-mono text-xs text-muted-foreground break-all">
                  {ruleset.filename}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge className="cyber-badge cyber-badge-info">
                {getSourceLabel(ruleset.source)}
              </Badge>
              <Badge
                className={
                  ruleset.is_active
                    ? "cyber-badge cyber-badge-success"
                    : "cyber-badge cyber-badge-muted"
                }
              >
                {ruleset.is_active ? "启用" : "禁用"}
              </Badge>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <DetailSectionTitle>基本信息</DetailSectionTitle>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <DetailInfoCard label="名称" value={ruleset.name || "-"} />
            <DetailInfoCard label="文件名" value={ruleset.filename || "-"} mono />
            <DetailInfoCard
              label="Ruleset 标识"
              value={ruleset.ruleset_name?.trim() || "未标注 ruleset 标识"}
              mono
            />
            <DetailInfoCard label="规则数" value={String(ruleset.rule_count ?? 0)} mono />
            <div className="rounded-md border border-border/60 bg-muted/30 p-3">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                编程语言
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {languages.length > 0 ? (
                  languages.map((language) => (
                    <Badge key={`${ruleset.id}-${language}`} className="cyber-badge cyber-badge-info">
                      {language}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">未标注</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <DetailSectionTitle>说明信息</DetailSectionTitle>
          <div className="rounded-md border border-border/60 bg-muted/20 p-4">
            <p className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground">
              {description}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <DetailSectionTitle>原始 XML</DetailSectionTitle>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void onCopyRawXml()}
              className="cyber-btn-ghost h-7 text-xs"
            >
              <Copy className="mr-1 h-3 w-3" />
              复制 XML
            </Button>
          </div>
          <div className="rounded-md border border-border bg-background/70 p-4 shadow-inner">
            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-foreground">
              {ruleset.raw_xml?.trim() || "<ruleset />"}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PmdRules({
  showEngineSelector = false,
  engineValue = "pmd",
  onEngineChange,
}: PmdRulesProps) {
  const [loading, setLoading] = useState(true);
  const [, setPresets] = useState<PmdPreset[]>([]);
  const [builtinRulesets, setBuiltinRulesets] = useState<PmdRulesetSummary[]>([]);
  const [customRuleConfigs, setCustomRuleConfigs] = useState<PmdRuleConfig[]>([]);
  const [builtinLoadError, setBuiltinLoadError] = useState<string | null>(null);
  const [presetsLoadError, setPresetsLoadError] = useState<string | null>(null);
  const [customConfigsLoadError, setCustomConfigsLoadError] = useState<string | null>(null);
  const [selectedRuleset, setSelectedRuleset] = useState<PmdRulesRow | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importName, setImportName] = useState("");
  const [importDescription, setImportDescription] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const { initialState, syncStateToUrl } = useDataTableUrlState(true);
  const [tableState, setTableState] = useState<DataTableQueryState>(() =>
    createInitialTableState(initialState),
  );
  const resolvedUrlState = useMemo(
    () => createInitialTableState(initialState),
    [initialState],
  );

  const applyLoaderResult = (result: PmdRulesLoaderResult) => {
    setPresets(result.presets);
    setBuiltinRulesets(result.builtinRulesets);
    setCustomRuleConfigs(result.customRuleConfigs);
    setBuiltinLoadError(result.builtinLoadError);
    setPresetsLoadError(result.presetsLoadError);
    setCustomConfigsLoadError(result.customConfigsLoadError);
  };

  const loadPageData = async () => {
    try {
      setLoading(true);
      const result = await loadPmdRulesPageData();
      applyLoaderResult(result);
      if (result.builtinLoadError) {
        toast.error(result.builtinLoadError);
      }
      if (result.presetsLoadError) {
        toast.error(result.presetsLoadError || PMD_PRESETS_LOAD_ERROR_FALLBACK);
      }
      if (result.customConfigsLoadError) {
        toast.error(
          result.customConfigsLoadError ||
          PMD_CUSTOM_RULE_CONFIGS_LOAD_ERROR_FALLBACK,
        );
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPageData();
  }, []);

  useEffect(() => {
    setTableState((current) =>
      areDataTableQueryStatesEqual(current, resolvedUrlState) ? current : resolvedUrlState,
    );
  }, [resolvedUrlState]);

  useEffect(() => {
    syncStateToUrl(tableState);
  }, [syncStateToUrl, tableState]);

  const rows = useMemo(
    () => [...builtinRulesets, ...customRuleConfigs],
    [builtinRulesets, customRuleConfigs],
  );

  const stats = useMemo(() => {
    const active = rows.filter((row) => row.is_active).length;
    return {
      total: rows.length,
      builtin: builtinRulesets.length,
      custom: customRuleConfigs.length,
      active,
    };
  }, [builtinRulesets.length, customRuleConfigs.length, rows]);

  const languageOptions = useMemo(
    () =>
      Array.from(new Set(rows.flatMap((row) => row.languages || []).filter(Boolean)))
        .sort()
        .map((language) => ({ label: language, value: language })),
    [rows],
  );

  const engineSelector = showEngineSelector ? (
    <div className="min-w-[150px]">
      <Select
        value={engineValue}
        onValueChange={(value) => {
          if (isScanEngineTab(value)) {
            onEngineChange?.(value);
          }
        }}
      >
        <SelectTrigger className="cyber-input h-10 min-w-[150px]">
          <SelectValue placeholder="选择引擎" />
        </SelectTrigger>
        <SelectContent className="cyber-dialog border-border">
          {SCAN_ENGINE_SELECTOR_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  ) : null;

  const columns = useMemo<AppColumnDef<PmdRulesRow, unknown>[]>(
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
        id: "ruleset",
        accessorFn: (row) =>
          [row.name, row.ruleset_name, row.filename, row.description].filter(Boolean).join(" "),
        header: "规则集",
        enableSorting: false,
        enableHiding: false,
        meta: { label: "规则集", filterVariant: "text", minWidth: 220 },
        cell: ({ row }) => (
          <div className="space-y-1">
            <div className="font-semibold text-foreground break-all">{row.original.name}</div>
          </div>
        ),
      },
      {
        accessorKey: "source",
        header: "来源",
        enableSorting: false,
        enableHiding: false,
        meta: {
          label: "来源",
          filterVariant: "select",
          filterOptions: [
            { label: "内置 ruleset", value: "builtin" },
            { label: "自定义 ruleset", value: "custom" },
          ],
        },
        cell: ({ row }) => (
          <Badge className="cyber-badge-info">{getSourceLabel(row.original.source)}</Badge>
        ),
      },
      {
        id: "languages",
        accessorFn: (row) => row.languages.join(","),
        header: "语言",
        enableSorting: false,
        meta: {
          label: "语言",
          filterVariant: "select",
          filterOptions: languageOptions,
        },
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.languages.length > 0 ? (
              row.original.languages.map((language) => (
                <Badge key={`${row.original.id}-${language}`} className="cyber-badge-muted">
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
        id: "active",
        accessorFn: (row) => (row.is_active ? "启用" : "禁用"),
        header: "启用状态",
        enableSorting: false,
        meta: {
          label: "启用状态",
          filterVariant: "select",
          filterOptions: [
            { label: "启用", value: "启用" },
            { label: "禁用", value: "禁用" },
          ],
        },
        cell: ({ row }) => (
          <Badge className={row.original.is_active ? "cyber-badge-success" : "cyber-badge-muted"}>
            {row.original.is_active ? "启用" : "禁用"}
          </Badge>
        ),
      },
      {
        id: "actions",
        header: "操作",
        enableSorting: false,
        meta: { label: "操作", align: "center", width: 96 },
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8"
            onClick={() => {
              setSelectedRuleset(row.original);
              setShowDetail(true);
            }}
          >
            查看
          </Button>
        ),
      },
    ],
    [languageOptions],
  );

  const handleImport = async () => {
    if (!importName.trim()) {
      toast.error("请输入 ruleset 名称");
      return;
    }
    if (!importFile) {
      toast.error("请上传 XML ruleset 文件");
      return;
    }

    try {
      setImporting(true);
      await importPmdRuleConfig({
        name: importName.trim(),
        description: importDescription.trim() || undefined,
        xmlFile: importFile,
      });
      toast.success("PMD 自定义 ruleset 导入成功");
      setShowImportDialog(false);
      setImportName("");
      setImportDescription("");
      setImportFile(null);
      await loadPageData();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "导入 PMD ruleset 失败");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">有效规则总数</p>
              <p className="stat-value">{stats.total}</p>
            </div>
            <div className="stat-icon text-primary">
              <Shield className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">内置规则</p>
              <p className="stat-value">{stats.builtin}</p>
            </div>
            <div className="stat-icon text-cyan-400">
              <Database className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">自定义规则</p>
              <p className="stat-value">{stats.custom}</p>
            </div>
            <div className="stat-icon text-indigo-400">
              <Upload className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">启用状态</p>
              <p className="stat-value">{stats.active}</p>
            </div>
            <div className="stat-icon text-emerald-400">
              <FileCode2 className="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      {presetsLoadError ? (
        <div
          role="status"
          className="rounded border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200"
        >
          {presetsLoadError}
        </div>
      ) : null}

      {customConfigsLoadError ? (
        <div
          role="status"
          className="rounded border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200"
        >
          {customConfigsLoadError}
        </div>
      ) : null}

      {/* <div className="cyber-card space-y-4 overflow-hidden p-4"> */}
      <DataTable
        data={rows}
        columns={columns}
        state={tableState}
        onStateChange={setTableState}
        loading={loading}
        error={builtinLoadError || undefined}
        emptyState={{
          title: "暂无可展示的 PMD ruleset",
          description:
            builtinRulesets.length === 0 && customRuleConfigs.length === 0
              ? "当前没有可展示的 PMD ruleset"
              : "调整筛选条件后重试",
        }}
        toolbar={{
          searchPlaceholder: "搜索名称、文件名或描述...",
          leadingActions: engineSelector,
          showGlobalSearch: false,
          showColumnVisibility: false,
          showDensityToggle: false,
          showReset: false,
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
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 text-muted-foreground"
                disabled
              >
                取消操作
              </Button>
              <Button
                type="button"
                size="sm"
                className="cyber-btn-primary h-9"
                onClick={() => setShowImportDialog(true)}
              >
                导入自定义规则
              </Button>
            </>
          ),
        }}
        pagination={{ enabled: true, pageSizeOptions: [10, 20, 50] }}
        tableClassName="min-w-[1180px]"
        getRowId={(row) => row.id}
      />
      {/* </div> */}

      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="!w-[min(92vw,980px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
          <DialogHeader className="px-6 pt-4 flex-shrink-0 border-b border-border bg-muted/30">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Code2 className="w-5 h-5 text-primary" />
              PMD ruleset 详情
            </DialogTitle>
          </DialogHeader>
          {selectedRuleset ? (
            <PmdRulesetDetailPanel
              ruleset={selectedRuleset}
              onCopyRawXml={async () => {
                try {
                  await navigator.clipboard.writeText(selectedRuleset.raw_xml || "");
                  toast.success("已复制 XML");
                } catch {
                  toast.error("复制失败，请手动复制");
                }
              }}
            />
          ) : null}
          <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
            <Button
              type="button"
              variant="outline"
              onClick={() => setShowDetail(false)}
              className="cyber-btn-outline"
            >
              关闭
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="cyber-dialog max-w-3xl border border-border">
          <DialogHeader>
            <DialogTitle>导入自定义规则</DialogTitle>
          </DialogHeader>
          <PmdImportDialogContent
            importName={importName}
            importDescription={importDescription}
            importing={importing}
            onImportNameChange={setImportName}
            onImportDescriptionChange={setImportDescription}
            onImportFileChange={setImportFile}
            onImport={handleImport}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
