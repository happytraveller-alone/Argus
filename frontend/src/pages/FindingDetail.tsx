import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import FindingDetailView from "@/pages/finding-detail/FindingDetailView";
import {
  buildAgentFindingDetailModel,
  buildBanditFindingDetailModel,
  buildGitleaksFindingDetailModel,
  buildOpengrepFindingDetailModel,
  buildPhpstanFindingDetailModel,
  getAgentFalsePositiveEvidence,
  isAgentFalsePositiveFinding,
} from "@/pages/finding-detail/viewModel";
import {
  getAgentFinding,
  getAgentTask,
  type AgentFinding,
} from "@/shared/api/agentTasks";
import {
  getBanditFinding,
  getBanditScanTask,
  type BanditFinding,
  type BanditScanTask,
} from "@/shared/api/bandit";
import {
  getGitleaksFinding,
  getGitleaksScanTask,
  type GitleaksFinding,
  type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import {
  getPhpstanFinding,
  getPhpstanScanTask,
  type PhpstanFinding,
  type PhpstanScanTask,
} from "@/shared/api/phpstan";
import {
  getOpengrepFindingContext,
  getOpengrepScanFinding,
  getOpengrepScanTask,
  type OpengrepFinding,
  type OpengrepFindingContext,
  type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api as databaseApi } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import {
  isFindingDetailLocationState,
  normalizeReturnToPath,
  resolveFindingDetailBackTarget,
} from "@/shared/utils/findingRoute";

type FindingSource = "static" | "agent";
type StaticEngine = "opengrep" | "gitleaks" | "bandit" | "phpstan";

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
  if (value === "gitleaks") return "gitleaks";
  if (value === "bandit") return "bandit";
  if (value === "phpstan") return "phpstan";
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

function getErrorStatus(error: unknown): number {
  const apiError = error as {
    response?: { status?: number };
  };
  return Number(apiError?.response?.status || 0);
}

function FindingDetailShell({
  title,
  onBack,
  children,
}: {
  title: string;
  onBack: () => void;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background p-4 sm:p-6 flex flex-col gap-4 sm:gap-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[0.08em] text-foreground">{title}</h1>
        <Button variant="outline" className="cyber-btn-outline" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          返回
        </Button>
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
  const [gitleaksTask, setGitleaksTask] = useState<GitleaksScanTask | null>(null);
  const [gitleaksFinding, setGitleaksFinding] = useState<GitleaksFinding | null>(null);
  const [banditTask, setBanditTask] = useState<BanditScanTask | null>(null);
  const [banditFinding, setBanditFinding] = useState<BanditFinding | null>(null);
  const [phpstanTask, setPhpstanTask] = useState<PhpstanScanTask | null>(null);
  const [phpstanFinding, setPhpstanFinding] = useState<PhpstanFinding | null>(null);
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
      setGitleaksTask(null);
      setGitleaksFinding(null);
      setBanditTask(null);
      setBanditFinding(null);
      setPhpstanTask(null);
      setPhpstanFinding(null);
      setAgentFinding(null);
      setProject(null);

      try {
        if (source === "static") {
          if (staticEngine === "gitleaks") {
            const [task, finding] = await Promise.all([
              getGitleaksScanTask(taskId),
              getGitleaksFinding({ taskId, findingId }),
            ]);
            if (cancelled) return;
            setGitleaksTask(task);
            setGitleaksFinding(finding);
            const nextProject = await databaseApi.getProjectById(task.project_id);
            if (cancelled) return;
            setProject(nextProject);
          } else if (staticEngine === "bandit") {
            const [task, finding] = await Promise.all([
              getBanditScanTask(taskId),
              getBanditFinding({ taskId, findingId }),
            ]);
            if (cancelled) return;
            setBanditTask(task);
            setBanditFinding(finding);
            const nextProject = await databaseApi.getProjectById(task.project_id);
            if (cancelled) return;
            setProject(nextProject);
          } else if (staticEngine === "phpstan") {
            // PHPStan integration: static finding detail fetch path.
            const [task, finding] = await Promise.all([
              getPhpstanScanTask(taskId),
              getPhpstanFinding({ taskId, findingId }),
            ]);
            if (cancelled) return;
            setPhpstanTask(task);
            setPhpstanFinding(finding);
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
        } else {
          try {
            const agentTask = await getAgentTask(taskId);
            if (cancelled) return;
            const nextProject = await databaseApi.getProjectById(agentTask.project_id);
            if (cancelled) return;
            setProject(nextProject);
          } catch {
            if (!cancelled) {
              setProject(null);
            }
          }
          const canUseSnapshot =
            agentFindingSnapshot && isAgentFalsePositiveFinding(agentFindingSnapshot);
          const retryDelaysMs = canUseSnapshot ? [0, 1200, 2400] : [0];
          let resolved = false;

          for (let attempt = 0; attempt < retryDelaysMs.length; attempt += 1) {
            if (attempt > 0) {
              await new Promise((resolve) =>
                window.setTimeout(resolve, retryDelaysMs[attempt]),
              );
              if (cancelled) return;
            }

            try {
              const finding = await getAgentFinding(taskId, findingId, {
                include_false_positive: true,
              });
              if (cancelled) return;
              setAgentFinding(finding);
              setError("");
              resolved = true;
              break;
            } catch (agentLoadError) {
              const status = getErrorStatus(agentLoadError);
              if (status === 404 && canUseSnapshot) {
                setAgentFinding(agentFindingSnapshot);
                setError("");
                setLoading(false);
                continue;
              }
              throw agentLoadError;
            }
          }

          if (!resolved && canUseSnapshot) {
            if (cancelled) return;
            setAgentFinding(agentFindingSnapshot);
          }
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

    if (source === "static" && staticEngine === "gitleaks" && gitleaksFinding) {
      return buildGitleaksFindingDetailModel({
        finding: gitleaksFinding,
        taskId,
        findingId,
        taskName: gitleaksTask?.name,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    if (source === "static" && staticEngine === "bandit" && banditFinding) {
      return buildBanditFindingDetailModel({
        finding: banditFinding,
        taskId,
        findingId,
        taskName: banditTask?.name,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    if (source === "static" && staticEngine === "phpstan" && phpstanFinding) {
      return buildPhpstanFindingDetailModel({
        finding: phpstanFinding,
        taskId,
        findingId,
        taskName: phpstanTask?.name,
        projectId: project?.id,
        projectSourceType: project?.source_type,
        projectName: project?.name,
      });
    }

    return null;
  }, [
    agentFinding,
    banditFinding,
    banditTask?.name,
    findingId,
    gitleaksFinding,
    gitleaksTask?.name,
    phpstanFinding,
    phpstanTask?.name,
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
      <FindingDetailShell title={fallbackTitle} onBack={handleBack}>
        <div className="cyber-card p-8 text-base text-muted-foreground">漏洞详情加载中...</div>
      </FindingDetailShell>
    );
  }

  if (error) {
    return (
      <FindingDetailShell title={fallbackTitle} onBack={handleBack}>
        <div className="cyber-card p-8 text-base text-rose-400">{error}</div>
      </FindingDetailShell>
    );
  }

  if (!model) {
    return (
      <FindingDetailShell title={fallbackTitle} onBack={handleBack}>
        <div className="cyber-card p-8 text-base text-muted-foreground">
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
      onLoadFullFile={handleLoadFullFile}
    />
  );
}
