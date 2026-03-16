import { type AgentTask, getAgentTasks } from "@/shared/api/agentTasks";
import {
	type GitleaksScanTask,
	getGitleaksScanTasks,
} from "@/shared/api/gitleaks";
import {
	type BanditScanTask,
	getBanditScanTasks,
} from "@/shared/api/bandit";
import {
	type PhpstanScanTask,
	getPhpstanScanTasks,
} from "@/shared/api/phpstan";
import {
	getOpengrepScanTasks,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import type { Project } from "@/shared/types";
import {
	getEstimatedTaskProgressPercent,
	INTERRUPTED_STATUSES,
} from "./taskProgress";
import {
	buildStaticScanGroups,
	resolveStaticScanGroupStatus,
} from "./staticScanGrouping";

export {
	buildStaticScanGroups,
	resolveStaticScanGroupStatus,
	type StaticScanGroup,
	type StaticScanGroupStatus,
} from "./staticScanGrouping";

export type TaskActivityKind = "rule_scan" | "intelligent_audit";
export type TaskActivitySourceMode =
	| "static"
	| "intelligent"
	| "hybrid"
	| "unknown";

export const HYBRID_TASK_NAME_MARKER = "[HYBRID]";
export const INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]";

type StaticSeverityCounts = {
	critical: number;
	high: number;
	medium: number;
	low: number;
};

export interface TaskActivityItem {
	id: string;
	projectName: string;
	kind: TaskActivityKind;
	sourceMode: TaskActivitySourceMode;
	status: string;
	gitleaksEnabled?: boolean;
	staticFindingStats?: StaticSeverityCounts;
	agentFindingStats?: {
		critical: number;
		high: number;
		medium: number;
		low: number;
		total: number;
	};
	createdAt: string;
	startedAt?: string | null;
	completedAt?: string | null;
	durationMs?: number | null;
	route: string;
}

function normalizeTaskName(name: string | null | undefined): string {
	return String(name || "").trim().toLowerCase();
}

export function resolveSourceModeFromTaskMeta(
	kind: TaskActivityKind,
	name: string | null | undefined,
	description?: string | null | undefined,
): TaskActivitySourceMode {
	const normalizedName = normalizeTaskName(name);
	const normalizedDescription = normalizeTaskName(description);
	const normalizedCombined = `${normalizedName} ${normalizedDescription}`;
	if (
		normalizedCombined.includes(HYBRID_TASK_NAME_MARKER.toLowerCase()) ||
		normalizedCombined.includes("混合扫描")
	) {
		return "hybrid";
	}
	if (normalizedCombined.includes(INTELLIGENT_TASK_NAME_MARKER.toLowerCase())) {
		return "intelligent";
	}
	if (kind === "rule_scan") {
		return "static";
	}
	// Legacy intelligent_audit tasks created before markers are migrated to hybrid.
	return "hybrid";
}

export function isIntelligentAgentActivity(
	activity: Pick<TaskActivityItem, "kind" | "sourceMode">,
): boolean {
	return (
		activity.kind === "intelligent_audit" &&
		activity.sourceMode === "intelligent"
	);
}

export function isHybridAgentActivity(
	activity: Pick<TaskActivityItem, "kind" | "sourceMode">,
): boolean {
	return (
		activity.kind === "intelligent_audit" &&
		activity.sourceMode === "hybrid"
	);
}

export function getTaskKindText(
	activity: Pick<TaskActivityItem, "kind" | "sourceMode">,
): string {
	if (activity.kind === "rule_scan") {
		return "静态扫描";
	}
	if (activity.sourceMode === "hybrid") {
		return "混合扫描";
	}
	return "智能扫描";
}

function mapProjectNames(projects: Project[]) {
	return new Map(projects.map((project) => [project.id, project.name]));
}

function normalizeStatus(status: string | null | undefined): string {
	return String(status || "").trim().toLowerCase();
}

function toNonNegativeInt(value: unknown): number {
	const parsed = Number(value);
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 0;
	}
	return Math.floor(parsed);
}

function buildOpengrepSeverityCounts(
	task?: OpengrepScanTask | null,
): StaticSeverityCounts {
	const total = toNonNegativeInt(task?.total_findings);
	const error = toNonNegativeInt(task?.error_count);
	const warning = toNonNegativeInt(task?.warning_count);
	return {
		critical: 0,
		high: 0,
		medium: error + warning,
		low: Math.max(total - error - warning, 0),
	};
}

function buildGitleaksSeverityCounts(
	task?: GitleaksScanTask | null,
): StaticSeverityCounts {
	return {
		critical: 0,
		high: 0,
		medium: 0,
		low: toNonNegativeInt(task?.total_findings),
	};
}

