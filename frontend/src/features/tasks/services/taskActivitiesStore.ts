import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import {
	fetchTaskActivities,
	type TaskActivityItem,
} from "@/features/tasks/services/taskActivities";
import { cancelIntelligentTask } from "@/shared/api/intelligentTasks";

const STALE_MS = 30_000;
const MAX_AGE_MS = 5 * 60_000;

type TaskActivitiesStoreListener = () => void;

export interface TaskActivitiesSnapshot {
	projects: Project[];
	activities: TaskActivityItem[];
	fetchedAt: number;
	staleAt: number;
	expiresAt: number;
}

export interface TaskActivitiesStoreState {
	snapshot: TaskActivitiesSnapshot | null;
	loading: boolean;
	refreshing: boolean;
	error: string | null;
}

const listeners = new Set<TaskActivitiesStoreListener>();

let state: TaskActivitiesStoreState = {
	snapshot: null,
	loading: false,
	refreshing: false,
	error: null,
};

let inFlightRequest: Promise<TaskActivitiesSnapshot> | null = null;

function emitChange() {
	for (const listener of listeners) {
		listener();
	}
}

function setState(nextState: Partial<TaskActivitiesStoreState>) {
	state = {
		...state,
		...nextState,
	};
	emitChange();
}

function normalizeError(error: unknown): string {
	if (error instanceof Error) {
		return error.message || "加载任务数据失败";
	}
	if (typeof error === "string" && error.trim()) {
		return error;
	}
	return "加载任务数据失败";
}

function buildSnapshot(
	projects: Project[],
	activities: TaskActivityItem[],
): TaskActivitiesSnapshot {
	const fetchedAt = Date.now();
	return {
		projects,
		activities,
		fetchedAt,
		staleAt: fetchedAt + STALE_MS,
		expiresAt: fetchedAt + MAX_AGE_MS,
	};
}

async function requestSnapshot(): Promise<TaskActivitiesSnapshot> {
	const projects = await api.getProjects();
	const activities = await fetchTaskActivities(projects);
	return buildSnapshot(projects, activities);
}

async function fetchSnapshot(background: boolean): Promise<TaskActivitiesSnapshot> {
	if (inFlightRequest) {
		return inFlightRequest;
	}

	if (background) {
		setState({ refreshing: true, error: null });
	} else {
		setState({ loading: true, refreshing: false, error: null });
	}

	inFlightRequest = requestSnapshot()
		.then((snapshot) => {
			setState({
				snapshot,
				loading: false,
				refreshing: false,
				error: null,
			});
			return snapshot;
		})
		.catch((error) => {
			setState({
				loading: false,
				refreshing: false,
				error: normalizeError(error),
			});
			if (state.snapshot) {
				return state.snapshot;
			}
			throw error;
		})
		.finally(() => {
			inFlightRequest = null;
		});

	return inFlightRequest;
}

export async function loadTaskActivitiesSnapshot(options?: {
	force?: boolean;
}): Promise<TaskActivitiesSnapshot> {
	const force = Boolean(options?.force);
	const snapshot = state.snapshot;

	if (!force && snapshot) {
		const now = Date.now();
		if (now < snapshot.staleAt) {
			return snapshot;
		}
		if (now < snapshot.expiresAt) {
			void fetchSnapshot(true);
			return snapshot;
		}
	}

	return fetchSnapshot(Boolean(snapshot));
}

export async function refreshTaskActivitiesSnapshot(): Promise<TaskActivitiesSnapshot> {
	return fetchSnapshot(Boolean(state.snapshot));
}

export async function prefetchTaskActivitiesSnapshot(): Promise<TaskActivitiesSnapshot> {
	return loadTaskActivitiesSnapshot();
}

export function getTaskActivitiesStoreState(): TaskActivitiesStoreState {
	return state;
}

export function subscribeTaskActivitiesStore(
	listener: TaskActivitiesStoreListener,
): () => void {
	listeners.add(listener);
	return () => {
		listeners.delete(listener);
	};
}

/**
 * Cancel a task activity. Dispatches to the correct API based on cancelTarget.mode.
 * After cancellation, refreshes the snapshot.
 */
export async function cancelTaskActivity(
	activity: TaskActivityItem,
): Promise<void> {
	const target = activity.cancelTarget;
	if (!target) {
		throw new Error("该任务无可取消目标");
	}
	if (target.mode === "intelligent") {
		await cancelIntelligentTask(target.taskId);
	} else {
		throw new Error(`不支持的取消模式：${target.mode}`);
	}
	await refreshTaskActivitiesSnapshot();
}
