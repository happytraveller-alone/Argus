import { useEffect, useMemo, useState } from "react";
import { History, RefreshCw, RotateCcw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { CubesandboxTemplateRecord } from "@/shared/api/cubesandboxTemplates";
import {
  cleanupFailedSandboxTemplates,
  deleteFailedSandboxTemplateRecord,
  getSandboxTemplateManagementOverview,
  resetSandboxTemplateKind,
} from "@/shared/api/cubesandboxTemplates";
import { listCubeSandboxTasks, type CubeSandboxTaskRecord } from "@/shared/api/cubesandboxTasks";
import SandboxTemplatesTable from "@/pages/sandbox-management/SandboxTemplatesTable";

function matchesTemplate(record: CubesandboxTemplateRecord, keyword: string) {
  if (!keyword) return true;
  const haystack = [
    record.id,
    record.kind,
    record.status,
    record.templateId,
    record.imageRef,
    record.imageFingerprint,
    record.errorMessage,
    record.buildLogTail,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(keyword);
}

function formatTaskTime(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sleep(ms: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

export default function SandboxManagementPage() {
  const [templates, setTemplates] = useState<CubesandboxTemplateRecord[]>([]);
  const [tasks, setTasks] = useState<CubeSandboxTaskRecord[]>([]);
  const [failedCount, setFailedCount] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [cleanupRunning, setCleanupRunning] = useState(false);
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null);
  const [resettingKind, setResettingKind] = useState<"codeql_cpp" | "opengrep" | null>(null);
  /** AC-A4: default hide invalidated/failed; toggle to show full history */
  const [showFullHistory, setShowFullHistory] = useState(false);

  const filteredTemplates = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return templates.filter((record) => matchesTemplate(record, keyword));
  }, [searchTerm, templates]);

  const DEFAULT_STATUS_FILTER = "ready,building";

  async function loadData(fullHistory = showFullHistory) {
    setLoading(true);
    try {
      const statusFilter = fullHistory ? undefined : DEFAULT_STATUS_FILTER;
      const [overview, taskRecords] = await Promise.all([
        getSandboxTemplateManagementOverview(statusFilter),
        listCubeSandboxTasks(50),
      ]);
      setTemplates(overview.templates);
      setFailedCount(overview.failedCount);
      setTasks(taskRecords);
    } catch (error) {
      console.error("Failed to load sandbox management data:", error);
      toast.error("加载沙箱管理数据失败");
    } finally {
      setLoading(false);
    }
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadData is intentionally omitted — it is a plain function recreated each render; adding it would cause an infinite loop. Initial fetch only.
  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: loadData is intentionally omitted — see above. Re-runs only when showFullHistory changes.
  useEffect(() => {
    void loadData(showFullHistory);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showFullHistory]);

  async function handleDeleteFailed(record: CubesandboxTemplateRecord) {
    if (record.status !== "failed" && record.status !== "invalidated") return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `确认删除 ${record.status.toUpperCase()} 模板记录「${record.templateId ?? record.id}」？此操作只作用于 FAILED / INVALIDATED 模板记录/模板，不会删除运行中沙箱实例。`,
      )
    ) {
      return;
    }
    setDeletingRecordId(record.id ?? null);
    try {
      const result = await deleteFailedSandboxTemplateRecord(record.id ?? "");
      toast.success("模板已删除", {
        description: `删除记录 ${result.deletedRecords} 条，CubeMaster 模板 ${result.deletedTemplates} 个。`,
      });
      await loadData();
    } catch (error) {
      console.error("Failed to delete sandbox template:", error);
      toast.error("删除模板失败");
    } finally {
      setDeletingRecordId(null);
    }
  }

  async function handleCleanupFailed() {
    if (
      typeof window !== "undefined" &&
      !window.confirm("确认清空所有 FAILED 模板冗余记录？不会删除运行中沙箱实例。")
    ) {
      return;
    }
    setCleanupRunning(true);
    try {
      const result = await cleanupFailedSandboxTemplates();
      toast.success("FAILED 模板清理完成", {
        description: `扫描 ${result.scannedFailed ?? 0} 条，删除记录 ${result.deletedRecords} 条，删除模板 ${result.deletedTemplates} 个。`,
      });
      await loadData();
    } catch (error) {
      console.error("Failed to cleanup failed sandbox templates:", error);
      toast.error("清空 FAILED 模板失败");
    } finally {
      setCleanupRunning(false);
    }
  }

  async function handleReset(kind: "codeql_cpp" | "opengrep") {
    setResettingKind(kind);
    try {
      const result = await resetSandboxTemplateKind(kind);
      toast.success(kind === "codeql_cpp" ? "CodeQL 模板已重置并开始重建" : "OpenGrep 模板已重置并开始重建", {
        description: `删除记录 ${result.deletedRecords} 条，删除模板 ${result.deletedTemplates} 个；新记录目标状态 ready。`,
      });
      await loadData();
      for (let attempt = 0; attempt < 120; attempt += 1) {
        await sleep(3000);
        // Poll with full history during reset to catch all status transitions
        const overview = await getSandboxTemplateManagementOverview();
        setTemplates(overview.templates);
        setFailedCount(overview.failedCount);
        const latest = overview.templates.find((record) => {
          const recordKind = record.kind === "opengrep_dedicated" ? "opengrep" : record.kind;
          return recordKind === kind;
        });
        if (latest?.status === "ready") {
          toast.success(kind === "codeql_cpp" ? "CodeQL 模板已就绪" : "OpenGrep 模板已就绪", {
            description: latest.templateId ? `template_id=${latest.templateId}` : "状态 ready",
          });
          break;
        }
        if (latest?.status === "failed") {
          toast.error(kind === "codeql_cpp" ? "CodeQL 模板重建失败" : "OpenGrep 模板重建失败");
          break;
        }
      }
    } catch (error) {
      console.error("Failed to reset sandbox template kind:", error);
      toast.error("重置模板失败");
    } finally {
      setResettingKind(null);
    }
  }

  return (
    <div className="p-6 bg-background min-h-screen font-mono relative flex flex-col gap-6">
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
      <div className="relative z-10 flex flex-col gap-6">
        <section className="rounded-2xl border border-border/80 bg-card/70 p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-[0.12em] text-foreground">沙箱管理</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">FAILED {failedCount}</Badge>
              <Button
                size="sm"
                variant={showFullHistory ? "secondary" : "outline"}
                onClick={() => setShowFullHistory((prev) => !prev)}
              >
                <History className="mr-2 h-4 w-4" />
                {showFullHistory ? "隐藏历史" : "显示完整历史"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => void loadData()} disabled={loading}>
                <RefreshCw className="mr-2 h-4 w-4" />
                刷新
              </Button>
              <Button size="sm" variant="outline" onClick={handleCleanupFailed} disabled={cleanupRunning || failedCount === 0}>
                <Trash2 className="mr-2 h-4 w-4" />
                清空 FAILED 模板
              </Button>
              <Button size="sm" variant="outline" onClick={() => void handleReset("codeql_cpp")} disabled={resettingKind !== null}>
                <RotateCcw className="mr-2 h-4 w-4" />
                重置 CodeQL
              </Button>
              <Button size="sm" variant="outline" onClick={() => void handleReset("opengrep")} disabled={resettingKind !== null}>
                <RotateCcw className="mr-2 h-4 w-4" />
                重置 OpenGrep
              </Button>
            </div>
          </div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="relative w-full max-w-xl">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="按模板类型 / ID / 镜像 / 错误搜索"
                className="h-9 pl-9 font-mono"
              />
            </div>
            <span className="shrink-0 text-sm text-muted-foreground">共 {filteredTemplates.length} 条</span>
          </div>
          <SandboxTemplatesTable rows={filteredTemplates} deletingRecordId={deletingRecordId} onDeleteFailed={handleDeleteFailed} />
        </section>

        <section className="rounded-2xl border border-border/80 bg-card/70 p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-[0.12em] text-foreground">沙箱状态</h2>
            </div>
            <Badge variant="outline">最近 {tasks.length} 条</Badge>
          </div>
          <div className="overflow-hidden rounded-xl border border-border/75">
            <table className="w-full text-sm">
              <thead className="bg-muted/70 text-muted-foreground">
                <tr>
                  <th className="border-b border-border p-3 text-left">任务 ID</th>
                  <th className="border-b border-border p-3 text-left">状态</th>
                  <th className="border-b border-border p-3 text-left">Sandbox ID</th>
                  <th className="border-b border-border p-3 text-left">清理状态</th>
                  <th className="border-b border-border p-3 text-left">更新时间</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td className="p-4 text-center text-muted-foreground" colSpan={5}>暂无沙箱任务状态</td>
                  </tr>
                ) : (
                  tasks.map((task) => (
                    <tr key={task.taskId}>
                      <td className="border-b border-border/70 p-3 text-muted-foreground">{task.taskId}</td>
                      <td className="border-b border-border/70 p-3">{task.status}</td>
                      <td className="border-b border-border/70 p-3 text-muted-foreground">{task.sandboxId ?? "-"}</td>
                      <td className="border-b border-border/70 p-3 text-muted-foreground">{task.cleanupStatus}</td>
                      <td className="border-b border-border/70 p-3 text-muted-foreground">{formatTaskTime(task.updatedAt)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
