import test from "node:test";
import assert from "node:assert/strict";

import { appendStaticScanBatchMarker } from "../src/shared/utils/staticScanBatch.ts";
import { apiClient } from "../src/shared/api/serverClient.ts";
import { fetchTaskActivities } from "../src/features/tasks/services/taskActivities.ts";

test("fetchTaskActivities aggregates opengrep static task severities by detail-page mapping", async () => {
	const originalGet = apiClient.get;
	const batchId = "static-batch-1";

	apiClient.get = (async (url: string) => {
		if (url.startsWith("/agent-tasks")) {
			return { data: [] };
		}
		if (url.startsWith("/static-tasks/tasks")) {
			return {
				data: [
					{
						id: "og-1",
						project_id: "project-1",
						name: appendStaticScanBatchMarker("静态分析-Opengrep", batchId),
						status: "completed",
						target_path: ".",
						total_findings: 5,
						error_count: 2,
						warning_count: 1,
						scan_duration_ms: 1000,
						files_scanned: 10,
						lines_scanned: 200,
						created_at: "2026-03-13T10:00:00.000Z",
						updated_at: "2026-03-13T10:01:00.000Z",
					},
				],
			};
		}
		throw new Error(`Unexpected apiClient.get call: ${url}`);
	}) as typeof apiClient.get;

	try {
		const activities = await fetchTaskActivities(
			[{ id: "project-1", name: "Demo Project" }] as any,
			20,
		);

		assert.equal(activities.length, 1);
		assert.deepEqual(activities[0]?.staticFindingStats, {
			critical: 0,
			high: 0,
			medium: 3,
			low: 2,
		});
	} finally {
		apiClient.get = originalGet;
	}
});

test("fetchTaskActivities clamps opengrep low severity count at zero", async () => {
	const originalGet = apiClient.get;
	const batchId = "static-batch-2";

	apiClient.get = (async (url: string) => {
		if (url.startsWith("/agent-tasks")) {
			return { data: [] };
		}
		if (url.startsWith("/static-tasks/tasks")) {
			return {
				data: [
					{
						id: "og-2",
						project_id: "project-2",
						name: appendStaticScanBatchMarker("静态分析-Opengrep", batchId),
						status: "completed",
						target_path: ".",
						total_findings: 2,
						error_count: 1,
						warning_count: 3,
						scan_duration_ms: 1000,
						files_scanned: 4,
						lines_scanned: 50,
						created_at: "2026-03-13T11:00:00.000Z",
						updated_at: "2026-03-13T11:01:00.000Z",
					},
				],
			};
		}
		throw new Error(`Unexpected apiClient.get call: ${url}`);
	}) as typeof apiClient.get;

	try {
		const activities = await fetchTaskActivities(
			[{ id: "project-2", name: "Clamp Project" }] as any,
			20,
		);

		assert.equal(activities.length, 1);
		assert.deepEqual(activities[0]?.staticFindingStats, {
			critical: 0,
			high: 0,
			medium: 4,
			low: 0,
		});
	} finally {
		apiClient.get = originalGet;
	}
});

test("fetchTaskActivities does not request removed static engine task endpoints", async () => {
	const originalGet = apiClient.get;
	const batchId = "static-batch-3";
	const calls: string[] = [];

	apiClient.get = (async (url: string) => {
		calls.push(url);
		if (url.startsWith("/agent-tasks")) {
			return { data: [] };
		}
		if (url.startsWith("/static-tasks/tasks")) {
			return {
				data: [
					{
						id: "og-3",
						project_id: "project-3",
						name: appendStaticScanBatchMarker("静态分析-Opengrep", batchId),
						status: "completed",
						target_path: ".",
						total_findings: 1,
						error_count: 0,
						warning_count: 1,
						scan_duration_ms: 1000,
						files_scanned: 2,
						lines_scanned: 20,
						created_at: "2026-03-13T12:00:00.000Z",
						updated_at: "2026-03-13T12:01:00.000Z",
					},
				],
			};
		}
		throw new Error(`Unexpected apiClient.get call: ${url}`);
	}) as typeof apiClient.get;

	try {
		const activities = await fetchTaskActivities(
			[{ id: "project-3", name: "Graceful Project" }] as any,
			20,
		);

		assert.equal(activities.length, 1);
		assert.equal(activities[0]?.projectName, "Graceful Project");
		assert.deepEqual(activities[0]?.staticFindingStats, {
			critical: 0,
			high: 0,
			medium: 1,
			low: 0,
		});
		assert.deepEqual(calls, [
			"/agent-tasks/",
			"/static-tasks/tasks?limit=20",
		]);
	} finally {
		apiClient.get = originalGet;
	}
});
