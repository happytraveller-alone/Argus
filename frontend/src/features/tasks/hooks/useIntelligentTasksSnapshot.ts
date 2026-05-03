import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { toIntelligentTaskActivity } from "@/features/tasks/services/intelligentTaskActivities";
import type { TaskActivityItem } from "@/features/tasks/services/taskActivities";
import {
	cancelIntelligentTask,
	listIntelligentTasks,
	type IntelligentTaskRecord,
} from "@/shared/api/intelligentTasks";

interface UseIntelligentTasksSnapshotOptions {
	pollingIntervalMs?: number;
	resolveProjectName?: (projectId: string) => string;
	limit?: number;
}

const ACTIVE_STATUSES: ReadonlySet<string> = new Set(["pending", "running"]);
const DEFAULT_POLLING_INTERVAL_MS = 3000;
const DEFAULT_LIMIT = 100;

export function useIntelligentTasksSnapshot(
	options: UseIntelligentTasksSnapshotOptions = {},
) {
	const {
		pollingIntervalMs = DEFAULT_POLLING_INTERVAL_MS,
		resolveProjectName,
		limit = DEFAULT_LIMIT,
	} = options;

	const [records, setRecords] = useState<IntelligentTaskRecord[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [isPageVisible, setIsPageVisible] = useState(() =>
		typeof document === "undefined" ? true : !document.hidden,
	);
	const recordsRef = useRef<IntelligentTaskRecord[]>([]);

	useEffect(() => {
		recordsRef.current = records;
	}, [records]);

	const resolveName = useCallback(
		(projectId: string) =>
			resolveProjectName ? resolveProjectName(projectId) : projectId,
		[resolveProjectName],
	);

	const fetchRecords = useCallback(async () => {
		try {
			const data = await listIntelligentTasks(limit);
			setRecords(
				data
					.slice()
					.sort(
						(a, b) =>
							new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
					),
			);
			setError(null);
		} catch (err) {
			const message =
				err instanceof Error ? err.message : "加载智能审计任务失败";
			setError(message);
		} finally {
			setLoading(false);
		}
	}, [limit]);

	useEffect(() => {
		void fetchRecords();
	}, [fetchRecords]);

	const hasActiveTasks = useMemo(
		() => records.some((r) => ACTIVE_STATUSES.has(r.status)),
		[records],
	);

	useEffect(() => {
		if (!pollingIntervalMs || !hasActiveTasks) return;
		if (typeof document !== "undefined" && document.hidden) return;
		if (!isPageVisible) return;
		const timer = window.setInterval(() => {
			if (typeof document !== "undefined" && document.hidden) return;
			void fetchRecords();
		}, pollingIntervalMs);
		return () => {
			window.clearInterval(timer);
		};
	}, [isPageVisible, pollingIntervalMs, hasActiveTasks, fetchRecords]);

	useEffect(() => {
		if (typeof window === "undefined" || typeof document === "undefined") {
			return;
		}
		const handleVisibilityChange = () => {
			setIsPageVisible(!document.hidden);
			if (!document.hidden) {
				void fetchRecords();
			}
		};
		const handleFocus = () => {
			if (document.hidden) return;
			setIsPageVisible(true);
			void fetchRecords();
		};
		document.addEventListener("visibilitychange", handleVisibilityChange);
		window.addEventListener("focus", handleFocus);
		return () => {
			document.removeEventListener("visibilitychange", handleVisibilityChange);
			window.removeEventListener("focus", handleFocus);
		};
	}, [fetchRecords]);

	const refresh = useCallback(async () => {
		await fetchRecords();
	}, [fetchRecords]);

	const cancel = useCallback(async (taskId: string) => {
		const previous = recordsRef.current;
		setRecords((prev) =>
			prev.map((r) =>
				r.taskId === taskId ? { ...r, status: "cancelled" as const } : r,
			),
		);
		try {
			const updated = await cancelIntelligentTask(taskId);
			setRecords((prev) =>
				prev.map((r) => (r.taskId === taskId ? updated : r)),
			);
		} catch (err) {
			setRecords(previous);
			throw err;
		}
	}, []);

	const activities = useMemo<TaskActivityItem[]>(
		() => records.map((record) => toIntelligentTaskActivity(record, resolveName)),
		[records, resolveName],
	);

	return {
		activities,
		records,
		loading,
		error,
		refresh,
		cancel,
	};
}
