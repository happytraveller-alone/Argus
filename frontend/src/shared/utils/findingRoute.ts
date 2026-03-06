export type FindingSource = "static" | "agent";
export type StaticFindingEngine = "opengrep" | "gitleaks";

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
	if (engine !== "opengrep" && engine !== "gitleaks") return basePath;
	return `${basePath}?engine=${normalizeSegment(engine)}`;
}

export function normalizeReturnToPath(rawValue: string | null | undefined): string {
	const value = String(rawValue || "").trim();
	if (!value.startsWith("/")) return "";
	if (value.startsWith("//")) return "";
	return value;
}

export function appendReturnTo(
	route: string,
	returnTo: string,
): string {
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
