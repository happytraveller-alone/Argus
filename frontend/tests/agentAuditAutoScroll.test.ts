import test from "node:test";
import assert from "node:assert/strict";

import {
	getTaskAutoScroll,
	persistTaskAutoScroll,
	loadAutoScrollState,
	shouldDisableAutoScrollOnScroll,
} from "../src/pages/AgentAudit/autoScrollState.ts";

class MemoryStorage implements Storage {
	#store = new Map<string, string>();

	get length(): number {
		return this.#store.size;
	}

	clear(): void {
		this.#store.clear();
	}

	getItem(key: string): string | null {
		return this.#store.get(key) ?? null;
	}

	key(index: number): string | null {
		return [...this.#store.keys()][index] ?? null;
	}

	removeItem(key: string): void {
		this.#store.delete(key);
	}

	setItem(key: string, value: string): void {
		this.#store.set(key, value);
	}
}

test("自动滚动对新任务默认开启，并忽略旧项目级状态", () => {
	const storage = new MemoryStorage();
	storage.setItem(
		"agentAudit.autoScrollByProject.v1",
		JSON.stringify({ "project-1": false }),
	);

	assert.equal(getTaskAutoScroll("task-new", storage), true);
	assert.deepEqual(loadAutoScrollState(storage), {});
});

test("自动滚动按任务持久化，并与其他任务隔离", () => {
	const storage = new MemoryStorage();

	persistTaskAutoScroll("task-1", false, storage);

	assert.deepEqual(loadAutoScrollState(storage), { "task-1": false });
	assert.equal(getTaskAutoScroll("task-1", storage), false);
	assert.equal(getTaskAutoScroll("task-2", storage), true);

	persistTaskAutoScroll("task-2", true, storage);

	assert.deepEqual(loadAutoScrollState(storage), {
		"task-1": false,
		"task-2": true,
	});
});

test("仅用户手动滚离底部时关闭自动滚动", () => {
	assert.equal(
		shouldDisableAutoScrollOnScroll({
			isAutoScrollEnabled: true,
			isProgrammaticScroll: true,
			distanceToBottom: 240,
			thresholdPx: 24,
		}),
		false,
	);

	assert.equal(
		shouldDisableAutoScrollOnScroll({
			isAutoScrollEnabled: true,
			isProgrammaticScroll: false,
			distanceToBottom: 12,
			thresholdPx: 24,
		}),
		false,
	);

	assert.equal(
		shouldDisableAutoScrollOnScroll({
			isAutoScrollEnabled: false,
			isProgrammaticScroll: false,
			distanceToBottom: 240,
			thresholdPx: 24,
		}),
		false,
	);

	assert.equal(
		shouldDisableAutoScrollOnScroll({
			isAutoScrollEnabled: true,
			isProgrammaticScroll: false,
			distanceToBottom: 240,
			thresholdPx: 24,
		}),
		true,
	);
});
