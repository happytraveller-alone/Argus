export type NormalizedSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export function normalizeStaticAnalysisSeverity(
	severity?: string | null,
): NormalizedSeverity {
	const normalized = String(severity || "").trim().toUpperCase();
	if (normalized === "CRITICAL") return "CRITICAL";
	if (normalized === "HIGH") return "HIGH";
	if (
		normalized === "ERROR" ||
		normalized === "WARNING" ||
		normalized === "MEDIUM"
	) {
		return "MEDIUM";
	}
	return "LOW";
}
