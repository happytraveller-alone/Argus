export type TaskFindingCategory = "static" | "intelligent";
export type TaskFindingSeverity =
	| "CRITICAL"
	| "HIGH"
	| "MEDIUM"
	| "LOW"
	| "UNKNOWN";
export type TaskFindingConfidence = "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";

export interface TaskFindingRow {
	id: string;
	taskId: string;
	taskCategory: TaskFindingCategory;
	title: string;
	typeLabel: string;
	typeTooltip?: string | null;
	filePath: string;
	line: number | null;
	severity: TaskFindingSeverity;
	confidence: TaskFindingConfidence;
	route: string | null;
	createdAt: string | null;
}

export type TaskFindingSeverityFilter = TaskFindingSeverity | "ALL";
export type TaskFindingConfidenceFilter = TaskFindingConfidence | "ALL";

export function normalizeTaskFindingSeverity(
	value: string | null | undefined,
): TaskFindingSeverity {
	const normalized = String(value || "")
		.trim()
		.toUpperCase();
	if (normalized.includes("CRITICAL")) return "CRITICAL";
	if (normalized.includes("HIGH") || normalized === "ERROR") return "HIGH";
	if (normalized.includes("MEDIUM") || normalized === "WARNING")
		return "MEDIUM";
	if (normalized.includes("LOW") || normalized === "INFO") return "LOW";
	return "UNKNOWN";
}

export function normalizeTaskFindingConfidence(
	value: string | number | null | undefined,
): TaskFindingConfidence {
	if (typeof value === "number" && Number.isFinite(value)) {
		if (value >= 0.8) return "HIGH";
		if (value >= 0.5) return "MEDIUM";
		if (value > 0) return "LOW";
		return "UNKNOWN";
	}

	const normalized = String(value || "")
		.trim()
		.toUpperCase();
	if (normalized === "HIGH") return "HIGH";
	if (normalized === "MEDIUM") return "MEDIUM";
	if (normalized === "LOW") return "LOW";
	return "UNKNOWN";
}

export function taskFindingSeverityRank(severity: TaskFindingSeverity): number {
	if (severity === "CRITICAL") return 5;
	if (severity === "HIGH") return 4;
	if (severity === "MEDIUM") return 3;
	if (severity === "LOW") return 2;
	return 1;
}

export function taskFindingConfidenceRank(
	confidence: TaskFindingConfidence,
): number {
	if (confidence === "HIGH") return 3;
	if (confidence === "MEDIUM") return 2;
	if (confidence === "LOW") return 1;
	return 0;
}

function toTimestamp(value: string | null | undefined): number {
	const timestamp = new Date(String(value || "")).getTime();
	return Number.isFinite(timestamp) ? timestamp : 0;
}

function compareBasePriority(a: TaskFindingRow, b: TaskFindingRow): number {
	const severityDelta =
		taskFindingSeverityRank(b.severity) - taskFindingSeverityRank(a.severity);
	if (severityDelta !== 0) return severityDelta;

	const confidenceDelta =
		taskFindingConfidenceRank(b.confidence) -
		taskFindingConfidenceRank(a.confidence);
	if (confidenceDelta !== 0) return confidenceDelta;

	return 0;
}

function compareStaticRows(a: TaskFindingRow, b: TaskFindingRow): number {
	const baseDelta = compareBasePriority(a, b);
	if (baseDelta !== 0) return baseDelta;

	const pathDelta = a.filePath.localeCompare(b.filePath, "zh-CN");
	if (pathDelta !== 0) return pathDelta;

	const lineA = a.line ?? Number.MAX_SAFE_INTEGER;
	const lineB = b.line ?? Number.MAX_SAFE_INTEGER;
	if (lineA !== lineB) return lineA - lineB;

	return a.id.localeCompare(b.id, "zh-CN");
}

function compareAgentRows(a: TaskFindingRow, b: TaskFindingRow): number {
	const baseDelta = compareBasePriority(a, b);
	if (baseDelta !== 0) return baseDelta;

	const timeDelta = toTimestamp(b.createdAt) - toTimestamp(a.createdAt);
	if (timeDelta !== 0) return timeDelta;

	const pathDelta = a.filePath.localeCompare(b.filePath, "zh-CN");
	if (pathDelta !== 0) return pathDelta;

	const lineA = a.line ?? Number.MAX_SAFE_INTEGER;
	const lineB = b.line ?? Number.MAX_SAFE_INTEGER;
	if (lineA !== lineB) return lineA - lineB;

	return a.id.localeCompare(b.id, "zh-CN");
}

export function sortTaskFindings(rows: TaskFindingRow[]): TaskFindingRow[] {
	return [...rows].sort((a, b) => {
		const aIsStatic = a.taskCategory === "static";
		const bIsStatic = b.taskCategory === "static";
		if (aIsStatic && bIsStatic) return compareStaticRows(a, b);
		if (!aIsStatic && !bIsStatic) return compareAgentRows(a, b);
		if (aIsStatic !== bIsStatic) return aIsStatic ? 1 : -1;
		return a.id.localeCompare(b.id, "zh-CN");
	});
}

export function filterTaskFindings(
	rows: TaskFindingRow[],
	severity: TaskFindingSeverityFilter,
	confidence: TaskFindingConfidenceFilter,
): TaskFindingRow[] {
	return rows.filter((row) => {
		if (severity !== "ALL" && row.severity !== severity) return false;
		if (confidence !== "ALL" && row.confidence !== confidence) return false;
		return true;
	});
}

export function paginateTaskFindings(
	rows: TaskFindingRow[],
	page: number,
	pageSize: number,
): {
	items: TaskFindingRow[];
	page: number;
	pageSize: number;
	startIndex: number;
	totalItems: number;
	totalPages: number;
} {
	const safePageSize = Math.max(1, Math.floor(pageSize) || 1);
	const totalItems = rows.length;
	const totalPages = Math.max(1, Math.ceil(totalItems / safePageSize));
	const safePage = Math.max(1, Math.floor(page) || 1);
	const startIndex = (safePage - 1) * safePageSize;
	return {
		items: rows.slice(startIndex, startIndex + safePageSize),
		page: safePage,
		pageSize: safePageSize,
		startIndex,
		totalItems,
		totalPages,
	};
}
