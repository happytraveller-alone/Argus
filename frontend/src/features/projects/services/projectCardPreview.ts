import type { AgentTask } from "@/shared/api/agentTasks";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { OpengrepFinding, OpengrepScanTask } from "@/shared/api/opengrep";
import type { AuditTask } from "@/shared/types";
import { resolveSourceModeFromTaskMeta } from "@/features/tasks/services/taskActivities";

const STATIC_GITLEAKS_PAIRING_WINDOW_MS = 60 * 1000;

export type ProjectCardTaskKind = "static" | "intelligent" | "audit";

export interface ProjectCardRecentTask {
  id: string;
  projectId: string;
  kind: ProjectCardTaskKind;
  status: string;
  progressPercent: number;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  durationMs?: number | null;
  route: string;
  label: string;
  scanTypeLabel: string;
  scannedFiles: number | null;
  scannedLines: number | null;
  vulnerabilities: number | null;
}

export interface ProjectCardLanguageSlice {
  name: string;
  proportion: number;
  loc: number;
  files: number;
}

export interface ProjectCardLanguageStats {
  status: "loading" | "pending" | "failed" | "unsupported" | "empty" | "ready";
  total: number;
  totalFiles: number;
  slices: ProjectCardLanguageSlice[];
}

export interface ProjectCardSummaryStats {
  totalTasks: number;
  completedTasks: number;
  totalIssues: number;
}

export interface ProjectFoundIssuesBreakdown {
  staticIssues: number;
  intelligentIssues: number;
  hybridIssues: number;
  totalIssues: number;
}

export type ProjectCardVulnerabilitySeverity =
  | "CRITICAL"
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "UNKNOWN";

export type ProjectCardVulnerabilityConfidence =
  | "HIGH"
  | "MEDIUM"
  | "LOW"
  | "UNKNOWN";

export interface ProjectCardPotentialVulnerability {
  id: string;
  taskId: string;
  title: string;
  severity: ProjectCardVulnerabilitySeverity;
  confidence: ProjectCardVulnerabilityConfidence;
  filePath: string;
  line: number | null;
  route: string;
}

type ProjectInfoPayload = {
  status?: string;
  language_info?: unknown;
} | null;

function toFiniteNumber(value: unknown): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function parseLanguageInfo(raw: unknown): {
  total: number;
  totalFiles: number;
  slices: ProjectCardLanguageSlice[];
} | null {
  if (!raw) return null;

  let parsed: unknown = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return null;
    }
  }

  if (!parsed || typeof parsed !== "object") return null;

  const parsedObject = parsed as {
    total?: unknown;
    total_files?: unknown;
    languages?: unknown;
  };

  const total = toFiniteNumber(parsedObject.total);
  const totalFiles = toFiniteNumber(parsedObject.total_files);
  const languages =
    parsedObject.languages && typeof parsedObject.languages === "object"
      ? (parsedObject.languages as Record<string, unknown>)
      : {};

  const slices = Object.entries(languages)
    .map(([name, info]) => {
      const payload = info as {
        proportion?: unknown;
        loc_number?: unknown;
        files_count?: unknown;
        file_count?: unknown;
      };

      return {
        name,
        proportion: toFiniteNumber(payload.proportion),
        loc: toFiniteNumber(payload.loc_number),
        files: toFiniteNumber(payload.files_count ?? payload.file_count),
      };
    })
    .filter((item) => item.name && item.proportion > 0)
    .sort((a, b) => b.proportion - a.proportion);

  return { total, totalFiles, slices };
}

export function normalizeProjectCardLanguageStats(
  projectInfo: ProjectInfoPayload,
): ProjectCardLanguageStats {
  if (!projectInfo) {
    return { status: "pending", total: 0, totalFiles: 0, slices: [] };
  }

  const rawStatus = String(projectInfo.status || "").toLowerCase();
  if (rawStatus === "unsupported") {
    return { status: "unsupported", total: 0, totalFiles: 0, slices: [] };
  }
  if (rawStatus === "loading" || rawStatus === "pending") {
    return { status: "pending", total: 0, totalFiles: 0, slices: [] };
  }
  if (rawStatus === "failed") {
    return { status: "failed", total: 0, totalFiles: 0, slices: [] };
  }

  const parsed = parseLanguageInfo(projectInfo.language_info);
  if (!parsed || parsed.slices.length === 0) {
    return {
      status: "empty",
      total: parsed?.total ?? 0,
      totalFiles: parsed?.totalFiles ?? 0,
      slices: [],
    };
  }

  return {
    status: "ready",
    total: parsed.total,
    totalFiles: parsed.totalFiles,
    slices: parsed.slices,
  };
}

