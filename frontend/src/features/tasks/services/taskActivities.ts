import type { AgentTask } from "@/shared/api/agentTasks";
import {
	getOpengrepScanTasks,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import type { Project } from "@/shared/types";
import {
	INTERRUPTED_STATUSES,
} from "./taskProgress";
import {
	formatTaskDuration,
	getTaskDisplayProgressPercent,
	getTaskDisplayStatusSummary,
} from "./taskDisplay";
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
export type TaskActivitySourceMode = "static" | "intelligent";
export type TaskActivityCancelTarget =
	| { mode: "intelligent"; taskId: string }
	| { mode: "static"; engine: "opengrep"; taskId: string };

export const INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]";

export type SeverityCounts = {
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
	staticFindingStats?: SeverityCounts;
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
	cancelTarget?: TaskActivityCancelTarget;
}

function normalizeTaskName(name: string | null | undefined): string {
	return String(name || "").trim().toLowerCase();
}

export function resolveSourceModeFromTaskMeta(
	kind: TaskActivityKind,
	name: string | null | undefined,
	description?: string | null | undefined,
): TaskActivitySourceMode {
	if (kind === "rule_scan") {
		return "static";
	}

	const normalizedName = normalizeTaskName(name);
	const normalizedDescription = normalizeTaskName(description);
	const normalizedCombined = `${normalizedName} ${normalizedDescription}`;
	if (normalizedCombined.includes(INTELLIGENT_TASK_NAME_MARKER.toLowerCase())) {
		return "intelligent";
	}

	// Legacy agent tasks are now all displayed as intelligent scans.
	return "intelligent";
}

export function isIntelligentAgentActivity(
	activity: Pick<TaskActivityItem, "kind" | "sourceMode">,
): boolean {
	return (
		activity.kind === "intelligent_audit" &&
		activity.sourceMode === "intelligent"
	);
}

export function getTaskKindText(
	activity: Pick<TaskActivityItem, "kind" | "sourceMode">,
): string {
	if (activity.kind === "rule_scan") {
		return "静态审计";
	}
	return "智能审计";
}

function mapProjectNames(projects: Project[]) {
	return new Map(projects.map((project) => [project.id, project.name]));
}

function normalizeStatus(status: string | null | undefined): string {
	return String(status || "").trim().toLowerCase();
}

const CANCELLABLE_TASK_STATUSES = new Set([
	"running",
	"pending",
	"created",
	"waiting",
	"queued",
	"in_progress",
	"processing",
]);

export function isTaskActivityCancellable(
	activity: Pick<TaskActivityItem, "status" | "cancelTarget">,
): boolean {
	return Boolean(
		activity.cancelTarget && CANCELLABLE_TASK_STATUSES.has(normalizeStatus(activity.status)),
	);
}

function toNonNegativeInt(value: unknown): number {
	const parsed = Number(value);
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 0;
	}
	return Math.floor(parsed);
}

function toOptionalNonNegativeInt(value: unknown): number | null {
	if (value === null || value === undefined) {
		return null;
	}
	const parsed = Number(value);
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 0;
	}
	return Math.floor(parsed);
}

export function getOpengrepVisibleFindingCount(
	task?: OpengrepScanTask | null,
): number {
	const total = toOptionalNonNegativeInt(task?.total_findings);
	if (total !== null) {
		return total;
	}

	const severityTotal =
		toNonNegativeInt(task?.error_count) + toNonNegativeInt(task?.warning_count);
	if (severityTotal > 0) {
		return severityTotal;
	}

	return toNonNegativeInt(task?.high_confidence_count);
}

export function buildOpengrepSeverityCounts(
	task?: OpengrepScanTask | null,
): SeverityCounts {
	const critical = toOptionalNonNegativeInt(task?.critical_count);
	const high = toOptionalNonNegativeInt(task?.high_count);
	const medium = toOptionalNonNegativeInt(task?.medium_count);
	const low = toOptionalNonNegativeInt(task?.low_count);
	if (critical !== null || high !== null || medium !== null || low !== null) {
		return {
			critical: critical ?? 0,
			high: high ?? 0,
			medium: medium ?? 0,
			low: low ?? 0,
		};
	}

	return {
		critical: 0,
		high: 0,
		medium: 0,
		low: getOpengrepVisibleFindingCount(task),
	};
}

