import { useCallback, useEffect, useMemo, useState } from "react";
import {
	getTaskActivitiesStoreState,
	loadTaskActivitiesSnapshot,
	refreshTaskActivitiesSnapshot,
	subscribeTaskActivitiesStore,
} from "@/features/tasks/services/taskActivitiesStore";

interface UseTaskActivitiesSnapshotOptions {
	autoLoad?: boolean;
	forceInitial?: boolean;
	pollingIntervalMs?: number;
	idlePollingIntervalMs?: number;
}

const ACTIVE_STATUSES = new Set(["running", "pending"]);

export function useTaskActivitiesSnapshot(
	options: UseTaskActivitiesSnapshotOptions = {},
) {
	const {
		autoLoad = true,
		forceInitial = false,
		pollingIntervalMs,
	} = options;
	const [storeState, setStoreState] = useState(() =>
		getTaskActivitiesStoreState(),
	);
	const [isPageVisible, setIsPageVisible] = useState(() =>
		typeof document === "undefined" ? true : !document.hidden,
	);

	useEffect(() => {
		return subscribeTaskActivitiesStore(() => {
			setStoreState(getTaskActivitiesStoreState());
		});
	}, []);

	useEffect(() => {
		if (!autoLoad) return;
		void loadTaskActivitiesSnapshot({ force: forceInitial });
	}, [autoLoad, forceInitial]);

	const hasActiveTasks = useMemo(
		() =>
			(storeState.snapshot?.activities ?? []).some((a) =>
				ACTIVE_STATUSES.has(a.status),
			),
		[storeState.snapshot?.activities],
	);

	useEffect(() => {
		if (!pollingIntervalMs || !hasActiveTasks || document.hidden) return;
		if (!isPageVisible) return;
		const timer = window.setInterval(() => {
			if (document.hidden) return;
			void refreshTaskActivitiesSnapshot();
		}, pollingIntervalMs);
		return () => {
			window.clearInterval(timer);
		};
	}, [isPageVisible, pollingIntervalMs, hasActiveTasks]);

	useEffect(() => {
		const handleVisibilityChange = () => {
			setIsPageVisible(!document.hidden);
			if (!document.hidden) {
				void refreshTaskActivitiesSnapshot();
			}
		};
		const handleFocus = () => {
			if (document.hidden) return;
			setIsPageVisible(true);
			void refreshTaskActivitiesSnapshot();
		};

		document.addEventListener("visibilitychange", handleVisibilityChange);
		window.addEventListener("focus", handleFocus);
		return () => {
			document.removeEventListener("visibilitychange", handleVisibilityChange);
			window.removeEventListener("focus", handleFocus);
		};
	}, []);

	const refresh = useCallback(() => {
		return refreshTaskActivitiesSnapshot();
	}, []);

	return {
		...storeState,
		projects: storeState.snapshot?.projects || [],
		activities: storeState.snapshot?.activities || [],
		refresh,
	};
}