function buildBanditSeverityCounts(
	task?: BanditScanTask | null,
): StaticSeverityCounts {
	return {
		critical: 0,
		high: toNonNegativeInt(task?.high_count),
		medium: toNonNegativeInt(task?.medium_count),
		low: toNonNegativeInt(task?.low_count),
	};
}

function buildPhpstanSeverityCounts(
	task?: PhpstanScanTask | null,
): StaticSeverityCounts {
	// PHPStan integration: dashboard/task活动口径将 phpstan 发现全部归入 low(hint)。
	return {
		critical: 0,
		high: 0,
		medium: 0,
		low: toNonNegativeInt(task?.total_findings),
	};
}

function mergeSeverityCounts(...counts: StaticSeverityCounts[]): StaticSeverityCounts {
	return counts.reduce<StaticSeverityCounts>(
		(acc, item) => ({
			critical: acc.critical + item.critical,
			high: acc.high + item.high,
			medium: acc.medium + item.medium,
			low: acc.low + item.low,
		}),
		{
			critical: 0,
			high: 0,
			medium: 0,
			low: 0,
		},
	);
}

function toRuleScanActivities(
	opengrepTasks: OpengrepScanTask[],
	gitleaksTasks: GitleaksScanTask[],
	banditTasks: BanditScanTask[],
	phpstanTasks: PhpstanScanTask[],
	resolveProjectName: (projectId: string) => string,
): TaskActivityItem[] {
	// Multi-engine grouping: one activity item can contain any selected static engines.
	const visibleOpengrepTasks = opengrepTasks.filter(
		(task) => !task.name.startsWith("Agent Bootstrap OpenGrep"),
	);
	const groups = buildStaticScanGroups({
		opengrepTasks: visibleOpengrepTasks,
		gitleaksTasks,
		banditTasks,
		phpstanTasks,
	});

	return groups
		.map((group): TaskActivityItem | null => {
		const opengrepTask = group.opengrepTask;
		const gitleaksTask = group.gitleaksTask;
		const banditTask = group.banditTask;
		const phpstanTask = group.phpstanTask;
		const primaryTask = opengrepTask || gitleaksTask || banditTask || phpstanTask;
		if (!primaryTask) {
			return null;
		}

		const params = new URLSearchParams();
		params.set("muteToast", "1");
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
		if (!opengrepTask && gitleaksTask && !banditTask && !phpstanTask) {
			params.set("tool", "gitleaks");
		}
		if (!opengrepTask && !gitleaksTask && banditTask && !phpstanTask) {
			params.set("tool", "bandit");
		}
		if (!opengrepTask && !gitleaksTask && !banditTask && phpstanTask) {
			params.set("tool", "phpstan");
		}

		const durationCandidates = [
			opengrepTask?.scan_duration_ms,
			gitleaksTask?.scan_duration_ms,
			banditTask?.scan_duration_ms,
			phpstanTask?.scan_duration_ms,
		];
		const durationMs = durationCandidates.reduce<number | null>((total, value) => {
			if (
				typeof value !== "number" ||
				!Number.isFinite(value) ||
				value <= 0
			) {
				return total;
			}
			return (total ?? 0) + value;
		}, null);

		const staticFindingStats = mergeSeverityCounts(
			buildOpengrepSeverityCounts(opengrepTask),
			buildGitleaksSeverityCounts(gitleaksTask),
			buildBanditSeverityCounts(banditTask),
			buildPhpstanSeverityCounts(phpstanTask),
		);

		const candidateStatuses = [opengrepTask, gitleaksTask, banditTask, phpstanTask]
			.map((task) => normalizeStatus(task?.status))
			.filter(Boolean);
		const hasRunningStatus = candidateStatuses.some(
			(status) => status === "running" || status === "pending",
		);
		const latestUpdatedAt = [opengrepTask, gitleaksTask, banditTask, phpstanTask].reduce<
			string | null
		>((latest, task) => {
			const current = task?.updated_at || null;
			if (!current) return latest;
			if (!latest) return current;
			return new Date(current).getTime() > new Date(latest).getTime()
				? current
				: latest;
		}, null);
		const completedAt = hasRunningStatus ? null : latestUpdatedAt;

		const item: TaskActivityItem = {
			id: `static-${primaryTask.id}`,
			projectName: resolveProjectName(group.projectId),
			kind: "rule_scan",
			sourceMode: resolveSourceModeFromTaskMeta(
				"rule_scan",
				opengrepTask?.name ||
					gitleaksTask?.name ||
					banditTask?.name ||
					phpstanTask?.name,
			),
			status: resolveStaticScanGroupStatus(group),
			gitleaksEnabled: Boolean(gitleaksTask),
			staticFindingStats,
			createdAt: group.createdAt,
			startedAt: group.createdAt,
			completedAt,
			durationMs,
			route: `/static-analysis/${primaryTask.id}?${params.toString()}`,
		};
		return item;
	})
		.filter((item): item is TaskActivityItem => item !== null);
}

