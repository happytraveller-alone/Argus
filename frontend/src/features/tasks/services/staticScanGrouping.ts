export const STATIC_SCAN_PAIRING_WINDOW_MS = 60 * 1000;

export interface StaticScanTaskLike {
	id: string;
	project_id: string;
	status: string;
	created_at: string;
}

export interface StaticScanGroup<
	TOpengrepTask extends StaticScanTaskLike = StaticScanTaskLike,
	TGitleaksTask extends StaticScanTaskLike = StaticScanTaskLike,
> {
	projectId: string;
	createdAt: string;
	opengrepTask?: TOpengrepTask;
	gitleaksTask?: TGitleaksTask;
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
>(params: {
	opengrepTasks: TOpengrepTask[];
	gitleaksTasks: TGitleaksTask[];
	pairingWindowMs?: number;
}): Array<StaticScanGroup<TOpengrepTask, TGitleaksTask>> {
	const {
		opengrepTasks,
		gitleaksTasks,
		pairingWindowMs = STATIC_SCAN_PAIRING_WINDOW_MS,
	} = params;

	const gitleaksByProject = new Map<string, TGitleaksTask[]>();
	for (const task of gitleaksTasks) {
		const list = gitleaksByProject.get(task.project_id) || [];
		list.push(task);
		gitleaksByProject.set(task.project_id, list);
	}

	for (const [projectId, list] of gitleaksByProject.entries()) {
		list.sort(
			(a, b) => normalizeTimestamp(a.created_at) - normalizeTimestamp(b.created_at),
		);
		gitleaksByProject.set(projectId, list);
	}

	const usedGitleaksTaskIds = new Set<string>();
	const groups: Array<StaticScanGroup<TOpengrepTask, TGitleaksTask>> = [];

	for (const opengrepTask of opengrepTasks) {
		const candidates = gitleaksByProject.get(opengrepTask.project_id) || [];
		const opengrepTimestamp = normalizeTimestamp(opengrepTask.created_at);
		let pairedGitleaksTask: TGitleaksTask | undefined;
		let bestDiff = Number.POSITIVE_INFINITY;

		for (const candidate of candidates) {
			if (usedGitleaksTaskIds.has(candidate.id)) continue;
			const diff = Math.abs(
				normalizeTimestamp(candidate.created_at) - opengrepTimestamp,
			);
			if (diff <= pairingWindowMs && diff < bestDiff) {
				pairedGitleaksTask = candidate;
				bestDiff = diff;
			}
		}

		if (pairedGitleaksTask) {
			usedGitleaksTaskIds.add(pairedGitleaksTask.id);
		}

		groups.push({
			projectId: opengrepTask.project_id,
			createdAt: opengrepTask.created_at,
			opengrepTask,
			gitleaksTask: pairedGitleaksTask,
		});
	}

	for (const gitleaksTask of gitleaksTasks) {
		if (usedGitleaksTaskIds.has(gitleaksTask.id)) continue;
		groups.push({
			projectId: gitleaksTask.project_id,
			createdAt: gitleaksTask.created_at,
			gitleaksTask,
		});
	}

	return groups;
}

export function resolveStaticScanGroupStatus(
	group: Pick<StaticScanGroup, "opengrepTask" | "gitleaksTask">,
): StaticScanGroupStatus {
	const statuses = [group.opengrepTask?.status, group.gitleaksTask?.status]
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
