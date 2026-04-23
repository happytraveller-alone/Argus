import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { api } from "../src/shared/api/database.ts";

test("projects api uses rust gateway owned project collection route", async () => {
	const originalGet = apiClient.get;
	const originalPost = apiClient.post;
	const getCalls: Array<{ url: string; config?: { params?: Record<string, unknown> } }> = [];
	const postCalls: Array<{ url: string; payload: unknown }> = [];

	apiClient.get = (async (url: string, config?: { params?: Record<string, unknown> }) => {
		getCalls.push({ url, config });
		return { data: [] };
	}) as typeof apiClient.get;

	apiClient.post = (async (url: string, payload?: unknown) => {
		postCalls.push({ url, payload });
		return { data: { id: "project-1", name: "demo" } };
	}) as typeof apiClient.post;

	try {
		await api.getProjects({ skip: 5, limit: 10, includeMetrics: true });
		await api.createProject({
			name: "demo",
			description: "",
			source_type: "zip",
			programming_languages: [],
		});
	} finally {
		apiClient.get = originalGet;
		apiClient.post = originalPost;
	}

	assert.deepEqual(getCalls, [
		{
			url: "/projects",
			config: {
				params: {
					skip: 5,
					limit: 10,
					include_metrics: true,
				},
			},
		},
	]);
	assert.equal(postCalls[0]?.url, "/projects");
});
