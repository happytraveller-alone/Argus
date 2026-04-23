import { useEffect, useRef, useState } from "react";
import { CheckCircle, Edit, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { validateZipFile } from "@/features/projects/services";
import type { CreateProjectForm, Project } from "@/shared/types";
import {
    HTTPS_ONLY_REPOSITORY_ERROR,
    isUnsupportedRepositoryUrl,
} from "@/shared/utils/projectUtils";
import { toast } from "sonner";
import {
    createEmptyProjectForm,
    normalizeProgrammingLanguages,
    PROJECT_ACTION_BTN_SUBTLE,
} from "../constants";

interface EditProjectDialogProps {
    open: boolean;
    project: Project | null;
    supportedLanguages: string[];
    onOpenChange: (open: boolean) => void;
    onSubmit: (
        projectId: string,
        input: Partial<CreateProjectForm>,
        zipFile?: File | null,
    ) => Promise<void>;
}

export default function EditProjectDialog({
    open,
    project,
    supportedLanguages,
    onOpenChange,
    onSubmit,
}: EditProjectDialogProps) {
    const [form, setForm] = useState<CreateProjectForm>(createEmptyProjectForm);
    const [zipFile, setZipFile] = useState<File | null>(null);
    const zipInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (!open || !project) {
            setForm(createEmptyProjectForm());
            setZipFile(null);
            return;
        }

        setForm({
            name: project.name,
            description: project.description || "",
            source_type: "zip",
            repository_url: undefined,
            repository_type: "other",
            default_branch: project.default_branch || "main",
            programming_languages: normalizeProgrammingLanguages(
                project.programming_languages,
            ),
        });
        setZipFile(null);
    }, [open, project]);

    if (!project) {
        return null;
    }

    function updateForm(updates: Partial<CreateProjectForm>) {
        setForm((previous) => ({
            ...previous,
            ...updates,
        }));
    }

    async function handleSubmit() {
        const projectId = project?.id;
        if (!projectId) return;

        if (!form.name.trim()) {
            toast.error("项目名称不能为空");
            return;
        }
        if (
            form.source_type === "repository" &&
            isUnsupportedRepositoryUrl(form.repository_url)
        ) {
            toast.error(HTTPS_ONLY_REPOSITORY_ERROR);
            return;
        }

        try {
            await onSubmit(projectId, form, zipFile);
            onOpenChange(false);
        } catch {
            // keep dialog state for retry
        }
    }

    function toggleLanguage(language: string) {
        updateForm({
            programming_languages: form.programming_languages.includes(language)
                ? form.programming_languages.filter((item) => item !== language)
                : [...form.programming_languages, language],
        });
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                aria-describedby={undefined}
                className="!w-[min(90vw,700px)] !max-w-none max-h-[85vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
            >
                <DialogHeader className="px-6 pt-4 flex-shrink-0">
                    <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                        <Edit className="w-5 h-5 text-primary" />
                        编辑项目配置
                        <Badge className="ml-2 cyber-badge-warning">
                            上传项目
                        </Badge>
                    </DialogTitle>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    <div className="space-y-4">
                        <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                            基本信息
                        </h3>
                        <div>
                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                项目名称
                            </Label>
                            <Input
                                value={form.name}
                                onChange={(event) =>
                                    updateForm({ name: event.target.value })
                                }
                                className="cyber-input mt-1"
                            />
                        </div>
                        <div>
                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                描述
                            </Label>
                            <Textarea
                                value={form.description}
                                onChange={(event) =>
                                    updateForm({
                                        description: event.target.value,
                                    })
                                }
                                rows={3}
                                className="cyber-input mt-1"
                            />
                        </div>
                    </div>

                    <div className="space-y-4">
                        <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2 flex items-center gap-2">
                            <Upload className="w-4 h-4" />
                            ZIP 文件管理
                        </h3>
                        <input
                            ref={zipInputRef}
                            type="file"
                            accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
                            className="hidden"
                            onChange={(event) => {
                                const file = event.target.files?.[0];
                                if (!file) return;
                                const validation = validateZipFile(file);
                                if (!validation.valid) {
                                    toast.error(validation.error || "文件无效");
                                    event.target.value = "";
                                    return;
                                }
                                setZipFile(file);
                            }}
                        />
                        <Button
                            variant="outline"
                            onClick={() => zipInputRef.current?.click()}
                            className="cyber-btn-outline w-full"
                        >
                            <Upload className="w-4 h-4 mr-2" />
                            {zipFile
                                ? `已选择: ${zipFile.name}`
                                : "选择 ZIP 文件"}
                        </Button>
                    </div>
                </div>

                <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        className="cyber-btn-outline"
                    >
                        取消
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        className={PROJECT_ACTION_BTN_SUBTLE}
                    >
                        保存更改
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
