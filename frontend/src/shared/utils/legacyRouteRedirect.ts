export function buildOpengrepRulesRedirectPath(rawSearch: string): string {
	const search = String(rawSearch || "").trim();
	const queryParams = new URLSearchParams(
		search.startsWith("?") ? search.slice(1) : search,
	);
	queryParams.set("tab", "opengrep");
	const query = queryParams.toString();
	return query
		? `/scan-config/engines?${query}`
		: "/scan-config/engines?tab=opengrep";
}
