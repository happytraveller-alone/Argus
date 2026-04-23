import type { AgentTask } from "@/shared/api/agentTasks";
import type { AgentFinding } from "@/shared/api/agentTasks";
import type { BanditScanTask } from "@/shared/api/bandit";
import type { GitleaksScanTask } from "@/shared/api/gitleaks";
import type { PhpstanScanTask } from "@/shared/api/phpstan";
import type { PmdScanTask } from "@/shared/api/pmd";
import type { OpengrepFinding, OpengrepScanTask } from "@/shared/api/opengrep";
import {
  buildBanditSeverityCounts,
  buildGitleaksSeverityCounts,
  buildOpengrepSeverityCounts,
  buildPmdSeverityCounts,
  buildPhpstanSeverityCounts,
  getAgentSeverityCounts,
  getSeverityCountTotal,
  mergeSeverityCounts,
  type SeverityCounts,
} from "@/features/tasks/services/taskActivities";
import {
  buildStaticScanGroups,
  resolveStaticScanGroupStatus,
} from "@/features/tasks/services/staticScanGrouping";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import { buildFindingDetailPath } from "@/shared/utils/findingRoute";

export type ProjectCardTaskKind = "static" | "intelligent";
export type ProjectCardTaskFindingCategory = "static" | "intelligent";

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
  taskCategory: ProjectCardTaskFindingCategory | null;
  supportsFindingsDetail: boolean;
  findingsButtonDisabledReason: string | null;
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
  runningTasks: number;
  totalIssues: number;
  severityBreakdown: ProjectSeverityBreakdown;
}

export interface ProjectFoundIssuesBreakdown {
  staticIssues: number;
  intelligentIssues: number;
  totalIssues: number;
}

