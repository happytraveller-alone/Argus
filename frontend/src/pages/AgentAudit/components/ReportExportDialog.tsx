import {
  useState,
  useEffect,
  useCallback,
  memo,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertTriangle,
  Check,
  Clock,
  Copy,
  Download,
  Eye,
  FileDown,
  FileJson,
  FileText,
  Keyboard,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { apiClient } from "@/shared/api/serverClient";
import type { AgentTask, AgentFinding } from "@/shared/api/agentTasks";
import {
  EnhancedStatsPanel,
  ExportOptionsPanel,
  FormatSelector,
  JsonPreview,
  MarkdownPreview,
  PreviewSearchBar,
  PreviewSkeleton,
  type ExportOptions,
  type ReportFormat,
} from "../report-export/components";
import {
  buildReportExportParams,
  buildReportPreviewCacheKey,
} from "../report-export/request";
import { formatReportExportBytes } from "../report-export/utils";

interface ReportExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: AgentTask | null;
  findings: AgentFinding[];
}

interface ReportPreview {
  content: string;
  format: ReportFormat;
  loading: boolean;
  error: string | null;
}

const FORMAT_CONFIG: Record<
  ReportFormat,
  {
    label: string;
    description: string;
    icon: ReactNode;
    extension: string;
    mime: string;
    color: string;
    bgColor: string;
  }
> = {
  markdown: {
    label: "Markdown",
    description: "可编辑文档格式",
    icon: <FileText className="w-5 h-5" />,
    extension: ".md",
    mime: "text/markdown",
    color: "text-sky-400",
    bgColor: "bg-sky-500/10 border-sky-500/30",
  },
  json: {
    label: "JSON",
    description: "结构化数据格式",
    icon: <FileJson className="w-5 h-5" />,
    extension: ".json",
    mime: "application/json",
    color: "text-amber-400",
    bgColor: "bg-amber-500/10 border-amber-500/30",
  },
  pdf: {
    label: "PDF",
    description: "便携文档格式",
    icon: <FileDown className="w-5 h-5" />,
    extension: ".pdf",
    mime: "application/pdf",
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/10 border-emerald-500/30",
  },
};

const DEFAULT_EXPORT_OPTIONS: ExportOptions = {
  includeCodeSnippets: true,
  includeRemediation: false,
  includeMetadata: true,
  compactMode: false,
};

