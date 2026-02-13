import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, Search, Trash2 } from "lucide-react";

export type RealtimeFindingItem = {
  id: string;
  title: string;
  severity: string;
  vulnerability_type: string;
  file_path?: string | null;
  line_start?: number | null;
  timestamp?: string | null;
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const SEVERITY_BADGE_CLASS: Record<string, string> = {
  critical: "bg-rose-500/20 text-rose-600 dark:text-rose-300 border-rose-500/40",
  high: "bg-orange-500/20 text-orange-600 dark:text-orange-300 border-orange-500/40",
  medium: "bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/40",
  low: "bg-sky-500/20 text-sky-600 dark:text-sky-300 border-sky-500/40",
  info: "bg-zinc-500/20 text-zinc-700 dark:text-zinc-300 border-zinc-500/40",
};

function normalizeSeverity(value: string): string {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "info";
  if (key in SEVERITY_ORDER) return key;
  return "info";
}

function formatLocation(item: RealtimeFindingItem): string {
  const path = String(item.file_path || "").trim();
  const line = item.line_start;
  if (path && typeof line === "number" && Number.isFinite(line)) {
    return `${path}:${line}`;
  }
  if (path) return path;
  return "-";
}

export default function RealtimeUnverifiedPanel(props: {
  items: RealtimeFindingItem[];
  isRunning: boolean;
  onClear: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [severity, setSeverity] = useState<"all" | string>("all");

  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    const sorted = [...props.items].sort((a, b) => {
      const aKey = normalizeSeverity(a.severity);
      const bKey = normalizeSeverity(b.severity);
      const aOrder = SEVERITY_ORDER[aKey] ?? 99;
      const bOrder = SEVERITY_ORDER[bKey] ?? 99;
      if (aOrder !== bOrder) return aOrder - bOrder;
      return (b.timestamp || "").localeCompare(a.timestamp || "");
    });

    return sorted.filter((item) => {
      const sevKey = normalizeSeverity(item.severity);
      const okSeverity = severity === "all" || sevKey === severity;
      if (!okSeverity) return false;
      if (!key) return true;
      return (
        String(item.title || "").toLowerCase().includes(key) ||
        String(item.vulnerability_type || "").toLowerCase().includes(key) ||
        String(item.file_path || "").toLowerCase().includes(key)
      );
    });
  }, [props.items, keyword, severity]);

  return (
    <div className="h-full flex flex-col border border-border rounded-xl bg-card/70 overflow-hidden">
      <div className="flex-shrink-0 px-4 py-3 border-b border-border bg-card">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">运行中实时漏洞（未验证）</span>
            <Badge variant="outline" className="text-[11px]">
              {filtered.length}
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
            <Button
              size="sm"
              variant={severity === "all" ? "default" : "outline"}
              onClick={() => setSeverity("all")}
            >
              全部
            </Button>
            <Button
              size="sm"
              variant={severity === "critical" ? "default" : "outline"}
              onClick={() => setSeverity("critical")}
            >
              CRIT
            </Button>
            <Button
              size="sm"
              variant={severity === "high" ? "default" : "outline"}
              onClick={() => setSeverity("high")}
            >
              HIGH
            </Button>
            <Button
              size="sm"
              variant={severity === "medium" ? "default" : "outline"}
              onClick={() => setSeverity("medium")}
            >
              MED
            </Button>
            <Button
              size="sm"
              variant={severity === "low" ? "default" : "outline"}
              onClick={() => setSeverity("low")}
            >
              LOW
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {filtered.length === 0 ? (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            <div className="flex flex-col items-center gap-2 text-center px-6">
              <AlertTriangle className="w-5 h-5 opacity-60" />
              <span className="text-sm">
                {props.isRunning ? "等待实时发现..." : "暂无未验证发现"}
              </span>
            </div>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="p-3 space-y-2">
              {filtered.map((item) => {
                const sevKey = normalizeSeverity(item.severity);
                return (
                  <div
                    key={item.id}
                    className="rounded-lg border border-border bg-background/40 hover:border-primary/30 transition-colors px-3 py-2.5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge
                            className={`border text-[11px] ${SEVERITY_BADGE_CLASS[sevKey] || SEVERITY_BADGE_CLASS.info}`}
                          >
                            {sevKey.toUpperCase()}
                          </Badge>
                          <span className="text-sm font-semibold break-words line-clamp-2">
                            {item.title || "未命名漏洞"}
                          </span>
                        </div>

                        <div className="mt-1 text-xs text-muted-foreground flex flex-wrap gap-x-3 gap-y-1">
                          <span>类型: {item.vulnerability_type || "-"}</span>
                          <span>定位: {formatLocation(item)}</span>
                        </div>
                      </div>

                      <Badge
                        variant="outline"
                        className="text-[11px] border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-500/10"
                      >
                        未验证
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}

