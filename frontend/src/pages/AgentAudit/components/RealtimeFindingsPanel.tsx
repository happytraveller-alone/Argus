import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ExternalLink,
  Search,
  Trash2,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import FindingCodeWindow from "./FindingCodeWindow";
import FindingNarrativeMarkdown from "./FindingNarrativeMarkdown";
import { collectRawEvidenceEntries } from "./findingNarrative";

export type RealtimeVerificationProgress = "pending" | "verified";
export type RealtimeDisplaySeverity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "invalid";

export type RealtimeMergedFindingItem = {
  id: string;
  merge_key?: string;
  fingerprint: string;
  title: string;
  display_title?: string | null;
  description?: string | null;
  description_markdown?: string | null;
  severity: string;
  display_severity: RealtimeDisplaySeverity;
  verification_progress: RealtimeVerificationProgress;
  vulnerability_type: string;
  file_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  cwe_id?: string | null;
  code_snippet?: string | null;
  code_context?: string | null;
  function_trigger_flow?: string[] | null;
  reachability_file?: string | null;
  reachability_function?: string | null;
  reachability_function_start_line?: number | null;
  reachability_function_end_line?: number | null;
  context_start_line?: number | null;
  context_end_line?: number | null;
  verification_evidence?: string | null;
  timestamp?: string | null;
  is_verified: boolean;
};

function normalizeVerificationProgress(
  value: string,
): RealtimeVerificationProgress {
  return String(value || "").trim().toLowerCase() === "verified"
    ? "verified"
    : "pending";
}

function getItemVerificationProgress(
  item: RealtimeMergedFindingItem,
): RealtimeVerificationProgress {
  if (item.verification_progress) {
    return normalizeVerificationProgress(item.verification_progress);
  }
  return item.is_verified ? "verified" : "pending";
}

function formatLocation(item: RealtimeMergedFindingItem): string {
  const path = String(item.file_path || "").trim();
  const line = item.line_start;
  if (path && typeof line === "number" && Number.isFinite(line)) {
    return `${path}:${line}`;
  }
  if (path) return path;
  return "-";
}

function pickRealtimeCode(item: RealtimeMergedFindingItem): {
  code: string;
  lineStart: number | null;
  lineEnd: number | null;
} | null {
  const context = String(item.code_context || "").trim();
  if (context) {
    return {
      code: context,
      lineStart: item.context_start_line ?? item.line_start ?? null,
      lineEnd: item.context_end_line ?? item.line_end ?? null,
    };
  }
  const snippet = String(item.code_snippet || "").trim();
  if (snippet) {
    return {
      code: snippet,
      lineStart: item.line_start ?? null,
      lineEnd: item.line_end ?? null,
    };
  }
  return null;
}

function getRawEvidenceFromRealtimeItem(item: RealtimeMergedFindingItem) {
  return collectRawEvidenceEntries({
    description: item.description,
    verification_evidence: item.verification_evidence,
    function_trigger_flow: item.function_trigger_flow,
    reachability_file: item.reachability_file,
    reachability_function: item.reachability_function,
    reachability_function_start_line: item.reachability_function_start_line,
    reachability_function_end_line: item.reachability_function_end_line,
  });
}

