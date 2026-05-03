import type {
	IntelligentTaskFinding,
	IntelligentTaskRecord,
	IntelligentTaskStatus,
} from "@/shared/api/intelligentTasks";
import type { TaskActivityItem } from "./taskActivities";

const KNOWN_SEVERITY_KEYS = ["critical", "high", "medium", "low"] as const;
type KnownSeverity = (typeof KNOWN_SEVERITY_KEYS)[number];
const KNOWN_SEVERITY_SET = new Set<string>(KNOWN_SEVERITY_KEYS);

export function mapIntelligentStatus(status: IntelligentTaskStatus): string {
	return status;
}

function bucketSeverity(findings: IntelligentTaskFinding[]) {
	const counts: Record<KnownSeverity, number> & { total: number } = {
		critical: 0,
		high: 0,
		medium: 0,
		low: 0,
		total: findings.length,
	};
	for (const f of findings) {
		const key = (f.severity ?? "").toLowerCase();
		if (KNOWN_SEVERITY_SET.has(key)) {
			counts[key as KnownSeverity] += 1;
		}
	}
	return counts;
}

export function toIntelligentTaskActivity(
	record: IntelligentTaskRecord,
): TaskActivityItem {
	return {
		id: `intelligent-${record.taskId}`,
		projectName: String(record.projectName || "").trim() || "-",
		kind: "intelligent_audit",
		sourceMode: "intelligent",
		status: mapIntelligentStatus(record.status),
		agentFindingStats: bucketSeverity(record.findings ?? []),
		createdAt: record.createdAt,
		startedAt: record.startedAt ?? null,
		completedAt: record.completedAt ?? null,
		durationMs: record.durationMs ?? null,
		route: `/agent-audit/${record.taskId}`,
		cancelTarget: { mode: "intelligent", taskId: record.taskId },
	};
}