export interface ProjectSeverityBreakdown extends SeverityCounts {
  total: number;
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
  source: "static" | "agent";
  taskCategory: ProjectCardTaskFindingCategory;
  title: string;
  cweLabel: string;
  cweTooltip?: string | null;
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

function isRunningStatus(status: string | undefined | null): boolean {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "running" || normalized === "pending";
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

export function getProjectCardSummaryStats(params: {
  projectId: string;
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
  gitleaksTasks?: GitleaksScanTask[];
  banditTasks?: BanditScanTask[];
  phpstanTasks?: PhpstanScanTask[];
  pmdTasks?: PmdScanTask[];
}): ProjectCardSummaryStats {
  const { projectId, agentTasks, opengrepTasks } = params;
  const gitleaksTasks = params.gitleaksTasks || [];
  const banditTasks = params.banditTasks || [];
  const phpstanTasks = params.phpstanTasks || [];
  const pmdTasks = params.pmdTasks || [];

  const projectAgentTasks = agentTasks.filter((task) => task.project_id === projectId);
  const projectOpengrepTasks = opengrepTasks.filter((task) => task.project_id === projectId);
  const projectGitleaksTasks = gitleaksTasks.filter((task) => task.project_id === projectId);
  const projectBanditTasks = banditTasks.filter((task) => task.project_id === projectId);
  const projectPhpstanTasks = phpstanTasks.filter((task) => task.project_id === projectId);
  const projectPmdTasks = pmdTasks.filter((task) => task.project_id === projectId);
  const totalTasks =
    projectAgentTasks.length +
    projectOpengrepTasks.length +
    projectGitleaksTasks.length +
    projectBanditTasks.length +
    projectPhpstanTasks.length +
    projectPmdTasks.length;

  const completedTasks =
    projectAgentTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectOpengrepTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectGitleaksTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectBanditTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectPhpstanTasks.filter((task) => isCompletedStatus(task.status)).length +
    projectPmdTasks.filter((task) => isCompletedStatus(task.status)).length;
  const runningTasks =
    projectAgentTasks.filter((task) => isRunningStatus(task.status)).length +
    projectOpengrepTasks.filter((task) => isRunningStatus(task.status)).length +
    projectGitleaksTasks.filter((task) => isRunningStatus(task.status)).length +
    projectBanditTasks.filter((task) => isRunningStatus(task.status)).length +
    projectPhpstanTasks.filter((task) => isRunningStatus(task.status)).length +
    projectPmdTasks.filter((task) => isRunningStatus(task.status)).length;

  const severityBreakdown = getProjectSeverityBreakdown({
    projectId,
    agentTasks,
    opengrepTasks,
    gitleaksTasks,
    banditTasks,
    phpstanTasks,
    pmdTasks,
  });

  return {
    totalTasks,
    completedTasks,
    runningTasks,
    totalIssues: severityBreakdown.total,
    severityBreakdown,
  };
}

function toProjectSeverityBreakdown(
  counts: SeverityCounts,
): ProjectSeverityBreakdown {
  return {
    ...counts,
    total: getSeverityCountTotal(counts),
  };
}

export function getProjectSeverityBreakdown(params: {
  projectId: string;
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
  gitleaksTasks?: GitleaksScanTask[];
  banditTasks?: BanditScanTask[];
  phpstanTasks?: PhpstanScanTask[];
  pmdTasks?: PmdScanTask[];
}): ProjectSeverityBreakdown {
  const { projectId, agentTasks, opengrepTasks } = params;
  const gitleaksTasks = params.gitleaksTasks || [];
  const banditTasks = params.banditTasks || [];
  const phpstanTasks = params.phpstanTasks || [];
  const pmdTasks = params.pmdTasks || [];

  const staticCounts = mergeSeverityCounts(
    ...opengrepTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => buildOpengrepSeverityCounts(task)),
    ...gitleaksTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => buildGitleaksSeverityCounts(task)),
    ...banditTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => buildBanditSeverityCounts(task)),
    ...phpstanTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => buildPhpstanSeverityCounts(task)),
    ...pmdTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => buildPmdSeverityCounts(task)),
  );

  const agentCounts = mergeSeverityCounts(
    ...agentTasks
      .filter((task) => task.project_id === projectId)
      .map((task) => getAgentSeverityCounts(task)),
  );

  return toProjectSeverityBreakdown(
    mergeSeverityCounts(staticCounts, agentCounts),
  );
}

export function getProjectFoundIssuesBreakdown(params: {
  projectId: string;
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
  gitleaksTasks?: GitleaksScanTask[];
  banditTasks?: BanditScanTask[];
  phpstanTasks?: PhpstanScanTask[];
  pmdTasks?: PmdScanTask[];
}): ProjectFoundIssuesBreakdown {
  const { projectId, agentTasks, opengrepTasks } = params;
  const gitleaksTasks = params.gitleaksTasks || [];
  const banditTasks = params.banditTasks || [];
  const phpstanTasks = params.phpstanTasks || [];
  const pmdTasks = params.pmdTasks || [];

  const staticIssues = getSeverityCountTotal(
    mergeSeverityCounts(
      ...opengrepTasks
        .filter((task) => task.project_id === projectId)
        .map((task) => buildOpengrepSeverityCounts(task)),
      ...gitleaksTasks
        .filter((task) => task.project_id === projectId)
        .map((task) => buildGitleaksSeverityCounts(task)),
      ...banditTasks
        .filter((task) => task.project_id === projectId)
        .map((task) => buildBanditSeverityCounts(task)),
      ...phpstanTasks
        .filter((task) => task.project_id === projectId)
        .map((task) => buildPhpstanSeverityCounts(task)),
      ...pmdTasks
        .filter((task) => task.project_id === projectId)
        .map((task) => buildPmdSeverityCounts(task)),
    ),
  );

  const projectAgentTasks = agentTasks.filter((task) => task.project_id === projectId);

  let intelligentIssues = 0;
  for (const task of projectAgentTasks) {
    const total = getSeverityCountTotal(getAgentSeverityCounts(task));
    intelligentIssues += total;
  }

  return {
    staticIssues,
    intelligentIssues,
    totalIssues: staticIssues + intelligentIssues,
  };
}

