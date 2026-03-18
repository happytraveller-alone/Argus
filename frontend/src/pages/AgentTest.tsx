/**
 * Agent 单体测试页面
 * 用于独立测试 ReconAgent / AnalysisAgent / VerificationAgent / BusinessLogicScanAgent
 * / BusinessLogicReconAgent / BusinessLogicAnalysisAgent
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronRight,
  Cpu,
  DatabaseBackup,
  Download,
  FileArchive,
  RefreshCw,
  Search,
  Shield,
  Telescope,
  Upload,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { api, type ProjectImportResponse } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import {
  AnalysisPanel,
  BusinessLogicReconPanel,
  BusinessLogicAnalysisPanel,
  ReconPanel,
  VerificationPanel,
} from "./agent-test/panels";

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

function TransferPanel() {
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
    <div className="space-y-4">
      <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
        <p className="text-xs text-muted-foreground">
          <strong className="text-cyan-400">Project Transfer</strong> —
          项目域数据迁移工具：自动发现项目关联数据并导出（项目、任务、扫描结果、Agent 轨迹等）与 ZIP 源码包，
          导入时会将归属重绑定到当前用户。
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <section className="rounded border border-border/40 bg-background/70 p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <FileArchive className="h-4 w-4 text-cyan-400" />
                导出项目迁移包
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                默认导出当前用户可见的非初始化项目，并自动发现关联表数据。可按项目筛选后只导出选中项。
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => void loadProjects()}
              disabled={loadingProjects}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingProjects ? "animate-spin" : ""}`} />
              刷新项目
            </Button>
          </div>

          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center">
            <input
              value={projectFilter}
              onChange={(event) => setProjectFilter(event.target.value)}
              placeholder="按项目名称或描述过滤"
              className="cyber-input h-9 w-full min-w-0 rounded-sm border border-input bg-background px-4 py-2 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-primary focus:shadow-focus"
            />
            <Label className="flex items-center gap-2 text-xs text-muted-foreground">
              <Checkbox
                checked={includeArchives}
                onCheckedChange={(checked) => setIncludeArchives(checked === true)}
              />
              包含 ZIP 源码归档
            </Label>
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <Label className="flex items-center gap-2">
              <Checkbox
                checked={allVisibleSelected}
                onCheckedChange={(checked) => toggleSelectVisible(checked === true)}
              />
              全选当前筛选结果
            </Label>
            <span>共 {projects.length} 个项目</span>
            <span>当前筛选 {visibleProjects.length} 个</span>
            <span>已选择 {selectedProjectIds.length} 个</span>
          </div>

          <div className="max-h-[24rem] space-y-2 overflow-y-auto rounded border border-border/30 bg-muted/10 p-2">
            {loadingProjects ? (
              <div className="rounded border border-dashed border-border/40 px-3 py-8 text-center text-xs text-muted-foreground">
                正在加载项目列表...
              </div>
            ) : visibleProjects.length === 0 ? (
              <div className="rounded border border-dashed border-border/40 px-3 py-8 text-center text-xs text-muted-foreground">
                没有匹配的项目
              </div>
            ) : (
              visibleProjects.map((project) => {
                const checked = selectedProjectIds.includes(project.id);
                return (
                  <label
                    key={project.id}
                    className="flex cursor-pointer items-start gap-3 rounded border border-border/30 bg-background/80 px-3 py-2 transition-colors hover:border-cyan-500/40"
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(next) => toggleProject(project.id, next === true)}
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-medium text-foreground">
                          {project.name}
                        </span>
                        <span className="shrink-0 rounded border border-border/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {project.source_type || "zip"}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {project.description || "无项目描述"}
                      </p>
                    </div>
                  </label>
                );
              })
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              type="button"
              className="gap-2"
              disabled={exporting || loadingProjects || selectedProjectIds.length === 0}
              onClick={() => void handleExport("selected")}
            >
              <Download className="h-4 w-4" />
              {exporting ? "导出中..." : "导出选中项目"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="gap-2"
              disabled={exporting || loadingProjects || projects.length === 0}
              onClick={() => void handleExport("all")}
            >
              <DatabaseBackup className="h-4 w-4" />
              {exporting ? "导出中..." : "导出全部项目"}
            </Button>
          </div>
        </section>

        <section className="rounded border border-border/40 bg-background/70 p-4">
          <div className="mb-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Upload className="h-4 w-4 text-cyan-400" />
              导入项目迁移包
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              导入默认按 skip 策略处理冲突，并将项目归属、任务创建者等用户字段重绑定到当前用户。
            </p>
          </div>

          <div className="space-y-3">
            <div className="rounded border border-dashed border-border/40 bg-muted/10 p-3">
              <Label htmlFor="project-transfer-bundle" className="text-xs text-muted-foreground">
                选择迁移包文件
              </Label>
              <div className="mt-2 space-y-2">
                <input
                  id="project-transfer-bundle"
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0] || null;
                    setSelectedBundle(file);
                  }}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="gap-2"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <FileArchive className="h-4 w-4" />
                    选择 ZIP 文件
                  </Button>
                  {selectedBundle ? (
                    <Button
                      type="button"
                      variant="ghost"
                      className="px-3 text-xs text-muted-foreground"
                      onClick={() => {
                        setSelectedBundle(null);
                        if (fileInputRef.current) {
                          fileInputRef.current.value = "";
                        }
                      }}
                    >
                      清除选择
                    </Button>
                  ) : null}
                </div>

                <div className="rounded border border-border/30 bg-background/70 px-3 py-2">
                  {selectedBundle ? (
                    <div className="space-y-1">
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        已选择文件
                      </p>
                      <p className="break-all text-sm text-foreground">
                        {selectedBundle.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        大小：{Math.max(1, Math.round(selectedBundle.size / 1024))} KB
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs leading-5 text-muted-foreground">
                      请选择由“项目迁移导出”生成的 ZIP 包。
                    </p>
                  )}
                </div>
              </div>
            </div>

            <Button
              type="button"
              className="w-full gap-2"
              disabled={importing || !selectedBundle}
              onClick={() => void handleImport()}
            >
              <Upload className="h-4 w-4" />
              {importing ? "导入中..." : "开始导入"}
            </Button>
          </div>

          <div className="mt-4 rounded border border-border/30 bg-muted/10 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              导入规则摘要
            </h3>
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              <li>只导入项目域数据，不导入系统模板、系统规则、用户配置。</li>
              <li>导入时按当前后端可识别的项目域表执行，未知表会跳过并记录警告。</li>
              <li>建议导出端与导入端保持接近版本，减少兼容性警告。</li>
              <li>冲突优先按 ZIP 哈希判断，其次按项目名 + 来源类型 + 仓库地址跳过。</li>
              <li>ZIP 项目缺失源码包时会失败，不会导入半残项目。</li>
            </ul>
          </div>
        </section>
      </div>

      {importSummary ? (
        <div className="rounded border border-border/40 bg-background/70 p-4">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h2 className="text-sm font-semibold text-foreground">最近一次导入结果</h2>
            <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-300">
              成功 {importSummary.imported_projects.length}
            </span>
            <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
              跳过 {importSummary.skipped_projects.length}
            </span>
            <span className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-300">
              失败 {importSummary.failed_projects.length}
            </span>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded border border-border/30 bg-muted/10 p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Imported
              </h3>
              <div className="space-y-2 text-xs">
                {importSummary.imported_projects.length === 0 ? (
                  <p className="text-muted-foreground">无成功导入项目</p>
                ) : (
                  importSummary.imported_projects.map((item) => (
                    <div key={`${item.source_project_id}-${item.project_id}`} className="rounded border border-border/20 px-2 py-1.5">
                      <p className="font-medium text-foreground">{item.name || item.source_project_id}</p>
                      <p className="text-muted-foreground">目标项目 ID: {item.project_id}</p>
                      {item.reason ? (
                        <p className="text-muted-foreground">说明: {formatReason(item.reason)}</p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded border border-border/30 bg-muted/10 p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Skipped
              </h3>
              <div className="space-y-2 text-xs">
                {importSummary.skipped_projects.length === 0 ? (
                  <p className="text-muted-foreground">无跳过项目</p>
                ) : (
                  importSummary.skipped_projects.map((item) => (
                    <div key={`${item.source_project_id}-${item.reason || "skip"}`} className="rounded border border-border/20 px-2 py-1.5">
                      <p className="font-medium text-foreground">{item.name || item.source_project_id}</p>
                      <p className="text-muted-foreground">原因: {formatReason(item.reason)}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded border border-border/30 bg-muted/10 p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Failed / Warnings
              </h3>
              <div className="space-y-2 text-xs">
                {importSummary.failed_projects.map((item) => (
                  <div key={`${item.source_project_id}-${item.reason || "failed"}`} className="rounded border border-rose-500/20 px-2 py-1.5">
                    <p className="font-medium text-foreground">{item.name || item.source_project_id}</p>
                    <p className="text-muted-foreground">原因: {item.reason || "未知错误"}</p>
                  </div>
                ))}
                {importSummary.warnings.map((warning) => (
                  <div key={warning} className="rounded border border-amber-500/20 px-2 py-1.5 text-muted-foreground">
                    {warning}
                  </div>
                ))}
                {importSummary.failed_projects.length === 0 && importSummary.warnings.length === 0 ? (
                  <p className="text-muted-foreground">无失败或警告</p>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function AgentTestPage() {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-background font-mono">
      <div className="pointer-events-none absolute inset-0 cyber-grid-subtle" />

      <div className="relative z-10 flex h-full flex-col gap-4 p-6">
        <div className="flex shrink-0 items-center gap-3">
          <Bot className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">Agent 单体测试</h1>
            <p className="text-xs text-muted-foreground">
              独立测试单个 Agent 的能力，实时查看执行过程
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground/60">
            <ChevronRight className="h-3 w-3" />
            <span>直连 Agent，不创建审计任务</span>
          </div>
        </div>

        <div className="cyber-card flex min-h-0 flex-1 flex-col overflow-hidden p-4">
          <Tabs defaultValue="recon" className="flex min-h-0 flex-1 flex-col">
            <TabsList className="mb-4 grid w-full shrink-0 grid-cols-6">
              <TabsTrigger value="recon" className="gap-1.5 text-xs">
                <Search className="h-3.5 w-3.5" /> Recon
              </TabsTrigger>
              <TabsTrigger value="bl-recon" className="gap-1.5 text-xs">
                <Telescope className="h-3.5 w-3.5" /> BL Recon
              </TabsTrigger>
              <TabsTrigger value="analysis" className="gap-1.5 text-xs">
                <Cpu className="h-3.5 w-3.5" /> Analysis
              </TabsTrigger>
              <TabsTrigger value="bl-analysis" className="gap-1.5 text-xs">
                <Zap className="h-3.5 w-3.5" /> BL Analysis
              </TabsTrigger>
              <TabsTrigger value="verification" className="gap-1.5 text-xs">
                <Shield className="h-3.5 w-3.5" /> Verification
              </TabsTrigger>
              <TabsTrigger value="transfer" className="gap-1.5 text-xs">
                <DatabaseBackup className="h-3.5 w-3.5" /> Transfer
              </TabsTrigger>
            </TabsList>

            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <TabsContent value="recon" className="mt-0">
                <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">ReconAgent</strong> —
                    信息收集阶段：扫描项目结构、识别技术栈、发现 HTTP 入口点和高风险区域。
                  </p>
                </div>
                <ReconPanel />
              </TabsContent>

              <TabsContent value="analysis" className="mt-0">
                <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">AnalysisAgent</strong> —
                    漏洞分析阶段：深度分析代码，发现 SQL 注入、XSS、越权等安全漏洞。
                    可提供 Recon 阶段的入口点和高风险区域作为上下文。
                  </p>
                </div>
                <AnalysisPanel />
              </TabsContent>

              <TabsContent value="verification" className="mt-0">
                <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">VerificationAgent</strong> —
                    漏洞验证阶段：对已发现的漏洞进行深度代码审查，验证真实性并评估可利用性。
                    以 JSON 数组形式输入待验证的漏洞列表。
                  </p>
                </div>
                <VerificationPanel />
              </TabsContent>

              <TabsContent value="bl-recon" className="mt-0">
                <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">BusinessLogicReconAgent</strong>{" "}
                    —
                    业务逻辑风险侦察：扫描整个项目，识别 IDOR、权限绕过、支付逻辑、竞态条件、批量赋值等业务逻辑风险点，
                    推入 BL 风险队列供 <strong className="text-cyan-400">BusinessLogicAnalysisAgent</strong> 深度分析。
                  </p>
                </div>
                <BusinessLogicReconPanel />
              </TabsContent>

              <TabsContent value="bl-analysis" className="mt-0">
                <div className="mb-3 rounded border border-border/30 bg-muted/30 p-2.5">
                  <p className="text-xs text-muted-foreground">
                    <strong className="text-cyan-400">BusinessLogicAnalysisAgent</strong>{" "}
                    —
                    业务逻辑漏洞深度分析：对单个 BL 风险点进行深度代码审查，确认漏洞真实性、评估影响范围，
                    将确认的漏洞推入漏洞队列。输入来自 BL Recon 阶段的风险点 JSON 对象。
                  </p>
                </div>
                <BusinessLogicAnalysisPanel />
              </TabsContent>

              <TabsContent value="transfer" className="mt-0">
                <TransferPanel />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
