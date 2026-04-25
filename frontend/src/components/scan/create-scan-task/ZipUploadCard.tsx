import { Loader2, Package, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  SUPPORTED_ARCHIVE_INPUT_ACCEPT,
  validateZipFile,
} from "@/features/projects/services/repoZipScan";
import { formatFileSize, useZipFile } from "../hooks/useZipFile";

export default function ZipUploadCard({
  zipState,
  onUpload,
  uploading,
}: {
  zipState: ReturnType<typeof useZipFile>;
  onUpload: () => void;
  uploading: boolean;
}) {
  if (zipState.loading) {
    return (
      <div className="flex items-center gap-3 p-3 border border-border rounded bg-blue-50 dark:bg-blue-950/20">
        <Loader2 className="w-5 h-5 animate-spin text-blue-600 dark:text-blue-400" />
        <span className="text-sm font-mono text-blue-600 dark:text-blue-400">
          检查文件中...
        </span>
      </div>
    );
  }

  if (zipState.storedZipInfo?.has_file) {
    return (
      <div className="p-3 border border-border rounded bg-emerald-50 dark:bg-emerald-950/20 space-y-3">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-emerald-500/20 rounded">
            <Package className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold text-emerald-700 dark:text-emerald-300 font-mono">
              {zipState.storedZipInfo.original_filename}
            </p>
            <p className="text-xs text-emerald-600 dark:text-emerald-500 font-mono">
              {zipState.storedZipInfo.file_size &&
                formatFileSize(zipState.storedZipInfo.file_size)}
              {zipState.storedZipInfo.uploaded_at &&
                ` · ${new Date(zipState.storedZipInfo.uploaded_at).toLocaleDateString("zh-CN")}`}
            </p>
          </div>
        </div>

        {!zipState.useStoredZip && (
          <div className="flex gap-2 items-center">
            <Input
              type="file"
              accept={SUPPORTED_ARCHIVE_INPUT_ACCEPT}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  const validation = validateZipFile(file);
                  if (!validation.valid) {
                    toast.error(validation.error || "文件无效");
                    e.target.value = "";
                    return;
                  }
                  zipState.handleFileSelect(file, e.target);
                }
              }}
              className="h-9 flex-1 border border-border rounded bg-background px-3 py-1.5 text-sm font-mono file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-mono file:bg-primary/20 file:text-primary hover:file:bg-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
            {zipState.zipFile && (
              <Button
                size="sm"
                onClick={onUpload}
                disabled={uploading}
                className="h-9 px-3 cyber-btn-primary"
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
              </Button>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="p-3 border border-dashed border-amber-500/50 rounded bg-amber-50 dark:bg-amber-950/20">
      <div className="flex items-start gap-3">
        <div className="p-1.5 bg-amber-500/20 rounded">
          <Upload className="w-4 h-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold text-amber-700 dark:text-amber-300 font-mono uppercase">
            上传源码归档
          </p>
          <div className="flex gap-2 items-center mt-2">
            <Input
              type="file"
              accept={SUPPORTED_ARCHIVE_INPUT_ACCEPT}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  const validation = validateZipFile(file);
                  if (!validation.valid) {
                    toast.error(validation.error || "文件无效");
                    e.target.value = "";
                    return;
                  }
                  zipState.handleFileSelect(file, e.target);
                }
              }}
              className="h-9 flex-1 border border-border rounded bg-background px-3 py-1.5 text-sm font-mono file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-mono file:bg-primary/20 file:text-primary hover:file:bg-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
            {zipState.zipFile && (
              <Button
                size="sm"
                onClick={onUpload}
                disabled={uploading}
                className="h-9 px-3 cyber-btn-primary"
              >
                {uploading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
              </Button>
            )}
          </div>
          {zipState.zipFile && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-2 font-mono">
              已选: {zipState.zipFile.name} ({formatFileSize(zipState.zipFile.size)})
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
