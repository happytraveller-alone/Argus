/**
 * Projects Page
 * Cyberpunk Terminal Aesthetic
 */

import { lazy, Suspense, useState, useEffect, useMemo, useRef, useCallback } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
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
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import {
    Plus,
    Search,
    GitBranch,
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
    Key,
    Sparkles,
} from "lucide-react";
import { api } from "@/shared/config/database";
import { validateZipFile } from "@/features/projects/services";
import type { Project, CreateProjectForm, AuditTask } from "@/shared/types";
import {
    uploadZipFile,
    type ZipFileMeta,
} from "@/shared/utils/zipStorage";
import {
    getSourceTypeBadge,
} from "@/shared/utils/projectUtils";
import { Link, useLocation } from "react-router-dom";
import { toast } from "sonner";
import DeferredSection from "@/components/performance/DeferredSection";
import type { AuditCreateMode } from "@/components/audit/CreateProjectAuditDialog";
import { SUPPORTED_LANGUAGES, REPOSITORY_PLATFORMS } from "@/shared/constants";
import { useI18n } from "@/shared/i18n";
import { apiClient } from "@/shared/api/serverClient";
import { getAgentTasks, type AgentTask } from "@/shared/api/agentTasks";
import {
    getGitleaksScanTasks,
    type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
    getOpengrepScanFindings,
    getOpengrepScanTasks,
    type OpengrepFinding,
    type OpengrepScanTask,
} from "@/shared/api/opengrep";
import {
    getProjectCardPotentialVulnerabilities,
    getProjectCardSummaryStats,
    getProjectCardRecentTasks,
    normalizeProjectCardLanguageStats,
    type ProjectCardLanguageStats,
    type ProjectCardPotentialVulnerability,
} from "@/features/projects/services/projectCardPreview";
const PROJECT_PAGE_SIZE = 1;
const MODULE_SCROLL_DELAY_MS = 80;
const TASK_POOL_MAX_TOTAL = 800;
const AGENT_TASK_PAGE_LIMIT = 100;
const OPENGREP_TASK_PAGE_LIMIT = 200;
const GITLEAKS_TASK_PAGE_LIMIT = 200;
const LANGUAGE_STATS_RETRY_INTERVAL_MS = 2500;
const LANGUAGE_STATS_MAX_RETRIES = 6;
const PROJECT_CARD_POTENTIAL_SOURCE_TASK_LIMIT = 3;
const PROJECT_CARD_POTENTIAL_FINDINGS_FETCH_LIMIT = 200;
const PROJECT_CARD_POTENTIAL_TOP_LIMIT = 5;
const PROJECT_CARD_PIE_COLORS = [
    "#0ea5e9",
    "#22c55e",
    "#f59e0b",
    "#a855f7",
    "#ef4444",
    "#14b8a6",
];

function getErrorStatusCode(error: unknown): number {
    const apiError = error as { response?: { status?: number } };
    return Number(apiError?.response?.status || 0);
}
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

const CreateProjectAuditDialog = lazy(
    () => import("@/components/audit/CreateProjectAuditDialog"),
);
const ProjectLanguagePieChart = lazy(
    () => import("@/features/projects/components/ProjectLanguagePieChart"),
);

const stripArchiveSuffix = (filename: string) => {
    const lower = filename.toLowerCase();
    const matched = ARCHIVE_SUFFIXES.find((suffix) => lower.endsWith(suffix));
    if (!matched) return filename;
    return filename.slice(0, filename.length - matched.length);
};

const PROJECT_ACTION_BTN =
    "border border-sky-400/35 bg-gradient-to-r from-sky-500/20 via-cyan-500/16 to-blue-500/20 text-sky-100 shadow-[0_8px_22px_-14px_rgba(14,165,233,0.9)] hover:from-sky-500/30 hover:via-cyan-500/24 hover:to-blue-500/30 hover:border-sky-300/55";

const PROJECT_ACTION_BTN_SUBTLE =
    "border border-sky-500/30 bg-sky-500/12 text-sky-100 hover:bg-sky-500/22 hover:border-sky-400/55";

type ProjectCardPotentialVulnerabilityState = {
    status: "loading" | "ready" | "empty" | "failed";
    items: ProjectCardPotentialVulnerability[];
};

type ProjectTaskPoolState = {
    status: "loading" | "ready" | "failed";
    auditTasks: AuditTask[];
    agentTasks: AgentTask[];
    opengrepTasks: OpengrepScanTask[];
    gitleaksTasks: GitleaksScanTask[];
};