export function getAgentSeverityCounts(
	task?:
		| Pick<
				AgentTask,
				"critical_count" | "high_count" | "medium_count" | "low_count"
		  >
		| null,
): SeverityCounts {
	return {
		critical: toNonNegativeInt(task?.critical_count),
		high: toNonNegativeInt(task?.high_count),
		medium: toNonNegativeInt(task?.medium_count),
		low: toNonNegativeInt(task?.low_count),
	};
}

export function mergeSeverityCounts(...counts: SeverityCounts[]): SeverityCounts {
	return counts.reduce<SeverityCounts>(
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

export function getSeverityCountTotal(counts: SeverityCounts): number {
	return counts.critical + counts.high + counts.medium + counts.low;
}

function toRuleScanActivities(
	opengrepTasks: OpengrepScanTask[],
	resolveProjectName: (projectId: string) => string,
): TaskActivityItem[] {
	const visibleOpengrepTasks = opengrepTasks.filter(
		(task) => !task.name.startsWith("Agent Bootstrap OpenGrep"),
	);
	const groups = buildStaticScanGroups({
		opengrepTasks: visibleOpengrepTasks,
		gitleaksTasks: [],
	});

	return groups
		.map((group): TaskActivityItem | null => {
		const opengrepTask = group.opengrepTask;
		const primaryTask = opengrepTask;
		if (!primaryTask) {
			return null;
		}

		const params = new URLSearchParams();
		params.set("muteToast", "1");
		if (opengrepTask) {
			params.set("opengrepTaskId", opengrepTask.id);
		}

		const durationCandidates = [opengrepTask?.scan_duration_ms];
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

		const staticFindingStats = buildOpengrepSeverityCounts(opengrepTask);

		const candidateStatuses = [opengrepTask]
			.map((task) => normalizeStatus(task?.status))
			.filter(Boolean);
		const hasRunningStatus = candidateStatuses.some(
			(status) => status === "running" || status === "pending",
		);
		const latestUpdatedAt = [opengrepTask].reduce<string | null>((latest, task) => {
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
			sourceMode: resolveSourceModeFromTaskMeta("rule_scan", opengrepTask?.name),
			status: resolveStaticScanGroupStatus(group),
			gitleaksEnabled: false,
			staticFindingStats,
			createdAt: group.createdAt,
			startedAt: group.createdAt,
			completedAt,
			durationMs,
			route: `/static-analysis/${primaryTask.id}?${params.toString()}`,
			cancelTarget: { mode: "static", engine: "opengrep", taskId: primaryTask.id },
		};
		return item;
	})
		.filter((item): item is TaskActivityItem => item !== null);
}

export async function fetchTaskActivities(
	projects: Project[],
	limit = 100,
): Promise<TaskActivityItem[]> {
	const opengrepTasks = await getOpengrepScanTasks({ limit });

	const projectNameMap = mapProjectNames(projects);
	const resolveProjectName = (projectId: string) =>
		projectNameMap.get(projectId) || "未知项目";

	const activities = [
		...toRuleScanActivities(opengrepTasks, resolveProjectName),
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

	const kindText = kind === "rule_scan" ? "静态审计" : "智能审计";
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
	return getTaskDisplayStatusSummary(status).statusLabel;
}

export function getTaskStatusClassName(status: string): string {
	if (status === "completed") {
		return "bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40";
	}
	if (status === "running" || status === "pending") {
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
	return getTaskDisplayStatusSummary(status).badgeClassName;
}

export function getTaskProgressBarClassName(status: string): string {
	return getTaskDisplayStatusSummary(status).progressBarClassName;
}

export function getTaskProgressPercent(
	activity: TaskActivityItem,
	nowMs = Date.now(),
): number {
	return getTaskDisplayProgressPercent({
		status: activity.status,
		createdAt: activity.createdAt,
		startedAt: activity.startedAt,
		nowMs,
	});
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
	return formatTaskDuration(durationMs, { showMsWhenSubSecond: true });
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
			} else {
				acc.intelligentTotal += 1;
			}

			if (activity.status === "running" || activity.status === "pending") acc.running += 1;
			else if (activity.status === "completed") acc.completed += 1;
			else if (activity.status === "failed") acc.failed += 1;
			else if (INTERRUPTED_STATUSES.has(activity.status)) acc.interrupted += 1;

			return acc;
		},
		{
			staticTotal: 0,
			intelligentTotal: 0,
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
			} else if (activity.status === "running" || activity.status === "pending") {
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
