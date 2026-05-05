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
	/**
	 * 当存在运行中或待处理的任务时，以该间隔（毫秒）自动刷新数据。
	 * 所有任务均为终态时停止轮询。
	 */
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
		idlePollingIntervalMs,
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
		if (!idlePollingIntervalMs || idlePollingIntervalMs <= 0) return;
		if (hasActiveTasks) return;
		if (!isPageVisible || document.hidden) return;
		const timer = window.setInterval(() => {
			if (document.hidden) return;
			void refreshTaskActivitiesSnapshot();
		}, idlePollingIntervalMs);
		return () => {
			window.clearInterval(timer);
		};
	}, [isPageVisible, idlePollingIntervalMs, hasActiveTasks]);

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
