import { useEffect, useMemo, useRef, useState } from "react";
import {
  DatabaseBackup,
  Download,
  FileArchive,
  RefreshCw,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api, type ProjectImportResponse } from "@/shared/api/database";
import type { Project } from "@/shared/types";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function formatReason(reason?: string | null) {
  if (!reason) return "未提供原因";
  return reason.replace(/_/g, " ");
}

export default function DataManagementPage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [projectFilter, setProjectFilter] = useState("");
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([]);
  const [includeArchives, setIncludeArchives] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedBundle, setSelectedBundle] = useState<File | null>(null);
  const [importSummary, setImportSummary] = useState<ProjectImportResponse | null>(null);

  const visibleProjects = useMemo(() => {
    const keyword = projectFilter.trim().toLowerCase();
    if (!keyword) return projects;
    return projects.filter((project) => {
      const name = String(project.name || "").toLowerCase();
      const description = String(project.description || "").toLowerCase();
      return name.includes(keyword) || description.includes(keyword);
    });
  }, [projectFilter, projects]);

  const visibleProjectIds = useMemo(
    () => visibleProjects.map((project) => project.id),
    [visibleProjects],
  );
  const allVisibleSelected =
    visibleProjectIds.length > 0 &&
    visibleProjectIds.every((projectId) => selectedProjectIds.includes(projectId));

  async function loadProjects() {
    setLoadingProjects(true);
    try {
      const data = await api.getProjects({ limit: 500 });
      setProjects(data);
      setSelectedProjectIds((current) =>
        current.filter((projectId) => data.some((project) => project.id === projectId)),
      );
    } catch (error) {
      console.error("Failed to load projects for transfer panel:", error);
      toast.error("加载项目列表失败");
    } finally {
      setLoadingProjects(false);
    }
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  function toggleProject(projectId: string, checked: boolean) {
    setSelectedProjectIds((current) => {
      if (checked) {
        return current.includes(projectId) ? current : [...current, projectId];
      }
      return current.filter((id) => id !== projectId);
    });
  }

  function toggleSelectVisible(checked: boolean) {
    setSelectedProjectIds((current) => {
      const remaining = current.filter((id) => !visibleProjectIds.includes(id));
      return checked ? [...remaining, ...visibleProjectIds] : remaining;
    });
  }

  async function handleExport(scope: "selected" | "all") {
    if (scope === "selected" && selectedProjectIds.length === 0) {
      toast.error("请至少选择一个项目");
      return;
    }

    setExporting(true);
    try {
      const result = await api.exportProjectBundle({
        projectIds: scope === "selected" ? selectedProjectIds : undefined,
        includeArchives,
      });
      downloadBlob(result.blob, result.filename);
      toast.success(
        scope === "selected"
          ? `已导出 ${selectedProjectIds.length} 个项目`
          : "已导出当前用户全部项目",
        {
          description: includeArchives
            ? "迁移包已包含项目 ZIP 源码归档。"
            : "迁移包仅包含数据库记录，不含项目 ZIP 源码归档。",
        },
      );
    } catch (error: any) {
      console.error("Failed to export project bundle:", error);
      toast.error(error?.response?.data?.detail || "导出项目迁移包失败");
    } finally {
      setExporting(false);
    }
  }

  async function handleImport() {
    if (!selectedBundle) {
      toast.error("请先选择迁移包文件");
      return;
    }

    setImporting(true);
    try {
      const result = await api.importProjectBundle(selectedBundle);
      setImportSummary(result);
      await loadProjects();

      const importedCount = result.imported_projects.length;
      const skippedCount = result.skipped_projects.length;
      const failedCount = result.failed_projects.length;
      const warningCount = result.warnings.length;
      if (failedCount > 0) {
        toast.warning(`导入完成：成功 ${importedCount} / 跳过 ${skippedCount} / 失败 ${failedCount}`, {
          description:
            warningCount > 0 ? `另有 ${warningCount} 条警告，请查看下方详情。` : undefined,
        });
      } else if (warningCount > 0) {
        toast.warning(`导入完成：成功 ${importedCount} / 跳过 ${skippedCount}`, {
          description: `存在 ${warningCount} 条警告，请查看下方详情。`,
        });
      } else {
        toast.success(`导入完成：成功 ${importedCount} / 跳过 ${skippedCount}`);
      }
    } catch (error: any) {
      console.error("Failed to import project bundle:", error);
      toast.error(error?.response?.data?.detail || "导入项目迁移包失败");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col gap-6 bg-background p-6 font-mono">
      <div className="pointer-events-none absolute inset-0 cyber-grid-subtle" />

      <div className="relative z-10 flex items-center gap-3">
        <DatabaseBackup className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-bold tracking-tight text-foreground">数据管理</h1>
      </div>

      <div className="relative z-10 grid flex-1 gap-6 xl:grid-cols-[1.4fr_1fr]">
          <div className="rounded-lg border border-border bg-card p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Download className="h-4 w-4 text-cyan-400" />
                导出迁移包
              </h2>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-muted-foreground"
                onClick={() => void loadProjects()}
                disabled={loadingProjects}
              >
                <RefreshCw className={`h-3 w-3 ${loadingProjects ? "animate-spin" : ""}`} />
                刷新
              </Button>
            </div>

            <div className="mb-3 flex items-center gap-3">
              <Input
                value={projectFilter}
                onChange={(event) => setProjectFilter(event.target.value)}
                placeholder="搜索项目"
                className="h-8 text-sm"
              />
              <Label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                <Checkbox
                  checked={includeArchives}
                  onCheckedChange={(checked) => setIncludeArchives(checked === true)}
                />
                含源码
              </Label>
            </div>

            <div className="mb-3 flex items-center gap-3 text-xs text-muted-foreground">
              <Label className="flex items-center gap-1.5">
                <Checkbox
                  checked={allVisibleSelected}
                  onCheckedChange={(checked) => toggleSelectVisible(checked === true)}
                />
                全选
              </Label>
              <span>共 {projects.length}</span>
              <span>筛选 {visibleProjects.length}</span>
              <Badge variant="outline" className="text-[11px]">
                已选 {selectedProjectIds.length}
              </Badge>
            </div>

            <div className="max-h-[22rem] space-y-1.5 overflow-y-auto rounded-md border border-border/40 bg-muted/5 p-2">
              {loadingProjects ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  加载中...
                </div>
              ) : visibleProjects.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">
                  没有匹配的项目
                </div>
              ) : (
                visibleProjects.map((project) => {
                  const checked = selectedProjectIds.includes(project.id);
                  return (
                    <label
                      key={project.id}
                      className={`flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-muted/30 ${checked ? "bg-muted/20" : ""}`}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(next) => toggleProject(project.id, next === true)}
                      />
                      <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                        {project.name}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {project.source_type || "zip"}
                      </span>
                    </label>
                  );
                })
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <Button
                type="button"
                size="sm"
                className="gap-1.5"
                disabled={exporting || loadingProjects || selectedProjectIds.length === 0}
                onClick={() => void handleExport("selected")}
              >
                <Download className="h-3.5 w-3.5" />
                {exporting ? "导出中..." : "导出选中"}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={exporting || loadingProjects || projects.length === 0}
                onClick={() => void handleExport("all")}
              >
                <DatabaseBackup className="h-3.5 w-3.5" />
                {exporting ? "导出中..." : "导出全部"}
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <div className="rounded-lg border border-border bg-card p-5">
              <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
                <Upload className="h-4 w-4 text-cyan-400" />
                导入迁移包
              </h2>

              <div className="space-y-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0] || null;
                    setSelectedBundle(file);
                  }}
                />
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <FileArchive className="h-3.5 w-3.5" />
                    选择文件
                  </Button>
                  {selectedBundle ? (
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                      {selectedBundle.name}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">未选择文件</span>
                  )}
                </div>
                <Button
                  type="button"
                  size="sm"
                  className="w-full gap-1.5"
                  disabled={importing || !selectedBundle}
                  onClick={() => void handleImport()}
                >
                  <Upload className="h-3.5 w-3.5" />
                  {importing ? "导入中..." : "开始导入"}
                </Button>
              </div>
            </div>

            {importSummary ? (
              <div className="rounded-lg border border-border bg-card p-5">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold text-foreground">导入结果</h2>
                  <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                    成功 {importSummary.imported_projects.length}
                  </Badge>
                  <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-300">
                    跳过 {importSummary.skipped_projects.length}
                  </Badge>
                  <Badge className="border-rose-500/30 bg-rose-500/10 text-rose-300">
                    失败 {importSummary.failed_projects.length}
                  </Badge>
                </div>

                <div className="space-y-2 text-xs">
                  {importSummary.imported_projects.map((item) => (
                    <div key={`${item.source_project_id}-${item.project_id}`} className="flex items-center gap-2 rounded-md bg-emerald-500/5 px-3 py-2">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                      <span className="font-medium text-foreground">{item.name || item.source_project_id}</span>
                    </div>
                  ))}
                  {importSummary.skipped_projects.map((item) => (
                    <div key={`${item.source_project_id}-${item.reason || "skip"}`} className="flex items-center gap-2 rounded-md bg-amber-500/5 px-3 py-2">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                      <span className="text-foreground">{item.name || item.source_project_id}</span>
                      <span className="text-muted-foreground">{formatReason(item.reason)}</span>
                    </div>
                  ))}
                  {importSummary.failed_projects.map((item) => (
                    <div key={`${item.source_project_id}-${item.reason || "failed"}`} className="flex items-center gap-2 rounded-md bg-rose-500/5 px-3 py-2">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-400" />
                      <span className="text-foreground">{item.name || item.source_project_id}</span>
                      <span className="text-muted-foreground">{item.reason || "未知错误"}</span>
                    </div>
                  ))}
                  {importSummary.warnings.map((warning) => (
                    <div key={warning} className="rounded-md bg-amber-500/5 px-3 py-2 text-muted-foreground">
                      {warning}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
      </div>
    </div>
  );
}
