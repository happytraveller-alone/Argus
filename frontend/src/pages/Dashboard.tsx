import {
	lazy,
	startTransition,
	Suspense,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";
import { toast } from "sonner";
import DeferredSection from "@/components/performance/DeferredSection";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveCweDisplay } from "@/shared/security/cweCatalog";
import type { DashboardSnapshotResponse } from "@/shared/types";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";
import { loadDashboardSnapshot } from "@/features/dashboard/services/dashboardSnapshotStore";

const DashboardCommandCenter = lazy(
	() => import("@/features/dashboard/components/DashboardCommandCenter"),
);

type RangeDays = 7 | 14 | 30;

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
	engine_breakdown: [],
	project_hotspots: [],
	language_risk: [],
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
			<div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
				<Skeleton className="h-[22rem] rounded-3xl xl:col-span-8" />
				<div className="grid gap-4 xl:col-span-4">
					<Skeleton className="h-[16rem] rounded-3xl" />
					<Skeleton className="h-[18rem] rounded-3xl" />
				</div>
			</div>
			<div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
				<Skeleton className="h-[24rem] rounded-3xl xl:col-span-7" />
				<Skeleton className="h-[24rem] rounded-3xl xl:col-span-5" />
			</div>
			<div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
				<Skeleton className="h-[24rem] rounded-3xl xl:col-span-5" />
				<Skeleton className="h-[24rem] rounded-3xl xl:col-span-7" />
			</div>
		</div>
	);
}

function normalizeSnapshot(snapshot: DashboardSnapshotResponse): DashboardSnapshotResponse {
	return {
		...snapshot,
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

function hasSnapshotContent(snapshot: DashboardSnapshotResponse) {
	return (
		snapshot.summary.total_projects > 0 ||
		snapshot.daily_activity.length > 0 ||
		snapshot.project_hotspots.length > 0 ||
		snapshot.language_risk.length > 0 ||
		snapshot.cwe_distribution.length > 0
	);
}

export default function Dashboard() {
	const [snapshot, setSnapshot] = useState<DashboardSnapshotResponse>(EMPTY_SNAPSHOT);
	const [loading, setLoading] = useState(true);
	const [rangeDays, setRangeDays] = useState<RangeDays>(14);
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
							force: true,
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
				toast.error("数据加载失败");
			}
		},
		[rangeDays],
	);

	useEffect(() => {
		void loadDashboardData();

		const timer = window.setInterval(() => {
			void loadDashboardData({ silent: true });
		}, 15000);

		return () => {
			window.clearInterval(timer);
		};
	}, [loadDashboardData]);

	const handleRangeDaysChange = useCallback((value: RangeDays) => {
		startTransition(() => {
			setRangeDays(value);
		});
	}, []);

	const showFallback = loading && !hasSnapshotContent(snapshot);

	return (
		<div className="min-h-screen space-y-6 bg-background p-6 font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			{loading ? (
				<div className="relative z-10 text-xs text-muted-foreground">
					同步最新数据中...
				</div>
			) : null}

			<DeferredSection minHeight={1600} priority>
				{showFallback ? (
					<DashboardFallback />
				) : (
					<Suspense fallback={<DashboardFallback />}>
						<DashboardCommandCenter
							snapshot={snapshot}
							rangeDays={rangeDays}
							onRangeDaysChange={handleRangeDaysChange}
						/>
					</Suspense>
				)}
			</DeferredSection>
		</div>
	);
}
