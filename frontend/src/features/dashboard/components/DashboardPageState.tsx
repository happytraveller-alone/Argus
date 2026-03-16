import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { DashboardSnapshotResponse } from "@/shared/types";

export type DashboardPageStateVariant =
	| "idle"
	| "blocking-error"
	| "inline-error";

export interface ResolveDashboardPageStateInput {
	loading: boolean;
	error: string | null;
	snapshot: DashboardSnapshotResponse;
}

export interface DashboardPageState {
	variant: DashboardPageStateVariant;
	message: string | null;
	showFallback: boolean;
	hasSnapshotContent: boolean;
}

export interface DashboardPageFeedbackProps {
	state: DashboardPageState;
	onRetry: () => void;
	retrying?: boolean;
}

export function hasDashboardSnapshotContent(snapshot: DashboardSnapshotResponse) {
	return (
		snapshot.summary.total_projects > 0 ||
		snapshot.daily_activity.length > 0 ||
		snapshot.project_hotspots.length > 0 ||
		snapshot.language_risk.length > 0 ||
		snapshot.cwe_distribution.length > 0
	);
}

function normalizeDashboardErrorMessage(error: string | null) {
	return error?.trim() || "加载仪表盘快照失败";
}

export function resolveDashboardPageState({
	loading,
	error,
	snapshot,
}: ResolveDashboardPageStateInput): DashboardPageState {
	const hasSnapshotContent = hasDashboardSnapshotContent(snapshot);

	if (loading && !hasSnapshotContent) {
		return {
			variant: "idle",
			message: null,
			showFallback: true,
			hasSnapshotContent,
		};
	}

	if (error && !hasSnapshotContent) {
		return {
			variant: "blocking-error",
			message: normalizeDashboardErrorMessage(error),
			showFallback: false,
			hasSnapshotContent,
		};
	}

	if (error) {
		return {
			variant: "inline-error",
			message: normalizeDashboardErrorMessage(error),
			showFallback: false,
			hasSnapshotContent,
		};
	}

	return {
		variant: "idle",
		message: null,
		showFallback: false,
		hasSnapshotContent,
	};
}

export function DashboardPageFeedback({
	state,
	onRetry,
	retrying = false,
}: DashboardPageFeedbackProps) {
	if (state.variant === "idle") {
		return null;
	}

	if (state.variant === "blocking-error") {
		return (
			<div className="cyber-card rounded-3xl border border-rose-500/30 bg-slate-950/80 p-6 shadow-2xl shadow-rose-950/20">
				<Alert
					variant="destructive"
					className="border border-rose-500/20 bg-rose-500/10"
				>
					<AlertTriangle className="h-5 w-5" />
					<AlertTitle>仪表盘数据加载失败</AlertTitle>
					<AlertDescription>
						<p>{state.message}</p>
						<p>请稍后重试；如果问题持续出现，请检查后端服务与 API 代理配置。</p>
					</AlertDescription>
				</Alert>
				<div className="mt-5">
					<Button type="button" onClick={onRetry} disabled={retrying}>
						<RefreshCw className={retrying ? "animate-spin" : ""} />
						重试加载
					</Button>
				</div>
			</div>
		);
	}

	return (
		<Alert className="border border-amber-500/30 bg-amber-500/10 text-amber-50">
			<AlertTriangle className="h-5 w-5 text-amber-300" />
			<AlertTitle>最新数据刷新失败</AlertTitle>
			<AlertDescription>
				<p>当前展示的是上次成功同步的数据。</p>
				<p>{state.message}</p>
				<div className="pt-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={onRetry}
						disabled={retrying}
						className="border-amber-300/30 text-amber-50 hover:bg-amber-500/10"
					>
						<RefreshCw className={retrying ? "animate-spin" : ""} />
						重试加载
					</Button>
				</div>
			</AlertDescription>
		</Alert>
	);
}