function isCompletedStatus(status: string | undefined | null): boolean {
  return String(status || "").trim().toLowerCase() === "completed";
}

function toNullableNonNegativeNumber(value: unknown): number | null {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return null;
  return num;
}

function normalizeStatus(status: string | undefined | null): string {
  return String(status || "").trim().toLowerCase();
}

function clampPercent(value: unknown): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  if (num <= 0) return 0;
  if (num >= 100) return 100;
  return num;
}

function computeDurationMs(
  startedAt: string | null | undefined,
  completedAt: string | null | undefined,
): number | null {
  if (!startedAt || !completedAt) return null;
  const startedMs = new Date(startedAt).getTime();
  const completedMs = new Date(completedAt).getTime();
  if (!Number.isFinite(startedMs) || !Number.isFinite(completedMs)) return null;
  const diff = completedMs - startedMs;
  if (!Number.isFinite(diff) || diff < 0) return null;
  return diff;
}

function getStatusProgressBaseline(status: string | undefined | null): number {
  const normalized = normalizeStatus(status);
  if (normalized === "completed") return 100;
  if (normalized === "running") return 60;
  if (normalized === "pending") return 0;
  if (
    normalized === "failed" ||
    normalized === "cancelled" ||
    normalized === "interrupted" ||
    normalized === "aborted"
  ) {
    return 0;
  }
  return 0;
}

function computeAuditProgressPercent(task: AuditTask): number {
  const totalFiles = Number(task.total_files);
  const scannedFiles = Number(task.scanned_files);
  if (
    Number.isFinite(totalFiles) &&
    totalFiles > 0 &&
    Number.isFinite(scannedFiles) &&
    scannedFiles >= 0
  ) {
    return clampPercent((scannedFiles / totalFiles) * 100);
  }
  return getStatusProgressBaseline(task.status);
}

export function getProjectCardSummaryStats(params: {
  projectId: string;
  auditTasks: AuditTask[];
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
}): ProjectCardSummaryStats {
  const { projectId, auditTasks, agentTasks, opengrepTasks } = params;

  const projectAuditTasks = auditTasks.filter((task) => task.project_id === projectId);
  const projectAgentTasks = agentTasks.filter((task) => task.project_id === projectId);
  const projectOpengrepTasks = opengrepTasks.filter((task) => task.project_id === projectId);

  const totalTasks =
    projectAuditTasks.length +
    projectAgentTasks.length +
    projectOpengrepTasks.length;

  const completedTasks =
    projectAuditTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectAgentTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectOpengrepTasks.filter((task) => isCompletedStatus(task.status)).length;

  const issueBreakdown = getProjectFoundIssuesBreakdown({
    projectId,
    agentTasks,
    opengrepTasks,
  });

  return {
    totalTasks,
    completedTasks,
    totalIssues: issueBreakdown.totalIssues,
  };
}

export function getProjectFoundIssuesBreakdown(params: {
  projectId: string;
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
}): ProjectFoundIssuesBreakdown {
  const { projectId, agentTasks, opengrepTasks } = params;

  const staticIssues = opengrepTasks
    .filter((task) => task.project_id === projectId)
    .reduce(
      (sum, task) =>
        sum + Math.max(Number(task.high_confidence_count ?? 0), 0),
      0,
    );

  const projectAgentTasks = agentTasks.filter((task) => task.project_id === projectId);

  let intelligentIssues = 0;
  let hybridIssues = 0;
  for (const task of projectAgentTasks) {
    const verified = Math.max(Number(task.verified_count ?? 0), 0);
    const sourceMode = resolveSourceModeFromTaskMeta(
      "intelligent_audit",
      task.name,
      task.description,
    );
    if (sourceMode === "intelligent") {
      intelligentIssues += verified;
    } else {
      hybridIssues += verified;
    }
  }

  return {
    staticIssues,
    intelligentIssues,
    hybridIssues,
    totalIssues: staticIssues + intelligentIssues + hybridIssues,
  };
}

