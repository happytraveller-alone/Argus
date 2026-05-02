import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import FindingDetailHeaderActions, {
  type FindingDetailCodeBrowserAction,
} from "@/pages/finding-detail/FindingDetailHeaderActions";
import FindingDetailView from "@/pages/finding-detail/FindingDetailView";
import {
  buildAgentFindingDetailModel,
  buildCodeqlFindingDetailModel,
  getAgentFalsePositiveEvidence,
  buildOpengrepFindingDetailModel,
  isAgentFalsePositiveFinding,
} from "@/pages/finding-detail/viewModel";
import type { AgentFinding } from "@/shared/api/agentTasks";
import {
  getOpengrepFindingContext,
  getCodeqlFindingContext,
  getCodeqlScanFinding,
  getCodeqlScanTask,
  getOpengrepScanFinding,
  getOpengrepScanTask,
  type OpengrepFinding,
  type OpengrepFindingContext,
  type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api as databaseApi } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import {
  buildProjectCodeBrowserRoute,
  isFindingDetailLocationState,
  normalizeReturnToPath,
  resolveFindingDetailBackTarget,
} from "@/shared/utils/findingRoute";
import SilentLoadingState from "@/components/performance/SilentLoadingState";

type FindingSource = "static" | "agent";
type StaticEngine = "opengrep" | "codeql";

function decodePathParam(raw: string | undefined): string {
  try {
    return decodeURIComponent(String(raw || "")).trim();
  } catch {
    return String(raw || "").trim();
  }
}

function resolveFindingSource(raw: string | undefined): FindingSource | null {
  const value = decodePathParam(raw);
  if (value === "static" || value === "agent") return value;
  return null;
}

function resolveStaticEngine(raw: string | null): StaticEngine {
  const value = decodePathParam(raw ?? undefined).toLowerCase();
  if (value === "codeql") return "codeql";
  return "opengrep";
}

function getErrorMessage(error: unknown): string {
  const apiError = error as {
    response?: { status?: number; data?: { detail?: string } };
    message?: string;
  };
  const status = Number(apiError?.response?.status || 0);
  if (status === 404) return "漏洞不存在或已被清理";
  return String(
    apiError?.response?.data?.detail ||
      apiError?.message ||
      "漏洞详情加载失败，请稍后重试",
  );
}

function FindingDetailShell({
  title,
  onBack,
  children,
  codeBrowserAction,
}: {
  title: string;
  onBack: () => void;
  children: ReactNode;
  codeBrowserAction?: FindingDetailCodeBrowserAction | null;
}) {
  return (
    <div className="min-h-screen bg-background p-4 sm:p-6 flex flex-col gap-4 sm:gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[0.08em] text-foreground">{title}</h1>
        <FindingDetailHeaderActions codeBrowserAction={codeBrowserAction} onBack={onBack} />
      </div>
      {children}
    </div>
  );
}