export const ReportExportDialog = memo(function ReportExportDialog({
  open,
  onOpenChange,
  task,
  findings,
}: ReportExportDialogProps) {
  const [activeFormat, setActiveFormat] = useState<ReportFormat>("markdown");
  const [preview, setPreview] = useState<ReportPreview>({
    content: "",
    format: "markdown",
    loading: false,
    error: null,
  });
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadSuccess, setDownloadSuccess] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [exportOptions, setExportOptions] =
    useState<ExportOptions>(DEFAULT_EXPORT_OPTIONS);
  const [optionsExpanded, setOptionsExpanded] = useState(false);
  const previewCache = useRef<Map<string, string>>(new Map());
  const reportRevision = useMemo(
    () =>
      findings
        .map((finding) =>
          [
            finding.id,
            finding.status ?? "",
            finding.verdict ?? "",
            finding.authenticity ?? "",
            finding.is_verified ? "1" : "0",
          ].join(":"),
        )
        .sort()
        .join("|"),
    [findings],
  );

  const searchMatchCount = useMemo(() => {
    if (!searchQuery || !preview.content) return 0;
    const regex = new RegExp(
      searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
      "gi",
    );
    return (preview.content.match(regex) || []).length;
  }, [preview.content, searchQuery]);

  const fetchPreview = useCallback(
    async (format: ReportFormat, forceRefresh = false) => {
      if (!task) return;
      const cacheKey = `${buildReportPreviewCacheKey(format, exportOptions)}::${task.id}::${reportRevision}`;
      const requestFormat = format === "pdf" ? "markdown" : format;

      if (!forceRefresh && previewCache.current.has(cacheKey)) {
        setPreview({
          content: previewCache.current.get(cacheKey) || "",
          format,
          loading: false,
          error: null,
        });
        return;
      }

      setPreview((prev) => ({ ...prev, loading: true, error: null }));

      try {
        let content = "";
        if (requestFormat === "json") {
          const response = await apiClient.get(`/agent-tasks/${task.id}/report`, {
            params: buildReportExportParams(requestFormat, exportOptions),
          });
          content = JSON.stringify(response.data, null, 2);
        } else {
          const response = await apiClient.get(`/agent-tasks/${task.id}/report`, {
            params: buildReportExportParams(requestFormat, exportOptions),
            responseType: "text",
          });
          content = response.data;
        }

        previewCache.current.set(cacheKey, content);
        setPreview({ content, format, loading: false, error: null });
      } catch (error) {
        console.error("Failed to fetch report preview:", error);
        setPreview((prev) => ({
          ...prev,
          loading: false,
          error: "加载预览失败，请重试",
        }));
      }
    },
    [exportOptions, reportRevision, task],
  );

  useEffect(() => {
    if (open && task) {
      void fetchPreview(activeFormat);
    }
  }, [activeFormat, exportOptions, fetchPreview, open, reportRevision, task]);

  useEffect(() => {
    if (!open) {
      previewCache.current.clear();
      setSearchQuery("");
      setDownloadSuccess(false);
    }
  }, [open]);

  const handleCopy = useCallback(async () => {
    if (!preview.content) return;
    try {
      await navigator.clipboard.writeText(preview.content);
      setCopied(true);
      toast.success("已复制到剪贴板");
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
      toast.error("复制失败");
    }
  }, [preview.content]);

  const resolveFilenameFromDisposition = useCallback(
    (contentDisposition: string | undefined, fallback: string) => {
      if (!contentDisposition) return fallback;
      const filenameStarMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (filenameStarMatch?.[1]) {
        try {
          return decodeURIComponent(filenameStarMatch[1]);
        } catch {
          return filenameStarMatch[1];
        }
      }
      const filenameMatch = contentDisposition.match(/filename=([^;]+)/i);
      if (!filenameMatch?.[1]) return fallback;
      return filenameMatch[1].trim().replace(/['"]/g, "") || fallback;
    },
    [],
  );

  const triggerBrowserDownload = useCallback((blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, []);

  const handleDownload = useCallback(async () => {
    if (!task) return;

    setDownloading(true);
    try {
      const config = FORMAT_CONFIG[activeFormat];
      const datePart = new Date().toISOString().slice(0, 10);
      const baseName = `audit_report_${task.name || task.id.substring(0, 8)}_${datePart}`;

      if (activeFormat === "pdf") {
        const response = await apiClient.get(`/agent-tasks/${task.id}/report`, {
          params: buildReportExportParams("pdf", exportOptions),
          responseType: "blob",
        });
        const fallbackFilename = `${baseName}${config.extension}`;
        const filename = resolveFilenameFromDisposition(
          response.headers?.["content-disposition"],
          fallbackFilename,
        );
        const blob =
          response.data instanceof Blob
            ? response.data
            : new Blob([response.data], { type: config.mime });
        triggerBrowserDownload(blob, filename);
      } else {
        let content = preview.content;
        if (!content) {
          if (activeFormat === "json") {
            const response = await apiClient.get(`/agent-tasks/${task.id}/report`, {
              params: buildReportExportParams(activeFormat, exportOptions),
            });
            content = JSON.stringify(response.data, null, 2);
          } else {
            const response = await apiClient.get(`/agent-tasks/${task.id}/report`, {
              params: buildReportExportParams(activeFormat, exportOptions),
              responseType: "text",
            });
            content = response.data;
          }
        }
        const filename = `${baseName}${config.extension}`;
        const blob = new Blob([content], { type: config.mime });
        triggerBrowserDownload(blob, filename);
      }

      setDownloadSuccess(true);
      toast.success(`报告已导出为 ${config.label} 格式`);
      setTimeout(() => {
        onOpenChange(false);
      }, 1000);
    } catch (error) {
      console.error("Download failed:", error);
      toast.error("导出报告失败，请重试");
    } finally {
      setDownloading(false);
    }
  }, [
    activeFormat,
    exportOptions,
    onOpenChange,
    preview.content,
    resolveFilenameFromDisposition,
    task,
    triggerBrowserDownload,
  ]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key === "c" &&
        !window.getSelection()?.toString()
      ) {
        event.preventDefault();
        void handleCopy();
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "s") {
        event.preventDefault();
        void handleDownload();
      }
      if (event.key === "1") setActiveFormat("markdown");
      if (event.key === "2") setActiveFormat("json");
      if (event.key === "3") setActiveFormat("pdf");
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleCopy, handleDownload, open]);

  if (!task) return null;

  const formatItems = (Object.keys(FORMAT_CONFIG) as ReportFormat[]).map((key) => ({
    key,
    ...FORMAT_CONFIG[key],
  }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[90vh] bg-background border-border p-0 gap-0 overflow-hidden shadow-2xl">
        <div className="relative px-6 py-5 border-b border-border bg-card">
          <DialogHeader className="relative">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="relative p-3 rounded-xl bg-primary/10 border border-primary/30">
                  <FileDown className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <DialogTitle className="text-xl font-bold text-foreground flex items-center gap-2">
                    导出扫描报告
                    <Sparkles className="w-4 h-4 text-primary/60" />
                  </DialogTitle>
                  <p className="text-xs text-muted-foreground mt-1 font-mono flex items-center gap-2">
                    <Clock className="w-3 h-3" />
                    {task.name || `Task ${task.id.slice(0, 8)}`}
                  </p>
                </div>
              </div>
              <div className="hidden md:flex items-center gap-2 text-xs text-muted-foreground">
                <div className="flex items-center gap-1 px-2 py-1 rounded bg-muted border border-border">
                  <Keyboard className="w-3 h-3" />
                  <span>⌘S 下载</span>
                </div>
                <div className="flex items-center gap-1 px-2 py-1 rounded bg-muted border border-border">
                  <span>1-3 切换</span>
                </div>
              </div>
            </div>
          </DialogHeader>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-6 py-4 border-b border-border bg-card/80">
            <EnhancedStatsPanel task={task} findings={findings} />
          </div>

          <div className="flex-1 flex min-h-0">
            <div className="w-72 flex-shrink-0 border-r border-border bg-card/50 p-4 space-y-4 overflow-y-auto">
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" />
                  选择格式
                </h3>
                <FormatSelector
                  activeFormat={activeFormat}
                  onFormatChange={setActiveFormat}
                  items={formatItems}
                />
              </div>

              <ExportOptionsPanel
                options={exportOptions}
                onOptionsChange={setExportOptions}
                expanded={optionsExpanded}
                onToggle={() => setOptionsExpanded(!optionsExpanded)}
              />

              <div className="p-3 rounded-xl bg-muted border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <div className={FORMAT_CONFIG[activeFormat].color}>
                    {FORMAT_CONFIG[activeFormat].icon}
                  </div>
                  <span className="text-sm font-medium text-foreground">
                    {FORMAT_CONFIG[activeFormat].label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {activeFormat === "markdown" &&
                    "Markdown格式便于编辑和版本控制，可用任何文本编辑器打开。"}
                  {activeFormat === "json" &&
                    "JSON格式包含完整的结构化数据，适合程序处理和数据分析。"}
                  {activeFormat === "pdf" &&
                    "PDF格式适合正式归档和分享，下载时将直接使用后端导出的 PDF 文件。"}
                </p>
              </div>
            </div>

            <div className="flex-1 flex flex-col min-h-0 cyber-dialog">
              <div className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-border bg-muted/50">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <Eye className="w-4 h-4 text-muted-foreground" />
                    <span className="text-xs text-muted-foreground font-medium">
                      预览
                    </span>
                  </div>
                  <Badge className="text-xs bg-muted/50 text-muted-foreground border-0 font-mono">
                    {formatReportExportBytes(preview.content.length)}
                  </Badge>
                </div>

                <div className="flex items-center gap-2">
                  <PreviewSearchBar
                    searchQuery={searchQuery}
                    onSearchChange={setSearchQuery}
                    matchCount={searchMatchCount}
                    onClear={() => setSearchQuery("")}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleCopy()}
                    disabled={preview.loading || !preview.content}
                    className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  >
                    {copied ? (
                      <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5 mr-1.5" />
                    )}
                    {copied ? "已复制" : "复制"}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void fetchPreview(activeFormat, true)}
                    disabled={preview.loading}
                    className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  >
                    <RefreshCw
                      className={`w-3.5 h-3.5 mr-1.5 ${preview.loading ? "animate-spin" : ""}`}
                    />
                    刷新
                  </Button>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-hidden">
                <ScrollArea className="h-full">
                  <div className="p-5">
                    {preview.loading ? (
                      <PreviewSkeleton />
                    ) : preview.error ? (
                      <div className="flex items-center justify-center py-16">
                        <div className="flex flex-col items-center gap-4 text-center">
                          <div className="p-4 rounded-full bg-amber-500/10 border border-amber-500/30">
                            <AlertTriangle className="w-8 h-8 text-amber-400" />
                          </div>
                          <div>
                            <p className="text-sm text-foreground font-medium mb-1">
                              加载失败
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {preview.error}
                            </p>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void fetchPreview(activeFormat, true)}
                            className="mt-2"
                          >
                            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                            重试
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-border overflow-hidden bg-card">
                        <div className="p-5 min-h-[300px]">
                          {(activeFormat === "markdown" || activeFormat === "pdf") && (
                            <MarkdownPreview
                              content={preview.content}
                              searchQuery={searchQuery}
                            />
                          )}
                          {activeFormat === "json" && (
                            <JsonPreview
                              content={preview.content}
                              searchQuery={searchQuery}
                            />
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-border bg-card">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${FORMAT_CONFIG[activeFormat].bgColor}`}
              >
                <span className={FORMAT_CONFIG[activeFormat].color}>
                  {FORMAT_CONFIG[activeFormat].icon}
                </span>
                <span className="font-mono">
                  {FORMAT_CONFIG[activeFormat].label} (
                  {FORMAT_CONFIG[activeFormat].extension})
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                className="h-10 px-5 text-sm text-muted-foreground hover:text-foreground"
              >
                取消
              </Button>

              <Button
                onClick={() => void handleDownload()}
                disabled={downloading || preview.loading || !preview.content}
                className={`h-10 px-6 text-sm font-medium transition-all duration-300 ${downloadSuccess
                    ? "bg-emerald-600 hover:bg-emerald-600"
                    : "bg-primary hover:bg-primary/90"
                  }`}
              >
                {downloading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    导出中...
                  </>
                ) : downloadSuccess ? (
                  <>
                    <Check className="w-4 h-4 mr-2" />
                    导出成功
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    下载 {FORMAT_CONFIG[activeFormat].label}
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});

export default ReportExportDialog;