function buildStaticRouteMap(
  opengrepTasks: OpengrepScanTask[],
  gitleaksTasks: GitleaksScanTask[],
): Map<string, string> {
  const gitleaksByProject = new Map<string, GitleaksScanTask[]>();
  for (const task of gitleaksTasks) {
    const list = gitleaksByProject.get(task.project_id) || [];
    list.push(task);
    gitleaksByProject.set(task.project_id, list);
  }

  for (const [projectId, list] of gitleaksByProject.entries()) {
    list.sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
    gitleaksByProject.set(projectId, list);
  }

  const usedGitleaksTaskIds = new Set<string>();

  const pickPairedGitleaksTask = (opengrepTask: OpengrepScanTask) => {
    const candidates = gitleaksByProject.get(opengrepTask.project_id) || [];
    const opengrepTime = new Date(opengrepTask.created_at).getTime();
    let bestTask: GitleaksScanTask | null = null;
    let bestDiff = Number.POSITIVE_INFINITY;

    for (const candidate of candidates) {
      if (usedGitleaksTaskIds.has(candidate.id)) continue;
      const diff = Math.abs(
        new Date(candidate.created_at).getTime() - opengrepTime,
      );
      if (diff <= STATIC_GITLEAKS_PAIRING_WINDOW_MS && diff < bestDiff) {
        bestTask = candidate;
        bestDiff = diff;
      }
    }

    if (bestTask) {
      usedGitleaksTaskIds.add(bestTask.id);
    }

    return bestTask;
  };

  const routeMap = new Map<string, string>();
  for (const opengrepTask of opengrepTasks) {
    const params = new URLSearchParams();
    params.set("opengrepTaskId", opengrepTask.id);

    const pairedGitleaksTask = pickPairedGitleaksTask(opengrepTask);
    if (pairedGitleaksTask) {
      params.set("gitleaksTaskId", pairedGitleaksTask.id);
    }
    routeMap.set(
      opengrepTask.id,
      `/static-analysis/${opengrepTask.id}?${params.toString()}`,
    );
  }

  return routeMap;
}