export function getProjectCardRecentTasks(params: {
  projectId: string;
  agentTasks: AgentTask[];
  opengrepTasks: OpengrepScanTask[];
  gitleaksTasks: GitleaksScanTask[];
  banditTasks?: BanditScanTask[];
  phpstanTasks?: PhpstanScanTask[];
  pmdTasks?: PmdScanTask[];
  limit?: number;
}): ProjectCardRecentTask[] {
  const { projectId, agentTasks, opengrepTasks, gitleaksTasks } = params;
  const banditTasks = params.banditTasks || [];
  const phpstanTasks = params.phpstanTasks || [];
  const pmdTasks = params.pmdTasks || [];
  const limit = params.limit ?? 3;
  // Multi-engine grouping: a static creation with N engines should render as one recent task item.
  const staticGroups = buildStaticScanGroups({
    opengrepTasks,
    gitleaksTasks,
    banditTasks,
    phpstanTasks,
    pmdTasks,
  }).filter((group) => group.projectId === projectId);

  const staticItems: ProjectCardRecentTask[] = staticGroups
    .map((group): ProjectCardRecentTask | null => {
      const opengrepTask = group.opengrepTask;
      const gitleaksTask = group.gitleaksTask;
      const banditTask = group.banditTask;
      const phpstanTask = group.phpstanTask;
      const pmdTask = group.pmdTask;
      const primaryTask = opengrepTask || gitleaksTask || banditTask || phpstanTask || pmdTask;
      if (!primaryTask) return null;

      const params = new URLSearchParams();
      if (opengrepTask) {
        params.set("opengrepTaskId", opengrepTask.id);
      }
      if (gitleaksTask) {
        params.set("gitleaksTaskId", gitleaksTask.id);
      }
      if (banditTask) {
        params.set("banditTaskId", banditTask.id);
      }
      if (phpstanTask) {
        params.set("phpstanTaskId", phpstanTask.id);
      }
      if (pmdTask) {
        params.set("pmdTaskId", pmdTask.id);
      }
      if (!opengrepTask && gitleaksTask && !banditTask && !phpstanTask && !pmdTask) {
        params.set("tool", "gitleaks");
      }
      if (!opengrepTask && !gitleaksTask && banditTask && !phpstanTask && !pmdTask) {
        params.set("tool", "bandit");
      }
      if (!opengrepTask && !gitleaksTask && !banditTask && phpstanTask && !pmdTask) {
        params.set("tool", "phpstan");
      }
      if (!opengrepTask && !gitleaksTask && !banditTask && !phpstanTask && pmdTask) {
        params.set("tool", "pmd");
      }

      const filesScanned = [
        opengrepTask?.files_scanned,
        gitleaksTask?.files_scanned,
        banditTask?.files_scanned,
        phpstanTask?.files_scanned,
        pmdTask?.files_scanned,
      ].reduce<number | null>((maxValue, value) => {
        const numeric = toNullableNonNegativeNumber(value);
        if (numeric === null) return maxValue;
        if (maxValue === null) return numeric;
        return Math.max(maxValue, numeric);
      }, null);
      const scannedLines = toNullableNonNegativeNumber(opengrepTask?.lines_scanned);
      const vulnerabilities = toNullableNonNegativeNumber(
          Math.max(opengrepTask?.high_confidence_count ?? 0, 0) +
          Math.max(gitleaksTask?.total_findings ?? 0, 0) +
          Math.max(pmdTask?.total_findings ?? 0, 0) +
          Math.max(phpstanTask?.total_findings ?? 0, 0) +
          Math.max(
            banditTask?.total_findings ??
              Math.max(banditTask?.high_count ?? 0, 0) +
                Math.max(banditTask?.medium_count ?? 0, 0) +
                Math.max(banditTask?.low_count ?? 0, 0),
            0,
          ),
      );
      const durationMs = [
        opengrepTask?.scan_duration_ms,
        gitleaksTask?.scan_duration_ms,
        banditTask?.scan_duration_ms,
        phpstanTask?.scan_duration_ms,
        pmdTask?.scan_duration_ms,
      ].reduce<number | null>((sum, value) => {
        const numeric = toNullableNonNegativeNumber(value);
        if (numeric === null || numeric === 0) return sum;
        return (sum ?? 0) + numeric;
      }, null);
      const latestUpdatedAt = [
        opengrepTask,
        gitleaksTask,
        banditTask,
        phpstanTask,
        pmdTask,
      ].reduce<string | null>((latest, task) => {
        const current = task?.updated_at || null;
        if (!current) return latest;
        if (!latest) return current;
        return new Date(current).getTime() > new Date(latest).getTime()
          ? current
          : latest;
      }, null);

      const status = resolveStaticScanGroupStatus(group);
      const item: ProjectCardRecentTask = {
        id: primaryTask.id,
        projectId: group.projectId,
        kind: "static",
        status,
        progressPercent: getStatusProgressBaseline(status),
        createdAt: group.createdAt,
        startedAt: group.createdAt,
        completedAt: status === "running" ? null : latestUpdatedAt,
        durationMs,
        route: `/static-analysis/${primaryTask.id}?${params.toString()}`,
        label: "静态审计",
        scanTypeLabel: "静态审计",
        scannedFiles: filesScanned,
        scannedLines,
        vulnerabilities,
        taskCategory: "static",
        supportsFindingsDetail: true,
        findingsButtonDisabledReason: null,
      };
      return item;
    })
    .filter((item): item is ProjectCardRecentTask => item !== null);

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
      const scanLabel = "智能审计";

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
        taskCategory: "intelligent",
        supportsFindingsDetail: true,
        findingsButtonDisabledReason: null,
      };
    });

  return [...staticItems, ...intelligentItems]
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
  agentTaskCategoryMap?: Record<string, ProjectCardTaskFindingCategory>;
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
      const confidence = toAgentConfidence(
        finding.ai_confidence ?? finding.confidence ?? null,
      );
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
      const cweDisplay = resolveCweDisplay({
        cwe: finding.cwe_id,
        fallbackLabel:
          String(finding.vulnerability_type || "").trim() || title || "潜在漏洞",
      });
      const taskCategory: ProjectCardPotentialVulnerability["taskCategory"] =
        params.agentTaskCategoryMap?.[finding.task_id] === "static"
          ? "static"
          : "intelligent";
      return {
        id: finding.id,
        taskId: finding.task_id,
        source: "agent" as const,
        taskCategory,
        title,
        cweLabel: cweDisplay.label,
        cweTooltip: cweDisplay.tooltip,
        severity,
        confidence,
        filePath,
        line,
        route: buildFindingDetailPath({
          source: "agent",
          taskId: finding.task_id,
          findingId: finding.id,
        }),
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
      const cweDisplay = resolveCweDisplay({
        cwe: finding.cwe,
        fallbackLabel: title,
      });
      return {
        id: finding.id,
        taskId: finding.scan_task_id,
        source: "static" as const,
        taskCategory: "static" as const,
        title,
        cweLabel: cweDisplay.label,
        cweTooltip: cweDisplay.tooltip,
        severity,
        confidence,
        filePath: finding.file_path,
        line,
        route: buildFindingDetailPath({
          source: "static",
          taskId: finding.scan_task_id,
          findingId: finding.id,
        }),
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
      item.source,
      item.taskCategory,
      item.cweLabel,
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
    source: item.source,
    taskCategory: item.taskCategory,
    title: item.title,
    cweLabel: item.cweLabel,
    cweTooltip: item.cweTooltip,
    severity: item.severity,
    confidence: item.confidence,
    filePath: item.filePath,
    line: item.line,
    route: item.route,
  }));
}
