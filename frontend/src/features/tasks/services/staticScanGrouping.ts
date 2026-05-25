import { extractStaticScanBatchId } from "@/shared/utils/staticScanBatch";

export const STATIC_SCAN_PAIRING_WINDOW_MS = 60 * 1000;

export interface StaticScanTaskLike {
	id: string;
	project_id: string;
	status: string;
	created_at: string;
	name?: string | null;
}

export interface StaticScanGroup<
	TOpengrepTask extends StaticScanTaskLike = StaticScanTaskLike,
	TCodeqlTask extends StaticScanTaskLike = StaticScanTaskLike,
	TJoernTask extends StaticScanTaskLike = StaticScanTaskLike,
> {
	projectId: string;
	createdAt: string;
	opengrepTask?: TOpengrepTask;
	codeqlTask?: TCodeqlTask;
	joernTask?: TJoernTask;
}

export type StaticScanGroupStatus =
	| "completed"
	| "running"
	| "pending"
	| "failed"
	| "interrupted";

type EngineTask<TOpengrepTask, TCodeqlTask, TJoernTask> =
	| { engine: "opengrep"; task: TOpengrepTask }
	| { engine: "codeql"; task: TCodeqlTask }
	| { engine: "joern"; task: TJoernTask };

function normalizeTimestamp(value: string): number {
	const timestamp = new Date(value).getTime();
	return Number.isFinite(timestamp) ? timestamp : 0;
}

function normalizeStatus(value: string | null | undefined): string {
	return String(value || "").trim().toLowerCase();
}

export function buildStaticScanGroups<
	TOpengrepTask extends StaticScanTaskLike,
	TCodeqlTask extends StaticScanTaskLike,
	TJoernTask extends StaticScanTaskLike = StaticScanTaskLike,
>(params: {
	opengrepTasks: TOpengrepTask[];
	codeqlTasks?: TCodeqlTask[];
	joernTasks?: TJoernTask[];
	pairingWindowMs?: number;
}): Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>> {
	const {
		opengrepTasks,
		codeqlTasks = [],
		joernTasks = [],
		pairingWindowMs = STATIC_SCAN_PAIRING_WINDOW_MS,
	} = params;

	const tasksByProject = new Map<
		string,
		Array<EngineTask<TOpengrepTask, TCodeqlTask, TJoernTask>>
	>();
	const pushTask = (
		projectId: string,
		engineTask: EngineTask<TOpengrepTask, TCodeqlTask, TJoernTask>,
	) => {
		const list = tasksByProject.get(projectId) || [];
		list.push(engineTask);
		tasksByProject.set(projectId, list);
	};

	for (const task of opengrepTasks) {
		pushTask(task.project_id, { engine: "opengrep", task });
	}
	for (const task of codeqlTasks) {
		pushTask(task.project_id, { engine: "codeql", task });
	}
	for (const task of joernTasks) {
		pushTask(task.project_id, { engine: "joern", task });
	}

	const groups: Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>> = [];

	for (const [projectId, list] of tasksByProject.entries()) {
		const sorted = [...list].sort(
			(a, b) =>
				normalizeTimestamp(a.task.created_at) -
				normalizeTimestamp(b.task.created_at),
		);
		const batchTaggedTasks = sorted.filter((item) =>
			Boolean(extractStaticScanBatchId(item.task.name)),
		);
		const legacyTasks = sorted.filter(
			(item) => !extractStaticScanBatchId(item.task.name),
		);
		const projectGroups: Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>> = [];

		const assignTaskToGroups = (
			item: EngineTask<TOpengrepTask, TCodeqlTask, TJoernTask>,
			candidateGroups: Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>>,
			ignoreWindow = false,
		) => {
			const taskTimestamp = normalizeTimestamp(item.task.created_at);
			let bestGroupIndex = -1;
			let bestDiff = Number.POSITIVE_INFINITY;

			for (let index = 0; index < candidateGroups.length; index += 1) {
				const group = candidateGroups[index];
				const groupTimestamp = normalizeTimestamp(group.createdAt);
				const diff = Math.abs(taskTimestamp - groupTimestamp);
				if (!ignoreWindow && diff > pairingWindowMs) continue;

				const hasSameEngineTask =
					(item.engine === "opengrep" && Boolean(group.opengrepTask)) ||
					(item.engine === "codeql" && Boolean(group.codeqlTask)) ||
					(item.engine === "joern" && Boolean(group.joernTask));
				if (hasSameEngineTask) continue;

				if (diff < bestDiff) {
					bestDiff = diff;
					bestGroupIndex = index;
				}
			}

			if (bestGroupIndex === -1) {
				const nextGroup: StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask> = {
					projectId,
					createdAt: item.task.created_at,
				};
				if (item.engine === "opengrep") {
					nextGroup.opengrepTask = item.task;
				} else if (item.engine === "codeql") {
					nextGroup.codeqlTask = item.task;
				} else {
					nextGroup.joernTask = item.task;
				}
				candidateGroups.push(nextGroup);
				return;
			}

			const targetGroup = candidateGroups[bestGroupIndex];
			if (item.engine === "opengrep") {
				targetGroup.opengrepTask = item.task;
			} else if (item.engine === "codeql") {
				targetGroup.codeqlTask = item.task;
			} else {
				targetGroup.joernTask = item.task;
			}
		};

		const groupsByBatch = new Map<
			string,
			Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>>
		>();
		for (const item of batchTaggedTasks) {
			const batchId = extractStaticScanBatchId(item.task.name);
			if (!batchId) continue;
			const candidateGroups = groupsByBatch.get(batchId) || [];
			assignTaskToGroups(item, candidateGroups, true);
			groupsByBatch.set(batchId, candidateGroups);
		}
		for (const groupsOfBatch of groupsByBatch.values()) {
			projectGroups.push(...groupsOfBatch);
		}

		const legacyGroups: Array<StaticScanGroup<TOpengrepTask, TCodeqlTask, TJoernTask>> = [];
		for (const item of legacyTasks) {
			assignTaskToGroups(item, legacyGroups, false);
		}
		projectGroups.push(...legacyGroups);

		groups.push(...projectGroups);
	}

	return groups;
}

export function resolveStaticScanGroupStatus(
	group: Pick<StaticScanGroup, "opengrepTask" | "codeqlTask" | "joernTask">,
): StaticScanGroupStatus {
	const statuses = [
		group.opengrepTask?.status,
		group.codeqlTask?.status,
		group.joernTask?.status,
	]
		.map((status) => normalizeStatus(status))
		.filter(Boolean);

	if (statuses.length === 0) return "failed";
	if (statuses.some((status) => status === "running")) return "running";
	if (statuses.every((status) => status === "pending")) return "pending";
	if (statuses.some((status) => status === "failed")) return "failed";
	if (statuses.some((status) => status === "pending")) return "running";
	if (statuses.every((status) => status === "completed")) return "completed";

	const interruptedStatuses = new Set(["cancelled", "interrupted", "aborted"]);
	if (statuses.some((status) => interruptedStatuses.has(status))) {
		return "interrupted";
	}

	console.warn(
		"[taskActivities] Unknown static scan group statuses, fallback to failed:",
		statuses,
	);
	return "failed";
}
