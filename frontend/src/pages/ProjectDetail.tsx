/**
 * Project Detail Page
 * Cyberpunk Terminal Aesthetic
 */

import { useMemo, useState, useEffect } from "react";
import { useParams, useLocation, useNavigate, Link } from "react-router-dom";
import {
    PieChart,
    Pie,
    Cell,
    Tooltip as ChartTooltip,
    ResponsiveContainer,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    ArrowLeft,
    ExternalLink,
    Shield,
    Activity,
    AlertTriangle,
    CheckCircle,
    Clock,
    XCircle,
    Terminal,
} from "lucide-react";
import { api } from "@/shared/config/database";
import type {
    Project,
    AuditTask,
    AuditIssue,
} from "@/shared/types";
import type { AgentFinding, AgentTask } from "@/shared/api/agentTasks";
import { getAgentTasks } from "@/shared/api/agentTasks";
import { apiClient } from "@/shared/api/serverClient";
import {
    getOpengrepScanTasks,
    type OpengrepScanTask,
} from "@/shared/api/opengrep";
import {
    getGitleaksScanTasks,
    type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
    isRepositoryProject,
    getSourceTypeLabel,
    getRepositoryPlatformLabel,
} from "@/shared/utils/projectUtils";
import { toast } from "sonner";
import CreateTaskDialog from "@/components/audit/CreateTaskDialog";
import type {
    AggregatedAgentFinding,
    AggregatedAuditIssue,
    IssuesSummary,
    LatestProblem,
    UnifiedTask,
} from "@/shared/types";
import {
    PROJECT_DETAIL_ISSUES_FETCH_CONCURRENCY as ISSUES_FETCH_CONCURRENCY,
    PROJECT_DETAIL_ISSUES_MAX_TASKS as ISSUES_MAX_TASKS,
    PROJECT_DETAIL_REQUEST_TIMEOUT_MS as REQUEST_TIMEOUT_MS,
} from "@/shared/constants";
import { ProjectTasksTab } from "@/pages/project-detail/components/ProjectTasksTab";
import {
    ProjectStatsCards,
    type ProjectCombinedStats,
} from "@/pages/project-detail/components/ProjectStatsCards";

const LANGUAGE_PIE_COLORS = [
    "#0ea5e9",
    "#22c55e",
    "#f59e0b",
    "#8b5cf6",
    "#ef4444",
    "#14b8a6",
    "#f97316",
    "#a855f7",
];