export function getProjectCardRecentTasks(params: {
  projectId: string;
  auditTasks: AuditTask[];
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
  gitleaksTasks: GitleaksScanTask[];
  limit?: number;
}): ProjectCardRecentTask[] {
  const { projectId, auditTasks, agentTasks, opengrepTasks, gitleaksTasks } =
    params;
  const limit = params.limit ?? 3;
  const staticRouteMap = buildStaticRouteMap(opengrepTasks, gitleaksTasks);
  const gitleaksById = new Map(gitleaksTasks.map((task) => [task.id, task]));

  const staticItems: ProjectCardRecentTask[] = opengrepTasks
    .filter((task) => task.project_id === projectId)
    .map((task) => {
      const staticRoute = staticRouteMap.get(task.id) || `/static-analysis/${task.id}`;
      const query = staticRoute.split("?")[1] || "";
      const pairedGitleaksTaskId = new URLSearchParams(query).get("gitleaksTaskId");
      const pairedGitleaksTask = pairedGitleaksTaskId
        ? gitleaksById.get(pairedGitleaksTaskId)
        : null;
      const durationCandidates = [task.scan_duration_ms, pairedGitleaksTask?.scan_duration_ms];
      const durationMs = durationCandidates.reduce<number | null>((total, value) => {
        if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
          return total;
        }
        return (total ?? 0) + value;
      }, null);

      return {
        id: task.id,
        projectId: task.project_id,
        kind: "static",
        status: task.status,
        progressPercent: getStatusProgressBaseline(task.status),
        createdAt: task.created_at,
        startedAt: task.created_at,
        completedAt: task.updated_at ?? null,
        durationMs,
        route: staticRoute,
        label: "静态扫描",
        scanTypeLabel: "静态扫描",
        scannedFiles: toNullableNonNegativeNumber(task.files_scanned),
        scannedLines: toNullableNonNegativeNumber(task.lines_scanned),
        vulnerabilities: toNullableNonNegativeNumber(task.high_confidence_count ?? 0),
      };
    });

  const intelligentItems: ProjectCardRecentTask[] = agentTasks
    .filter((task) => task.project_id === projectId)
    .map((task) => {
      const dynamicTask = task as AgentTask & {
        lines_scanned?: number | null;
        total_lines?: number | null;
        scanned_files?: number | null;
      };

      const analyzedFiles = toNullableNonNegativeNumber(task.analyzed_files);
      const totalFiles = toNullableNonNegativeNumber(task.total_files);
      const sourceMode = resolveSourceModeFromTaskMeta(
        "intelligent_audit",
        task.name,
        task.description,
      );
      const scanLabel = sourceMode === "hybrid" ? "混合扫描" : "智能扫描";

      return {
        id: task.id,
        projectId: task.project_id,
        kind: "intelligent",
        status: task.status,
        progressPercent: clampPercent(
          task.progress_percentage ?? getStatusProgressBaseline(task.status),
        ),
        createdAt: task.created_at,
        startedAt: task.started_at,
        completedAt: task.completed_at,
        durationMs: computeDurationMs(task.started_at, task.completed_at),
        route: `/agent-audit/${task.id}`,
        label: scanLabel,
        scanTypeLabel: scanLabel,
        scannedFiles:
          analyzedFiles !== null && analyzedFiles > 0
            ? analyzedFiles
            : (analyzedFiles ?? totalFiles ?? toNullableNonNegativeNumber(dynamicTask.scanned_files)),
        scannedLines: toNullableNonNegativeNumber(
          dynamicTask.lines_scanned ?? dynamicTask.total_lines,
        ),
        vulnerabilities: toNullableNonNegativeNumber(task.verified_count),
      };
    });

  const auditItems: ProjectCardRecentTask[] = auditTasks
    .filter((task) => task.project_id === projectId)
    .map((task) => ({
      id: task.id,
      projectId: task.project_id,
      kind: "audit",
      status: task.status,
      progressPercent: computeAuditProgressPercent(task),
      createdAt: task.created_at,
      startedAt: task.started_at ?? null,
      completedAt: task.completed_at ?? null,
      durationMs: computeDurationMs(task.started_at, task.completed_at),
      route: `/tasks/${task.id}`,
      label: task.task_type === "instant" ? "即时分析" : "审计任务",
      scanTypeLabel: "审计任务",
      scannedFiles: toNullableNonNegativeNumber(task.scanned_files ?? task.total_files),
      scannedLines: toNullableNonNegativeNumber(task.total_lines),
      vulnerabilities: toNullableNonNegativeNumber(task.issues_count),
    }));

  return [...staticItems, ...intelligentItems, ...auditItems]
    .sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    )
    .slice(0, limit);
}

function normalizeVulnerabilitySeverity(
  severity: string | null | undefined,
): ProjectCardVulnerabilitySeverity {
  const normalized = String(severity || "").trim().toUpperCase();
  if (normalized.includes("CRITICAL")) return "CRITICAL";
  if (normalized.includes("HIGH") || normalized === "ERROR") return "HIGH";
  if (normalized.includes("MEDIUM") || normalized === "WARNING") return "MEDIUM";
  if (normalized.includes("LOW") || normalized === "INFO") return "LOW";
  return "UNKNOWN";
}

function normalizeVulnerabilityConfidence(
  confidence: string | null | undefined,
): ProjectCardVulnerabilityConfidence {
  const normalized = String(confidence || "").trim().toUpperCase();
  if (normalized === "HIGH") return "HIGH";
  if (normalized === "MEDIUM") return "MEDIUM";
  if (normalized === "LOW") return "LOW";
  return "UNKNOWN";
}

function severityRank(severity: ProjectCardVulnerabilitySeverity): number {
  if (severity === "CRITICAL") return 5;
  if (severity === "HIGH") return 4;
  if (severity === "MEDIUM") return 3;
  if (severity === "LOW") return 2;
  return 1;
}

function confidenceRank(confidence: ProjectCardVulnerabilityConfidence): number {
  if (confidence === "HIGH") return 3;
  if (confidence === "MEDIUM") return 2;
  if (confidence === "LOW") return 1;
  return 0;
}