export default function FindingDetail() {
  const { source: sourceParam, taskId: rawTaskId, findingId: rawFindingId } = useParams<{
    source: string;
    taskId: string;
    findingId: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();

  const source = useMemo(() => resolveFindingSource(sourceParam), [sourceParam]);
  const taskId = useMemo(() => decodePathParam(rawTaskId), [rawTaskId]);
  const findingId = useMemo(() => decodePathParam(rawFindingId), [rawFindingId]);
  const staticEngine = useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    return resolveStaticEngine(searchParams.get("engine"));
  }, [location.search]);
  const returnTo = useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    return normalizeReturnToPath(searchParams.get("returnTo"));
  }, [location.search]);
  const routeState = useMemo(
    () => (isFindingDetailLocationState(location.state) ? location.state : null),
    [location.state],
  );
  const agentFindingSnapshot = useMemo(() => {
    if (source !== "agent") return null;
    return routeState?.agentFindingSnapshot ?? null;
  }, [routeState, source]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [staticTask, setStaticTask] = useState<OpengrepScanTask | null>(null);
  const [staticFinding, setStaticFinding] = useState<OpengrepFinding | null>(null);
  const [staticContext, setStaticContext] = useState<OpengrepFindingContext | null>(null);
  const [agentFinding, setAgentFinding] = useState<AgentFinding | null>(null);
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!source || !taskId || !findingId) {
        setError("漏洞参数无效");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      setStaticTask(null);
      setStaticFinding(null);
      setStaticContext(null);
      setAgentFinding(null);
      setProject(null);

      try {
        if (source === "static") {
          if (staticEngine === "codeql") {
            const [task, finding, context] = await Promise.all([
              getCodeqlScanTask(taskId),
              getCodeqlScanFinding({ taskId, findingId }),
              getCodeqlFindingContext({
                taskId,
                findingId,
                before: 5,
                after: 5,
              }),
            ]);
            if (cancelled) return;
            setStaticTask(task);
            setStaticFinding(finding);
            setStaticContext(context);
            const nextProject = await databaseApi.getProjectById(task.project_id);
            if (cancelled) return;
            setProject(nextProject);
          } else {
            const [task, finding, context] = await Promise.all([
              getOpengrepScanTask(taskId),
              getOpengrepScanFinding({ taskId, findingId }),
              getOpengrepFindingContext({
                taskId,
                findingId,
                before: 5,
                after: 5,
              }),
            ]);
            if (cancelled) return;
            setStaticTask(task);
            setStaticFinding(finding);
            setStaticContext(context);
            const nextProject = await databaseApi.getProjectById(task.project_id);
            if (cancelled) return;
            setProject(nextProject);
          }
        } else if (agentFindingSnapshot) {
          setAgentFinding(agentFindingSnapshot);
        } else {
          setError("智能审计详情接口已退役，仅支持从历史任务列表携带快照打开。");
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(getErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [agentFindingSnapshot, findingId, source, staticEngine, taskId]);

  const model = useMemo(() => {
    if (source === "agent" && agentFinding) {
      return buildAgentFindingDetailModel({
        finding: agentFinding,
        taskId,
        findingId,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    if (source === "static" && staticEngine === "opengrep" && staticFinding) {
      return buildOpengrepFindingDetailModel({
        finding: staticFinding,
        taskId,
        findingId,
        taskName: staticTask?.name,
        context: staticContext,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    if (source === "static" && staticEngine === "codeql" && staticFinding) {
      return buildCodeqlFindingDetailModel({
        finding: staticFinding,
        taskId,
        findingId,
        taskName: staticTask?.name,
        context: staticContext,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    return null;
  }, [
    agentFinding,
    findingId,
    project?.id,
    project?.name,
    project?.source_type,
    source,
    staticContext,
    staticEngine,
    staticFinding,
    staticTask?.name,
    taskId,
  ]);

  const codeBrowserAction = useMemo<FindingDetailCodeBrowserAction>(() => {
    const label = "代码浏览";
    if (loading) {
      return { label, disabledReason: "正在加载项目数据..." };
    }
    if (!project) {
      return { label, disabledReason: "当前漏洞未关联项目" };
    }
    if (!project.id) {
      return { label, disabledReason: "项目信息缺失，暂无法跳转" };
    }
    if (project.source_type !== "zip") {
      return { label, disabledReason: "仅 ZIP 类型项目支持代码浏览" };
    }

    const targetFilePath = model?.codeBrowserTarget?.filePath ?? null;
    if (!targetFilePath) {
      return { label, disabledReason: "当前漏洞未提供可定位的文件路径" };
    }

    return {
      label,
      to: buildProjectCodeBrowserRoute({
        projectId: project.id,
        filePath: targetFilePath,
        line: model?.codeBrowserTarget?.line ?? null,
      }),
      state: {
        from: `${location.pathname}${location.search}`,
      },
    };
  }, [loading, location.pathname, location.search, model, project]);

  const handleBack = () => {
    const target = resolveFindingDetailBackTarget({
      returnTo,
      hasHistory: typeof window !== "undefined" && window.history.length > 1,
      state: location.state,
    });
    if (target === -1) {
      navigate(-1);
      return;
    }
    navigate(target);
  };

  const handleLoadFullFile = async (request: { projectId: string; filePath: string }) => {
    const response = await databaseApi.getProjectFileContent(request.projectId, request.filePath);
    return {
      content: response.content,
      isText: response.is_text,
    };
  };

  const fallbackTitle =
    source === "agent" && isAgentFalsePositiveFinding(agentFinding ?? agentFindingSnapshot)
      ? "误报判定依据"
      : "统一漏洞详情";

  if (loading) {
    return (
      <FindingDetailShell
        title={fallbackTitle}
        onBack={handleBack}
        codeBrowserAction={codeBrowserAction}
      >
        <SilentLoadingState className="rounded-[24px]" minHeight={240} />
      </FindingDetailShell>
    );
  }

  if (error) {
    return (
      <FindingDetailShell
        title={fallbackTitle}
        onBack={handleBack}
        codeBrowserAction={codeBrowserAction}
      >
        <div className="rounded-[24px] border border-rose-500/30 bg-rose-500/5 p-8 text-base text-rose-500 shadow-sm">
          {error}
        </div>
      </FindingDetailShell>
    );
  }

  if (!model) {
    return (
      <FindingDetailShell
        title={fallbackTitle}
        onBack={handleBack}
        codeBrowserAction={codeBrowserAction}
      >
        <div className="rounded-[24px] border border-border/70 bg-background p-8 text-base text-muted-foreground shadow-sm">
          {source === "agent" && isAgentFalsePositiveFinding(agentFindingSnapshot)
            ? getAgentFalsePositiveEvidence(agentFindingSnapshot)
            : "暂无漏洞信息"}
        </div>
      </FindingDetailShell>
    );
  }

  return (
    <FindingDetailView
      model={model}
      onBack={handleBack}
      codeBrowserAction={codeBrowserAction}
      onLoadFullFile={handleLoadFullFile}
    />
  );
}
