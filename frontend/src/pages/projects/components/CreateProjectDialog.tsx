import {
    useEffect,
    useMemo,
    useRef,
    useState,
    type ChangeEvent,
    type DragEvent,
} from "react";
import {
    AlertTriangle,
    CheckCircle2,
    FileText,
    Loader2,
    Package,
    Plus,
    Terminal,
    Trash2,
    Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
    SUPPORTED_ARCHIVE_INPUT_ACCEPT,
    validateZipFile,
} from "@/features/projects/services";
import type { CreateProjectForm } from "@/shared/types";
import { formatFileSize } from "@/shared/utils/zipStorage";
import { toast } from "sonner";
import {
    createEmptyProjectForm,
    PROJECT_ACTION_BTN_SUBTLE,
} from "../constants";
import type {
    BatchCreateZipProjectItem,
    BatchCreateZipProjectsProgressEvent,
    BatchCreateZipProjectsResult,
} from "../data/projectsPageWorkflows";
import {
    appendZipBatchFiles,
    validateZipBatchItems,
    type ZipBatchItem,
    type ZipBatchItemStatus,
} from "../lib/createProjectDialogBatch";

interface CreateProjectDialogProps {
    open: boolean;
    supportedLanguages: string[];
    onOpenChange: (open: boolean) => void;
    onCreateZipProjects: (
        items: BatchCreateZipProjectItem[],
        sharedInput: Omit<CreateProjectForm, "name">,
        onProgress?: (event: BatchCreateZipProjectsProgressEvent) => void,
    ) => Promise<BatchCreateZipProjectsResult>;
}



function getStatusBadgeVariant(status: ZipBatchItemStatus) {
    switch (status) {
        case "success":
            return "default";
        case "failed":
            return "destructive";
        case "creating":
            return "secondary";
        default:
            return "outline";
    }
}

function getStatusLabel(status: ZipBatchItemStatus) {
    switch (status) {
        case "success":
            return "已创建";
        case "failed":
            return "失败";
        case "creating":
            return "创建中";
        default:
            return "待创建";
    }
}

