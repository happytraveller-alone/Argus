/**
 * Projects Page
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect, useMemo, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import {
    Plus,
    Search,
    GitBranch,
    Clock,
    Code,
    Shield,
    Upload,
    FileText,
    AlertCircle,
    Trash2,
    Edit,
    CheckCircle,
    Terminal,
    Github,
    Folder,
    ArrowUpRight,
    Key,
    Sparkles,
} from "lucide-react";
import { api } from "@/shared/config/database";
import { validateZipFile } from "@/features/projects/services";
import type { Project, CreateProjectForm } from "@/shared/types";
import {
    uploadZipFile,
    getZipFileInfo,
    type ZipFileMeta,
} from "@/shared/utils/zipStorage";
import {
    isZipProject,
    getSourceTypeBadge,
} from "@/shared/utils/projectUtils";
import { Link, useLocation } from "react-router-dom";
import { toast } from "sonner";
import CreateProjectAuditDialog, {
    type AuditCreateMode,
} from "@/components/audit/CreateProjectAuditDialog";
import CreateStaticAuditDialog from "@/components/audit/CreateStaticAuditDialog";
import CreateAgentAuditDialog from "@/components/audit/CreateAgentAuditDialog";
import { SUPPORTED_LANGUAGES, REPOSITORY_PLATFORMS } from "@/shared/constants";
import { useI18n } from "@/shared/i18n";
import {
    getAgentTasks,
    type AgentTask,
} from "@/shared/api/agentTasks";
import {
    getOpengrepScanTasks,
    type OpengrepScanTask,
} from "@/shared/api/opengrep";
import {
    getGitleaksScanTasks,
    type GitleaksScanTask,
} from "@/shared/api/gitleaks";

type RecentActivityItem = {
    id: string;
    projectName: string;
    kind: "rule_scan" | "intelligent_audit";
    status: string;
    gitleaksEnabled?: boolean;
    createdAt: string;
    startedAt?: string | null;
    completedAt?: string | null;
    durationMs?: number | null;
    route: string;
};

const INTERRUPTED_STATUSES = new Set(["interrupted", "aborted", "cancelled"]);
const ACTIVITY_PAGE_SIZE = 10;
const PROJECT_PAGE_SIZE = 6;
const MODULE_SCROLL_DELAY_MS = 80;
const ARCHIVE_SUFFIXES = [
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".tbz2",
    ".zip",
    ".tar",
    ".7z",
    ".rar",
];

const stripArchiveSuffix = (filename: string) => {
    const lower = filename.toLowerCase();
    const matched = ARCHIVE_SUFFIXES.find((suffix) => lower.endsWith(suffix));
    if (!matched) return filename;
    return filename.slice(0, filename.length - matched.length);
};

function formatDurationMs(durationMs: number): string {
    const safe = Number.isFinite(durationMs)
        ? Math.max(0, Math.floor(durationMs))
        : 0;
    const totalSeconds = Math.floor(safe / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

const PROJECT_ACTION_BTN =
    "border border-sky-400/35 bg-gradient-to-r from-sky-500/20 via-cyan-500/16 to-blue-500/20 text-sky-100 shadow-[0_8px_22px_-14px_rgba(14,165,233,0.9)] hover:from-sky-500/30 hover:via-cyan-500/24 hover:to-blue-500/30 hover:border-sky-300/55";

const PROJECT_ACTION_BTN_SUBTLE =
    "border border-sky-500/30 bg-sky-500/12 text-sky-100 hover:bg-sky-500/22 hover:border-sky-400/55";

export default function Projects() {
    const location = useLocation();
    const { t } = useI18n();
    const [projects, setProjects] = useState<Project[]>([]);
    const [recentActivities, setRecentActivities] = useState<
        RecentActivityItem[]
    >([]);
    const [activityKeyword, setActivityKeyword] = useState("");
    const [activityPage, setActivityPage] = useState(1);
    const [nowTick, setNowTick] = useState(0);
    const [projectPage, setProjectPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [showCreateAuditDialog, setShowCreateAuditDialog] = useState(false);
    const [showCreateStaticAuditDialog, setShowCreateStaticAuditDialog] =
        useState(false);
    const [showCreateAgentAuditDialog, setShowCreateAgentAuditDialog] =
        useState(false);
    const [auditPreselectedProjectId, setAuditPreselectedProjectId] =
        useState<string>("");
    const [auditInitialMode, setAuditInitialMode] =
        useState<AuditCreateMode>("static");
    const [auditReturnTarget, setAuditReturnTarget] = useState<
        "task-browser" | "quick-actions" | "project-browser"
    >("task-browser");
    const [auditNavigateOnSuccess, setAuditNavigateOnSuccess] = useState(true);
    const [staticAuditNavigateOnSuccess, setStaticAuditNavigateOnSuccess] =
        useState(true);
    const [agentAuditNavigateOnSuccess, setAgentAuditNavigateOnSuccess] =
        useState(true);
    const [createProjectReturnTarget, setCreateProjectReturnTarget] =
        useState<"project-browser" | "quick-actions">("project-browser");
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploading, setUploading] = useState(false);
    const [generatingDescription, setGeneratingDescription] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [showDeleteDialog, setShowDeleteDialog] = useState(false);
    const [projectToDelete, setProjectToDelete] = useState<Project | null>(
        null,
    );
    const [showEditDialog, setShowEditDialog] = useState(false);
    const [projectToEdit, setProjectToEdit] = useState<Project | null>(null);
    const [editForm, setEditForm] = useState<CreateProjectForm>({
        name: "",
        description: "",
        source_type: "repository",
        repository_url: "",
        repository_type: "github",
        default_branch: "main",
        programming_languages: [],
    });
    const [createForm, setCreateForm] = useState<CreateProjectForm>({
        name: "",
        description: "",
        source_type: "repository",
        repository_url: "",
        repository_type: "github",
        default_branch: "main",
        programming_languages: [],
    });

    const [selectedFile, setSelectedFile] = useState<File | null>(null);

    // 编辑对话框中的ZIP文件状态
    const [editZipInfo, setEditZipInfo] = useState<ZipFileMeta | null>(null);
    const [editZipFile, setEditZipFile] = useState<File | null>(null);
    const [loadingEditZipInfo, setLoadingEditZipInfo] = useState(false);
    const editZipInputRef = useRef<HTMLInputElement>(null);

    // 将小写语言名转换为显示格式
    const formatLanguageName = (lang: string): string => {
        const nameMap: Record<string, string> = {
            javascript: "JavaScript",
            typescript: "TypeScript",
            python: "Python",
            java: "Java",
            go: "Go",
            rust: "Rust",
            cpp: "C++",
            csharp: "C#",
            php: "PHP",
            ruby: "Ruby",
            swift: "Swift",
            kotlin: "Kotlin",
        };
        return nameMap[lang] || lang.charAt(0).toUpperCase() + lang.slice(1);
    };

    const supportedLanguages = SUPPORTED_LANGUAGES.map(formatLanguageName);

    useEffect(() => {
        loadProjects();
    }, []);

    useEffect(() => {
        const interval = window.setInterval(() => {
            setNowTick((prev) => prev + 1);
        }, 1000);
        return () => window.clearInterval(interval);
    }, []);

    useEffect(() => {
        const hash = window.location.hash;
        if (
            hash !== "#project-browser" &&
            hash !== "#task-browser" &&
            hash !== "#quick-actions"
        ) {
            return;
        }
        const timer = window.setTimeout(() => {
            document.getElementById(hash.replace("#", ""))?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        }, 80);
        return () => window.clearTimeout(timer);
    }, []);

    const loadProjects = async () => {
        try {
            setLoading(true);
            const data = await api.getProjects();
            setProjects(data);
            await loadRecentActivities(data);
        } catch (error) {
            console.error("Failed to load projects:", error);
            toast.error("加载项目失败");
        } finally {
            setLoading(false);
        }
    };

    const loadRecentActivities = async (allProjects: Project[]) => {
        try {
            const [agentTasks, opengrepTasks, gitleaksTasks] =
                await Promise.all([
                    getAgentTasks({ limit: 100 }),
                    getOpengrepScanTasks({ limit: 100 }),
                    getGitleaksScanTasks({ limit: 100 }),
                ]);

            const projectNameMap = new Map(
                allProjects.map((project) => [project.id, project.name]),
            );
            const resolveProjectName = (projectId: string) =>
                projectNameMap.get(projectId) || "未知项目";

            const gitleaksByProject = new Map<string, GitleaksScanTask[]>();
            for (const task of gitleaksTasks) {
                const list = gitleaksByProject.get(task.project_id) || [];
                list.push(task);
                gitleaksByProject.set(task.project_id, list);
            }
            for (const [projectId, list] of gitleaksByProject.entries()) {
                list.sort(
                    (a, b) =>
                        new Date(a.created_at).getTime() -
                        new Date(b.created_at).getTime(),
                );
                gitleaksByProject.set(projectId, list);
            }

            const usedGitleaksTaskIds = new Set<string>();
            const pairingWindowMs = 60 * 1000;
            const pickPairedGitleaksTask = (opengrepTask: OpengrepScanTask) => {
                const candidates =
                    gitleaksByProject.get(opengrepTask.project_id) || [];
                if (candidates.length === 0) return null;
                const opengrepTime = new Date(opengrepTask.created_at).getTime();
                let bestTask: GitleaksScanTask | null = null;
                let bestDiff = Number.POSITIVE_INFINITY;
                for (const candidate of candidates) {
                    if (usedGitleaksTaskIds.has(candidate.id)) continue;
                    const diff = Math.abs(
                        new Date(candidate.created_at).getTime() - opengrepTime,
                    );
                    if (diff <= pairingWindowMs && diff < bestDiff) {
                        bestTask = candidate;
                        bestDiff = diff;
                    }
                }
                if (bestTask) {
                    usedGitleaksTaskIds.add(bestTask.id);
                }
                return bestTask;
            };

            const visibleOpengrepTasks = opengrepTasks.filter(
                (task) => !task.name.startsWith("Agent Bootstrap OpenGrep"),
            );

            const ruleScanActivities: RecentActivityItem[] = visibleOpengrepTasks.map(
                (task) => {
                    const pairedGitleaksTask = pickPairedGitleaksTask(task);
                    const params = new URLSearchParams();
                    params.set("opengrepTaskId", task.id);
                    params.set("muteToast", "1");
                    if (pairedGitleaksTask) {
                        params.set("gitleaksTaskId", pairedGitleaksTask.id);
                    }
                    return {
                        id: `opengrep-${task.id}`,
                        projectName: resolveProjectName(task.project_id),
                        kind: "rule_scan" as const,
                        status: task.status,
                        gitleaksEnabled: Boolean(pairedGitleaksTask),
                        createdAt: task.created_at,
                        durationMs:
                            (task.scan_duration_ms || 0) +
                            (pairedGitleaksTask?.scan_duration_ms || 0),
                        route: `/static-analysis/${task.id}?${params.toString()}`,
                    };
                },
            );

            const activityItems: RecentActivityItem[] = [
                ...ruleScanActivities,
                ...agentTasks.map((task: AgentTask) => ({
                    id: `agent-${task.id}`,
                    projectName: resolveProjectName(task.project_id),
                    kind: "intelligent_audit" as const,
                    status: task.status,
                    createdAt: task.created_at,
                    startedAt: task.started_at,
                    completedAt: task.completed_at,
                    route: `/agent-audit/${task.id}?muteToast=1`,
                })),
            ].sort(
                (a, b) =>
                    new Date(b.createdAt).getTime() -
                    new Date(a.createdAt).getTime(),
            );

            setRecentActivities(activityItems);
        } catch (error) {
            console.error("加载任务浏览失败:", error);
            setRecentActivities([]);
        }
    };

    const scrollToModule = (
        moduleId: "task-browser" | "project-browser" | "quick-actions",
    ) => {
        window.setTimeout(() => {
            document.getElementById(moduleId)?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        }, MODULE_SCROLL_DELAY_MS);
    };

    const pinToModuleHash = (
        moduleId: "task-browser" | "project-browser" | "quick-actions",
    ) => {
        const { pathname, search } = window.location;
        window.history.replaceState(
            window.history.state,
            "",
            `${pathname}${search}#${moduleId}`,
        );
    };

    const closeCreateProjectDialog = (
        target: "project-browser" | "quick-actions" = createProjectReturnTarget,
    ) => {
        setShowCreateDialog(false);
        pinToModuleHash(target);
        scrollToModule(target);
        setCreateProjectReturnTarget("project-browser");
    };

    const handleCreateProjectDialogOpenChange = (open: boolean) => {
        if (open) {
            setShowCreateDialog(true);
            return;
        }
        closeCreateProjectDialog();
    };

    const handleCreateAuditDialogOpenChange = (open: boolean) => {
        setShowCreateAuditDialog(open);
        if (!open) {
            setAuditPreselectedProjectId("");
            pinToModuleHash(auditReturnTarget);
            scrollToModule(auditReturnTarget);
            setAuditReturnTarget("task-browser");
            setAuditNavigateOnSuccess(true);
            setAuditInitialMode("static");
        }
    };

    const handleCreateStaticAuditDialogOpenChange = (open: boolean) => {
        setShowCreateStaticAuditDialog(open);
        if (!open) {
            pinToModuleHash("quick-actions");
            scrollToModule("quick-actions");
            setStaticAuditNavigateOnSuccess(true);
        }
    };

    const handleCreateAgentAuditDialogOpenChange = (open: boolean) => {
        setShowCreateAgentAuditDialog(open);
        if (!open) {
            pinToModuleHash("quick-actions");
            scrollToModule("quick-actions");
            setAgentAuditNavigateOnSuccess(true);
        }
    };

    const handleOpenCreateProject = () => {
        setCreateProjectReturnTarget("project-browser");
        pinToModuleHash("project-browser");
        setShowCreateDialog(true);
    };

    const openCreateProjectFromQuickActions = () => {
        setCreateProjectReturnTarget("quick-actions");
        pinToModuleHash("quick-actions");
        setShowCreateDialog(true);
    };

    const openCreateAuditDialog = (
        mode: AuditCreateMode = "static",
        projectId = "",
        options?: {
            returnTarget?: "task-browser" | "quick-actions" | "project-browser";
            navigateOnSuccess?: boolean;
        },
    ) => {
        const returnTarget = options?.returnTarget || "task-browser";
        const navigateOnSuccess = options?.navigateOnSuccess ?? true;
        pinToModuleHash(returnTarget);
        setAuditInitialMode(mode);
        setAuditPreselectedProjectId(projectId);
        setAuditReturnTarget(returnTarget);
        setAuditNavigateOnSuccess(navigateOnSuccess);
        setShowCreateAuditDialog(true);
    };

    const openCreateStaticAuditDialog = (
        options?: { navigateOnSuccess?: boolean },
    ) => {
        pinToModuleHash("quick-actions");
        setStaticAuditNavigateOnSuccess(options?.navigateOnSuccess ?? true);
        setShowCreateStaticAuditDialog(true);
    };

    const openCreateAgentAuditDialog = (
        options?: { navigateOnSuccess?: boolean },
    ) => {
        pinToModuleHash("quick-actions");
        setAgentAuditNavigateOnSuccess(options?.navigateOnSuccess ?? true);
        setShowCreateAgentAuditDialog(true);
    };

    const handleCreateProject = async () => {
        if (!createForm.name.trim()) {
            toast.error("请输入项目名称");
            return;
        }

        try {
            await api.createProject({
                ...createForm,
            } as any);

            import("@/shared/utils/logger").then(({ logger }) => {
                logger.logUserAction("创建项目", {
                    projectName: createForm.name,
                    repositoryType: createForm.repository_type,
                    languages: createForm.programming_languages,
                });
            });

            toast.success("项目创建成功");
            closeCreateProjectDialog();
            resetCreateForm();
            await loadProjects();
        } catch (error) {
            console.error("Failed to create project:", error);
            import("@/shared/utils/errorHandler").then(({ handleError }) => {
                handleError(error, "创建项目失败");
            });
            const errorMessage =
                error instanceof Error ? error.message : "未知错误";
            toast.error(`创建项目失败: ${errorMessage}`);
        }
    };

    const resetCreateForm = () => {
        setCreateForm({
            name: "",
            description: "",
            source_type: "repository",
            repository_url: "",
            repository_type: "github",
            default_branch: "main",
            programming_languages: [],
        });
        setSelectedFile(null);
        setGeneratingDescription(false);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
        const inputEl = event.target;
        const file = event.target.files?.[0];
        if (!file) return;

        const validation = validateZipFile(file);
        if (!validation.valid) {
            toast.error(validation.error);
            return;
        }

        const autoProjectName = stripArchiveSuffix(file.name).trim();
        if (autoProjectName) {
            setCreateForm((prev) => ({
                ...prev,
                name: autoProjectName,
            }));
        }
        setSelectedFile(file);
        inputEl.value = "";
    };

    const handleUploadAndCreate = async () => {
        if (!selectedFile) {
            toast.error("请先选择压缩包文件");
            return;
        }

        if (!createForm.name.trim()) {
            toast.error("请先输入项目名称");
            return;
        }

        let createdProject: Project | null = null;
        let progressInterval: ReturnType<typeof setInterval> | null = null;
        try {
            setUploading(true);
            setUploadProgress(0);

            progressInterval = setInterval(() => {
                setUploadProgress((prev) => {
                    if (prev >= 100) {
                        if (progressInterval) clearInterval(progressInterval);
                        return 100;
                    }
                    return prev + 20;
                });
            }, 100);

            createdProject = await api.createProject({
                ...createForm,
                source_type: "zip",
                repository_type: "other",
                repository_url: undefined,
            } as any);

            const uploadResult = await uploadZipFile(
                createdProject.id,
                selectedFile,
            );
            if (!uploadResult.success) {
                throw new Error(uploadResult.message || "压缩包上传失败");
            }
            const detectedLanguages = uploadResult.detected_languages || [];

            if (progressInterval) clearInterval(progressInterval);
            setUploadProgress(100);

            import("@/shared/utils/logger").then(({ logger }) => {
                logger.logUserAction("上传ZIP文件创建项目", {
                    projectName: createdProject?.name,
                    fileName: selectedFile.name,
                    fileSize: selectedFile.size,
                });
            });

            closeCreateProjectDialog();
            resetCreateForm();
            await loadProjects();

            toast.success(`项目 "${createdProject.name}" 已创建`, {
                description:
                    detectedLanguages.length > 0
                        ? `已自动识别语言: ${detectedLanguages.join(" / ")}`
                        : "项目压缩包已保存，您可以启动代码审计",
                duration: 4000,
            });
        } catch (error: any) {
            console.error("Upload failed:", error);
            if (createdProject) {
                try {
                    await api.deleteProject(createdProject.id);
                } catch (cleanupError) {
                    console.error("回滚失败项目失败:", cleanupError);
                }
            }
            await loadProjects();
            import("@/shared/utils/errorHandler").then(({ handleError }) => {
                handleError(error, "上传ZIP文件失败");
            });
            const rawErrorMessage = error?.message || "未知错误";
            const errorMessage = rawErrorMessage.includes("解压文件数超过 10000")
                ? "压缩包解压后文件数量超过 10000 个，请精简后重试"
                : rawErrorMessage.includes("相同内容压缩包") || rawErrorMessage.includes("相同压缩包")
                    ? "检测到重复压缩包，系统已阻止重复上传"
                    : rawErrorMessage;
            toast.error(`上传失败: ${errorMessage}`);
        } finally {
            if (progressInterval) clearInterval(progressInterval);
            setUploading(false);
            setUploadProgress(0);
        }
    };

    const handleGenerateProjectDescription = async () => {
        if (!selectedFile) {
            toast.error("请先选择压缩包文件");
            return;
        }

        try {
            setGeneratingDescription(true);
            const result = await api.generateProjectDescription({
                file: selectedFile,
                project_name: createForm.name,
            });
            setCreateForm((prev) => ({
                ...prev,
                description: result.description || "",
            }));
            if (result.source === "llm") {
                toast.success("已生成项目描述");
            } else {
                toast.success("LLM不可用，已回退静态描述");
            }
        } catch (error) {
            console.error("Failed to generate project description:", error);
            import("@/shared/utils/errorHandler").then(({ handleError }) => {
                handleError(error, "生成项目描述失败");
            });
            toast.error("生成项目描述失败");
        } finally {
            setGeneratingDescription(false);
        }
    };

    const filteredActivities = useMemo(() => {
        const keyword = activityKeyword.trim().toLowerCase();
        if (!keyword) return recentActivities;
        return recentActivities.filter((activity) => {
            const kindText =
                activity.kind === "rule_scan" ? "静态扫描" : "智能审计";
            return (
                activity.projectName.toLowerCase().includes(keyword) ||
                kindText.includes(keyword) ||
                getTaskStatusText(activity.status).includes(keyword)
            );
        });
    }, [recentActivities, activityKeyword]);

    const totalActivityPages = Math.max(
        1,
        Math.ceil(filteredActivities.length / ACTIVITY_PAGE_SIZE),
    );

    useEffect(() => {
        setActivityPage(1);
    }, [activityKeyword]);

    useEffect(() => {
        if (activityPage > totalActivityPages) {
            setActivityPage(totalActivityPages);
        }
    }, [activityPage, totalActivityPages]);

    const pagedActivities = useMemo(() => {
        const start = (activityPage - 1) * ACTIVITY_PAGE_SIZE;
        return filteredActivities.slice(start, start + ACTIVITY_PAGE_SIZE);
    }, [filteredActivities, activityPage]);

    const filteredProjects = useMemo(() => {
        const keyword = searchTerm.trim().toLowerCase();
        if (!keyword) return projects;
        return projects.filter((project) => {
            return (
                project.name.toLowerCase().includes(keyword) ||
                (project.description || "").toLowerCase().includes(keyword) ||
                (project.repository_url || "").toLowerCase().includes(keyword)
            );
        });
    }, [projects, searchTerm]);

    const totalProjectPages = Math.max(
        1,
        Math.ceil(filteredProjects.length / PROJECT_PAGE_SIZE),
    );

    useEffect(() => {
        setProjectPage(1);
    }, [searchTerm]);

    useEffect(() => {
        if (projectPage > totalProjectPages) {
            setProjectPage(totalProjectPages);
        }
    }, [projectPage, totalProjectPages]);

    const pagedProjects = useMemo(() => {
        const start = (projectPage - 1) * PROJECT_PAGE_SIZE;
        return filteredProjects.slice(start, start + PROJECT_PAGE_SIZE);
    }, [filteredProjects, projectPage]);
    const projectDetailFrom = `${location.pathname}${location.search}${location.hash}`;

    const getTaskStatusText = (status: string) => {
        switch (status) {
            case "completed":
                return "任务完成";
            case "running":
                return "任务运行中";
            case "failed":
                return "任务失败";
            case "pending":
                return "任务待处理";
            case "cancelled":
            case "interrupted":
            case "aborted":
                return "任务中止";
            default:
                return status || "未知状态";
        }
    };

    const getTaskStatusClassName = (status: string) => {
        if (status === "completed") {
            return "bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40";
        }
        if (status === "running") {
            return "bg-sky-500/5 border-sky-500/20 hover:border-sky-500/40";
        }
        if (status === "failed") {
            return "bg-rose-500/5 border-rose-500/20 hover:border-rose-500/40";
        }
        if (INTERRUPTED_STATUSES.has(status)) {
            return "bg-orange-500/5 border-orange-500/20 hover:border-orange-500/40";
        }
        return "bg-muted/30 border-border hover:border-border";
    };

    const getTaskStatusBadgeClassName = (status: string) => {
        if (status === "completed") return "cyber-badge-success";
        if (status === "running") return "cyber-badge-info";
        if (status === "failed") return "cyber-badge-danger";
        if (INTERRUPTED_STATUSES.has(status)) return "cyber-badge-warning";
        return "cyber-badge-muted";
    };

    const formatCreatedAt = (time: string) => {
        const date = new Date(time);
        if (Number.isNaN(date.getTime())) return time;
        return date.toLocaleString("zh-CN", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });
    };

    const getRelativeTime = (time: string) => {
        const now = new Date();
        const taskDate = new Date(time);
        const diffMs = now.getTime() - taskDate.getTime();
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        if (diffMins < 60) return `${Math.max(diffMins, 1)}分钟前`;
        if (diffHours < 24) return `${diffHours}小时前`;
        return `${diffDays}天前`;
    };

    const getRepositoryIcon = (type?: string) => {
        switch (type) {
            case "github":
                return <Github className="w-5 h-5" />;
            case "gitlab":
                return <GitBranch className="w-5 h-5 text-orange-500" />;
            case "gitea":
                return <GitBranch className="w-5 h-5 text-green-600" />;
            case "other":
                return <Key className="w-5 h-5 text-cyan-500" />;
            default:
                return <Folder className="w-5 h-5 text-muted-foreground" />;
        }
    };

    const getActivityDurationLabel = (activity: RecentActivityItem): string => {
        // ensure tick is referenced so running items refresh
        void nowTick;

        if (activity.kind === "rule_scan") {
            if (
                typeof activity.durationMs === "number" &&
                Number.isFinite(activity.durationMs)
            ) {
                return `用时：${formatDurationMs(activity.durationMs)}`;
            }
            return "用时：-";
        }

        const started = activity.startedAt || activity.createdAt || null;
        const completed = activity.completedAt || null;

        if (started && completed) {
            const duration =
                new Date(completed).getTime() - new Date(started).getTime();
            if (Number.isFinite(duration) && duration >= 0) {
                return `用时：${formatDurationMs(duration)}`;
            }
            return "用时：-";
        }

        if (activity.status === "running" && started) {
            const elapsed = Date.now() - new Date(started).getTime();
            if (Number.isFinite(elapsed) && elapsed >= 0) {
                return `已运行：${formatDurationMs(elapsed)}`;
            }
            return "已运行：-";
        }

        return "用时：-";
    };

    const handleCreateTask = (projectId: string) => {
        openCreateAuditDialog("agent", projectId, {
            returnTarget: "project-browser",
            navigateOnSuccess: true,
        });
    };

    const handleSaveEdit = async () => {
        if (!projectToEdit) return;

        if (!editForm.name.trim()) {
            toast.error("项目名称不能为空");
            return;
        }

        try {
            await api.updateProject(projectToEdit.id, editForm);

            if (editZipFile && editForm.source_type === "zip") {
                const result = await uploadZipFile(
                    projectToEdit.id,
                    editZipFile,
                );
                if (result.success) {
                    toast.success(`ZIP文件已更新: ${result.original_filename}`);
                } else {
                    toast.error(`ZIP文件上传失败: ${result.message}`);
                }
            }

            toast.success(`项目 "${editForm.name}" 已更新`);
            setShowEditDialog(false);
            setProjectToEdit(null);
            setEditZipFile(null);
            setEditZipInfo(null);
            loadProjects();
        } catch (error) {
            console.error("Failed to update project:", error);
            toast.error("更新项目失败");
        }
    };

    const handleToggleLanguage = (lang: string) => {
        const currentLanguages = editForm.programming_languages || [];
        const newLanguages = currentLanguages.includes(lang)
            ? currentLanguages.filter((l) => l !== lang)
            : [...currentLanguages, lang];

        setEditForm({ ...editForm, programming_languages: newLanguages });
    };

    const handleDeleteClick = (project: Project) => {
        setProjectToDelete(project);
        setShowDeleteDialog(true);
    };

    const handleConfirmDelete = async () => {
        if (!projectToDelete) return;

        try {
            await api.deleteProject(projectToDelete.id);

            import("@/shared/utils/logger").then(({ logger }) => {
                logger.logUserAction("删除项目", {
                    projectId: projectToDelete.id,
                    projectName: projectToDelete.name,
                });
            });

            toast.success(`项目 "${projectToDelete.name}" 删除成功`, {
                description: "项目已从列表中移除",
                duration: 4000,
            });
            setShowDeleteDialog(false);
            setProjectToDelete(null);
            loadProjects();
        } catch (error) {
            console.error("Failed to delete project:", error);
            import("@/shared/utils/errorHandler").then(({ handleError }) => {
                handleError(error, "删除项目失败");
            });
            const errorMessage =
                error instanceof Error ? error.message : "未知错误";
            toast.error(`删除项目失败: ${errorMessage}`);
        }
    };

    const handleTaskCreated = () => {
        toast.success("审计任务已创建", {
            description:
                "因为网络和代码文件大小等因素，审计时长通常至少需要1分钟，请耐心等待...",
            duration: 5000,
        });
        loadProjects();
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center space-y-4">
                    <div className="loading-spinner mx-auto" />
                    <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
                        加载项目数据...
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
            {/* Grid background */}
            <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

            {/* 创建项目对话框 */}
            <Dialog
                open={showCreateDialog}
                onOpenChange={handleCreateProjectDialogOpenChange}
            >
                <DialogTrigger asChild className="hidden">
                    <Button className="cyber-btn-primary">
                        <Plus className="w-5 h-5 mr-2" />
                        初始化项目
                    </Button>
                </DialogTrigger>
                <DialogContent className="!w-[min(90vw,700px)] !max-w-none max-h-[85vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
                    {/* Terminal Header */}
                    <DialogHeader className="px-6 pt-4 flex-shrink-0">
                        <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                            <Terminal className="w-5 h-5 text-primary" />
                            初始化新项目
                        </DialogTitle>
                    </DialogHeader>

                    <div className="flex-1 overflow-y-auto p-6">
                        <Tabs defaultValue="upload" className="w-full">

                            <TabsContent
                                value="repository"
                                className="flex flex-col gap-5 mt-5"
                            >
                                <div className="grid grid-cols-2 gap-5">
                                    <div className="space-y-1.5">
                                        <Label
                                            htmlFor="name"
                                            className="font-mono font-bold uppercase text-base text-muted-foreground"
                                        >
                                            项目名称
                                        </Label>
                                        <Input
                                            id="name"
                                            value={createForm.name}
                                            onChange={(e) =>
                                                setCreateForm({
                                                    ...createForm,
                                                    name: e.target.value,
                                                })
                                            }
                                            placeholder="输入项目名称"
                                            className="h-11 text-base border-0 border-b border-border rounded-none px-0 bg-transparent focus-visible:ring-0 focus-visible:border-primary"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label
                                            htmlFor="repository_type"
                                            className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                        >
                                            认证类型
                                        </Label>
                                        <Select
                                            value={createForm.repository_type}
                                            onValueChange={(value: any) =>
                                                setCreateForm({
                                                    ...createForm,
                                                    repository_type: value,
                                                })
                                            }
                                        >
                                            <SelectTrigger className="cyber-input">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="cyber-dialog border-border">
                                                {REPOSITORY_PLATFORMS.map(
                                                    (platform) => (
                                                        <SelectItem
                                                            key={platform.value}
                                                            value={
                                                                platform.value
                                                            }
                                                        >
                                                            {platform.label}
                                                        </SelectItem>
                                                    ),
                                                )}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <Label
                                        htmlFor="description"
                                        className="font-mono font-bold uppercase text-base text-muted-foreground"
                                    >
                                        描述
                                    </Label>
                                    <Textarea
                                        id="description"
                                        value={createForm.description}
                                        onChange={(e) =>
                                            setCreateForm({
                                                ...createForm,
                                                description: e.target.value,
                                            })
                                        }
                                        placeholder="// 项目描述..."
                                        rows={3}
                                        className="cyber-input min-h-[80px]"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-5">
                                    <div className="space-y-1.5">
                                        <Label
                                            htmlFor="repository_url"
                                            className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                        >
                                            仓库地址
                                        </Label>
                                        <Input
                                            id="repository_url"
                                            value={createForm.repository_url}
                                            onChange={(e) =>
                                                setCreateForm({
                                                    ...createForm,
                                                    repository_url:
                                                        e.target.value,
                                                })
                                            }
                                            placeholder={
                                                createForm.repository_type ===
                                                    "other"
                                                    ? "git@github.com:user/repo.git"
                                                    : "https://github.com/user/repo"
                                            }
                                            className="cyber-input"
                                        />
                                        {createForm.repository_type ===
                                            "other" && (
                                                <p className="text-xs text-muted-foreground font-mono">
                                                    💡 SSH Key认证请使用 git@
                                                    格式的SSH URL
                                                </p>
                                            )}
                                        {createForm.repository_type !==
                                            "other" && (
                                                <p className="text-xs text-muted-foreground font-mono">
                                                    💡 Token认证请使用 https://
                                                    格式的URL
                                                </p>
                                            )}
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label
                                            htmlFor="default_branch"
                                            className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                        >
                                            默认分支
                                        </Label>
                                        <Input
                                            id="default_branch"
                                            value={createForm.default_branch}
                                            onChange={(e) =>
                                                setCreateForm({
                                                    ...createForm,
                                                    default_branch:
                                                        e.target.value,
                                                })
                                            }
                                            placeholder="main"
                                            className="cyber-input"
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        技术栈
                                    </Label>
                                    <div className="flex flex-wrap gap-2">
                                        {supportedLanguages.map((lang) => (
                                            <label
                                                key={lang}
                                                className={`flex items-center space-x-2 px-3 py-1.5 border cursor-pointer transition-all rounded ${createForm.programming_languages.includes(
                                                    lang,
                                                )
                                                        ? "border-primary bg-primary/10 text-primary"
                                                        : "border-border hover:border-border text-muted-foreground"
                                                    }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={createForm.programming_languages.includes(
                                                        lang,
                                                    )}
                                                    onChange={(e) => {
                                                        if (e.target.checked) {
                                                            setCreateForm({
                                                                ...createForm,
                                                                programming_languages:
                                                                    [
                                                                        ...createForm.programming_languages,
                                                                        lang,
                                                                    ],
                                                            });
                                                        } else {
                                                            setCreateForm({
                                                                ...createForm,
                                                                programming_languages:
                                                                    createForm.programming_languages.filter(
                                                                        (l) =>
                                                                            l !==
                                                                            lang,
                                                                    ),
                                                            });
                                                        }
                                                    }}
                                                    className="rounded border border-border w-3.5 h-3.5 text-primary focus:ring-0 bg-transparent"
                                                />
                                                <span className="text-xs font-mono font-bold uppercase">
                                                    {lang}
                                                </span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                <div className="flex justify-end space-x-4 pt-4 border-t border-border">
                                    <Button
                                        variant="outline"
                                        onClick={closeCreateProjectDialog}
                                        className="cyber-btn-outline"
                                    >
                                        取消
                                    </Button>
                                    <Button
                                        onClick={handleCreateProject}
                                        className={PROJECT_ACTION_BTN_SUBTLE}
                                    >
                                        执行创建
                                    </Button>
                                </div>
                            </TabsContent>

                            <TabsContent
                                value="upload"
                                className="flex flex-col gap-5 mt-5"
                            >
                                <div className="space-y-1.5">
                                    <Label
                                        htmlFor="upload-name"
                                        className="font-mono font-bold uppercase text-base text-muted-foreground"
                                    >
                                        项目名称
                                    </Label>
                                    <Input
                                        id="upload-name"
                                        value={createForm.name}
                                        onChange={(e) =>
                                            setCreateForm({
                                                ...createForm,
                                                name: e.target.value,
                                            })
                                        }
                                        placeholder="输入项目名称"
                                        className="h-11 text-base border-0 border-b border-border rounded-none px-0 bg-transparent focus-visible:ring-0 focus-visible:border-primary"
                                    />
                                </div>

                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between gap-2">
                                        <Label
                                            htmlFor="upload-description"
                                            className="font-mono font-bold uppercase text-base text-muted-foreground"
                                        >
                                            描述
                                        </Label>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            onClick={handleGenerateProjectDescription}
                                            disabled={
                                                !selectedFile ||
                                                uploading ||
                                                generatingDescription
                                            }
                                            className="cyber-btn-outline h-8 text-xs"
                                        >
                                            <Sparkles className="w-3 h-3 mr-1.5" />
                                            {generatingDescription
                                                ? "生成中..."
                                                : "一键生成"}
                                        </Button>
                                    </div>
                                    <Textarea
                                        id="upload-description"
                                        value={createForm.description}
                                        onChange={(e) =>
                                            setCreateForm({
                                                ...createForm,
                                                description: e.target.value,
                                            })
                                        }
                                        placeholder="// 项目描述..."
                                        rows={3}
                                        className="cyber-input min-h-[80px]"
                                        disabled={uploading}
                                    />
                                </div>

                                <div className="space-y-4">
                                    <Label className="font-mono font-bold uppercase text-base text-muted-foreground">
                                        源代码
                                    </Label>

                                    {!selectedFile ? (
                                        <div
                                            className="border border-dashed border-border bg-muted/50 rounded p-6 text-center hover:bg-muted hover:border-border transition-colors cursor-pointer group"
                                            onClick={() =>
                                                fileInputRef.current?.click()
                                            }
                                        >
                                            <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3 group-hover:text-primary transition-colors" />
                                            <h3 className="text-base font-bold text-foreground uppercase mb-1">
                                                上传项目文件
                                            </h3>
                                            <p className="text-xs font-mono text-muted-foreground mb-3">
                                                最大: 500MB // 格式: .zip .tar
                                                .tar.gz .tar.bz2 .7z .rar
                                            </p>
                                            <input
                                                ref={fileInputRef}
                                                type="file"
                                                accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
                                                onChange={handleFileSelect}
                                                className="hidden"
                                                disabled={uploading}
                                            />
                                            <Button
                                                type="button"
                                                variant="outline"
                                                className="cyber-btn-outline h-8 text-xs"
                                                disabled={uploading}
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    fileInputRef.current?.click();
                                                }}
                                            >
                                                <FileText className="w-3 h-3 mr-2" />
                                                选择文件
                                            </Button>
                                        </div>
                                    ) : (
                                        <div className="border border-border bg-muted/50 p-4 flex items-center justify-between rounded">
                                            <div className="flex items-center space-x-3 overflow-hidden">
                                                <div className="w-10 h-10 bg-muted border border-border rounded flex items-center justify-center flex-shrink-0">
                                                    <FileText className="w-5 h-5 text-primary" />
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="font-mono font-bold text-sm text-foreground truncate">
                                                        {selectedFile.name}
                                                    </p>
                                                    <p className="font-mono text-xs text-muted-foreground">
                                                        {(
                                                            selectedFile.size /
                                                            1024 /
                                                            1024
                                                        ).toFixed(2)}{" "}
                                                        MB
                                                    </p>
                                                </div>
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => {
                                                    setSelectedFile(null);
                                                    setGeneratingDescription(false);
                                                    setCreateForm((prev) => ({
                                                        ...prev,
                                                        programming_languages:
                                                            [],
                                                    }));
                                                }}
                                                disabled={uploading}
                                                className="hover:bg-rose-500/10 hover:text-rose-400"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    )}

                                    <div className="border border-border bg-muted/30 p-3 rounded">
                                        <p className="text-xs font-mono text-muted-foreground mb-1">
                                            语言自动识别
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            支持 ZIP / TAR / TAR.GZ / TAR.BZ2 /
                                            7Z /
                                            RAR，上传后自动解包并识别项目语言。
                                        </p>
                                    </div>

                                    {uploading && (
                                        <div className="space-y-1.5">
                                            <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                                                <span>上传并分析中...</span>
                                                <span className="text-primary">
                                                    {uploadProgress}%
                                                </span>
                                            </div>
                                            <Progress
                                                value={uploadProgress}
                                                className="h-2 bg-muted [&>div]:bg-primary"
                                            />
                                        </div>
                                    )}
                                </div>

                                <div className="flex justify-end space-x-4 pt-4 border-t border-border mt-auto">
                                    
                                    <Button
                                        variant="outline"
                                        onClick={closeCreateProjectDialog}
                                        disabled={uploading || generatingDescription}
                                        className="cyber-btn-outline"
                                    >
                                        取消
                                    </Button>
                                    <Button
                                        onClick={handleUploadAndCreate}
                                        className={PROJECT_ACTION_BTN_SUBTLE}
                                        disabled={
                                            !selectedFile ||
                                            uploading ||
                                            generatingDescription
                                        }
                                    >
                                        {uploading ? "上传中..." : "执行创建"}
                                    </Button>
                                </div>
                            </TabsContent>
                        </Tabs>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Quick Actions */}
            <div id="quick-actions" className="cyber-card p-4 relative z-10">
                <div className="section-header">
                    <Terminal className="w-5 h-5 text-primary" />
                    <h3 className="section-title">快速操作</h3>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
                    <Button
                        className={`${PROJECT_ACTION_BTN} h-10 justify-start`}
                        onClick={openCreateProjectFromQuickActions}
                    >
                        <Plus className="w-4 h-4 mr-2" />
                        创建项目
                    </Button>
                    <Button
                        className={`${PROJECT_ACTION_BTN} h-10 justify-start`}
                        onClick={() => openCreateStaticAuditDialog()}
                    >
                        <Shield className="w-4 h-4 mr-2" />
                        创建静态扫描
                    </Button>
                    <Button
                        className={`${PROJECT_ACTION_BTN} h-10 justify-start`}
                        onClick={() => openCreateAgentAuditDialog()}
                    >
                        <Terminal className="w-4 h-4 mr-2" />
                        创建智能审计
                    </Button>
                </div>
            </div>

            {/* Task Browser */}
            <div className="relative z-10">
                <div id="task-browser" className="cyber-card p-4">
                    <div className="flex items-center justify-between gap-3">
                        <div className="section-header">
                            <Terminal className="w-5 h-5 text-amber-400" />
                            <h3 className="section-title">任务浏览</h3>
                        </div>
                        <Button
                            size="sm"
                            className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 px-3`}
                            onClick={() =>
                                openCreateAuditDialog("static", "", {
                                    returnTarget: "task-browser",
                                    navigateOnSuccess: true,
                                })
                            }
                        >
                            <Shield className="w-4 h-4 mr-2" />
                            创建审计
                        </Button>
                    </div>
                    <div className="space-y-3 mb-3">
                        <div className="flex items-center gap-2">
                            <Input
                                value={activityKeyword}
                                onChange={(e) => setActivityKeyword(e.target.value)}
                                placeholder="按项目名/任务类型/状态搜索"
                                className="h-9 font-mono"
                            />
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>按时间倒序展示</span>
                            <span>共 {filteredActivities.length} 条</span>
                        </div>
                    </div>
                    <div className="space-y-2">
                        {pagedActivities.length > 0 ? (
                            pagedActivities.map((activity) => {
                                const activityName =
                                    activity.kind === "rule_scan"
                                        ? `${activity.projectName}-静态扫描`
                                        : `${activity.projectName}-智能审计`;
                                return (
                                    <Link
                                        key={activity.id}
                                        to={activity.route}
                                        className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
                                    >
                                        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                                            <p className="text-base font-medium text-foreground">
                                                {activityName}
                                            </p>
                                            {activity.kind === "rule_scan" && (
                                                <span className="text-xs text-muted-foreground">
                                                    Gitleaks扫描：
                                                    {activity.gitleaksEnabled ? "已启用" : "未启用"}
                                                </span>
                                            )}
                                            <Badge className={getTaskStatusBadgeClassName(activity.status)}>
                                                漏洞扫描状态：{getTaskStatusText(activity.status)}
                                            </Badge>
                                            <span className="text-sm text-muted-foreground/80">
                                                创建时间：{formatCreatedAt(activity.createdAt)}（
                                                {getRelativeTime(activity.createdAt)}）
                                            </span>
                                            <span className="text-sm text-muted-foreground/80">
                                                {getActivityDurationLabel(activity)}
                                            </span>
                                        </div>
                                    </Link>
                                );
                            })
                        ) : (
                            <div className="empty-state py-6">
                                <Clock className="w-10 h-10 text-muted-foreground mb-2" />
                                <p className="text-base text-muted-foreground">
                                    暂无活动记录
                                </p>
                            </div>
                        )}
                    </div>
                    {filteredActivities.length > 0 && (
                        <div className="mt-4 flex items-center justify-between">
                            <div className="text-xs text-muted-foreground">
                                第 {activityPage} / {totalActivityPages} 页（每页{" "}
                                {ACTIVITY_PAGE_SIZE} 条）
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="cyber-btn-outline h-8 px-3"
                                    disabled={activityPage <= 1}
                                    onClick={() =>
                                        setActivityPage((prev) => Math.max(prev - 1, 1))
                                    }
                                >
                                    上一页
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="cyber-btn-outline h-8 px-3"
                                    disabled={activityPage >= totalActivityPages}
                                    onClick={() =>
                                        setActivityPage((prev) =>
                                            Math.min(prev + 1, totalActivityPages),
                                        )
                                    }
                                >
                                    下一页
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Project Browser */}
            <div id="project-browser" className="cyber-card p-4 relative z-10">
                <div className="flex items-center justify-between gap-3">
                    <div className="section-header">
                        <Code className="w-5 h-5 text-primary" />
                        <h3 className="section-title">项目浏览</h3>
                    </div>
                    <Button
                        size="sm"
                        className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 px-3`}
                        onClick={handleOpenCreateProject}
                    >
                        <Plus className="w-4 h-4 mr-2" />
                        创建项目
                    </Button>
                </div>
                <div className="space-y-3 mb-3 mt-3">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <Input
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder={t("projects.searchPlaceholder", "按项目名称/描述/仓库地址搜索")}
                            className="h-9 font-mono pl-9"
                        />
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>项目管理同源数据</span>
                        <span>共 {filteredProjects.length} 个</span>
                    </div>
                </div>
                <div className="space-y-2">
                    {pagedProjects.length > 0 ? (
                        pagedProjects.map((project) => (
                            <div
                                key={project.id}
                                className={`block p-3 rounded-lg border transition-all ${project.is_active
                                        ? "bg-primary/5 border-primary/20 hover:border-primary/40"
                                        : "bg-muted/20 border-border hover:border-border"
                                    }`}
                            >
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                                    <span className="inline-flex items-center gap-1 text-muted-foreground">
                                        {getRepositoryIcon(project.repository_type)}
                                    </span>
                                    <Link
                                        to={`/projects/${project.id}`}
                                        state={{ from: projectDetailFrom }}
                                        className="text-base font-medium text-foreground hover:text-primary transition-colors"
                                    >
                                        {project.name}
                                    </Link>
                                    <Badge
                                        className={
                                            project.is_active
                                                ? "cyber-badge-success"
                                                : "cyber-badge-muted"
                                        }
                                    >
                                        {project.is_active ? "活跃" : "暂停"}
                                    </Badge>
                                    <Badge
                                        className={
                                            project.source_type === "zip"
                                                ? "cyber-badge-warning"
                                                : "cyber-badge-info"
                                        }
                                    >
                                        {getSourceTypeBadge(project.source_type)}
                                    </Badge>
                                    <span className="text-xs text-muted-foreground">
                                        创建时间：{formatCreatedAt(project.created_at)}
                                    </span>
                                    <Link
                                        to={`/projects/${project.id}`}
                                        state={{ from: projectDetailFrom }}
                                        className="text-xs text-primary inline-flex items-center gap-1"
                                    >
                                        查看详情 <ArrowUpRight className="w-3 h-3" />
                                    </Link>
                                    <div className="ml-auto flex items-center gap-2">
                                        <Button
                                            size="sm"
                                            className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 text-xs`}
                                            onClick={() => handleCreateTask(project.id)}
                                        >
                                            <Shield className="w-3 h-3 mr-2" />
                                            审计
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="cyber-btn-ghost h-8 px-2 hover:bg-rose-500/10 hover:text-rose-400 hover:border-rose-500/30"
                                            onClick={() => handleDeleteClick(project)}
                                        >
                                            <Trash2 className="w-3 h-3" />
                                        </Button>
                                    </div>
                                </div>
                                {project.description && (
                                    <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
                                        {project.description}
                                    </p>
                                )}
                            </div>
                        ))
                    ) : (
                        <div className="empty-state py-10">
                            <Code className="w-12 h-12 text-muted-foreground mb-3" />
                            <p className="text-base text-muted-foreground">
                                {searchTerm ? "未匹配到项目" : "暂无项目"}
                            </p>
                            {!searchTerm && (
                                <Button
                                    onClick={handleOpenCreateProject}
                                    className={`${PROJECT_ACTION_BTN} mt-4`}
                                >
                                    <Plus className="w-4 h-4 mr-2" />
                                    初始化项目
                                </Button>
                            )}
                        </div>
                    )}
                </div>
                {filteredProjects.length > 0 && (
                    <div className="mt-4 flex items-center justify-between">
                        <div className="text-xs text-muted-foreground">
                            第 {projectPage} / {totalProjectPages} 页（每页{" "}
                            {PROJECT_PAGE_SIZE} 条）
                        </div>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                className="cyber-btn-outline h-8 px-3"
                                disabled={projectPage <= 1}
                                onClick={() =>
                                    setProjectPage((prev) => Math.max(prev - 1, 1))
                                }
                            >
                                上一页
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                className="cyber-btn-outline h-8 px-3"
                                disabled={projectPage >= totalProjectPages}
                                onClick={() =>
                                    setProjectPage((prev) =>
                                        Math.min(prev + 1, totalProjectPages),
                                    )
                                }
                            >
                                下一页
                            </Button>
                        </div>
                    </div>
                )}
            </div>

            <CreateProjectAuditDialog
                open={showCreateAuditDialog}
                onOpenChange={handleCreateAuditDialogOpenChange}
                onTaskCreated={handleTaskCreated}
                preselectedProjectId={auditPreselectedProjectId}
                initialMode={auditInitialMode}
                navigateOnSuccess={auditNavigateOnSuccess}
                showReturnButton={auditReturnTarget === "quick-actions"}
                onReturn={() => {
                    pinToModuleHash("quick-actions");
                    scrollToModule("quick-actions");
                }}
            />

            <CreateStaticAuditDialog
                open={showCreateStaticAuditDialog}
                onOpenChange={handleCreateStaticAuditDialogOpenChange}
                onTaskCreated={handleTaskCreated}
                navigateOnSuccess={staticAuditNavigateOnSuccess}
                showReturnButton
                onReturn={() => {
                    pinToModuleHash("quick-actions");
                    scrollToModule("quick-actions");
                }}
            />

            <CreateAgentAuditDialog
                open={showCreateAgentAuditDialog}
                onOpenChange={handleCreateAgentAuditDialogOpenChange}
                onTaskCreated={handleTaskCreated}
                navigateOnSuccess={agentAuditNavigateOnSuccess}
                showReturnButton
                onReturn={() => {
                    pinToModuleHash("quick-actions");
                    scrollToModule("quick-actions");
                }}
            />

            {/* Edit Dialog */}
            <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
                <DialogContent className="!w-[min(90vw,700px)] !max-w-none max-h-[85vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
                    <DialogHeader className="px-6 pt-4 flex-shrink-0">
                        <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                            <Edit className="w-5 h-5 text-primary" />
                            编辑项目配置
                            {projectToEdit && (
                                <Badge
                                    className={`ml-2 ${editForm.source_type === "repository" ? "cyber-badge-info" : "cyber-badge-warning"}`}
                                >
                                    {editForm.source_type === "repository"
                                        ? "远程仓库"
                                        : "上传项目"}
                                </Badge>
                            )}
                        </DialogTitle>
                    </DialogHeader>

                    <div className="flex-1 overflow-y-auto p-6 space-y-6">
                        {/* 基本信息 */}
                        <div className="space-y-4">
                            <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                                基本信息
                            </h3>
                            <div>
                                <Label
                                    htmlFor="edit-name"
                                    className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                >
                                    项目名称
                                </Label>
                                <Input
                                    id="edit-name"
                                    value={editForm.name}
                                    onChange={(e) =>
                                        setEditForm({
                                            ...editForm,
                                            name: e.target.value,
                                        })
                                    }
                                    className="cyber-input mt-1"
                                />
                            </div>
                            <div>
                                <Label
                                    htmlFor="edit-description"
                                    className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                >
                                    描述
                                </Label>
                                <Textarea
                                    id="edit-description"
                                    value={editForm.description}
                                    onChange={(e) =>
                                        setEditForm({
                                            ...editForm,
                                            description: e.target.value,
                                        })
                                    }
                                    rows={3}
                                    className="cyber-input mt-1"
                                />
                            </div>
                        </div>

                        {/* 仓库信息 - 仅远程仓库类型显示 */}
                        {editForm.source_type === "repository" && (
                            <div className="space-y-4">
                                <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2 flex items-center gap-2">
                                    <GitBranch className="w-4 h-4" />
                                    仓库信息
                                </h3>

                                <div>
                                    <Label
                                        htmlFor="edit-repo-url"
                                        className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                    >
                                        仓库地址
                                    </Label>
                                    <Input
                                        id="edit-repo-url"
                                        value={editForm.repository_url}
                                        onChange={(e) =>
                                            setEditForm({
                                                ...editForm,
                                                repository_url: e.target.value,
                                            })
                                        }
                                        placeholder={
                                            editForm.repository_type === "other"
                                                ? "git@github.com:user/repo.git"
                                                : "https://github.com/user/repo"
                                        }
                                        className="cyber-input mt-1"
                                    />
                                    {editForm.repository_type === "other" && (
                                        <p className="text-xs text-muted-foreground font-mono mt-1">
                                            💡 SSH Key认证请使用 git@ 格式的SSH
                                            URL
                                        </p>
                                    )}
                                    {editForm.repository_type !== "other" && (
                                        <p className="text-xs text-muted-foreground font-mono mt-1">
                                            💡 Token认证请使用 https://
                                            格式的URL
                                        </p>
                                    )}
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <Label
                                            htmlFor="edit-repo-type"
                                            className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                        >
                                            认证类型
                                        </Label>
                                        <Select
                                            value={editForm.repository_type}
                                            onValueChange={(value: any) =>
                                                setEditForm({
                                                    ...editForm,
                                                    repository_type: value,
                                                })
                                            }
                                        >
                                            <SelectTrigger
                                                id="edit-repo-type"
                                                className="cyber-input mt-1"
                                            >
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="cyber-dialog border-border">
                                                {REPOSITORY_PLATFORMS.map(
                                                    (platform) => (
                                                        <SelectItem
                                                            key={platform.value}
                                                            value={
                                                                platform.value
                                                            }
                                                        >
                                                            {platform.label}
                                                        </SelectItem>
                                                    ),
                                                )}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div>
                                        <Label
                                            htmlFor="edit-default-branch"
                                            className="font-mono font-bold uppercase text-xs text-muted-foreground"
                                        >
                                            默认分支
                                        </Label>
                                        <Input
                                            id="edit-default-branch"
                                            value={editForm.default_branch}
                                            onChange={(e) =>
                                                setEditForm({
                                                    ...editForm,
                                                    default_branch:
                                                        e.target.value,
                                                })
                                            }
                                            placeholder="main"
                                            className="cyber-input mt-1"
                                        />
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* ZIP项目文件管理 */}
                        {editForm.source_type === "zip" && (
                            <div className="space-y-4">
                                <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2 flex items-center gap-2">
                                    <Upload className="w-4 h-4" />
                                    ZIP文件管理
                                </h3>

                                {loadingEditZipInfo ? (
                                    <div className="flex items-center space-x-3 p-4 bg-sky-500/10 border border-sky-500/30 rounded">
                                        <div className="loading-spinner w-5 h-5"></div>
                                        <p className="text-sm text-sky-400 font-bold font-mono">
                                            正在加载ZIP文件信息...
                                        </p>
                                    </div>
                                ) : editZipInfo?.has_file ? (
                                    <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded">
                                        <div className="flex items-start space-x-3">
                                            <FileText className="w-5 h-5 text-emerald-400 mt-0.5" />
                                            <div className="flex-1 text-sm font-mono">
                                                <p className="font-bold text-emerald-300 mb-1 uppercase">
                                                    当前存储的ZIP文件
                                                </p>
                                                <p className="text-emerald-400/80 text-xs">
                                                    文件名:{" "}
                                                    {
                                                        editZipInfo.original_filename
                                                    }
                                                    {editZipInfo.file_size && (
                                                        <>
                                                            {" "}
                                                            (
                                                            {editZipInfo.file_size >=
                                                                1024 * 1024
                                                                ? `${(editZipInfo.file_size / 1024 / 1024).toFixed(2)} MB`
                                                                : `${(editZipInfo.file_size / 1024).toFixed(2)} KB`}
                                                            )
                                                        </>
                                                    )}
                                                </p>
                                                {editZipInfo.uploaded_at && (
                                                    <p className="text-emerald-500/60 text-xs mt-0.5">
                                                        上传时间:{" "}
                                                        {new Date(
                                                            editZipInfo.uploaded_at,
                                                        ).toLocaleString(
                                                            "zh-CN",
                                                        )}
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded">
                                        <div className="flex items-start space-x-3">
                                            <AlertCircle className="w-5 h-5 text-amber-400 mt-0.5" />
                                            <div className="text-sm font-mono">
                                                <p className="font-bold text-amber-300 mb-1 uppercase">
                                                    暂无ZIP文件
                                                </p>
                                                <p className="text-amber-400/80 text-xs">
                                                    此项目还没有上传ZIP文件，请上传文件以便进行代码审计。
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* 上传新文件 */}
                                <div className="space-y-2">
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        {editZipInfo?.has_file
                                            ? "更新ZIP文件"
                                            : "上传ZIP文件"}
                                    </Label>
                                    <input
                                        ref={editZipInputRef}
                                        type="file"
                                        accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
                                        className="hidden"
                                        onChange={(e) => {
                                            const file = e.target.files?.[0];
                                            if (file) {
                                                const validation =
                                                    validateZipFile(file);
                                                if (!validation.valid) {
                                                    toast.error(
                                                        validation.error ||
                                                        "文件无效",
                                                    );
                                                    e.target.value = "";
                                                    return;
                                                }
                                                setEditZipFile(file);
                                                toast.success(
                                                    `已选择文件: ${file.name}`,
                                                );
                                            }
                                        }}
                                    />

                                    {editZipFile ? (
                                        <div className="flex items-center justify-between p-3 bg-sky-500/10 border border-sky-500/30 rounded">
                                            <div className="flex items-center space-x-2">
                                                <FileText className="w-4 h-4 text-sky-400" />
                                                <span className="text-sm font-mono font-bold text-sky-300">
                                                    {editZipFile.name}
                                                </span>
                                                <span className="text-xs text-muted-foreground">
                                                    (
                                                    {(
                                                        editZipFile.size /
                                                        1024 /
                                                        1024
                                                    ).toFixed(2)}{" "}
                                                    MB)
                                                </span>
                                            </div>
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() =>
                                                    setEditZipFile(null)
                                                }
                                                className="cyber-btn-ghost h-7 text-xs"
                                            >
                                                取消
                                            </Button>
                                        </div>
                                    ) : (
                                        <Button
                                            variant="outline"
                                            onClick={() =>
                                                editZipInputRef.current?.click()
                                            }
                                            className="cyber-btn-outline w-full"
                                        >
                                            <Upload className="w-4 h-4 mr-2" />
                                            {editZipInfo?.has_file
                                                ? "选择新文件替换"
                                                : "选择ZIP文件"}
                                        </Button>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* 技术栈 */}
                        <div className="space-y-4">
                            <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                                技术栈
                            </h3>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                {supportedLanguages.map((lang) => (
                                    <div
                                        key={lang}
                                        className={`flex items-center space-x-2 p-2 border cursor-pointer transition-all rounded ${editForm.programming_languages?.includes(
                                            lang,
                                        )
                                                ? "border-primary bg-primary/10 text-primary"
                                                : "border-border hover:border-border text-muted-foreground"
                                            }`}
                                        onClick={() =>
                                            handleToggleLanguage(lang)
                                        }
                                    >
                                        <div
                                            className={`w-4 h-4 border-2 rounded-sm flex items-center justify-center ${editForm.programming_languages?.includes(
                                                lang,
                                            )
                                                    ? "bg-primary border-primary"
                                                    : "border-border"
                                                }`}
                                        >
                                            {editForm.programming_languages?.includes(
                                                lang,
                                            ) && (
                                                    <CheckCircle className="w-3 h-3 text-foreground" />
                                                )}
                                        </div>
                                        <span className="text-sm font-mono font-bold uppercase">
                                            {lang}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
                        <Button
                            variant="outline"
                            onClick={() => setShowEditDialog(false)}
                            className="cyber-btn-outline"
                        >
                            取消
                        </Button>
                        <Button
                            onClick={handleSaveEdit}
                            className={PROJECT_ACTION_BTN_SUBTLE}
                        >
                            保存更改
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Delete Dialog */}
            <AlertDialog
                open={showDeleteDialog}
                onOpenChange={setShowDeleteDialog}
            >
                <AlertDialogContent className="cyber-card border-border cyber-dialog p-0 !fixed">
                    <AlertDialogHeader className="p-6">
                        <AlertDialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                            <Trash2 className="w-5 h-5 text-rose-400" />
                            确认删除
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-muted-foreground font-mono">
                            您确定要删除{" "}
                            <span className="font-bold text-rose-400">
                                "{projectToDelete?.name}"
                            </span>{" "}
                            吗？
                        </AlertDialogDescription>
                    </AlertDialogHeader>

                    <div className="px-6 pb-6">
                        <div className="bg-sky-500/10 border border-sky-500/30 p-4 rounded">
                            <p className="text-sky-300 font-bold mb-2 font-mono uppercase text-sm">
                                系统通知:
                            </p>
                            <ul className="list-none text-sky-400/80 space-y-1 text-xs font-mono">
                                <li className="flex items-center gap-2">
                                    <span className="text-sky-400">&gt;</span>{" "}
                                    项目将被删除
                                </li>
                                <li className="flex items-center gap-2">
                                    <span className="text-sky-400">&gt;</span>{" "}
                                    审计数据保留
                                </li>
                                <li className="flex items-center gap-2">
                                    <span className="text-sky-400">&gt;</span>{" "}
                                    此操作将立即生效
                                </li>
                            </ul>
                        </div>
                    </div>

                    <AlertDialogFooter className="p-4 border-t border-border bg-muted/50">
                        <AlertDialogCancel className="cyber-btn-outline">
                            取消
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleConfirmDelete}
                            className="cyber-btn bg-rose-500/90 border-rose-500/50 text-foreground hover:bg-rose-500"
                        >
                            确认删除
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
