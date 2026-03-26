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
	TPhpstanTask extends StaticScanTaskLike = StaticScanTaskLike,
	TPmdTask extends StaticScanTaskLike = StaticScanTaskLike,
	TYasaTask extends StaticScanTaskLike = StaticScanTaskLike,
> {
	projectId: string;
	createdAt: string;
	opengrepTask?: TOpengrepTask;
	gitleaksTask?: TGitleaksTask;
	banditTask?: TBanditTask;
	phpstanTask?: TPhpstanTask;
	pmdTask?: TPmdTask;
	yasaTask?: TYasaTask;
}

export type StaticScanGroupStatus =
	| "completed"
	| "running"
	| "pending"
	| "failed"
	| "interrupted";

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
	TPhpstanTask extends StaticScanTaskLike,
	TPmdTask extends StaticScanTaskLike,
	TYasaTask extends StaticScanTaskLike,
>(params: {
	opengrepTasks: TOpengrepTask[];
	gitleaksTasks: TGitleaksTask[];
	banditTasks?: TBanditTask[];
	phpstanTasks?: TPhpstanTask[];
	pmdTasks?: TPmdTask[];
	yasaTasks?: TYasaTask[];
	pairingWindowMs?: number;
}): Array<
	StaticScanGroup<
		TOpengrepTask,
		TGitleaksTask,
		TBanditTask,
		TPhpstanTask,
		TPmdTask,
		TYasaTask
	>
> {
	const {
		opengrepTasks,
		gitleaksTasks,
		banditTasks = [],
		phpstanTasks = [],
		pmdTasks = [],
		yasaTasks = [],
		pairingWindowMs = STATIC_SCAN_PAIRING_WINDOW_MS,
	} = params;

	type EngineTask =
		| { engine: "opengrep"; task: TOpengrepTask }
		| { engine: "gitleaks"; task: TGitleaksTask }
		| { engine: "bandit"; task: TBanditTask }
		| { engine: "phpstan"; task: TPhpstanTask }
		| { engine: "pmd"; task: TPmdTask }
		| { engine: "yasa"; task: TYasaTask };

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
	for (const task of phpstanTasks) {
		pushTask(task.project_id, { engine: "phpstan", task });
	}
	for (const task of pmdTasks) {
		pushTask(task.project_id, { engine: "pmd", task });
	}
	for (const task of yasaTasks) {
		pushTask(task.project_id, { engine: "yasa", task });
	}

	const groups: Array<
		StaticScanGroup<
			TOpengrepTask,
			TGitleaksTask,
			TBanditTask,
			TPhpstanTask,
			TPmdTask,
			TYasaTask
		>
	> = [];

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
			StaticScanGroup<
				TOpengrepTask,
				TGitleaksTask,
				TBanditTask,
				TPhpstanTask,
				TPmdTask,
				TYasaTask
			>
		> = [];

		// Batch-first grouping: tasks created in one user action carry same batch marker.
		const assignTaskToGroups = (
			item: EngineTask,
			candidateGroups: Array<
				StaticScanGroup<
					TOpengrepTask,
					TGitleaksTask,
					TBanditTask,
					TPhpstanTask,
					TPmdTask,
					TYasaTask
				>
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
					(item.engine === "bandit" && Boolean(group.banditTask)) ||
					(item.engine === "phpstan" && Boolean(group.phpstanTask)) ||
					(item.engine === "pmd" && Boolean(group.pmdTask)) ||
					(item.engine === "yasa" && Boolean(group.yasaTask));
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
					TBanditTask,
					TPhpstanTask,
					TPmdTask,
					TYasaTask
				> = {
					projectId,
					createdAt: item.task.created_at,
				};
				if (item.engine === "opengrep") {
					nextGroup.opengrepTask = item.task;
				} else if (item.engine === "gitleaks") {
					nextGroup.gitleaksTask = item.task;
				} else if (item.engine === "bandit") {
					nextGroup.banditTask = item.task;
				} else if (item.engine === "phpstan") {
					nextGroup.phpstanTask = item.task;
				} else if (item.engine === "pmd") {
					nextGroup.pmdTask = item.task;
				} else {
					nextGroup.yasaTask = item.task;
				}
				candidateGroups.push(nextGroup);
				return;
			}

			const targetGroup = candidateGroups[bestGroupIndex];
			if (item.engine === "opengrep") {
				targetGroup.opengrepTask = item.task;
			} else if (item.engine === "gitleaks") {
				targetGroup.gitleaksTask = item.task;
			} else if (item.engine === "bandit") {
				targetGroup.banditTask = item.task;
			} else if (item.engine === "phpstan") {
				targetGroup.phpstanTask = item.task;
			} else if (item.engine === "pmd") {
				targetGroup.pmdTask = item.task;
			} else {
				targetGroup.yasaTask = item.task;
			}
		};

		const groupsByBatch = new Map<
			string,
			Array<
				StaticScanGroup<
					TOpengrepTask,
					TGitleaksTask,
					TBanditTask,
					TPhpstanTask,
					TPmdTask,
					TYasaTask
				>
			>
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
			StaticScanGroup<
				TOpengrepTask,
				TGitleaksTask,
				TBanditTask,
				TPhpstanTask,
				TPmdTask,
				TYasaTask
			>
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
	group: Pick<
		StaticScanGroup,
		"opengrepTask" | "gitleaksTask" | "banditTask" | "phpstanTask" | "yasaTask"
		| "pmdTask"
	>,
): StaticScanGroupStatus {
	const statuses = [
		group.opengrepTask?.status,
		group.gitleaksTask?.status,
		group.banditTask?.status,
		group.phpstanTask?.status,
		group.pmdTask?.status,
		group.yasaTask?.status,
	]
		.map((status) => normalizeStatus(status))
		.filter(Boolean);

	if (statuses.length === 0) {
		return "failed";
	}

	if (statuses.some((status) => status === "running")) {
		return "running";
	}

	if (statuses.every((status) => status === "pending")) {
		return "pending";
	}

	if (statuses.some((status) => status === "failed")) {
		return "failed";
	}

	if (statuses.some((status) => status === "pending")) {
		return "running";
	}

	if (statuses.every((status) => status === "completed")) {
		return "completed";
	}

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