export function getProjectCardPotentialVulnerabilities(params: {
  opengrepFindings?: OpengrepFinding[];
  verifiedAgentFindings?: AgentFinding[];
  limit?: number;
}): ProjectCardPotentialVulnerability[] {
  const limit = params.limit ?? 5;
  const toNormalizedTimestamp = (value: string | null | undefined): number => {
    const ts = new Date(String(value || "")).getTime();
    return Number.isFinite(ts) ? ts : 0;
  };

  const toAgentConfidence = (
    value: number | null | undefined,
  ): ProjectCardVulnerabilityConfidence => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "UNKNOWN";
    if (value >= 0.8) return "HIGH";
    if (value >= 0.5) return "MEDIUM";
    if (value > 0) return "LOW";
    return "UNKNOWN";
  };

  type RankedCandidate = ProjectCardPotentialVulnerability & {
    groupPriority: 1 | 2;
    sortTime: number;
  };

  const rankedCandidates: RankedCandidate[] = [];
  const deduped = new Set<string>();

  const agentCandidates = (params.verifiedAgentFindings || [])
    .map((finding) => {
      const severity = normalizeVulnerabilitySeverity(finding.severity);
      const confidence = toAgentConfidence(finding.ai_confidence);
      const line =
        typeof finding.line_start === "number" && Number.isFinite(finding.line_start)
          ? finding.line_start
          : null;
      const title =
        String(finding.display_title || "").trim() ||
        String(finding.title || "").trim() ||
        String(finding.vulnerability_type || "").trim() ||
        String(finding.description || "").trim() ||
        "潜在漏洞";
      const filePath = String(finding.file_path || "").trim() || "-";
      return {
        id: finding.id,
        taskId: finding.task_id,
        title,
        severity,
        confidence,
        filePath,
        line,
        route: `/agent-audit/${finding.task_id}?detailType=finding&detailId=${finding.id}`,
        groupPriority: 1 as const,
        sortTime: toNormalizedTimestamp(finding.created_at),
      };
    })
    .filter((item) => item.severity === "CRITICAL" || item.severity === "HIGH")
    .sort((a, b) => {
      const bySeverity = severityRank(b.severity) - severityRank(a.severity);
      if (bySeverity !== 0) return bySeverity;
      const byConfidence = confidenceRank(b.confidence) - confidenceRank(a.confidence);
      if (byConfidence !== 0) return byConfidence;
      return b.sortTime - a.sortTime;
    });

  const staticCandidates = (params.opengrepFindings || [])
    .map((finding) => {
      const severity = normalizeVulnerabilitySeverity(finding.severity);
      const confidence = normalizeVulnerabilityConfidence(finding.confidence);
      const line =
        typeof finding.start_line === "number" && Number.isFinite(finding.start_line)
          ? finding.start_line
          : null;
      const title =
        String(finding.rule_name || "").trim() ||
        String(finding.description || "").trim() ||
        "潜在漏洞";
      return {
        id: finding.id,
        taskId: finding.scan_task_id,
        title,
        severity,
        confidence,
        filePath: finding.file_path,
        line,
        route: `/static-analysis/${finding.scan_task_id}?opengrepTaskId=${finding.scan_task_id}`,
        groupPriority: 2 as const,
        sortTime: 0,
      };
    })
    .filter((item) => item.confidence === "HIGH")
    .sort((a, b) => {
      const bySeverity = severityRank(b.severity) - severityRank(a.severity);
      if (bySeverity !== 0) return bySeverity;
      return a.filePath.localeCompare(b.filePath, "zh-CN");
    });

  for (const item of [...agentCandidates, ...staticCandidates]) {
    const dedupeKey = [
      item.groupPriority,
      item.taskId,
      item.filePath,
      item.line ?? "",
      item.title,
      item.severity,
      item.confidence,
    ].join("|");
    if (deduped.has(dedupeKey)) continue;
    deduped.add(dedupeKey);
    rankedCandidates.push(item);
    if (rankedCandidates.length >= limit) break;
  }

  return rankedCandidates.map((item) => ({
    id: item.id,
    taskId: item.taskId,
    title: item.title,
    severity: item.severity,
    confidence: item.confidence,
    filePath: item.filePath,
    line: item.line,
    route: item.route,
  }));
}
