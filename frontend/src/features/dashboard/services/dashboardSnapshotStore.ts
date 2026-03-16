import { api } from "@/shared/api/database";
import type { DashboardSnapshotResponse } from "@/shared/types";

const STALE_MS = 30_000;
const MAX_AGE_MS = 5 * 60_000;

type DashboardSnapshotStoreListener = () => void;

export interface DashboardSnapshot {
	data: DashboardSnapshotResponse;
	fetchedAt: number;
	staleAt: number;
	expiresAt: number;
	topN: number;
}

export interface DashboardSnapshotStoreState {
	snapshot: DashboardSnapshot | null;
	loading: boolean;
	refreshing: boolean;
	error: string | null;
}

const listeners = new Set<DashboardSnapshotStoreListener>();

let state: DashboardSnapshotStoreState = {
	snapshot: null,
	loading: false,
	refreshing: false,
	error: null,
};

let inFlightRequest: Promise<DashboardSnapshot> | null = null;
let inFlightTopN = 10;

function emitChange() {
	for (const listener of listeners) {
		listener();
	}
}

function setState(nextState: Partial<DashboardSnapshotStoreState>) {
	state = {
		...state,
		...nextState,
	};
	emitChange();
}

function normalizeError(error: unknown): string {
	if (error instanceof Error) {
		return error.message || "加载仪表盘快照失败";
	}
	if (typeof error === "string" && error.trim()) {
		return error;
	}
	return "加载仪表盘快照失败";
}

function buildSnapshot(
	data: DashboardSnapshotResponse,
	topN: number,
): DashboardSnapshot {
	const fetchedAt = Date.now();
	return {
		data,
		fetchedAt,
		staleAt: fetchedAt + STALE_MS,
		expiresAt: fetchedAt + MAX_AGE_MS,
		topN,
	};
}

async function requestSnapshot(topN: number): Promise<DashboardSnapshot> {
	const data = await api.getDashboardSnapshot(topN);
	return buildSnapshot(data, topN);
}

async function fetchSnapshot(
	background: boolean,
	topN: number,
): Promise<DashboardSnapshot> {
	if (inFlightRequest && inFlightTopN === topN) {
		return inFlightRequest;
	}

	inFlightTopN = topN;
	if (background) {
		setState({ refreshing: true, error: null });
	} else {
		setState({ loading: true, refreshing: false, error: null });
	}

	inFlightRequest = requestSnapshot(topN)
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
			if (state.snapshot && state.snapshot.topN === topN) {
				return state.snapshot;
			}
			throw error;
		})
		.finally(() => {
			inFlightRequest = null;
		});

	return inFlightRequest;
}

export async function loadDashboardSnapshot(options?: {
	force?: boolean;
	topN?: number;
}): Promise<DashboardSnapshot> {
	const force = Boolean(options?.force);
	const requestedTopN = Number(options?.topN ?? 10);
	const topN = Number.isFinite(requestedTopN)
		? Math.min(Math.max(Math.floor(requestedTopN), 1), 50)
		: 10;
	const snapshot = state.snapshot;
	const snapshotMatchesTopN = Boolean(snapshot && snapshot.topN === topN);

	if (!force && snapshot && snapshotMatchesTopN) {
		const now = Date.now();
		if (now < snapshot.staleAt) {
			return snapshot;
		}
		if (now < snapshot.expiresAt) {
			void fetchSnapshot(true, topN);
			return snapshot;
		}
	}

	return fetchSnapshot(Boolean(snapshot && snapshotMatchesTopN), topN);
}

export async function refreshDashboardSnapshot(
	topN = 10,
): Promise<DashboardSnapshot> {
	const requestedTopN = Number(topN);
	const safeTopN = Number.isFinite(requestedTopN)
		? Math.min(Math.max(Math.floor(requestedTopN), 1), 50)
		: 10;
	return fetchSnapshot(Boolean(state.snapshot), safeTopN);
}

export async function prefetchDashboardSnapshot(
	topN = 10,
): Promise<DashboardSnapshot> {
	return loadDashboardSnapshot({ topN });
}

export function getDashboardSnapshotStoreState(): DashboardSnapshotStoreState {
	return state;
}

export function subscribeDashboardSnapshotStore(
	listener: DashboardSnapshotStoreListener,
): () => void {
	listeners.add(listener);
	return () => {
		listeners.delete(listener);
	};
}
