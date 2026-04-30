const AUTO_SCROLL_BY_TASK_STORAGE_KEY = "agentAudit.autoScrollByTask.v1";

export const PROGRAMMATIC_SCROLL_GUARD_MS = 400;

type AutoScrollByTaskState = Record<string, boolean>;

type ScrollDecisionInput = {
	isAutoScrollEnabled: boolean;
	isProgrammaticScroll: boolean;
	distanceToBottom: number;
	thresholdPx: number;
};

function resolveStorage(storage?: Storage): Storage | null {
	if (storage) return storage;
	if (typeof window === "undefined") return null;
	return window.localStorage;
}

export function loadAutoScrollState(storage?: Storage): AutoScrollByTaskState {
	const target = resolveStorage(storage);
	if (!target) return {};

	try {
		const raw = target.getItem(AUTO_SCROLL_BY_TASK_STORAGE_KEY);
		if (!raw) return {};
		const parsed = JSON.parse(raw) as unknown;
		if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
			return {};
		}

		const normalized: AutoScrollByTaskState = {};
		for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
			if (typeof value === "boolean" && key.trim()) {
				normalized[key] = value;
			}
		}
		return normalized;
	} catch {
		return {};
	}
}

export function getTaskAutoScroll(taskId: string | null, storage?: Storage): boolean {
	const normalizedTaskId = String(taskId || "").trim();
	if (!normalizedTaskId) return true;

	const state = loadAutoScrollState(storage);
	if (Object.prototype.hasOwnProperty.call(state, normalizedTaskId)) {
		return state[normalizedTaskId];
	}
	return true;
}

export function persistTaskAutoScroll(
	taskId: string,
	enabled: boolean,
	storage?: Storage,
): void {
	const normalizedTaskId = String(taskId || "").trim();
	if (!normalizedTaskId) return;

	const target = resolveStorage(storage);
	if (!target) return;

	try {
		const state = loadAutoScrollState(target);
		state[normalizedTaskId] = enabled;
		target.setItem(AUTO_SCROLL_BY_TASK_STORAGE_KEY, JSON.stringify(state));
	} catch {
	}
}

export function shouldDisableAutoScrollOnScroll({
	isAutoScrollEnabled,
	isProgrammaticScroll,
	distanceToBottom,
	thresholdPx,
}: ScrollDecisionInput): boolean {
	if (!isAutoScrollEnabled) return false;
	if (isProgrammaticScroll) return false;
	return distanceToBottom > thresholdPx;
}
