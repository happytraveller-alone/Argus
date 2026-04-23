import test from "node:test";
import assert from "node:assert/strict";

test("AgentStreamHandler disconnect clears any scheduled reconnect timeout", async () => {
  const { AgentStreamHandler } = await import("../src/shared/api/agentStream.ts");

  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const scheduled: Array<{ id: number; delay: number }> = [];
  const cleared: number[] = [];

  globalThis.setTimeout = ((callback: TimerHandler, delay?: number) => {
    const id = scheduled.length + 1;
    scheduled.push({ id, delay: Number(delay ?? 0) });
    void callback;
    return id as unknown as ReturnType<typeof setTimeout>;
  }) as unknown as typeof globalThis.setTimeout;
  globalThis.clearTimeout = ((id?: number | ReturnType<typeof setTimeout>) => {
    cleared.push(Number(id));
  }) as typeof globalThis.clearTimeout;

  try {
    const handler = new AgentStreamHandler("task-1");
    (handler as any).scheduleReconnect("transport", "boom");

    assert.equal(scheduled.length, 1);

    handler.disconnect();

    assert.deepEqual(cleared, [scheduled[0].id]);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});
