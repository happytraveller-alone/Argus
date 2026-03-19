import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { api } from "../src/shared/api/database.ts";

test("project description api posts to stored-project generate endpoint", async () => {
	const originalPost = apiClient.post;
	const calls: string[] = [];

	apiClient.post = (async (url: string) => {
		calls.push(url);
		return {
			data: {
				description: "Auto generated summary",
				language_info: '{"total": 1, "total_files": 1, "languages": {}}',
				source: "llm",
			},
		};
	}) as typeof apiClient.post;

	try {
		const result = await api.generateStoredProjectDescription("project-1");
		assert.equal(result.description, "Auto generated summary");
		assert.equal(result.source, "llm");
	} finally {
		apiClient.post = originalPost;
	}

	assert.deepEqual(calls, ["/projects/project-1/description/generate"]);
});
