import { ChevronRight, FolderOpen, Settings2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";

export default function AdvancedOptionsSection({
  open,
  onOpenChange,
  excludePatterns,
  onResetExcludes,
  onRemoveExclude,
  onAddExclude,
  onCustomExcludeEnter,
  canSelectFiles,
  selectedFiles,
  onResetSelectedFiles,
  onOpenFileSelection,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  excludePatterns: string[];
  onResetExcludes: () => void;
  onRemoveExclude: (pattern: string) => void;
  onAddExclude: (pattern: string) => void;
  onCustomExcludeEnter: (value: string) => void;
  canSelectFiles: boolean;
  selectedFiles?: string[];
  onResetSelectedFiles: () => void;
  onOpenFileSelection: () => void;
}) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <CollapsibleTrigger className="flex items-center gap-2 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors">
        <ChevronRight
          className={`w-4 h-4 transition-transform ${open ? "rotate-90" : ""}`}
        />
        <Settings2 className="w-4 h-4" />
        <span className="uppercase font-bold">高级选项</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-3 space-y-3">
        <div className="p-3 border border-dashed border-border rounded bg-muted/50 space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs uppercase font-bold text-muted-foreground">
              排除模式
            </span>
            <button
              type="button"
              onClick={onResetExcludes}
              className="text-xs font-mono text-primary hover:text-primary/80"
            >
              重置为默认
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {excludePatterns.map((pattern) => (
              <Badge
                key={pattern}
                className="bg-muted text-foreground border-0 font-mono text-xs cursor-pointer hover:bg-rose-100 dark:hover:bg-rose-900/50 hover:text-rose-600 dark:hover:text-rose-400"
                onClick={() => onRemoveExclude(pattern)}
              >
                {pattern} ×
              </Badge>
            ))}
            {excludePatterns.length === 0 && (
              <span className="text-xs text-muted-foreground font-mono">
                无排除模式
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-muted-foreground font-mono mr-1">
              快捷添加:
            </span>
            {[".test.", ".spec.", ".min.", "coverage/", "docs/", ".md"].map(
              (pattern) => (
                <button
                  key={pattern}
                  type="button"
                  disabled={excludePatterns.includes(pattern)}
                  onClick={() => onAddExclude(pattern)}
                  className="text-xs font-mono px-1.5 py-0.5 border border-border bg-muted hover:bg-muted text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed rounded"
                >
                  +{pattern}
                </button>
              ),
            )}
          </div>

          <Input
            placeholder="添加自定义排除模式，回车确认"
            className="h-8 cyber-input text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.currentTarget.value) {
                onCustomExcludeEnter(e.currentTarget.value);
                e.currentTarget.value = "";
              }
            }}
          />
        </div>

        <div className="flex items-center justify-between p-3 border border-dashed border-border rounded bg-muted/50">
          <div>
            <p className="font-mono text-xs uppercase font-bold text-muted-foreground">
              扫描范围
            </p>
            <p className="text-sm font-bold text-foreground mt-1">
              {selectedFiles ? `已选 ${selectedFiles.length} 个文件` : "全部文件"}
            </p>
          </div>
          <div className="flex gap-2">
            {selectedFiles && canSelectFiles && (
              <Button
                size="sm"
                variant="ghost"
                onClick={onResetSelectedFiles}
                className="h-8 text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/30 hover:text-rose-700 dark:hover:text-rose-300"
              >
                重置
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={onOpenFileSelection}
              disabled={!canSelectFiles}
              className="h-8 text-xs cyber-btn-outline font-mono font-bold disabled:opacity-50"
            >
              <FolderOpen className="w-3 h-3 mr-1" />
              选择文件
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
