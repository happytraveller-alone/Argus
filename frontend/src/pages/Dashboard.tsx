import {
	lazy,
	startTransition,
	Suspense,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import DeferredSection from "@/components/performance/DeferredSection";
import { Skeleton } from "@/components/ui/skeleton";
import {
	DashboardPageFeedback,
	resolveDashboardPageState,
} from "@/features/dashboard/components/DashboardPageState";
import {
	getDashboardSnapshotStoreState,
	loadDashboardSnapshot,
	subscribeDashboardSnapshotStore,
} from "@/features/dashboard/services/dashboardSnapshotStore";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import type { DashboardSnapshotResponse } from "@/shared/types";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";

const DashboardCommandCenter = lazy(
	() => import("@/features/dashboard/components/DashboardCommandCenter"),
);

type RangeDays = 7 | 14 | 30;
const DASHBOARD_REFRESH_INTERVAL_MS = 30_000;

function createEmptyTaskStatusByScanType() {
	return {
		pending: { static: 0, intelligent: 0 },
		running: { static: 0, intelligent: 0 },
		completed: { static: 0, intelligent: 0 },
		failed: { static: 0, intelligent: 0 },
		interrupted: { static: 0, intelligent: 0 },
		cancelled: { static: 0, intelligent: 0 },
	};
}

const EMPTY_SNAPSHOT: DashboardSnapshotResponse = {
	generated_at: "",
	total_scan_duration_ms: 0,
	scan_runs: [],
	vulns: [],
	rule_confidence: [],
	rule_confidence_by_language: [],
	cwe_distribution: [],
	summary: {
		total_projects: 0,
		current_effective_findings: 0,
		current_verified_findings: 0,
		total_model_tokens: 0,
		false_positive_rate: 0,
		scan_success_rate: 0,
		avg_scan_duration_ms: 0,
		window_scanned_projects: 0,
		window_new_effective_findings: 0,
		window_verified_findings: 0,
		window_false_positive_rate: 0,
		window_scan_success_rate: 0,
		window_avg_scan_duration_ms: 0,
	},
	daily_activity: [],
	verification_funnel: {
		raw_findings: 0,
		effective_findings: 0,
		verified_findings: 0,
		false_positive_count: 0,
	},
	task_status_breakdown: {
		pending: 0,
		running: 0,
		completed: 0,
		failed: 0,
		interrupted: 0,
		cancelled: 0,
	},
	task_status_by_scan_type: createEmptyTaskStatusByScanType(),
	engine_breakdown: [],
	project_hotspots: [],
	language_risk: [],
	recent_tasks: [],
	project_risk_distribution: [],
	verified_vulnerability_types: [],
	static_engine_rule_totals: [],
	language_loc_distribution: [],
};

function DashboardFallback() {
	return (
		<div className="space-y-4">
			<div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
				{Array.from({ length: 6 }).map((_, index) => (
					<div key={index} className="cyber-card rounded-3xl p-4">
						<Skeleton className="h-4 w-24" />
						<Skeleton className="mt-4 h-9 w-24" />
						<Skeleton className="mt-3 h-4 w-full" />
						<Skeleton className="mt-4 h-10 w-full" />
					</div>
				))}
			</div>
			<div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
				<Skeleton className="h-[22rem] rounded-3xl lg:col-span-7" />
				<Skeleton className="h-[18rem] rounded-3xl lg:col-span-5" />
				<Skeleton className="h-[24rem] rounded-3xl lg:col-span-7" />
				<Skeleton className="h-[22rem] rounded-3xl lg:col-span-5" />
				<Skeleton className="h-[24rem] rounded-3xl lg:col-span-7" />
				<Skeleton className="h-[22rem] rounded-3xl lg:col-span-5" />
			</div>
			<Skeleton className="h-[24rem] rounded-3xl" />
			<Skeleton className="h-[24rem] rounded-3xl" />
		</div>
	);
}

export function normalizeSnapshot(
	snapshot: DashboardSnapshotResponse,
): DashboardSnapshotResponse {
	const rawTaskStatusByScanType =
		snapshot.task_status_by_scan_type || createEmptyTaskStatusByScanType();

	const normalizeStatusBreakdown = (
		statusKey: keyof ReturnType<typeof createEmptyTaskStatusByScanType>,
	) => {
		const current = rawTaskStatusByScanType[statusKey] as
			| { static?: number; intelligent?: number }
			| undefined;
		return {
			static: Math.max(Number(current.static || 0), 0),
			intelligent: Math.max(Number(current.intelligent || 0), 0),
		};
	};

	const taskStatusByScanType = {
		pending: normalizeStatusBreakdown("pending"),
		running: normalizeStatusBreakdown("running"),
		completed: normalizeStatusBreakdown("completed"),
		failed: normalizeStatusBreakdown("failed"),
		interrupted: normalizeStatusBreakdown("interrupted"),
		cancelled: normalizeStatusBreakdown("cancelled"),
	};

	return {
		...snapshot,
		task_status_by_scan_type: {
			pending: {
				...createEmptyTaskStatusByScanType().pending,
				...(taskStatusByScanType.pending || {}),
			},
			running: {
				...createEmptyTaskStatusByScanType().running,
				...(taskStatusByScanType.running || {}),
			},
			completed: {
				...createEmptyTaskStatusByScanType().completed,
				...(taskStatusByScanType.completed || {}),
			},
			failed: {
				...createEmptyTaskStatusByScanType().failed,
				...(taskStatusByScanType.failed || {}),
			},
			interrupted: {
				...createEmptyTaskStatusByScanType().interrupted,
				...(taskStatusByScanType.interrupted || {}),
			},
			cancelled: {
				...createEmptyTaskStatusByScanType().cancelled,
				...(taskStatusByScanType.cancelled || {}),
			},
		},
		daily_activity: (snapshot.daily_activity || []).map((item) => ({
			...item,
			agent_findings: Math.max(Number(item.agent_findings || 0), 0),
			opengrep_findings: Math.max(Number(item.opengrep_findings || 0), 0),
			gitleaks_findings: Math.max(Number(item.gitleaks_findings || 0), 0),
			bandit_findings: Math.max(Number(item.bandit_findings || 0), 0),
			phpstan_findings: Math.max(Number(item.phpstan_findings || 0), 0),
			static_findings: Math.max(Number(item.static_findings || 0), 0),
			intelligent_verified_findings: Math.max(
				Number(item.intelligent_verified_findings || 0),
				0,
			),
			total_new_findings: Math.max(Number(item.total_new_findings || 0), 0),
		})),
		cwe_distribution: (snapshot.cwe_distribution || []).map((item) => {
			const cweDisplay = resolveCweDisplay({
				cwe: item.cwe_id,
				fallbackLabel: item.cwe_name || item.cwe_id || "CWE-UNKNOWN",
			});
			return {
				...item,
				cwe_id: item.cwe_id || cweDisplay.cweId || "CWE-UNKNOWN",
				cwe_name: cweDisplay.label,
				total_findings: Math.max(Number(item.total_findings || 0), 0),
				opengrep_findings: Math.max(Number(item.opengrep_findings || 0), 0),
				agent_findings: Math.max(Number(item.agent_findings || 0), 0),
				bandit_findings: Math.max(Number(item.bandit_findings || 0), 0),
			};
		}),
	};
}

export default function Dashboard() {
	const [snapshot, setSnapshot] = useState<DashboardSnapshotResponse>(EMPTY_SNAPSHOT);
	const [loading, setLoading] = useState(true);
	const [rangeDays, setRangeDays] = useState<RangeDays>(14);
	const [isPageVisible, setIsPageVisible] = useState(() =>
		typeof document === "undefined" ? true : !document.hidden,
	);
	const [storeState, setStoreState] = useState(() =>
		getDashboardSnapshotStoreState(),
	);
	const requestSeqRef = useRef(0);

	const loadDashboardData = useCallback(
		async (options?: { silent?: boolean }) => {
			const requestSeq = requestSeqRef.current + 1;
			requestSeqRef.current = requestSeq;

			try {
				await runWithRefreshMode(
					async () => {
						const nextSnapshot = await loadDashboardSnapshot({
							topN: 10,
							rangeDays,
						});
						if (requestSeq !== requestSeqRef.current) {
							return;
						}
						setSnapshot(normalizeSnapshot(nextSnapshot.data));
					},
					{ ...options, setLoading },
				);
			} catch (error) {
				if (requestSeq !== requestSeqRef.current) {
					return;
				}
				console.error("仪表盘数据加载失败:", error);
			}
		},
		[rangeDays],
	);

	useEffect(() => {
		return subscribeDashboardSnapshotStore(() => {
			setStoreState(getDashboardSnapshotStoreState());
		});
	}, []);

	useEffect(() => {
		void loadDashboardData();
	}, [loadDashboardData]);

	useEffect(() => {
		const storeSnapshot = storeState.snapshot;
		if (!storeSnapshot) return;
		if (storeSnapshot.rangeDays !== rangeDays) return;
		setSnapshot(normalizeSnapshot(storeSnapshot.data));
	}, [rangeDays, storeState.snapshot]);

	useEffect(() => {
		const handleVisibilityChange = () => {
			setIsPageVisible(!document.hidden);
			if (document.hidden) {
				return;
			}
			void loadDashboardData({ silent: true });
		};
		const handleFocus = () => {
			if (document.hidden) return;
			setIsPageVisible(true);
			void loadDashboardData({ silent: true });
		};

		document.addEventListener("visibilitychange", handleVisibilityChange);
		window.addEventListener("focus", handleFocus);
		return () => {
			document.removeEventListener("visibilitychange", handleVisibilityChange);
			window.removeEventListener("focus", handleFocus);
		};
	}, [loadDashboardData]);

	useEffect(() => {
		if (!isPageVisible) return;
		const timer = window.setInterval(() => {
			if (document.hidden) {
				return;
			}
			void loadDashboardData({ silent: true });
		}, DASHBOARD_REFRESH_INTERVAL_MS);

		return () => {
			window.clearInterval(timer);
		};
	}, [isPageVisible, loadDashboardData]);

	const handleRangeDaysChange = useCallback((value: RangeDays) => {
		startTransition(() => {
			setRangeDays(value);
		});
	}, []);

	const handleRetry = useCallback(() => {
		void loadDashboardData();
	}, [loadDashboardData]);

	const pageState = resolveDashboardPageState({
		loading,
		error: storeState.error,
		snapshot,
	});

	return (
		<div className="min-h-screen space-y-6 bg-background p-6 font-mono relative xl:flex xl:h-[100dvh] xl:min-h-0 xl:flex-col xl:overflow-hidden">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			{loading ? (
				<div className="relative z-10 text-xs text-muted-foreground">
					同步最新数据中...
				</div>
			) : null}

			<DeferredSection className="xl:min-h-0 xl:flex-1" minHeight={960} priority>
				{pageState.showFallback ? (
					<div className="xl:h-full xl:min-h-0">
						<DashboardFallback />
					</div>
				) : pageState.variant === "blocking-error" ? (
					<div className="xl:flex xl:min-h-0 xl:h-full xl:flex-col">
						<DashboardPageFeedback
							state={pageState}
							onRetry={handleRetry}
							retrying={loading}
						/>
					</div>
				) : (
					<div className="space-y-4 xl:flex xl:h-full xl:min-h-0 xl:flex-col">
						<DashboardPageFeedback
							state={pageState}
							onRetry={handleRetry}
							retrying={loading}
						/>
						<div className="xl:min-h-0 xl:flex-1">
							<Suspense fallback={<DashboardFallback />}>
								<DashboardCommandCenter
									snapshot={snapshot}
									rangeDays={rangeDays}
									onRangeDaysChange={handleRangeDaysChange}
								/>
							</Suspense>
						</div>
					</div>
				)}
			</DeferredSection>
		</div>
	);
}
