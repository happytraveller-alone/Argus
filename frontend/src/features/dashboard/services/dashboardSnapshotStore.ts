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
	rangeDays: 7 | 14 | 30;
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
let inFlightRangeDays: 7 | 14 | 30 = 14;

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
	rangeDays: 7 | 14 | 30,
): DashboardSnapshot {
	const fetchedAt = Date.now();
	return {
		data,
		fetchedAt,
		staleAt: fetchedAt + STALE_MS,
		expiresAt: fetchedAt + MAX_AGE_MS,
		topN,
		rangeDays,
	};
}

async function requestSnapshot(
	topN: number,
	rangeDays: 7 | 14 | 30,
): Promise<DashboardSnapshot> {
	const data = await api.getDashboardSnapshot(topN, rangeDays);
	return buildSnapshot(data, topN, rangeDays);
}

async function fetchSnapshot(
	background: boolean,
	topN: number,
	rangeDays: 7 | 14 | 30,
): Promise<DashboardSnapshot> {
	if (
		inFlightRequest &&
		inFlightTopN === topN &&
		inFlightRangeDays === rangeDays
	) {
		return inFlightRequest;
	}

	inFlightTopN = topN;
	inFlightRangeDays = rangeDays;
	if (background) {
		setState({ refreshing: true, error: null });
	} else {
		setState({ loading: true, refreshing: false, error: null });
	}

	inFlightRequest = requestSnapshot(topN, rangeDays)
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
			if (
				state.snapshot &&
				state.snapshot.topN === topN &&
				state.snapshot.rangeDays === rangeDays
			) {
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
	rangeDays?: 7 | 14 | 30;
}): Promise<DashboardSnapshot> {
	const force = Boolean(options?.force);
	const requestedTopN = Number(options?.topN ?? 10);
	const topN = Number.isFinite(requestedTopN)
		? Math.min(Math.max(Math.floor(requestedTopN), 1), 50)
		: 10;
	const requestedRangeDays = options?.rangeDays;
	const rangeDays =
		requestedRangeDays === 7 || requestedRangeDays === 30 ? requestedRangeDays : 14;
	const snapshot = state.snapshot;
	const snapshotMatchesRequest = Boolean(
		snapshot && snapshot.topN === topN && snapshot.rangeDays === rangeDays,
	);

	if (!force && snapshot && snapshotMatchesRequest) {
		const now = Date.now();
		if (now < snapshot.staleAt) {
			return snapshot;
		}
		if (now < snapshot.expiresAt) {
			void fetchSnapshot(true, topN, rangeDays);
			return snapshot;
		}
	}

	return fetchSnapshot(Boolean(snapshot && snapshotMatchesRequest), topN, rangeDays);
}

export async function refreshDashboardSnapshot(
	topN = 10,
	rangeDays: 7 | 14 | 30 = 14,
): Promise<DashboardSnapshot> {
	const requestedTopN = Number(topN);
	const safeTopN = Number.isFinite(requestedTopN)
		? Math.min(Math.max(Math.floor(requestedTopN), 1), 50)
		: 10;
	const safeRangeDays = rangeDays === 7 || rangeDays === 30 ? rangeDays : 14;
	return fetchSnapshot(Boolean(state.snapshot), safeTopN, safeRangeDays);
}

export async function prefetchDashboardSnapshot(
	topN = 10,
	rangeDays: 7 | 14 | 30 = 14,
): Promise<DashboardSnapshot> {
	return loadDashboardSnapshot({ topN, rangeDays });
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
