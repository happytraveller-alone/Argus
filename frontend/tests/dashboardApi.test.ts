import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { api } from "../src/shared/api/database.ts";

test("dashboard snapshot api forwards top_n and range_days params", async () => {
	const originalGet = apiClient.get;
	const calls: string[] = [];

	apiClient.get = (async (url: string, config?: { params?: Record<string, unknown> }) => {
		const params = new URLSearchParams(
			Object.entries(config?.params || {}).map(([key, value]) => [key, String(value)]),
		).toString();
		calls.push(`${url}?${params}`);
		return { data: { ok: true } };
	}) as typeof apiClient.get;

	try {
		await api.getDashboardSnapshot(12, 7);
		await api.getDashboardSnapshot(3, 30);
	} finally {
		apiClient.get = originalGet;
	}

	assert.deepEqual(calls, [
		"/projects/dashboard-snapshot?top_n=12&range_days=7",
		"/projects/dashboard-snapshot?top_n=3&range_days=30",
	]);
});