export default function ProjectDetail() {
    const { id } = useParams<{ id: string }>();
    const location = useLocation();
    const navigate = useNavigate();
    const [project, setProject] = useState<Project | null>(null);
    const [auditTasks, setAuditTasks] = useState<AuditTask[]>([]);
    const [agentTasks, setAgentTasks] = useState<AgentTask[]>([]);
    const [staticTasks, setStaticTasks] = useState<OpengrepScanTask[]>([]);
    const [gitleaksTasks, setGitleaksTasks] = useState<GitleaksScanTask[]>([]);
    const [projectInfo, setProjectInfo] = useState<{
        id?: string;
        project_id?: string;
        language_info?: string;
        description?: string;
        status?: string;
        created_at?: string;
    } | null>(null);
    const [projectInfoStatus, setProjectInfoStatus] = useState<string>("idle");
    const [loading, setLoading] = useState(true);
    const [showCreateTaskDialog, setShowCreateTaskDialog] = useState(false);
    const [activeTab, setActiveTab] = useState("overview");
    const [latestIssues, setLatestIssues] = useState<AggregatedAuditIssue[]>(
        [],
    );
    const [latestFindings, setLatestFindings] = useState<
        AggregatedAgentFinding[]
    >([]);
    const [loadingIssues, setLoadingIssues] = useState(false);
    const [issuesSummary, setIssuesSummary] = useState<IssuesSummary>({
        completedAuditTasksCount: 0,
        completedAgentTasksCount: 0,
        fetchedAuditTasksCount: 0,
        fetchedAgentTasksCount: 0,
        isLimited: false,
        maxTasks: 20,
    });
    const fallbackBackPath = "/projects#project-browser";
    const sourceFromState =
        typeof (location.state as { from?: unknown } | null)?.from === "string"
            ? ((location.state as { from?: string }).from ?? "")
            : "";
    const normalizedSourceFrom =
        sourceFromState.startsWith("/") ? sourceFromState : "";
    const backTarget =
        normalizedSourceFrom && normalizedSourceFrom !== location.pathname
            ? normalizedSourceFrom
            : fallbackBackPath;

    const handleBack = () => {
        navigate(backTarget);
    };

    // ============ Helpers ============

    async function withTimeout<T>(
        promise: Promise<T>,
        timeoutMs: number,
        label: string,
    ): Promise<T> {
        let timeoutId: number | undefined;
        const timeoutPromise = new Promise<T>((_resolve, reject) => {
            timeoutId = window.setTimeout(
                () =>
                    reject(
                        new Error(`${label} timed out after ${timeoutMs}ms`),
                    ),
                timeoutMs,
            );
        });
        try {
            return await Promise.race([promise, timeoutPromise]);
        } finally {
            if (timeoutId != null) window.clearTimeout(timeoutId);
        }
    }

    async function mapWithConcurrency<T, R>(
        items: T[],
        concurrency: number,
        mapper: (item: T) => Promise<R>,
    ): Promise<PromiseSettledResult<R>[]> {
        const results: PromiseSettledResult<R>[] = new Array(items.length);
        let nextIndex = 0;

        async function worker(): Promise<void> {
            while (true) {
                const currentIndex = nextIndex++;
                if (currentIndex >= items.length) return;
                try {
                    const value = await mapper(items[currentIndex]);
                    results[currentIndex] = { status: "fulfilled", value };
                } catch (reason) {
                    results[currentIndex] = { status: "rejected", reason };
                }
            }
        }

        const workers = Array.from({ length: Math.max(1, concurrency) }, () =>
            worker(),
        );
        await Promise.all(workers);
        return results;
    }

    async function fetchAuditIssues(taskId: string): Promise<AuditIssue[]> {
        // Use apiClient directly so we can control timeout behavior at the call site
        const res = await withTimeout(
            apiClient.get(`/tasks/${taskId}/issues`),
            REQUEST_TIMEOUT_MS,
            `GET /tasks/${taskId}/issues`,
        );
        return res.data;
    }

    async function fetchAgentFindings(taskId: string): Promise<AgentFinding[]> {
        const res = await withTimeout(
            apiClient.get(`/agent-tasks/${taskId}/findings`),
            REQUEST_TIMEOUT_MS,
            `GET /agent-tasks/${taskId}/findings`,
        );
        return res.data;
    }

    useEffect(() => {
        if (
            activeTab === "issues" &&
            (auditTasks.length > 0 || agentTasks.length > 0)
        ) {
            loadLatestIssues();
        }
    }, [activeTab, auditTasks, agentTasks]);

    const loadLatestIssues = async () => {
        const completedAuditTasks = auditTasks
            .filter((t: AuditTask) => t.status === "completed")
            .sort(
                (a: AuditTask, b: AuditTask) =>
                    new Date(b.created_at).getTime() -
                    new Date(a.created_at).getTime(),
            );
        const completedAgentTasks = agentTasks
            .filter((t: AgentTask) => t.status === "completed")
            .sort(
                (a: AgentTask, b: AgentTask) =>
                    new Date(b.created_at).getTime() -
                    new Date(a.created_at).getTime(),
            );

        const limitedAuditTasks = completedAuditTasks.slice(
            0,
            ISSUES_MAX_TASKS,
        );
        const limitedAgentTasks = completedAgentTasks.slice(
            0,
            ISSUES_MAX_TASKS,
        );

        setIssuesSummary({
            completedAuditTasksCount: completedAuditTasks.length,
            completedAgentTasksCount: completedAgentTasks.length,
            fetchedAuditTasksCount: limitedAuditTasks.length,
            fetchedAgentTasksCount: limitedAgentTasks.length,
            isLimited:
                completedAuditTasks.length > ISSUES_MAX_TASKS ||
                completedAgentTasks.length > ISSUES_MAX_TASKS,
            maxTasks: ISSUES_MAX_TASKS,
        });

        if (limitedAuditTasks.length === 0 && limitedAgentTasks.length === 0) {
            setLatestIssues([]);
            setLatestFindings([]);
            return;
        }

        setLoadingIssues(true);
        try {
            const [issuesResults, findingsResults] = await Promise.all([
                mapWithConcurrency(
                    limitedAuditTasks,
                    ISSUES_FETCH_CONCURRENCY,
                    async (task: AuditTask) => {
                        const issues = await fetchAuditIssues(task.id);
                        const enriched: AggregatedAuditIssue[] = (
                            issues || []
                        ).map((issue) => ({
                            ...(issue as AuditIssue),
                            task_created_at: task.created_at,
                            task_completed_at: task.completed_at,
                        }));
                        return enriched;
                    },
                ),
                mapWithConcurrency(
                    limitedAgentTasks,
                    ISSUES_FETCH_CONCURRENCY,
                    async (task: AgentTask) => {
                        const findings = await fetchAgentFindings(task.id);
                        const enriched: AggregatedAgentFinding[] = (
                            findings || []
                        ).map((finding) => ({
                            ...(finding as AgentFinding),
                            task_created_at: task.created_at,
                            task_completed_at: task.completed_at,
                        }));
                        return enriched;
                    },
                ),
            ]);

            const flatIssues = issuesResults
                .filter(
                    (
                        r: PromiseSettledResult<AggregatedAuditIssue[]>,
                    ): r is PromiseFulfilledResult<AggregatedAuditIssue[]> =>
                        r.status === "fulfilled",
                )
                .flatMap(
                    (r: PromiseFulfilledResult<AggregatedAuditIssue[]>) =>
                        r.value,
                );
            const flatFindings = findingsResults
                .filter(
                    (
                        r: PromiseSettledResult<AggregatedAgentFinding[]>,
                    ): r is PromiseFulfilledResult<AggregatedAgentFinding[]> =>
                        r.status === "fulfilled",
                )
                .flatMap(
                    (r: PromiseFulfilledResult<AggregatedAgentFinding[]>) =>
                        r.value,
                );

            const severityRank: Record<string, number> = {
                critical: 4,
                high: 3,
                medium: 2,
                low: 1,
            };
            flatIssues.sort(
                (a: AggregatedAuditIssue, b: AggregatedAuditIssue) => {
                    const createdAtA = new Date(a.created_at).getTime();
                    const createdAtB = new Date(b.created_at).getTime();
                    if (createdAtA !== createdAtB)
                        return createdAtB - createdAtA;

                    const severityA = severityRank[a.severity] ?? 0;
                    const severityB = severityRank[b.severity] ?? 0;
                    if (severityA !== severityB) return severityB - severityA;

                    const taskCreatedAtA = a.task_created_at
                        ? new Date(a.task_created_at).getTime()
                        : 0;
                    const taskCreatedAtB = b.task_created_at
                        ? new Date(b.task_created_at).getTime()
                        : 0;
                    return taskCreatedAtB - taskCreatedAtA;
                },
            );

            setLatestIssues(flatIssues);
            flatFindings.sort(
                (a: AggregatedAgentFinding, b: AggregatedAgentFinding) => {
                    const createdAtA = new Date(a.created_at).getTime();
                    const createdAtB = new Date(b.created_at).getTime();
                    if (createdAtA !== createdAtB)
                        return createdAtB - createdAtA;

                    const severityA =
                        severityRank[String(a.severity || "").toLowerCase()] ??
                        0;
                    const severityB =
                        severityRank[String(b.severity || "").toLowerCase()] ??
                        0;
                    if (severityA !== severityB) return severityB - severityA;

                    const taskCreatedAtA = a.task_created_at
                        ? new Date(a.task_created_at).getTime()
                        : 0;
                    const taskCreatedAtB = b.task_created_at
                        ? new Date(b.task_created_at).getTime()
                        : 0;
                    return taskCreatedAtB - taskCreatedAtA;
                },
            );
            setLatestFindings(flatFindings);
        } catch (error) {
            console.error("Failed to load issues:", error);
            toast.error("加载问题列表失败");
        } finally {
            setLoadingIssues(false);
        }
    };

    const latestProblems: LatestProblem[] = useMemo(() => {
        const parsePathLineFromTitle = (title: string) => {
            // Pattern examples:
            // "path/to/File.java:66 - Something"
            // "path/to/File.java:137-138 - Something"
            // Security hardening:
            // - Cap title length
            // - Restrict acceptable path characters
            // - Reject absolute paths and path traversal segments
            const safeTitle = String(title || "").slice(0, 500);
            const match = safeTitle.match(
                /^([A-Za-z0-9_.\-\/]+):(\d+)(?:-(\d+))?\s*-\s*(.+)$/,
            );
            if (!match) return null;
            const [, rawPath, lineStartStr, lineEndStr, rest] = match;

            if (
                rawPath.startsWith("/") ||
                rawPath.includes("..") ||
                rawPath.includes("\u0000")
            )
                return null;

            const lineStart = Number(lineStartStr);
            const lineEnd = lineEndStr ? Number(lineEndStr) : null;
            const normalizedLineStart = Number.isFinite(lineStart)
                ? lineStart
                : NaN;
            const normalizedLineEnd =
                lineEnd != null && Number.isFinite(lineEnd) ? lineEnd : null;
            if (
                !Number.isFinite(normalizedLineStart) ||
                normalizedLineStart <= 0
            )
                return null;
            return {
                file_path: rawPath,
                line_start: normalizedLineStart,
                line_end:
                    normalizedLineEnd != null && normalizedLineEnd > 0
                        ? normalizedLineEnd
                        : null,
                rest_title: rest,
            };
        };

        const normalizeSeverity = (s: unknown): LatestProblem["severity"] => {
            const v = String(s || "").toLowerCase();
            if (v === "critical") return "critical";
            if (v === "high") return "high";
            if (v === "medium") return "medium";
            return "low";
        };

        const audit: LatestProblem[] = latestIssues.map((i) => ({
            // AuditIssue 在后端 schema 里可能叫 message（frontend type 没显式定义），这里做兼容兜底
            // 同时优先展示更“可读”的说明字段，避免 UI 出现大量 '-'
            kind: "audit",
            id: i.id,
            task_id: i.task_id,
            task_created_at: i.task_created_at,
            created_at: i.created_at,
            severity: normalizeSeverity(i.severity),
            title: i.title || "(未命名问题)",
            description:
                i.description ??
                (i as any).message ??
                (i as any).ai_explanation ??
                (i as any).suggestion ??
                (i as any).code_snippet ??
                null,
            file_path: i.file_path,
            line_number: i.line_number ?? null,
            category: (i as any).issue_type ?? null,
        }));

        const agent: LatestProblem[] = latestFindings.map((f) => {
            const rawTitle = f.title || "(未命名漏洞)";
            const parsed =
                !f.file_path || f.file_path === "-"
                    ? parsePathLineFromTitle(rawTitle)
                    : null;

            return {
                kind: "agent",
                id: f.id,
                task_id: f.task_id,
                task_created_at: f.task_created_at,
                created_at: f.created_at,
                severity: normalizeSeverity(f.severity),
                // 如果 title 里带了 "path:line - xxx"，则剥离掉路径前缀，仅保留 xxx，避免标题重复且过长
                title: parsed?.rest_title || rawTitle,
                description: f.description,
                // 如果后端没给 file_path，尽量从 title 解析出来填到“文件”列
                file_path: f.file_path ?? parsed?.file_path ?? null,
                line_number: (f.line_start ??
                    parsed?.line_start ??
                    null) as any,
                line_end: (f.line_end ?? parsed?.line_end ?? null) as any,
                category: (f as any).vulnerability_type ?? null,
            };
        });

        const merged = [...audit, ...agent];
        // 按时间倒序（最新在前），时间相同再按严重程度
        const severityRank: Record<string, number> = {
            critical: 4,
            high: 3,
            medium: 2,
            low: 1,
        };
        merged.sort((a, b) => {
            const createdAtA = new Date(a.created_at).getTime();
            const createdAtB = new Date(b.created_at).getTime();
            if (createdAtA !== createdAtB) return createdAtB - createdAtA;

            const severityA = severityRank[a.severity] ?? 0;
            const severityB = severityRank[b.severity] ?? 0;
            if (severityA !== severityB) return severityB - severityA;

            const taskCreatedAtA = a.task_created_at
                ? new Date(a.task_created_at).getTime()
                : 0;
            const taskCreatedAtB = b.task_created_at
                ? new Date(b.task_created_at).getTime()
                : 0;
            return taskCreatedAtB - taskCreatedAtA;
        });
        return merged;
    }, [latestIssues, latestFindings]);

    const parsedLanguageInfo = useMemo(() => {
        if (!projectInfo?.language_info) return null;
        const raw = projectInfo.language_info;
        try {
            const data = typeof raw === "string" ? JSON.parse(raw) : raw;
            if (!data || typeof data !== "object") return null;

            const total = Number(data.total ?? 0);
            const totalFiles = Number(data.total_files ?? 0);
            const languages =
                data.languages && typeof data.languages === "object"
                    ? data.languages
                    : {};
            const items = Object.entries(languages)
                .map(([name, info]) => {
                    const loc = Number(
                        (info as { loc_number?: number }).loc_number ?? 0,
                    );
                    const files = Number(
                        (info as { files_count?: number; file_count?: number })
                            .files_count ??
                        (info as { files_count?: number; file_count?: number })
                            .file_count ??
                        0,
                    );
                    const proportion = Number(
                        (info as { proportion?: number }).proportion ?? 0,
                    );
                    return { name, loc, files, proportion };
                })
                .filter((item) => item.name && Number.isFinite(item.loc))
                .sort((a, b) => b.proportion - a.proportion);

            return { total, totalFiles, items };
        } catch {
            return null;
        }
    }, [projectInfo?.language_info]);

    const projectAnalysisDescription = useMemo(() => {
        const directDescription = (project?.description || "").trim();
        if (directDescription) return directDescription;
        const legacyDescription = (projectInfo?.description || "").trim();
        return legacyDescription;
    }, [project?.description, projectInfo?.description]);

    useEffect(() => {
        if (id) {
            loadProjectData();
        }
    }, [id]);

    const loadProjectData = async () => {
        if (!id) return;

        try {
            setLoading(true);
            const [
                projectRes,
                auditTasksRes,
                agentTasksRes,
                staticTasksRes,
                gitleaksTasksRes,
            ] =
                await Promise.allSettled([
                    api.getProjectById(id),
                    api.getAuditTasks(id),
                    getAgentTasks({ project_id: id }),
                    getOpengrepScanTasks({ projectId: id }),
                    getGitleaksScanTasks({ projectId: id }),
                ]);

            if (projectRes.status === "fulfilled") {
                setProject(projectRes.value);
            } else {
                console.error("Failed to load project:", projectRes.reason);
                setProject(null);
            }

            if (auditTasksRes.status === "fulfilled") {
                setAuditTasks(
                    Array.isArray(auditTasksRes.value)
                        ? auditTasksRes.value
                        : [],
                );
            } else {
                console.error(
                    "Failed to load audit tasks:",
                    auditTasksRes.reason,
                );
                setAuditTasks([]);
            }

            if (agentTasksRes.status === "fulfilled") {
                setAgentTasks(
                    Array.isArray(agentTasksRes.value)
                        ? agentTasksRes.value
                        : [],
                );
            } else {
                // do not silently swallow: log for debugging and degrade gracefully
                console.warn(
                    "Failed to load agent tasks:",
                    agentTasksRes.reason,
                );
                setAgentTasks([]);
            }

            if (staticTasksRes.status === "fulfilled") {
                setStaticTasks(
                    Array.isArray(staticTasksRes.value)
                        ? staticTasksRes.value
                        : [],
                );
            } else {
                console.warn(
                    "Failed to load static tasks:",
                    staticTasksRes.reason,
                );
                setStaticTasks([]);
            }

            if (gitleaksTasksRes.status === "fulfilled") {
                setGitleaksTasks(
                    Array.isArray(gitleaksTasksRes.value)
                        ? gitleaksTasksRes.value
                        : [],
                );
            } else {
                console.warn(
                    "Failed to load gitleaks tasks:",
                    gitleaksTasksRes.reason,
                );
                setGitleaksTasks([]);
            }

            const shouldLoadProjectInfo = projectRes.status === "fulfilled";
            if (!shouldLoadProjectInfo) {
                setProjectInfo(null);
                setProjectInfoStatus("idle");
            } else {
                try {
                    setProjectInfoStatus("loading");
                    const infoRes = await apiClient.get(`/projects/info/${id}`);
                    if (infoRes.data?.status) {
                        setProjectInfo(infoRes.data);
                        setProjectInfoStatus(infoRes.data.status || "completed");
                    } else if (infoRes.data?.detail) {
                        setProjectInfo(null);
                        setProjectInfoStatus("pending");
                    } else {
                        setProjectInfo(infoRes.data);
                        setProjectInfoStatus("completed");
                    }
                } catch (infoError: any) {
                    const statusCode = infoError?.response?.status;
                    if (statusCode === 202) {
                        setProjectInfoStatus("pending");
                    } else {
                        console.warn("Failed to load project info:", infoError);
                        setProjectInfoStatus("failed");
                    }
                }
            }
        } catch (error) {
            console.error("Failed to load project data:", error);
            toast.error("加载项目数据失败");
        } finally {
            setLoading(false);
        }
    };

    const unifiedTasks: UnifiedTask[] = useMemo(() => {
        const merged: UnifiedTask[] = [
            ...auditTasks.map((t) => ({ kind: "audit" as const, task: t })),
            ...agentTasks.map((t) => ({ kind: "agent" as const, task: t })),
            ...staticTasks.map((t) => ({ kind: "static" as const, task: t })),
        ];
        merged.sort(
            (a, b) =>
                new Date((b.task as any).created_at).getTime() -
                new Date((a.task as any).created_at).getTime(),
        );
        return merged;
    }, [auditTasks, agentTasks, staticTasks]);

    const staticTaskRouteMap = useMemo(() => {
        const map = new Map<string, string>();
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

        const pickPairedGitleaksTask = (
            opengrepTask: OpengrepScanTask,
        ): GitleaksScanTask | null => {
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

        for (const task of staticTasks) {
            const params = new URLSearchParams();
            params.set("opengrepTaskId", task.id);
            const pairedGitleaksTask = pickPairedGitleaksTask(task);
            if (pairedGitleaksTask) {
                params.set("gitleaksTaskId", pairedGitleaksTask.id);
            }
            map.set(task.id, `/static-analysis/${task.id}?${params.toString()}`);
        }

        return map;
    }, [staticTasks, gitleaksTasks]);

    const getTaskDetailRoute = (wrappedTask: UnifiedTask) => {
        const task: any = wrappedTask.task as any;
        if (wrappedTask.kind === "static") {
            return staticTaskRouteMap.get(task.id) || `/static-analysis/${task.id}`;
        }
        if (wrappedTask.kind === "audit") {
            return `/tasks/${task.id}`;
        }
        return `/agent-audit/${task.id}`;
    };

    const combinedStats: ProjectCombinedStats = useMemo(() => {
        const totalTasks =
            auditTasks.length + agentTasks.length + staticTasks.length;
        const completedTasks =
            auditTasks.filter((t) => t.status === "completed").length +
            agentTasks.filter((t) => t.status === "completed").length +
            staticTasks.filter((t) => t.status === "completed").length;
        const totalIssues =
            auditTasks.reduce((sum, t) => sum + (t.issues_count || 0), 0) +
            agentTasks.reduce((sum, t) => sum + (t.findings_count || 0), 0) +
            staticTasks.reduce((sum, t) => sum + (t.total_findings || 0), 0);
        return { totalTasks, completedTasks, totalIssues };
    }, [auditTasks, agentTasks, staticTasks]);

    const handleRunAudit = () => {
        setShowCreateTaskDialog(true);
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "completed":
                return <Badge className="cyber-badge-success">完成</Badge>;
            case "running":
                return <Badge className="cyber-badge-info">运行中</Badge>;
            case "failed":
                return <Badge className="cyber-badge-danger">失败</Badge>;
            case "interrupted":
                return <Badge className="bg-orange-500/20 text-orange-300 border-orange-500/30">中断</Badge>;
            case "cancelled":
                return <Badge className="cyber-badge-muted">已取消</Badge>;
            default:
                return <Badge className="cyber-badge-muted">等待中</Badge>;
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "completed":
                return <CheckCircle className="w-4 h-4 text-emerald-400" />;
            case "running":
                return <Activity className="w-4 h-4 text-sky-400" />;
            case "failed":
                return <AlertTriangle className="w-4 h-4 text-rose-400" />;
            case "interrupted":
                return <AlertTriangle className="w-4 h-4 text-orange-400" />;
            case "cancelled":
                return <XCircle className="w-4 h-4 text-muted-foreground" />;
            default:
                return <Clock className="w-4 h-4 text-muted-foreground" />;
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString("zh-CN", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    const handleCreateTask = () => {
        setShowCreateTaskDialog(true);
    };

    const handleTaskCreated = () => {
        toast.success("审计任务已创建", {
            description:
                "因为网络和代码文件大小等因素，审计时长通常至少需要1分钟，请耐心等待...",
            duration: 5000,
        });
        loadProjectData();
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

    if (!project) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="cyber-card p-8 text-center">
                    <AlertTriangle className="w-16 h-16 text-rose-400 mx-auto mb-4" />
                    <h2 className="text-2xl font-bold text-foreground mb-2 uppercase">
                        项目未找到
                    </h2>
                    <p className="text-muted-foreground mb-4 font-mono">
                        请检查项目ID是否正确
                    </p>
                    <Button className="cyber-btn-primary" onClick={handleBack}>
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        返回
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6 p-6 cyber-bg-elevated min-h-screen font-mono relative">
            {/* Grid background */}
            <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

            {/* 顶部操作栏 */}
            <div className="relative z-10 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-bold text-foreground uppercase tracking-wider">
                        {project.name}
                    </h1>
                    <Badge
                        className={`${project.is_active ? "cyber-badge-success" : "cyber-badge-muted"}`}
                    >
                        {project.is_active ? "活跃" : "暂停"}
                    </Badge>
                </div>

                <div className="flex items-center space-x-3">
                    <Button
                        variant="outline"
                        size="sm"
                        className="cyber-btn-ghost h-10 px-3 flex items-center justify-center gap-2"
                        onClick={handleBack}
                    >
                        <ArrowLeft className="w-5 h-5" />
                        返回
                    </Button>
                    <Button
                        onClick={handleRunAudit}
                        className="cyber-btn-primary"
                    >
                        <Shield className="w-4 h-4 mr-2" />
                        启动审计
                    </Button>
                </div>
            </div>

            {/* 统计卡片 */}
            <ProjectStatsCards stats={combinedStats} />

            {/* 主要内容 */}
            <Tabs
                value={activeTab}
                onValueChange={setActiveTab}
                className="w-full relative z-10"
            >
                <TabsList className="grid w-full grid-cols-2 bg-muted border border-border p-1 h-auto gap-1 rounded">
                    <TabsTrigger
                        value="overview"
                        className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm"
                    >
                        项目概览
                    </TabsTrigger>
                    <TabsTrigger
                        value="tasks"
                        className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm"
                    >
                        审计任务
                    </TabsTrigger>
                </TabsList>

                <TabsContent
                    value="overview"
                    className="flex flex-col gap-6 mt-6"
                >
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* 项目信息 */}
                        <div className="cyber-card p-4">
                            <div className="section-header">
                                <Terminal className="w-5 h-5 text-primary" />
                                <h3 className="section-title">项目信息</h3>
                            </div>
                            <div className="space-y-4 font-mono">
                                <div className="space-y-3">
                                    {project.repository_url && (
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm text-muted-foreground uppercase">
                                                仓库地址
                                            </span>
                                            <a
                                                href={project.repository_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-sm text-primary hover:underline flex items-center font-bold"
                                            >
                                                查看仓库
                                                <ExternalLink className="w-3 h-3 ml-1" />
                                            </a>
                                        </div>
                                    )}

                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground uppercase">
                                            项目类型
                                        </span>
                                        <Badge
                                            className={`${isRepositoryProject(project) ? "cyber-badge-info" : "cyber-badge-warning"}`}
                                        >
                                            {getSourceTypeLabel(
                                                project.source_type,
                                            )}
                                        </Badge>
                                    </div>

                                    {isRepositoryProject(project) && (
                                        <>
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm text-muted-foreground uppercase">
                                                    仓库平台
                                                </span>
                                                <Badge className="cyber-badge-muted">
                                                    {getRepositoryPlatformLabel(
                                                        project.repository_type,
                                                    )}
                                                </Badge>
                                            </div>

                                            <div className="flex items-center justify-between">
                                                <span className="text-sm text-muted-foreground uppercase">
                                                    默认分支
                                                </span>
                                                <span className="text-sm font-bold text-foreground bg-muted px-2 py-0.5 rounded border border-border">
                                                    {project.default_branch}
                                                </span>
                                            </div>
                                        </>
                                    )}

                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground uppercase">
                                            创建时间
                                        </span>
                                        <span className="text-sm text-foreground">
                                            {formatDate(project.created_at)}
                                        </span>
                                    </div>
                                </div>

                                {project.programming_languages && (
                                    <div className="pt-4 border-t border-border">
                                        <h4 className="text-sm font-bold mb-2 uppercase text-muted-foreground">
                                            支持的编程语言
                                        </h4>
                                        <div className="flex flex-wrap gap-2">
                                            {JSON.parse(
                                                project.programming_languages,
                                            ).map((lang: string) => (
                                                <Badge
                                                    key={lang}
                                                    className="cyber-badge-primary"
                                                >
                                                    {lang}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* 最近活动 */}
                        <div className="cyber-card p-4">
                            <div className="section-header">
                                <Clock className="w-5 h-5 text-emerald-400" />
                                <h3 className="section-title">最近活动</h3>
                            </div>
                            <div>
                                {unifiedTasks.length > 0 ? (
                                    <div className="space-y-2">
                                        {unifiedTasks.slice(0, 5).map((t) => (
                                            <Link
                                                key={`${t.kind}:${t.task.id}`}
                                                to={getTaskDetailRoute(t)}
                                                className="flex items-center justify-between p-3 bg-muted/50 rounded-lg hover:bg-muted transition-all group"
                                            >
                                                <div className="flex items-center space-x-3">
                                                    <div
                                                        className={`w-8 h-8 rounded-lg flex items-center justify-center ${t.task.status ===
                                                                "completed"
                                                                ? "bg-emerald-500/20"
                                                                : t.task
                                                                    .status ===
                                                                    "running"
                                                                    ? "bg-sky-500/20"
                                                                    : t.task
                                                                        .status ===
                                                                        "failed"
                                                                        ? "bg-rose-500/20"
                                                                        : "bg-muted"
                                                            }`}
                                                    >
                                                        {getStatusIcon(
                                                            t.task.status,
                                                        )}
                                                    </div>
                                                    <div>
                                                        <p className="text-sm font-bold text-foreground group-hover:text-primary transition-colors uppercase">
                                                            {t.kind === "static"
                                                                ? "静态分析"
                                                                : t.kind ===
                                                                    "audit"
                                                                    ? (
                                                                        t.task as AuditTask
                                                                    )
                                                                        .task_type ===
                                                                        "repository"
                                                                        ? "审计任务"
                                                                        : "即时分析"
                                                                    : "Agent 审计"}
                                                        </p>
                                                        <p className="text-xs text-muted-foreground font-mono">
                                                            {formatDate(
                                                                t.task
                                                                    .created_at,
                                                            )}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Badge
                                                        className={
                                                            t.kind === "agent"
                                                                ? "cyber-badge-info"
                                                                : "cyber-badge-muted"
                                                        }
                                                    >
                                                        {t.kind === "agent"
                                                            ? "AGENT"
                                                            : t.kind ===
                                                                "static"
                                                                ? "STATIC"
                                                                : "AUDIT"}
                                                    </Badge>
                                                    {getStatusBadge(
                                                        t.task.status,
                                                    )}
                                                </div>
                                            </Link>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="empty-state">
                                        <Activity className="empty-state-icon" />
                                        <p className="empty-state-description">
                                            暂无活动记录
                                        </p>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* 项目分析 */}
                        <div className="cyber-card p-4 lg:col-span-2">
                            <div className="section-header">
                                <Terminal className="w-5 h-5 text-primary" />
                                <h3 className="section-title">项目分析</h3>
                            </div>
                            {projectInfoStatus === "loading" && (
                                <p className="text-sm text-muted-foreground font-mono">
                                    正在生成项目分析...
                                </p>
                            )}
                            {projectInfoStatus === "pending" && (
                                <p className="text-sm text-muted-foreground font-mono">
                                    项目分析生成中，请稍后刷新。
                                </p>
                            )}
                            {projectInfoStatus === "failed" && (
                                <p className="text-sm text-rose-400 font-mono">
                                    项目分析生成失败，可稍后重试。
                                </p>
                            )}
                            <div className="space-y-2 font-mono">
                                <h4 className="text-sm font-bold uppercase text-muted-foreground">
                                    项目描述
                                </h4>
                                <div className="text-sm text-foreground bg-muted border border-border rounded p-3 whitespace-pre-wrap">
                                    {projectAnalysisDescription || "未设置项目描述"}
                                </div>
                            </div>
                            {projectInfoStatus !== "loading" &&
                                projectInfoStatus !== "pending" &&
                                projectInfoStatus !== "failed" &&
                                projectInfo && (
                                    <div className="space-y-4 font-mono">
                                        {projectInfo.language_info && (
                                            <div>
                                                <h4 className="text-sm font-bold mb-2 uppercase text-muted-foreground">
                                                    语言统计
                                                </h4>
                                                {parsedLanguageInfo ? (
                                                    <div className="space-y-3">
                                                        <div className="text-xs text-muted-foreground">
                                                            总计行数:{" "}
                                                            <span className="text-foreground font-semibold">
                                                                {parsedLanguageInfo.total.toLocaleString()}
                                                            </span>
                                                            {parsedLanguageInfo.totalFiles > 0 && (
                                                                <>
                                                                    {" "}
                                                                    · 总文件数:{" "}
                                                                    <span className="text-foreground font-semibold">
                                                                        {parsedLanguageInfo.totalFiles.toLocaleString()}
                                                                    </span>
                                                                </>
                                                            )}
                                                        </div>
                                                        {parsedLanguageInfo
                                                            .items.length > 0 ? (
                                                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                                                <div className="h-64">
                                                                    <ResponsiveContainer width="100%" height="100%">
                                                                        <PieChart>
                                                                            <Pie
                                                                                data={parsedLanguageInfo.items}
                                                                                dataKey="proportion"
                                                                                nameKey="name"
                                                                                cx="50%"
                                                                                cy="50%"
                                                                                outerRadius={90}
                                                                                innerRadius={40}
                                                                                stroke="none"
                                                                            >
                                                                                {parsedLanguageInfo.items.map(
                                                                                    (
                                                                                        _item,
                                                                                        index,
                                                                                    ) => (
                                                                                        <Cell
                                                                                            key={`overview-lang-pie-${index}`}
                                                                                            fill={
                                                                                                LANGUAGE_PIE_COLORS[
                                                                                                index %
                                                                                                LANGUAGE_PIE_COLORS.length
                                                                                                ]
                                                                                            }
                                                                                        />
                                                                                    ),
                                                                                )}
                                                                            </Pie>
                                                                            <ChartTooltip
                                                                                formatter={(
                                                                                    value: number,
                                                                                    _name: string,
                                                                                    payload: any,
                                                                                ) => {
                                                                                    const item = payload?.payload;
                                                                                    const percent =
                                                                                        Number(
                                                                                            value ||
                                                                                            0,
                                                                                        ) *
                                                                                        100;
                                                                                    return [
                                                                                        `${Number(item?.files || 0).toLocaleString()} 文件 · ${Number(item?.loc || 0).toLocaleString()} 行 · ${percent.toFixed(2)}%`,
                                                                                        item?.name ||
                                                                                        "未知语言",
                                                                                    ];
                                                                                }}
                                                                            />
                                                                        </PieChart>
                                                                    </ResponsiveContainer>
                                                                </div>
                                                                <div className="space-y-2">
                                                                    {parsedLanguageInfo.items.map(
                                                                        (
                                                                            item,
                                                                            index,
                                                                        ) => (
                                                                            <div
                                                                                key={
                                                                                    item.name
                                                                                }
                                                                                className="flex items-center justify-between gap-3 text-xs font-mono bg-muted/60 border border-border rounded px-3 py-2"
                                                                            >
                                                                                <div className="flex items-center gap-2 min-w-0">
                                                                                    <span
                                                                                        className="w-2.5 h-2.5 rounded-full shrink-0"
                                                                                        style={{
                                                                                            backgroundColor:
                                                                                                LANGUAGE_PIE_COLORS[
                                                                                                index %
                                                                                                LANGUAGE_PIE_COLORS.length
                                                                                                ],
                                                                                        }}
                                                                                    />
                                                                                    <span className="text-foreground truncate font-semibold">
                                                                                        {
                                                                                            item.name
                                                                                        }
                                                                                    </span>
                                                                                </div>
                                                                                <span className="text-muted-foreground shrink-0">
                                                                                    {item.files.toLocaleString()} 文件 ·{" "}
                                                                                    {item.loc.toLocaleString()} 行 ·{" "}
                                                                                    {(
                                                                                        item.proportion *
                                                                                        100
                                                                                    ).toFixed(
                                                                                        2,
                                                                                    )}
                                                                                    %
                                                                                </span>
                                                                            </div>
                                                                        ),
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <p className="text-xs text-muted-foreground">
                                                                暂无可展示的语言统计数据
                                                            </p>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <pre className="text-xs text-foreground bg-muted border border-border rounded p-3 whitespace-pre-wrap break-words">
                                                        {
                                                            projectInfo.language_info
                                                        }
                                                    </pre>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="tasks" className="flex flex-col gap-6 mt-6">
                    <ProjectTasksTab
                        unifiedTasks={unifiedTasks}
                        onCreateTask={handleCreateTask}
                        formatDate={formatDate}
                        renderStatusBadge={getStatusBadge}
                        renderStatusIcon={getStatusIcon}
                        getTaskRoute={getTaskDetailRoute}
                    />
                </TabsContent>
            </Tabs>

            {/* 创建任务对话框 */}
            <CreateTaskDialog
                open={showCreateTaskDialog}
                onOpenChange={setShowCreateTaskDialog}
                onTaskCreated={handleTaskCreated}
                preselectedProjectId={id}
            />
        </div>
    );
}
