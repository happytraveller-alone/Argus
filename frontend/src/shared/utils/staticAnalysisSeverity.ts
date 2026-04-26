export type NormalizedSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export function normalizeStaticAnalysisSeverity(
	severity?: string | null,
): NormalizedSeverity | null {
	const normalized = String(severity || "")
		.trim()
		.toUpperCase();
	if (normalized === "CRITICAL") return "HIGH";
	if (normalized === "HIGH") return "MEDIUM";
	if (
		normalized === "ERROR" ||
		normalized === "WARNING" ||
		normalized === "MEDIUM"
	) {
		return "LOW";
	}
	return null;
}