export default function RealtimeFindingsPanel(props: {
  items: RealtimeMergedFindingItem[];
  isRunning: boolean;
  onClear: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [verification, setVerification] = useState<
    "all" | RealtimeVerificationProgress
  >("all");
  const [detailItem, setDetailItem] = useState<RealtimeMergedFindingItem | null>(null);

  const counts = useMemo(() => {
    let pending = 0;
    let verified = 0;
    for (const item of props.items) {
      if (getItemVerificationProgress(item) === "verified") {
        verified += 1;
      } else {
        pending += 1;
      }
    }
    return { total: props.items.length, pending, verified };
  }, [props.items]);

  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    const sorted = [...props.items].sort((a, b) => {
      return String(b.timestamp || "").localeCompare(String(a.timestamp || ""));
    });

    return sorted.filter((item) => {
      const verificationKey = getItemVerificationProgress(item);
      const okVerification =
        verification === "all" || verificationKey === verification;
      if (!okVerification) return false;
      if (!key) return true;
      return (
        String(item.title || "").toLowerCase().includes(key) ||
        String(item.vulnerability_type || "").toLowerCase().includes(key) ||
        String(item.file_path || "").toLowerCase().includes(key)
      );
    });
  }, [props.items, keyword, verification]);

  return (
    <div className="h-full flex flex-col border border-border rounded-xl bg-card/70 overflow-hidden">
      <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold">潜在缺陷</span>
            <Badge variant="outline" className="text-[11px]">
              {counts.total}
            </Badge>
            <Badge
              variant="outline"
              className="text-[11px] border-amber-500/40 text-amber-600 dark:text-amber-300 bg-amber-500/10"
            >
              待验证 {counts.pending}
            </Badge>
            <Badge
              variant="outline"
              className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
            >
              已验证 {counts.verified}
            </Badge>
            {props.isRunning ? (
              <Badge
                variant="outline"
                className="text-[11px] border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
              >
                实时
              </Badge>
            ) : null}
          </div>

          <Button
            size="sm"
            variant="outline"
            onClick={props.onClear}
            disabled={props.items.length === 0}
          >
            <Trash2 className="w-3.5 h-3.5 mr-2" />
            清空
          </Button>
        </div>

        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索标题/类型/文件..."
              className="pl-9"
            />
          </div>

          <div className="flex items-center gap-2">
            <Select
              value={verification}
              onValueChange={(value) =>
                setVerification(value as "all" | RealtimeVerificationProgress)
              }
            >
              <SelectTrigger className="h-9 min-w-[112px] px-3 py-1.5 text-sm font-normal">
                <SelectValue placeholder="验证进度" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部</SelectItem>
                <SelectItem value="pending">待验证</SelectItem>
                <SelectItem value="verified">已验证</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {filtered.length === 0 ? (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            <div className="flex flex-col items-center gap-2 text-center px-6">
              <AlertTriangle className="w-5 h-5 opacity-60" />
              <span className="text-sm">
                {props.isRunning ? "等待新缺陷..." : "暂无缺陷"}
              </span>
            </div>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="p-3 space-y-2">
              {filtered.map((item) => {
                const verificationKey = getItemVerificationProgress(item);
                return (
                  <div
                    key={item.id}
                    className="rounded-lg border border-border bg-background/40 hover:border-primary/30 transition-colors px-3 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold break-words line-clamp-2">
                            {item.display_title || item.title || "未命名缺陷"}
                          </span>
                        </div>

                        <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
                          <span>类型: {item.vulnerability_type || "-"}</span>
                          <span>定位: {formatLocation(item)}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Badge
                          variant="outline"
                          className={`text-[11px] ${
                            verificationKey === "verified"
                              ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                              : "border-amber-500/40 text-amber-600 dark:text-amber-300 bg-amber-500/10"
                          }`}
                        >
                          {verificationKey === "verified" ? "已验证" : "待验证"}
                        </Badge>

                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2.5 text-[11px]"
                          onClick={() => setDetailItem(item)}
                        >
                          查看详情
                          <ExternalLink className="w-3.5 h-3.5 ml-1.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </div>

      <Dialog
        open={detailItem !== null}
        onOpenChange={(open) => {
          if (!open) setDetailItem(null);
        }}
      >
        <DialogContent className="max-w-3xl h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader className="border-b border-border pb-3">
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="flex items-center gap-2">
                <ExternalLink className="w-4 h-4" />
                缺陷详情
              </DialogTitle>
              <button
                type="button"
                onClick={() => setDetailItem(null)}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border hover:border-primary/40 hover:text-primary"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                返回
              </button>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto custom-scrollbar py-4 space-y-4">
            {detailItem ? (
              <section className="rounded-lg border border-border bg-card/70 p-3.5 space-y-2">
                <h3 className="text-sm font-semibold break-words">
                  {detailItem.display_title || detailItem.title || "未命名缺陷"}
                </h3>

                {(() => {
                  const code = pickRealtimeCode(detailItem);
                  if (!code) return null;
                  return (
                    <div className="pt-2">
                      <FindingCodeWindow
                        code={code.code}
                        filePath={detailItem.file_path}
                        lineStart={code.lineStart}
                        lineEnd={code.lineEnd}
                        highlightStartLine={detailItem.line_start ?? code.lineStart}
                        highlightEndLine={detailItem.line_end ?? code.lineEnd}
                        focusLine={detailItem.line_start ?? code.lineStart}
                        title="命中代码"
                      />
                    </div>
                  );
                })()}

                <div className="space-y-2 pt-2">
                  <div className="text-xs font-semibold text-muted-foreground">
                    漏洞详情（根因）
                  </div>
                  <FindingNarrativeMarkdown
                    finding={{
                      description: detailItem.description,
                      description_markdown: detailItem.description_markdown,
                      code_context: detailItem.code_context,
                      code_snippet: detailItem.code_snippet,
                      file_path: detailItem.file_path,
                      line_start: detailItem.line_start,
                      line_end: detailItem.line_end,
                      function_trigger_flow: detailItem.function_trigger_flow,
                      verification_evidence: detailItem.verification_evidence,
                      reachability_file: detailItem.reachability_file,
                      reachability_function: detailItem.reachability_function,
                      reachability_function_start_line:
                        detailItem.reachability_function_start_line,
                      reachability_function_end_line:
                        detailItem.reachability_function_end_line,
                    }}
                    className="rounded-md border border-border bg-background p-3"
                  />

                  <Collapsible className="rounded-md border border-border bg-card/60">
                    <CollapsibleTrigger className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground">
                      <span>原始证据</span>
                      <ChevronDown className="w-4 h-4" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="px-3 pb-3 space-y-2">
                      {getRawEvidenceFromRealtimeItem(detailItem).map((item) => (
                        <div key={item.key} className="space-y-1">
                          <div className="text-[11px] text-muted-foreground font-mono">
                            {item.label}
                            {item.truncated ? " (已截断至 2000 字)" : ""}
                          </div>
                          <pre className="text-xs font-mono bg-background border border-border rounded-md p-2 whitespace-pre-wrap break-words">
                            {item.value}
                          </pre>
                        </div>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              </section>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
