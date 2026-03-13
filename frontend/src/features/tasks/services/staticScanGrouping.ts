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
	TGitleaksTask extends StaticScanTaskLike = StaticScanTaskLike,
	TBanditTask extends StaticScanTaskLike = StaticScanTaskLike,
> {
	projectId: string;
	createdAt: string;
	opengrepTask?: TOpengrepTask;
	gitleaksTask?: TGitleaksTask;
	banditTask?: TBanditTask;
}

export type StaticScanGroupStatus = "completed" | "running" | "other";

function normalizeTimestamp(value: string): number {
	const timestamp = new Date(value).getTime();
	return Number.isFinite(timestamp) ? timestamp : 0;
}

function normalizeStatus(value: string | null | undefined): string {
	return String(value || "").trim().toLowerCase();
}

export function buildStaticScanGroups<
	TOpengrepTask extends StaticScanTaskLike,
	TGitleaksTask extends StaticScanTaskLike,
	TBanditTask extends StaticScanTaskLike,
>(params: {
	opengrepTasks: TOpengrepTask[];
	gitleaksTasks: TGitleaksTask[];
	banditTasks?: TBanditTask[];
	pairingWindowMs?: number;
}): Array<StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>> {
	const {
		opengrepTasks,
		gitleaksTasks,
		banditTasks = [],
		pairingWindowMs = STATIC_SCAN_PAIRING_WINDOW_MS,
	} = params;

	type EngineTask =
		| { engine: "opengrep"; task: TOpengrepTask }
		| { engine: "gitleaks"; task: TGitleaksTask }
		| { engine: "bandit"; task: TBanditTask };

	const tasksByProject = new Map<string, EngineTask[]>();
	const pushTask = (projectId: string, engineTask: EngineTask) => {
		const list = tasksByProject.get(projectId) || [];
		list.push(engineTask);
		tasksByProject.set(projectId, list);
	};

	for (const task of opengrepTasks) {
		pushTask(task.project_id, { engine: "opengrep", task });
	}
	for (const task of gitleaksTasks) {
		pushTask(task.project_id, { engine: "gitleaks", task });
	}
	for (const task of banditTasks) {
		pushTask(task.project_id, { engine: "bandit", task });
	}

	const groups: Array<StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>> = [];

	for (const [projectId, list] of tasksByProject.entries()) {
		const sorted = [...list].sort(
			(a, b) =>
				normalizeTimestamp(a.task.created_at) - normalizeTimestamp(b.task.created_at),
		);
		const batchTaggedTasks = sorted.filter((item) =>
			Boolean(extractStaticScanBatchId(item.task.name)),
		);
		const legacyTasks = sorted.filter(
			(item) => !extractStaticScanBatchId(item.task.name),
		);
		const projectGroups: Array<
			StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>
		> = [];

		// Batch-first grouping: tasks created in one user action carry same batch marker.
		const assignTaskToGroups = (
			item: EngineTask,
			candidateGroups: Array<
				StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>
			>,
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
					(item.engine === "gitleaks" && Boolean(group.gitleaksTask)) ||
					(item.engine === "bandit" && Boolean(group.banditTask));
				if (hasSameEngineTask) continue;

				if (diff < bestDiff) {
					bestDiff = diff;
					bestGroupIndex = index;
				}
			}

			if (bestGroupIndex === -1) {
				const nextGroup: StaticScanGroup<
					TOpengrepTask,
					TGitleaksTask,
					TBanditTask
				> = {
					projectId,
					createdAt: item.task.created_at,
				};
				if (item.engine === "opengrep") {
					nextGroup.opengrepTask = item.task;
				} else if (item.engine === "gitleaks") {
					nextGroup.gitleaksTask = item.task;
				} else {
					nextGroup.banditTask = item.task;
				}
				candidateGroups.push(nextGroup);
				return;
			}

			const targetGroup = candidateGroups[bestGroupIndex];
			if (item.engine === "opengrep") {
				targetGroup.opengrepTask = item.task;
			} else if (item.engine === "gitleaks") {
				targetGroup.gitleaksTask = item.task;
			} else {
				targetGroup.banditTask = item.task;
			}
		};

		const groupsByBatch = new Map<
			string,
			Array<StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>>
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

		// Legacy fallback for historical tasks without batch markers.
		const legacyGroups: Array<
			StaticScanGroup<TOpengrepTask, TGitleaksTask, TBanditTask>
		> = [];
		for (const item of legacyTasks) {
			assignTaskToGroups(item, legacyGroups, false);
		}
		projectGroups.push(...legacyGroups);

		groups.push(...projectGroups);
	}

	return groups;
}

export function resolveStaticScanGroupStatus(
	group: Pick<StaticScanGroup, "opengrepTask" | "gitleaksTask" | "banditTask">,
): StaticScanGroupStatus {
	const statuses = [
		group.opengrepTask?.status,
		group.gitleaksTask?.status,
		group.banditTask?.status,
	]
		.map((status) => normalizeStatus(status))
		.filter(Boolean);

	if (statuses.some((status) => status === "running" || status === "pending")) {
		return "running";
	}

	if (statuses.length > 0 && statuses.every((status) => status === "completed")) {
		return "completed";
	}

	return "other";
}