function toAgentActivities(
	agentTasks: AgentTask[],
	resolveProjectName: (projectId: string) => string,
): TaskActivityItem[] {
	return agentTasks.map((task) => ({
		id: `agent-${task.id}`,
		projectName: resolveProjectName(task.project_id),
		kind: "intelligent_audit",
		sourceMode: resolveSourceModeFromTaskMeta(
			"intelligent_audit",
			task.name,
			task.description,
		),
		status: task.status,
		agentFindingStats: {
			critical: Math.max(task.critical_count || 0, 0),
			high: Math.max(task.high_count || 0, 0),
			medium: Math.max(task.medium_count || 0, 0),
			low: Math.max(task.low_count || 0, 0),
			total: Math.max(task.findings_count || 0, 0),
		},
		createdAt: task.created_at,
		startedAt: task.started_at,
		completedAt: task.completed_at,
		route: `/agent-audit/${task.id}?muteToast=1`,
	}));
}

export async function fetchTaskActivities(
	projects: Project[],
	limit = 100,
): Promise<TaskActivityItem[]> {
	const [agentTasks, opengrepTasks, gitleaksTasks, banditTasks, phpstanTasks] =
		await Promise.all([
		getAgentTasks({ limit }),
		getOpengrepScanTasks({ limit }),
		getGitleaksScanTasks({ limit }),
		getBanditScanTasks({ limit }),
		getPhpstanScanTasks({ limit }),
	]);

	const projectNameMap = mapProjectNames(projects);
	const resolveProjectName = (projectId: string) =>
		projectNameMap.get(projectId) || "未知项目";

	const activities = [
		...toRuleScanActivities(
			opengrepTasks,
			gitleaksTasks,
			banditTasks,
			phpstanTasks,
			resolveProjectName,
		),
		...toAgentActivities(agentTasks, resolveProjectName),
	].sort(
		(a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
	);

	return activities;
}

export function filterActivitiesByKind(
	activities: TaskActivityItem[],
	kind: TaskActivityKind,
	keyword: string,
): TaskActivityItem[] {
	const trimmed = keyword.trim().toLowerCase();
	const filteredByKind = activities.filter(
		(activity) => activity.kind === kind,
	);
	if (!trimmed) return filteredByKind;

	const kindText = kind === "rule_scan" ? "静态扫描" : "智能扫描";
	return filteredByKind.filter((activity) => {
		return (
			activity.projectName.toLowerCase().includes(trimmed) ||
			kindText.includes(trimmed) ||
			getTaskStatusText(activity.status).includes(trimmed)
		);
	});
}

function matchesActivityKeyword(
	activity: TaskActivityItem,
	keyword: string,
): boolean {
	const trimmed = keyword.trim().toLowerCase();
	if (!trimmed) return true;
	const kindText = getTaskKindText(activity);
	return (
		activity.projectName.toLowerCase().includes(trimmed) ||
		kindText.includes(trimmed) ||
		getTaskStatusText(activity.status).includes(trimmed)
	);
}

export function filterIntelligentActivities(
	activities: TaskActivityItem[],
	keyword: string,
): TaskActivityItem[] {
	return activities.filter(
		(activity) =>
			isIntelligentAgentActivity(activity) &&
			matchesActivityKeyword(activity, keyword),
	);
}

export function filterHybridActivities(
	activities: TaskActivityItem[],
	keyword: string,
): TaskActivityItem[] {
	return activities.filter(
		(activity) =>
			isHybridAgentActivity(activity) &&
			matchesActivityKeyword(activity, keyword),
	);
}

export function filterMixedActivities(
	activities: TaskActivityItem[],
	keyword: string,
): TaskActivityItem[] {
	const trimmed = keyword.trim().toLowerCase();
	if (!trimmed) return activities;

	return activities.filter((activity) => {
		const kindText = getTaskKindText(activity);
		return (
			activity.projectName.toLowerCase().includes(trimmed) ||
			kindText.includes(trimmed) ||
			getTaskStatusText(activity.status).includes(trimmed)
		);
	});
}

export function getTaskStatusText(status: string): string {
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
}

export function getTaskStatusClassName(status: string): string {
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
}

export function getTaskStatusBadgeClassName(status: string): string {
	if (status === "completed") return "cyber-badge-success";
	if (status === "running") return "cyber-badge-info";
	if (status === "failed") return "cyber-badge-danger";
	if (INTERRUPTED_STATUSES.has(status)) return "cyber-badge-warning";
	return "cyber-badge-muted";
}

export function getTaskProgressBarClassName(status: string): string {
	if (status === "completed") return "bg-emerald-400";
	if (status === "running") return "bg-sky-400";
	if (status === "failed") return "bg-rose-400";
	if (INTERRUPTED_STATUSES.has(status)) return "bg-orange-400";
	return "bg-muted-foreground";
}

export function getTaskProgressPercent(
	activity: TaskActivityItem,
	nowMs = Date.now(),
): number {
	return getEstimatedTaskProgressPercent(
		{
			status: activity.status,
			createdAt: activity.createdAt,
			startedAt: activity.startedAt,
		},
		nowMs,
	);
}

export function formatCreatedAt(time: string): string {
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
}

export function getRelativeTime(time: string, nowMs = Date.now()): string {
	const now = new Date(nowMs);
	const taskDate = new Date(time);
	const diffMs = now.getTime() - taskDate.getTime();
	const diffMins = Math.floor(diffMs / 60000);
	const diffHours = Math.floor(diffMs / 3600000);
	const diffDays = Math.floor(diffMs / 86400000);
	if (diffMins < 60) return `${Math.max(diffMins, 1)}分钟前`;
	if (diffHours < 24) return `${diffHours}小时前`;
	return `${diffDays}天前`;
}

export function formatDurationMs(durationMs: number): string {
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

export function getActivityDurationLabel(
	activity: TaskActivityItem,
	nowMs = Date.now(),
): string {
	if (activity.kind === "rule_scan") {
		if (
			typeof activity.durationMs === "number" &&
			Number.isFinite(activity.durationMs) &&
			activity.durationMs > 0
		) {
			return `用时：${formatDurationMs(activity.durationMs)}`;
		}
		const started = activity.startedAt || activity.createdAt || null;
		const completed = activity.completedAt || null;
		if (started && completed) {
			const duration =
				new Date(completed).getTime() - new Date(started).getTime();
			if (Number.isFinite(duration) && duration > 0) {
				return `用时：${formatDurationMs(duration)}`;
			}
			return "用时：-";
		}
		if (activity.status === "running" && started) {
			const elapsed = nowMs - new Date(started).getTime();
			if (Number.isFinite(elapsed) && elapsed >= 0) {
				return `已运行：${formatDurationMs(elapsed)}`;
			}
			return "已运行：-";
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
		const elapsed = nowMs - new Date(started).getTime();
		if (Number.isFinite(elapsed) && elapsed >= 0) {
			return `已运行：${formatDurationMs(elapsed)}`;
		}
		return "已运行：-";
	}

	return "用时：-";
}

export interface TaskActivitySummary {
	staticTotal: number;
	intelligentTotal: number;
	hybridTotal: number;
	running: number;
	completed: number;
	failed: number;
	interrupted: number;
}

export interface TaskStatusSummary {
	total: number;
	completed: number;
	running: number;
}

export function summarizeTaskActivities(
	activities: TaskActivityItem[],
): TaskActivitySummary {
	return activities.reduce<TaskActivitySummary>(
		(acc, activity) => {
			if (activity.kind === "rule_scan") {
				acc.staticTotal += 1;
			} else if (isIntelligentAgentActivity(activity)) {
				acc.intelligentTotal += 1;
			} else {
				acc.hybridTotal += 1;
			}

			if (activity.status === "running") acc.running += 1;
			else if (activity.status === "completed") acc.completed += 1;
			else if (activity.status === "failed") acc.failed += 1;
			else if (INTERRUPTED_STATUSES.has(activity.status)) acc.interrupted += 1;

			return acc;
		},
		{
			staticTotal: 0,
			intelligentTotal: 0,
			hybridTotal: 0,
			running: 0,
			completed: 0,
			failed: 0,
			interrupted: 0,
		},
	);
}

export function summarizeTaskStatus(
	activities: TaskActivityItem[],
): TaskStatusSummary {
	return activities.reduce<TaskStatusSummary>(
		(acc, activity) => {
			acc.total += 1;
			if (activity.status === "completed") {
				acc.completed += 1;
			} else if (activity.status === "running") {
				acc.running += 1;
			}
			return acc;
		},
		{
			total: 0,
			completed: 0,
			running: 0,
		},
	);
}
