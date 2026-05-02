import type { AgentFinding } from "@/shared/api/agentTasks";

export type FindingSource = "static" | "agent";
export type StaticFindingEngine = "opengrep" | "gitleaks" | "bandit" | "phpstan" | "pmd";

export type FindingDetailLocationState = {
	fromTaskDetail: true;
	preferHistoryBack: true;
	agentFindingSnapshot?: AgentFinding | null;
};

function normalizeSegment(value: string): string {
	return encodeURIComponent(String(value || "").trim());
}

export function buildFindingDetailPath(params: {
	source: FindingSource;
	taskId: string;
	findingId: string;
	engine?: StaticFindingEngine;
}): string {
	const source = String(params.source || "").trim();
	const taskId = String(params.taskId || "").trim();
	const findingId = String(params.findingId || "").trim();
	const basePath = `/finding-detail/${normalizeSegment(source)}/${normalizeSegment(taskId)}/${normalizeSegment(findingId)}`;
	if (source !== "static") return basePath;
	const engine = String(params.engine || "").trim();
	if (
		engine !== "opengrep" &&
		engine !== "gitleaks" &&
		engine !== "bandit" &&
		engine !== "phpstan" &&
		engine !== "pmd"
	) {
		return basePath;
	}
	return `${basePath}?engine=${normalizeSegment(engine)}`;
}

export function normalizeReturnToPath(rawValue: string | null | undefined): string {
	const value = String(rawValue || "").trim();
	if (!value.startsWith("/")) return "";
	if (value.startsWith("//")) return "";
	return value;
}

export function appendReturnTo(route: string, returnTo: string): string {
	const normalizedRoute = String(route || "").trim();
	if (!normalizedRoute) return normalizedRoute;

	const normalizedReturnTo = normalizeReturnToPath(returnTo);
	if (!normalizedReturnTo) return normalizedRoute;

	const [pathPart, queryPart = ""] = normalizedRoute.split("?");
	const queryParams = new URLSearchParams(queryPart);
	queryParams.set("returnTo", normalizedReturnTo);
	const query = queryParams.toString();
	return query ? `${pathPart}?${query}` : pathPart;
}

export function sanitizeAgentAuditReturnTo(route: string): string {
	const normalizedRoute = String(route || "").trim();
	if (!normalizedRoute) return "";

	const [pathPart, queryPart = ""] = normalizedRoute.split("?");
	const queryParams = new URLSearchParams(queryPart);
	queryParams.delete("detailType");
	queryParams.delete("detailId");
	const query = queryParams.toString();
	return query ? `${pathPart}?${query}` : pathPart;
}

export function buildFindingDetailLocationState(
	snapshot?: AgentFinding | null,
): FindingDetailLocationState {
	const baseState: FindingDetailLocationState = {
		fromTaskDetail: true,
		preferHistoryBack: true,
	};
	if (snapshot) {
		baseState.agentFindingSnapshot = snapshot;
	}
	return baseState;
}

export function buildProjectCodeBrowserRoute(params: {
	projectId: string;
	filePath?: string | null;
	line?: number | null;
}): string {
	const projectId = String(params.projectId || "").trim();
	const basePath = `/projects/${normalizeSegment(projectId)}/code-browser`;
	const searchParams = new URLSearchParams();

	const filePath = String(params.filePath || "").trim();
	if (filePath) {
		searchParams.set("file", filePath);
	}

	if (
		typeof params.line === "number" &&
		Number.isFinite(params.line) &&
		params.line > 0
	) {
		searchParams.set("line", String(Math.trunc(params.line)));
	}

	const query = searchParams.toString();
	return query ? `${basePath}?${query}` : basePath;
}

export function isFindingDetailLocationState(
	value: unknown,
): value is FindingDetailLocationState {
	if (!value || typeof value !== "object") return false;
	const candidate = value as Record<string, unknown>;
	return (
		candidate.fromTaskDetail === true &&
		candidate.preferHistoryBack === true
	);
}

export function resolveFindingDetailBackTarget(params: {
	returnTo: string | null | undefined;
	hasHistory: boolean;
	state: unknown;
}): string | -1 {
	const normalizedReturnTo = normalizeReturnToPath(params.returnTo);
	if (normalizedReturnTo) {
		return normalizedReturnTo;
	}
	if (params.hasHistory && isFindingDetailLocationState(params.state)) {
		return -1;
	}
	if (params.hasHistory) {
		return -1;
	}
	return "/dashboard";
}