export default function CreateProjectDialog({
    open,
    onOpenChange,
    onCreateZipProjects,
}: CreateProjectDialogProps) {
    const [form, setForm] = useState<CreateProjectForm>(createEmptyProjectForm);
    const [batchItems, setBatchItems] = useState<ZipBatchItem[]>([]);
    const [uploading, setUploading] = useState(false);
    const [dragActive, setDragActive] = useState(false);
    const [invalidNameIds, setInvalidNameIds] = useState<string[]>([]);
    const [uploadSummary, setUploadSummary] =
        useState<BatchCreateZipProjectsResult | null>(null);
    const [uploadProgress, setUploadProgress] = useState({
        completed: 0,
        total: 0,
        currentProjectName: "",
    });
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (!open) {
            setBatchItems([]);
            setUploading(false);
            setDragActive(false);
            setInvalidNameIds([]);
            setUploadSummary(null);
            setUploadProgress({
                completed: 0,
                total: 0,
                currentProjectName: "",
            });
            setForm(createEmptyProjectForm());
        }
    }, [open]);

    function pushFiles(nextFiles: File[]) {
        if (nextFiles.length === 0) return;
        const result = appendZipBatchFiles({
            existingItems: batchItems,
            files: nextFiles,
            validateFile: validateZipFile,
        });
        setBatchItems(result.items);
        setInvalidNameIds([]);

        for (const rejection of result.rejections) {
            toast.error(`${rejection.fileName}: ${rejection.message}`);
        }
    }

    function handleFileSelect(event: ChangeEvent<HTMLInputElement>) {
        pushFiles(Array.from(event.target.files || []));
        event.target.value = "";
    }

    function handleDrop(event: DragEvent<HTMLDivElement>) {
        event.preventDefault();
        setDragActive(false);
        if (uploading || uploadSummary) return;
        pushFiles(Array.from(event.dataTransfer.files || []));
    }

    function handleUpdateBatchItemName(itemId: string, nextName: string) {
        setBatchItems((previous) =>
            previous.map((item) =>
                item.id === itemId
                    ? {
                        ...item,
                        editableName: nextName,
                    }
                    : item,
            ),
        );
        setInvalidNameIds((previous) => previous.filter((id) => id !== itemId));
    }

    function handleRemoveBatchItem(itemId: string) {
        setBatchItems((previous) =>
            previous.filter((item) => item.id !== itemId),
        );
        setInvalidNameIds((previous) => previous.filter((id) => id !== itemId));
    }

    async function handleCreateZipBatch() {
        if (batchItems.length === 0) {
            toast.error("请先选择至少一个压缩包文件");
            return;
        }

        const validation = validateZipBatchItems(batchItems);
        if (!validation.valid) {
            setInvalidNameIds(validation.invalidItemIds);
            toast.error("请先填写所有项目名称");
            return;
        }

        const submittedItems = batchItems.map((item) => ({
            ...item,
            editableName: item.editableName.trim(),
            status: "idle" as const,
            errorMessage: undefined,
        }));

        setBatchItems(submittedItems);
        setInvalidNameIds([]);
        setUploadSummary(null);
        setUploading(true);
        setUploadProgress({
            completed: 0,
            total: submittedItems.length,
            currentProjectName: submittedItems[0]?.editableName || "",
        });

        try {
            const result = await onCreateZipProjects(
                submittedItems.map((item) => ({
                    file: item.file,
                    projectName: item.editableName,
                })),
                {
                    description: "",
                    source_type: "zip",
                    repository_type: "other",
                    repository_url: undefined,
                    default_branch: form.default_branch,
                    programming_languages: form.programming_languages,
                },
                (event) => {
                    const targetId = submittedItems[event.index]?.id;
                    setBatchItems((previous) =>
                        previous.map((item) =>
                            item.id === targetId
                                ? {
                                    ...item,
                                    status:
                                        event.status === "creating"
                                            ? "creating"
                                            : event.status,
                                    errorMessage:
                                        event.status === "failed"
                                            ? event.message
                                            : undefined,
                                }
                                : item,
                        ),
                    );
                    setUploadProgress({
                        completed:
                            event.status === "creating"
                                ? event.index
                                : Math.min(
                                    event.index + 1,
                                    submittedItems.length,
                                ),
                        total: submittedItems.length,
                        currentProjectName: event.projectName,
                    });
                },
            );
            setUploadSummary(result);
            setUploadProgress({
                completed: result.total,
                total: result.total,
                currentProjectName: "",
            });
        } catch {
            toast.error("批量创建项目失败");
        } finally {
            setUploading(false);
        }
    }

    const progressValue = useMemo(() => {
        if (uploadProgress.total === 0) return 0;
        return Math.round(
            (uploadProgress.completed / uploadProgress.total) * 100,
        );
    }, [uploadProgress.completed, uploadProgress.total]);

    const isUploadComplete = Boolean(uploadSummary);

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (uploading) return;
                onOpenChange(nextOpen);
            }}
        >
            <DialogContent
                aria-describedby={undefined}
                className="!w-[min(92vw,760px)] !max-w-none max-h-[88vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
                showCloseButton={!uploading}
            >
                <DialogHeader className="px-6 pt-4 flex-shrink-0">
                    <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                        <Terminal className="w-5 h-5 text-primary" />
                        初始化新项目
                    </DialogTitle>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto p-6">
                    <div className="flex flex-col gap-5">
                        <div className="space-y-3">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <Label className="font-mono font-bold uppercase text-base text-muted-foreground">
                                        源码压缩包
                                    </Label>
                                </div>
                                {batchItems.length > 0 && !isUploadComplete ? (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="cyber-btn-outline h-9 text-xs"
                                        disabled={uploading}
                                        onClick={() =>
                                            fileInputRef.current?.click()
                                        }
                                    >
                                        <Plus className="w-3 h-3 mr-2" />
                                        继续添加
                                    </Button>
                                ) : null}
                            </div>

                            <input
                                ref={fileInputRef}
                                type="file"
                                accept={SUPPORTED_ARCHIVE_INPUT_ACCEPT}
                                onChange={handleFileSelect}
                                className="hidden"
                                disabled={uploading || isUploadComplete}
                                multiple
                            />

                            {batchItems.length === 0 ? (
                                <div
                                    className={`border rounded-lg border-dashed p-8 text-center transition-colors ${dragActive
                                        ? "border-primary bg-primary/5"
                                        : "border-border bg-muted/40 hover:bg-muted/70"
                                        } ${uploading ? "pointer-events-none opacity-60" : "cursor-pointer"}`}
                                    onClick={() => {
                                        if (uploading || isUploadComplete)
                                            return;
                                        fileInputRef.current?.click();
                                    }}
                                    onDragOver={(event) => {
                                        event.preventDefault();
                                        if (!uploading && !isUploadComplete) {
                                            setDragActive(true);
                                        }
                                    }}
                                    onDragLeave={() => setDragActive(false)}
                                    onDrop={handleDrop}
                                >
                                    <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                                    <h3 className="text-base font-bold text-foreground uppercase mb-1">
                                        选择压缩包
                                    </h3>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="cyber-btn-outline h-8 text-xs"
                                        disabled={uploading || isUploadComplete}
                                        onClick={(event) => {
                                            event.stopPropagation();
                                            fileInputRef.current?.click();
                                        }}
                                    >
                                        {/* <FileText className="w-3 h-3 mr-2" />
                                        选择压缩包 */}
                                    </Button>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                                        <span>
                                            导入队列 {batchItems.length} 项
                                        </span>
                                        <span>
                                            {uploading
                                                ? `处理中: ${uploadProgress.currentProjectName || "准备中"}`
                                                : isUploadComplete
                                                    ? `完成: 成功 ${uploadSummary?.successCount || 0} / 失败 ${uploadSummary?.failureCount || 0}`
                                                    : "提交前可逐项修改项目名"}
                                        </span>
                                    </div>
                                    <div className="max-h-[300px] overflow-y-auto space-y-3 pr-1">
                                        {batchItems.map((item) => {
                                            const isInvalid =
                                                invalidNameIds.includes(
                                                    item.id,
                                                );
                                            return (
                                                <div
                                                    key={item.id}
                                                    className={`rounded-lg border p-4 bg-muted/30 ${isInvalid
                                                        ? "border-rose-500/70"
                                                        : "border-border"
                                                        }`}
                                                >
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div className="min-w-0 flex-1 space-y-3">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <p className="font-mono font-bold text-sm text-foreground truncate">
                                                                    {
                                                                        item.fileName
                                                                    }
                                                                </p>
                                                                <Badge
                                                                    variant={getStatusBadgeVariant(
                                                                        item.status,
                                                                    )}
                                                                    className="text-[10px]"
                                                                >
                                                                    {item.status ===
                                                                        "creating" ? (
                                                                        <Loader2 className="w-3 h-3 animate-spin" />
                                                                    ) : item.status ===
                                                                        "success" ? (
                                                                        <CheckCircle2 className="w-3 h-3" />
                                                                    ) : item.status ===
                                                                        "failed" ? (
                                                                        <AlertTriangle className="w-3 h-3" />
                                                                    ) : (
                                                                        <Package className="w-3 h-3" />
                                                                    )}
                                                                    {getStatusLabel(
                                                                        item.status,
                                                                    )}
                                                                </Badge>
                                                                <span className="text-xs font-mono text-muted-foreground">
                                                                    {formatFileSize(
                                                                        item.size,
                                                                    )}
                                                                </span>
                                                            </div>
                                                            <div className="space-y-1.5">
                                                                <Label
                                                                    htmlFor={`zip-project-name-${item.id}`}
                                                                    className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground"
                                                                >
                                                                    项目名称
                                                                </Label>
                                                                <Input
                                                                    id={`zip-project-name-${item.id}`}
                                                                    value={
                                                                        item.editableName
                                                                    }
                                                                    onChange={(
                                                                        event,
                                                                    ) =>
                                                                        handleUpdateBatchItemName(
                                                                            item.id,
                                                                            event
                                                                                .target
                                                                                .value,
                                                                        )
                                                                    }
                                                                    disabled={
                                                                        uploading ||
                                                                        isUploadComplete
                                                                    }
                                                                    className={`h-10 font-mono ${isInvalid
                                                                        ? "border-rose-500 focus-visible:ring-rose-500/40"
                                                                        : "focus-visible:ring-primary/30"
                                                                        }`}
                                                                />
                                                                {isInvalid ? (
                                                                    <p className="text-xs font-mono text-rose-400">
                                                                        项目名称不能为空
                                                                    </p>
                                                                ) : null}
                                                                {item.errorMessage ? (
                                                                    <p className="text-xs font-mono text-rose-400">
                                                                        {
                                                                            item.errorMessage
                                                                        }
                                                                    </p>
                                                                ) : null}
                                                            </div>
                                                        </div>
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="icon"
                                                            disabled={
                                                                uploading ||
                                                                isUploadComplete
                                                            }
                                                            onClick={() =>
                                                                handleRemoveBatchItem(
                                                                    item.id,
                                                                )
                                                            }
                                                            className="hover:bg-rose-500/10 hover:text-rose-400 shrink-0"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {(uploading || isUploadComplete) &&
                                uploadProgress.total > 0 ? (
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                                        <span>
                                            {uploading
                                                ? "批量创建进行中..."
                                                : "批量创建已完成"}
                                        </span>
                                        <span className="text-primary">
                                            {uploadProgress.completed}/
                                            {uploadProgress.total}
                                        </span>
                                    </div>
                                    <Progress
                                        value={progressValue}
                                        className="h-2 bg-muted [&>div]:bg-primary"
                                    />
                                </div>
                            ) : null}
                        </div>

                        {uploadSummary ? (
                            <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                                <div className="flex flex-wrap items-center gap-2">
                                    <Badge className="text-[10px]">
                                        成功 {uploadSummary.successCount}
                                    </Badge>
                                    <Badge
                                        variant={
                                            uploadSummary.failureCount > 0
                                                ? "destructive"
                                                : "outline"
                                        }
                                        className="text-[10px]"
                                    >
                                        失败 {uploadSummary.failureCount}
                                    </Badge>
                                </div>
                                {uploadSummary.failureCount > 0 ? (
                                    <div className="space-y-2">
                                        <p className="text-xs font-mono uppercase tracking-wide text-muted-foreground">
                                            失败明细
                                        </p>
                                        <div className="max-h-32 overflow-y-auto space-y-2">
                                            {uploadSummary.failures.map(
                                                (failure) => (
                                                    <div
                                                        key={`${failure.fileName}-${failure.projectName}`}
                                                        className="rounded border border-rose-500/30 bg-rose-500/5 p-3"
                                                    >
                                                        <p className="text-sm font-mono font-semibold text-foreground">
                                                            {
                                                                failure.projectName
                                                            }
                                                        </p>
                                                        <p className="text-xs font-mono text-muted-foreground">
                                                            {failure.fileName}
                                                        </p>
                                                        <p className="mt-1 text-xs font-mono text-rose-300">
                                                            {failure.message}
                                                        </p>
                                                    </div>
                                                ),
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <p className="text-xs font-mono text-muted-foreground">
                                        全部压缩包均已创建为独立项目。
                                    </p>
                                )}
                            </div>
                        ) : null}

                        <div className="flex justify-end space-x-4 pt-4 border-t border-border mt-auto">
                            <Button
                                variant="outline"
                                onClick={() => onOpenChange(false)}
                                disabled={uploading}
                                className="cyber-btn-outline"
                            >
                                {uploadSummary ? "关闭" : "取消"}
                            </Button>
                            <Button
                                onClick={
                                    uploadSummary
                                        ? () => onOpenChange(false)
                                        : handleCreateZipBatch
                                }
                                className={PROJECT_ACTION_BTN_SUBTLE}
                                disabled={uploading || batchItems.length === 0}
                            >
                                {uploading
                                    ? "创建中..."
                                    : uploadSummary
                                        ? "完成"
                                        : "执行创建"}
                            </Button>
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