export default function Projects() {
    const location = useLocation();
    const { t } = useI18n();
    const [projects, setProjects] = useState<Project[]>([]);
    const [projectPage, setProjectPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [showCreateAuditDialog, setShowCreateAuditDialog] = useState(false);
    const [auditPreselectedProjectId, setAuditPreselectedProjectId] =
        useState<string>("");
    const [auditInitialMode, setAuditInitialMode] =
        useState<AuditCreateMode>("static");
    const [auditNavigateOnSuccess, setAuditNavigateOnSuccess] = useState(true);
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
    const [loadingEditZipInfo] = useState(false);
    const editZipInputRef = useRef<HTMLInputElement>(null);
    const [projectTaskPoolsMap, setProjectTaskPoolsMap] = useState<
        Record<string, ProjectTaskPoolState>
    >({});
    const [projectLanguageStatsMap, setProjectLanguageStatsMap] = useState<
        Record<string, ProjectCardLanguageStats>
    >({});
    const [projectPotentialVulnerabilityMap, setProjectPotentialVulnerabilityMap] = useState<
        Record<string, ProjectCardPotentialVulnerabilityState>
    >({});
    const languageStatsRetryCountRef = useRef<Record<string, number>>({});
    const languageStatsPollTimerRef = useRef<Record<string, number>>({});
    const potentialVulnerabilityLoadingRef = useRef<Record<string, boolean>>({});
    const projectTaskPoolLoadingRef = useRef<Record<string, boolean>>({});

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
        const hash = window.location.hash;
        if (hash !== "#project-browser") {
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

    const clearLanguageStatsPollTimer = useCallback((projectId: string) => {
        const timer = languageStatsPollTimerRef.current[projectId];
        if (timer) {
            window.clearTimeout(timer);
            delete languageStatsPollTimerRef.current[projectId];
        }
    }, []);

    const fetchProjectLanguageStats = useCallback(
        async (projectId: string) => {
            try {
                const response = await apiClient.get(`/projects/info/${projectId}`);
                const stats = normalizeProjectCardLanguageStats(response.data);
                setProjectLanguageStatsMap((previous) => ({
                    ...previous,
                    [projectId]: stats,
                }));

                if (stats.status === "pending") {
                    const retriedCount =
                        languageStatsRetryCountRef.current[projectId] ?? 0;
                    if (retriedCount < LANGUAGE_STATS_MAX_RETRIES) {
                        clearLanguageStatsPollTimer(projectId);
                        languageStatsRetryCountRef.current[projectId] =
                            retriedCount + 1;
                        languageStatsPollTimerRef.current[projectId] =
                            window.setTimeout(() => {
                                delete languageStatsPollTimerRef.current[projectId];
                                void fetchProjectLanguageStats(projectId);
                            }, LANGUAGE_STATS_RETRY_INTERVAL_MS);
                    } else {
                        setProjectLanguageStatsMap((previous) => ({
                            ...previous,
                            [projectId]: {
                                status: "failed",
                                total: 0,
                                totalFiles: 0,
                                slices: [],
                            },
                        }));
                        clearLanguageStatsPollTimer(projectId);
                    }
                } else {
                    languageStatsRetryCountRef.current[projectId] = 0;
                    clearLanguageStatsPollTimer(projectId);
                }
            } catch (error: unknown) {
                const statusCode = getErrorStatusCode(error);
                if (statusCode === 202) {
                    setProjectLanguageStatsMap((previous) => ({
                        ...previous,
                        [projectId]: {
                            status: "pending",
                            total: 0,
                            totalFiles: 0,
                            slices: [],
                        },
                    }));
                    const retriedCount =
                        languageStatsRetryCountRef.current[projectId] ?? 0;
                    if (retriedCount < LANGUAGE_STATS_MAX_RETRIES) {
                        clearLanguageStatsPollTimer(projectId);
                        languageStatsRetryCountRef.current[projectId] =
                            retriedCount + 1;
                        languageStatsPollTimerRef.current[projectId] =
                            window.setTimeout(() => {
                                delete languageStatsPollTimerRef.current[projectId];
                                void fetchProjectLanguageStats(projectId);
                            }, LANGUAGE_STATS_RETRY_INTERVAL_MS);
                    }
                    return;
                }

                setProjectLanguageStatsMap((previous) => ({
                    ...previous,
                    [projectId]: {
                        status: "failed",
                        total: 0,
                        totalFiles: 0,
                        slices: [],
                    },
                }));
                clearLanguageStatsPollTimer(projectId);
            }
        },
        [clearLanguageStatsPollTimer],
    );

    const fetchProjectPotentialVulnerabilities = useCallback(
        async (projectId: string) => {
            if (potentialVulnerabilityLoadingRef.current[projectId]) {
                return;
            }

            potentialVulnerabilityLoadingRef.current[projectId] = true;
            try {
                const sourceTasks = (projectTaskPoolsMap[projectId]?.opengrepTasks || [])
                    .filter((task) => task.project_id === projectId)
                    .sort(
                        (a, b) =>
                            new Date(b.created_at).getTime() -
                            new Date(a.created_at).getTime(),
                    )
                    .slice(0, PROJECT_CARD_POTENTIAL_SOURCE_TASK_LIMIT);

                if (sourceTasks.length === 0) {
                    setProjectPotentialVulnerabilityMap((previous) => ({
                        ...previous,
                        [projectId]: { status: "empty", items: [] },
                    }));
                    return;
                }

                const findingsResult = await Promise.allSettled(
                    sourceTasks.map((task) =>
                        getOpengrepScanFindings({
                            taskId: task.id,
                            limit: PROJECT_CARD_POTENTIAL_FINDINGS_FETCH_LIMIT,
                        }),
                    ),
                );

                const findings: OpengrepFinding[] = findingsResult.flatMap(
                    (result, index) => {
                        if (
                            result.status !== "fulfilled" ||
                            !Array.isArray(result.value)
                        ) {
                            return [];
                        }
                        const fallbackTaskId = sourceTasks[index]?.id || "";
                        return result.value.map((finding) => ({
                            ...finding,
                            scan_task_id: finding.scan_task_id || fallbackTaskId,
                        }));
                    },
                );

                const topVulnerabilities = getProjectCardPotentialVulnerabilities({
                    findings,
                    limit: PROJECT_CARD_POTENTIAL_TOP_LIMIT,
                });

                setProjectPotentialVulnerabilityMap((previous) => ({
                    ...previous,
                    [projectId]:
                        topVulnerabilities.length > 0
                            ? { status: "ready", items: topVulnerabilities }
                            : { status: "empty", items: [] },
                }));
            } catch {
                setProjectPotentialVulnerabilityMap((previous) => ({
                    ...previous,
                    [projectId]: { status: "failed", items: [] },
                }));
            } finally {
                delete potentialVulnerabilityLoadingRef.current[projectId];
            }
        },
        [projectTaskPoolsMap],
    );

    const fetchAgentTaskPoolByProject = useCallback(
        async (projectId: string): Promise<AgentTask[]> => {
            const taskPool: AgentTask[] = [];
            let skip = 0;
            while (taskPool.length < TASK_POOL_MAX_TOTAL) {
                const batch = await getAgentTasks({
                    project_id: projectId,
                    skip,
                    limit: AGENT_TASK_PAGE_LIMIT,
                });
                if (!Array.isArray(batch) || batch.length === 0) break;
                taskPool.push(...batch);
                if (batch.length < AGENT_TASK_PAGE_LIMIT) break;
                skip += batch.length;
            }
            return taskPool.slice(0, TASK_POOL_MAX_TOTAL);
        },
        [],
    );

    const fetchOpengrepTaskPoolByProject = useCallback(
        async (projectId: string): Promise<OpengrepScanTask[]> => {
            const taskPool: OpengrepScanTask[] = [];
            let skip = 0;
            while (taskPool.length < TASK_POOL_MAX_TOTAL) {
                const batch = await getOpengrepScanTasks({
                    projectId,
                    skip,
                    limit: OPENGREP_TASK_PAGE_LIMIT,
                });
                if (!Array.isArray(batch) || batch.length === 0) break;
                taskPool.push(...batch);
                if (batch.length < OPENGREP_TASK_PAGE_LIMIT) break;
                skip += batch.length;
            }
            return taskPool.slice(0, TASK_POOL_MAX_TOTAL);
        },
        [],
    );

    const fetchGitleaksTaskPoolByProject = useCallback(
        async (projectId: string): Promise<GitleaksScanTask[]> => {
            const taskPool: GitleaksScanTask[] = [];
            let skip = 0;
            while (taskPool.length < TASK_POOL_MAX_TOTAL) {
                const batch = await getGitleaksScanTasks({
                    projectId,
                    skip,
                    limit: GITLEAKS_TASK_PAGE_LIMIT,
                });
                if (!Array.isArray(batch) || batch.length === 0) break;
                taskPool.push(...batch);
                if (batch.length < GITLEAKS_TASK_PAGE_LIMIT) break;
                skip += batch.length;
            }
            return taskPool.slice(0, TASK_POOL_MAX_TOTAL);
        },
        [],
    );

    const loadProjectTaskPool = useCallback(async (projectId: string) => {
        const existing = projectTaskPoolsMap[projectId];
        if (
            existing?.status === "ready" ||
            existing?.status === "loading" ||
            existing?.status === "failed"
        ) {
            return;
        }
        if (projectTaskPoolLoadingRef.current[projectId]) {
            return;
        }

        projectTaskPoolLoadingRef.current[projectId] = true;
        setProjectTaskPoolsMap((previous) => ({
            ...previous,
            [projectId]: {
                status: "loading",
                auditTasks: previous[projectId]?.auditTasks || [],
                agentTasks: previous[projectId]?.agentTasks || [],
                opengrepTasks: previous[projectId]?.opengrepTasks || [],
                gitleaksTasks: previous[projectId]?.gitleaksTasks || [],
            },
        }));

        try {
            const [auditResult, agentResult, opengrepResult, gitleaksResult] =
                await Promise.allSettled([
                    api.getAuditTasks(projectId),
                    fetchAgentTaskPoolByProject(projectId),
                    fetchOpengrepTaskPoolByProject(projectId),
                    fetchGitleaksTaskPoolByProject(projectId),
                ]);

            setProjectTaskPoolsMap((previous) => ({
                ...previous,
                [projectId]: {
                    status: "ready",
                    auditTasks:
                        auditResult.status === "fulfilled" &&
                        Array.isArray(auditResult.value)
                            ? auditResult.value
                            : [],
                    agentTasks:
                        agentResult.status === "fulfilled" &&
                        Array.isArray(agentResult.value)
                            ? agentResult.value
                            : [],
                    opengrepTasks:
                        opengrepResult.status === "fulfilled" &&
                        Array.isArray(opengrepResult.value)
                            ? opengrepResult.value
                            : [],
                    gitleaksTasks:
                        gitleaksResult.status === "fulfilled" &&
                        Array.isArray(gitleaksResult.value)
                            ? gitleaksResult.value
                            : [],
                },
            }));
        } catch {
            setProjectTaskPoolsMap((previous) => ({
                ...previous,
                [projectId]: {
                    status: "failed",
                    auditTasks: [],
                    agentTasks: [],
                    opengrepTasks: [],
                    gitleaksTasks: [],
                },
            }));
        } finally {
            delete projectTaskPoolLoadingRef.current[projectId];
        }
    }, [
        fetchAgentTaskPoolByProject,
        fetchGitleaksTaskPoolByProject,
        fetchOpengrepTaskPoolByProject,
        projectTaskPoolsMap,
    ]);

    const loadProjects = async () => {
        try {
            setLoading(true);
            const projectData = await api.getProjects();
            const normalizedProjects = Array.isArray(projectData) ? projectData : [];
            setProjects(normalizedProjects);
            setProjectTaskPoolsMap({});
            setProjectLanguageStatsMap({});
            setProjectPotentialVulnerabilityMap({});
            for (const timer of Object.values(languageStatsPollTimerRef.current)) {
                window.clearTimeout(timer);
            }
            languageStatsPollTimerRef.current = {};
            languageStatsRetryCountRef.current = {};
            potentialVulnerabilityLoadingRef.current = {};
            projectTaskPoolLoadingRef.current = {};

            if (normalizedProjects.length === 0) {
                return;
            }
        } catch (error) {
            console.error("Failed to load projects:", error);
            toast.error("加载项目失败");
            setProjects([]);
            setProjectTaskPoolsMap({});
            setProjectPotentialVulnerabilityMap({});
        } finally {
            setLoading(false);
        }
    };

    const scrollToProjectBrowser = () => {
        window.setTimeout(() => {
            document.getElementById("project-browser")?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        }, MODULE_SCROLL_DELAY_MS);
    };

    const pinToProjectBrowserHash = () => {
        const { pathname, search } = window.location;
        window.history.replaceState(
            window.history.state,
            "",
            `${pathname}${search}#project-browser`,
        );
    };

    const closeCreateProjectDialog = () => {
        setShowCreateDialog(false);
        pinToProjectBrowserHash();
        scrollToProjectBrowser();
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
            pinToProjectBrowserHash();
            scrollToProjectBrowser();
            setAuditNavigateOnSuccess(true);
            setAuditInitialMode("static");
        }
    };

    const handleOpenCreateProject = () => {
        pinToProjectBrowserHash();
        setShowCreateDialog(true);
    };

    const openCreateAuditDialog = (
        mode: AuditCreateMode = "static",
        projectId = "",
        options?: { navigateOnSuccess?: boolean },
    ) => {
        const navigateOnSuccess = options?.navigateOnSuccess ?? true;
        pinToProjectBrowserHash();
        setAuditInitialMode(mode);
        setAuditPreselectedProjectId(projectId);
        setAuditNavigateOnSuccess(navigateOnSuccess);
        setShowCreateAuditDialog(true);
    };

    const handleCreateProject = async () => {
        if (!createForm.name.trim()) {
            toast.error("请输入项目名称");
            return;
        }

        try {
            await api.createProject({
                ...createForm,
            });

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
            });

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
        } catch (error: unknown) {
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
            const rawErrorMessage =
                error instanceof Error ? error.message : "未知错误";
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

    useEffect(() => {
        const visibleProjectIds = pagedProjects.map((project) => project.id);
        if (visibleProjectIds.length === 0) {
            return;
        }
        for (const projectId of visibleProjectIds) {
            void loadProjectTaskPool(projectId);
        }
    }, [loadProjectTaskPool, pagedProjects]);

    useEffect(() => {
        const visibleProjectIds = pagedProjects.map((project) => project.id);
        if (visibleProjectIds.length === 0) {
            return;
        }

        const pendingFetchIds = visibleProjectIds.filter((projectId) => {
            const current = projectLanguageStatsMap[projectId];
            return !current;
        });

        if (pendingFetchIds.length > 0) {
            setProjectLanguageStatsMap((previous) => {
                const next = { ...previous };
                for (const projectId of pendingFetchIds) {
                    if (!next[projectId]) {
                        next[projectId] = {
                            status: "loading",
                            total: 0,
                            totalFiles: 0,
                            slices: [],
                        };
                    }
                }
                return next;
            });

            for (const projectId of pendingFetchIds) {
                void fetchProjectLanguageStats(projectId);
            }
        }
    }, [pagedProjects, projectLanguageStatsMap, fetchProjectLanguageStats]);

    useEffect(() => {
        const visibleProjectIds = pagedProjects.map((project) => project.id);
        if (visibleProjectIds.length === 0) {
            return;
        }

        const pendingFetchIds = visibleProjectIds.filter((projectId) => {
            const current = projectPotentialVulnerabilityMap[projectId];
            const taskPoolState = projectTaskPoolsMap[projectId];
            return !current && taskPoolState?.status === "ready";
        });

        if (pendingFetchIds.length > 0) {
            setProjectPotentialVulnerabilityMap((previous) => {
                const next = { ...previous };
                for (const projectId of pendingFetchIds) {
                    if (!next[projectId]) {
                        next[projectId] = { status: "loading", items: [] };
                    }
                }
                return next;
            });

            for (const projectId of pendingFetchIds) {
                void fetchProjectPotentialVulnerabilities(projectId);
            }
        }
    }, [
        projectTaskPoolsMap,
        pagedProjects,
        projectPotentialVulnerabilityMap,
        fetchProjectPotentialVulnerabilities,
    ]);

    useEffect(() => {
        return () => {
            for (const timer of Object.values(languageStatsPollTimerRef.current)) {
                window.clearTimeout(timer);
            }
            languageStatsPollTimerRef.current = {};
            potentialVulnerabilityLoadingRef.current = {};
            projectTaskPoolLoadingRef.current = {};
        };
    }, []);

    const projectRecentTasksMap = useMemo(() => {
        return new Map(
            pagedProjects.map((project) => {
                const projectTaskPools = projectTaskPoolsMap[project.id];
                return [
                    project.id,
                    getProjectCardRecentTasks({
                        projectId: project.id,
                        auditTasks: projectTaskPools?.auditTasks || [],
                        agentTasks: projectTaskPools?.agentTasks || [],
                        opengrepTasks: projectTaskPools?.opengrepTasks || [],
                        gitleaksTasks: projectTaskPools?.gitleaksTasks || [],
                        limit: 3,
                    }),
                ];
            }),
        );
    }, [pagedProjects, projectTaskPoolsMap]);

    const projectSummaryStatsMap = useMemo(() => {
        return new Map(
            pagedProjects.map((project) => {
                const projectTaskPools = projectTaskPoolsMap[project.id];
                return [
                    project.id,
                    getProjectCardSummaryStats({
                        projectId: project.id,
                        auditTasks: projectTaskPools?.auditTasks || [],
                        agentTasks: projectTaskPools?.agentTasks || [],
                        opengrepTasks: projectTaskPools?.opengrepTasks || [],
                    }),
                ];
            }),
        );
    }, [pagedProjects, projectTaskPoolsMap]);

    const projectLanguagesMap = useMemo(() => {
        return new Map(
            pagedProjects.map((project) => {
                try {
                    const parsed = JSON.parse(project.programming_languages || "[]");
                    return [
                        project.id,
                        Array.isArray(parsed)
                            ? parsed.filter(
                                (item): item is string => typeof item === "string",
                            )
                            : [],
                    ];
                } catch {
                    return [project.id, [] as string[]];
                }
            }),
        );
    }, [pagedProjects]);

    const projectDetailFrom = `${location.pathname}${location.search}${location.hash}`;

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

    const getTaskStatusBadgeClassName = (status: string) => {
        if (status === "completed") return "cyber-badge-success";
        if (status === "running") return "cyber-badge-info";
        if (status === "failed") return "cyber-badge-danger";
        if (status === "interrupted" || status === "cancelled" || status === "aborted") {
            return "cyber-badge-warning";
        }
        return "cyber-badge-muted";
    };

    const getTaskStatusText = (status: string) => {
        switch (status) {
            case "completed":
                return "完成";
            case "running":
                return "运行中";
            case "failed":
                return "失败";
            case "interrupted":
            case "cancelled":
            case "aborted":
                return "已中断";
            case "pending":
                return "等待中";
            default:
                return status || "未知";
        }
    };

    const formatRecentTaskMetricValue = (value: number | null) => {
        if (value === null || !Number.isFinite(value)) return "--";
        return value.toLocaleString();
    };

    const getVulnerabilitySeverityBadgeClassName = (
        severity: ProjectCardPotentialVulnerability["severity"],
    ) => {
        if (severity === "CRITICAL") return "cyber-badge-danger";
        if (severity === "HIGH") return "cyber-badge-warning";
        if (severity === "MEDIUM") return "cyber-badge-info";
        if (severity === "LOW") return "cyber-badge-muted";
        return "cyber-badge-muted";
    };

    const getVulnerabilitySeverityText = (
        severity: ProjectCardPotentialVulnerability["severity"],
    ) => {
        if (severity === "CRITICAL") return "严重";
        if (severity === "HIGH") return "高危";
        if (severity === "MEDIUM") return "中危";
        if (severity === "LOW") return "低危";
        return "未知";
    };

    const getVulnerabilityConfidenceText = (
        confidence: ProjectCardPotentialVulnerability["confidence"],
    ) => {
        if (confidence === "HIGH") return "高";
        if (confidence === "MEDIUM") return "中";
        if (confidence === "LOW") return "低";
        return "未知";
    };

    const handleCreateTask = (projectId: string) => {
        openCreateAuditDialog("agent", projectId, {
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

    return (
        <div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
            {/* Grid background */}
            <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
            {loading && (
                <div className="relative z-10 text-xs text-muted-foreground">
                    加载项目列表中...
                </div>
            )}

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
                                            onValueChange={(value) =>
                                                setCreateForm({
                                                    ...createForm,
                                                    repository_type:
                                                        value as CreateProjectForm["repository_type"],
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
                                        onClick={() => closeCreateProjectDialog()}
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
                                        onClick={() => closeCreateProjectDialog()}
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

            {/* Project Browser */}
            <div id="project-browser" className="cyber-card p-4 relative z-10">
                <div className="flex items-center justify-between gap-3">
                    <div className="section-header">
                        <Code className="w-5 h-5 text-primary" />
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
                        <span>共 {filteredProjects.length} 个</span>
                    </div>
                </div>
                <div className="space-y-2">
                    {loading && projects.length === 0 ? (
                        <div className="cyber-card p-4 space-y-3">
                            <Skeleton className="h-5 w-40" />
                            <Skeleton className="h-8 w-full" />
                            <Skeleton className="h-8 w-full" />
                            <Skeleton className="h-56 w-full" />
                        </div>
                    ) : pagedProjects.length > 0 ? (
                        pagedProjects.map((project) => (
                            <div
                                key={project.id}
                                className={`block p-3 rounded-lg border transition-all ${project.is_active
                                        ? "bg-primary/5 border-primary/20 hover:border-primary/40"
                                        : "bg-muted/20 border-border hover:border-border"
                                    }`}
                            >
                                {(() => {
                                    const languageStats = projectLanguageStatsMap[project.id];
                                    const recentTasks = projectRecentTasksMap.get(project.id) || [];
                                    const programmingLanguages = projectLanguagesMap.get(project.id) || [];
                                    const potentialVulnerabilityState =
                                        projectPotentialVulnerabilityMap[project.id] ||
                                        (projectTaskPoolsMap[project.id]?.status === "loading"
                                            ? ({ status: "loading", items: [] } as ProjectCardPotentialVulnerabilityState)
                                            : undefined);
                                    const summaryStats = projectSummaryStatsMap.get(project.id) || {
                                        totalTasks: 0,
                                        completedTasks: 0,
                                        totalIssues: 0,
                                    };

                                    return (
                                        <>
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

                                <DeferredSection minHeight={420} priority>
                                <div className="mt-3 space-y-3">
                                    <div className="grid grid-cols-3 gap-2">
                                        <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
                                            <p className="text-[11px] text-muted-foreground">
                                                {t("projects.card.totalIssues")}
                                            </p>
                                            <p className="text-sm font-semibold text-amber-300">
                                                {summaryStats.totalIssues}
                                            </p>
                                        </div>
                                        <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
                                            <p className="text-[11px] text-muted-foreground">
                                                {t("projects.card.totalTasks")}
                                            </p>
                                            <p className="text-sm font-semibold text-foreground">
                                                {summaryStats.totalTasks}
                                            </p>
                                        </div>
                                        <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
                                            <p className="text-[11px] text-muted-foreground">
                                                {t("projects.card.completedTasks")}
                                            </p>
                                            <p className="text-sm font-semibold text-emerald-400">
                                                {summaryStats.completedTasks}
                                            </p>
                                        </div>
                                    </div>

                                    <p className="text-sm text-muted-foreground line-clamp-2">
                                        {project.description?.trim() || "暂无项目描述"}
                                    </p>

                                    <div className="flex flex-wrap gap-2">
                                        {programmingLanguages.length > 0 ? (
                                            programmingLanguages.slice(0, 5).map((language) => (
                                                <Badge key={`${project.id}-${language}`} className="cyber-badge-primary">
                                                    {language}
                                                </Badge>
                                            ))
                                        ) : (
                                            <Badge className="cyber-badge-muted">语言未识别</Badge>
                                        )}
                                    </div>

                                    <div className="grid grid-cols-1 xl:grid-cols-10 gap-3">
                                        <div className="rounded-lg border border-border bg-muted/40 p-3 xl:col-span-3">
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                    语言统计
                                                </p>
                                                {languageStats?.status === "ready" && (
                                                    <span className="text-[11px] text-muted-foreground">
                                                        {languageStats.total.toLocaleString()} 行
                                                    </span>
                                                )}
                                            </div>

                                            {languageStats?.status === "loading" ||
                                            languageStats?.status === "pending" ? (
                                                <p className="text-xs text-muted-foreground">
                                                    语言统计生成中...
                                                </p>
                                            ) : languageStats?.status === "unsupported" ? (
                                                <p className="text-xs text-muted-foreground">
                                                    {t("projects.language.unsupported")}
                                                </p>
                                            ) : languageStats?.status === "failed" ? (
                                                <p className="text-xs text-rose-400">
                                                    语言统计加载失败
                                                </p>
                                            ) : languageStats?.status === "ready" ? (
                                                <div className="space-y-3">
                                                    <div className="h-[170px]">
                                                        <Suspense
                                                            fallback={
                                                                <div className="h-full flex items-center justify-center text-xs text-muted-foreground">
                                                                    语言图表加载中...
                                                                </div>
                                                            }
                                                        >
                                                            <ProjectLanguagePieChart
                                                                projectId={project.id}
                                                                slices={languageStats.slices}
                                                                colors={PROJECT_CARD_PIE_COLORS}
                                                            />
                                                        </Suspense>
                                                    </div>
                                                    <div className="space-y-1.5 pt-2 border-t border-border/60">
                                                        {languageStats.slices.slice(0, 5).map((slice, index) => (
                                                            <div
                                                                key={`${project.id}-lang-item-${slice.name}`}
                                                                className="flex items-center justify-between text-[11px] gap-2"
                                                            >
                                                                <span className="inline-flex items-center gap-1.5 min-w-0">
                                                                    <span
                                                                        className="w-2 h-2 rounded-full shrink-0"
                                                                        style={{
                                                                            backgroundColor:
                                                                                PROJECT_CARD_PIE_COLORS[
                                                                                    index % PROJECT_CARD_PIE_COLORS.length
                                                                                ],
                                                                        }}
                                                                    />
                                                                    <span className="truncate text-foreground font-semibold">
                                                                        {slice.name}
                                                                    </span>
                                                                </span>
                                                                <span className="inline-flex items-center gap-2 shrink-0">
                                                                    <span className="text-muted-foreground">
                                                                        {(slice.proportion * 100).toFixed(1)}%
                                                                    </span>
                                                                    <span className="text-foreground/80">
                                                                        {slice.loc.toLocaleString()} 行
                                                                    </span>
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground">
                                                    暂无语言统计
                                                </p>
                                            )}
                                        </div>

                                        <div className="rounded-lg border border-border bg-muted/40 p-3 xl:col-span-3">
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                    最近任务
                                                </p>
                                                <span className="text-[11px] text-muted-foreground">
                                                    最近 3 条
                                                </span>
                                            </div>
                                            {recentTasks.length > 0 ? (
                                                <div className="space-y-2">
                                                    {recentTasks.map((task) => (
                                                        <Link
                                                            key={`${project.id}-${task.kind}-${task.id}`}
                                                            to={task.route}
                                                            className="block rounded border border-border bg-background/80 px-2.5 py-2 hover:border-primary/40 transition-colors"
                                                        >
                                                            <div className="flex items-center justify-between gap-2">
                                                                <p className="text-sm text-foreground font-semibold truncate">
                                                                    {task.label}
                                                                </p>
                                                                <Badge className={getTaskStatusBadgeClassName(task.status)}>
                                                                    {getTaskStatusText(task.status)}
                                                                </Badge>
                                                            </div>
                                                            <p className="mt-1 text-[11px] text-muted-foreground">
                                                                {formatCreatedAt(task.createdAt)}
                                                            </p>
                                                            <div className="mt-2 space-y-1">
                                                                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                                                                    <span>进度</span>
                                                                    <span>{Math.round(task.progressPercent)}%</span>
                                                                </div>
                                                                <Progress
                                                                    value={task.progressPercent}
                                                                    className="h-1.5 bg-muted/45 [&>div]:bg-primary"
                                                                />
                                                            </div>
                                                            <div className="mt-2 grid grid-cols-3 gap-1.5">
                                                                <div className="rounded border border-border/70 bg-muted/35 px-2 py-1.5">
                                                                    <p className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                                                                        <FileText className="w-3 h-3" />
                                                                        扫描文件
                                                                    </p>
                                                                    <p className="mt-1 text-xs font-semibold text-foreground">
                                                                        {formatRecentTaskMetricValue(task.scannedFiles)}
                                                                    </p>
                                                                </div>
                                                                <div className="rounded border border-border/70 bg-muted/35 px-2 py-1.5">
                                                                    <p className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                                                                        <Code className="w-3 h-3" />
                                                                        扫描代码行
                                                                    </p>
                                                                    <p className="mt-1 text-xs font-semibold text-foreground">
                                                                        {formatRecentTaskMetricValue(task.scannedLines)}
                                                                    </p>
                                                                </div>
                                                                <div className="rounded border border-border/70 bg-muted/35 px-2 py-1.5">
                                                                    <p className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                                                                        <AlertCircle className="w-3 h-3" />
                                                                        发现漏洞
                                                                    </p>
                                                                    <p className="mt-1 text-xs font-semibold text-amber-300">
                                                                        {formatRecentTaskMetricValue(task.vulnerabilities)}
                                                                    </p>
                                                                </div>
                                                            </div>
                                                        </Link>
                                                    ))}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground">
                                                    暂无任务记录
                                                </p>
                                            )}
                                        </div>

                                        <div className="rounded-lg border border-border bg-muted/40 p-3 xl:col-span-4">
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                    潜在漏洞
                                                </p>
                                                <span className="text-[11px] text-muted-foreground">
                                                    Top 5
                                                </span>
                                            </div>
                                            {potentialVulnerabilityState?.status === "loading" ? (
                                                <p className="text-xs text-muted-foreground">
                                                    潜在漏洞分析中...
                                                </p>
                                            ) : potentialVulnerabilityState?.status === "failed" ? (
                                                <p className="text-xs text-rose-400">
                                                    潜在漏洞加载失败
                                                </p>
                                            ) : potentialVulnerabilityState?.status === "ready" &&
                                              potentialVulnerabilityState.items.length > 0 ? (
                                                <div className="space-y-2">
                                                    {potentialVulnerabilityState.items.map((item) => (
                                                        <Link
                                                            key={`${project.id}-vuln-${item.id}`}
                                                            to={item.route}
                                                            className="block rounded border border-border bg-background/80 px-2.5 py-2 hover:border-primary/40 transition-colors"
                                                        >
                                                            <div className="flex items-center justify-between gap-2">
                                                                <p className="text-sm text-foreground font-semibold truncate">
                                                                    {item.title}
                                                                </p>
                                                                <Badge
                                                                    className={getVulnerabilitySeverityBadgeClassName(
                                                                        item.severity,
                                                                    )}
                                                                >
                                                                    {getVulnerabilitySeverityText(item.severity)}
                                                                </Badge>
                                                            </div>
                                                            <div className="mt-1 flex items-center justify-between gap-2 text-[11px]">
                                                                <p className="text-muted-foreground truncate">
                                                                    {item.filePath}
                                                                    {item.line ? `:${item.line}` : ""}
                                                                </p>
                                                                <span className="text-foreground/80 shrink-0">
                                                                    置信度 {getVulnerabilityConfidenceText(item.confidence)}
                                                                </span>
                                                            </div>
                                                        </Link>
                                                    ))}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground">
                                                    暂无潜在漏洞
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                </DeferredSection>
                                        </>
                                    );
                                })()}
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

            {showCreateAuditDialog ? (
                <Suspense fallback={null}>
                    <CreateProjectAuditDialog
                        open={showCreateAuditDialog}
                        onOpenChange={handleCreateAuditDialogOpenChange}
                        onTaskCreated={handleTaskCreated}
                        preselectedProjectId={auditPreselectedProjectId}
                        initialMode={auditInitialMode}
                        navigateOnSuccess={auditNavigateOnSuccess}
                    />
                </Suspense>
            ) : null}

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
                                            onValueChange={(value) =>
                                                setEditForm({
                                                    ...editForm,
                                                    repository_type:
                                                        value as CreateProjectForm["repository_type"],
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
