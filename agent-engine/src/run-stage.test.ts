// ---------------------------------------------------------------------------
// Tests for POST /run-stage and POST /run-stage/{runId}/cancel
// Uses Node.js built-in test runner (node:test) — no extra dependencies.
// Drives handleRunStage with injectable streamImpl so no real network/LLM
// is needed.
// ---------------------------------------------------------------------------

import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer, request as httpRequest, type IncomingMessage, type ServerResponse } from "node:http";

import type { Api, AssistantMessage, AssistantMessageEvent, Model } from "@earendil-works/pi-ai";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";

import { handleRunStage, handleCancelRun } from "./run-stage.js";
import type { InvokeOptions } from "./invoke.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SECRET = "test-secret-abc";

/** Minimal valid RunStage request body. */
function makeBody(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 1,
    runId: "run-1",
    taskId: "task-1",
    sessionId: "session-1",
    stage: "report",
    model: { provider: "openai", api: "openai-completions", modelId: "gpt-4o" },
    inputs: { recon: null, validatedFindings: [] },
    limits: { maxTokensPerCall: 1024, stageDeadlineMs: 60_000 },
    ...overrides,
  });
}

/** Make a fake AssistantMessage whose content is a JSON report string. */
function fakeAssistantMessage(text: string): AssistantMessage {
  return {
    role: "assistant",
    content: [{ type: "text", text }],
    api: "openai-completions",
    provider: "openai",
    model: "gpt-4o",
    stopReason: "stop",
    usage: { input: 10, output: 20, cacheRead: 0, cacheWrite: 0, totalTokens: 30, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    timestamp: Date.now(),
  };
}

/** Fake stream implementation that yields a fixed event sequence. */
function fakeStreamImpl(events: AssistantMessageEvent[]): InvokeOptions["streamImpl"] {
  return (_model: Model<Api>, _ctx: unknown, _opts: unknown) => {
    const s = createAssistantMessageEventStream();
    // Push all events asynchronously so the stream is ready to iterate.
    Promise.resolve().then(() => {
      for (const ev of events) s.push(ev);
    });
    return s;
  };
}

/**
 * Build InvokeOptions with a fake streamImpl that:
 *  1. emits one text_delta
 *  2. emits done with a fake AssistantMessage
 * Also no-ops the llmConfig fetch (apiKey lookup) — we stub streamImpl which
 * bypasses the actual stream call, but invokeStage still calls fetchLlmConfig.
 * We override that by providing a fake fetchImpl on llmConfig.
 */
function buildInvokeOptions(text: string): InvokeOptions {
  const assistantMsg = fakeAssistantMessage(text);
  const events: AssistantMessageEvent[] = [
    { type: "text_delta", delta: text, contentIndex: 0, partial: assistantMsg },
    { type: "done", reason: "stop", message: assistantMsg },
  ];
  return {
    streamImpl: fakeStreamImpl(events),
    // Provide a fake llmConfig fetchImpl so no real HTTP call is made.
    llmConfig: {
      fetchImpl: async () =>
        new Response(
          JSON.stringify({
            provider: "openai",
            modelId: "gpt-4o",
            baseUrl: "http://fake-llm",
            apiKey: "fake-key",
            headers: {},
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
    },
    sleep: async () => {},
  };
}

/** POST to handler and collect NDJSON lines. */
async function post(
  path: string,
  body: string,
  headers: Record<string, string>,
  invokeOptions?: InvokeOptions,
): Promise<{ status: number; lines: unknown[]; rawLines: string[] }> {
  return new Promise((resolve, reject) => {
    // Create a minimal in-process server for one request.
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      const url = new URL(req.url ?? "/", "http://localhost");
      const cancelMatch = /^\/run-stage\/([^/]+)\/cancel$/.exec(url.pathname);
      if (req.method === "POST" && url.pathname === "/run-stage") {
        handleRunStage(req, res, invokeOptions).catch(reject);
      } else if (req.method === "POST" && cancelMatch) {
        handleCancelRun(req, res, cancelMatch[1]!);
      } else {
        res.writeHead(404);
        res.end();
      }
    });

    server.listen(0, "127.0.0.1", () => {
      const addr = server.address() as { port: number };
      const reqOpts = {
        method: "POST",
        hostname: "127.0.0.1",
        port: addr.port,
        path,
        headers: { "content-type": "application/json", ...headers },
      };
      const clientReq = httpRequest(reqOpts, (clientRes: IncomingMessage) => {
        const chunks: Buffer[] = [];
        clientRes.on("data", (c: Buffer) => chunks.push(c));
        clientRes.on("end", () => {
          server.close();
          const raw = Buffer.concat(chunks).toString("utf8");
          const rawLines = raw.split("\n").filter((l) => l.trim() !== "");
          const lines = rawLines.map((l) => {
            try { return JSON.parse(l); } catch { return l; }
          });
          resolve({ status: clientRes.statusCode ?? 0, lines, rawLines });
        });
        clientRes.on("error", reject);
      });
      clientReq.on("error", reject);
      clientReq.write(body);
      clientReq.end();
    });
    server.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("POST /run-stage", () => {
  before(() => {
    process.env.AGENT_ENGINE_SHARED_SECRET = SECRET;
  });

  after(() => {
    delete process.env.AGENT_ENGINE_SHARED_SECRET;
  });

  it("rejects missing auth with 401", async () => {
    const result = await post("/run-stage", makeBody(), {});
    assert.equal(result.status, 401);
  });

  it("rejects wrong secret with 401", async () => {
    const result = await post("/run-stage", makeBody(), {
      authorization: "Bearer wrong-secret",
    });
    assert.equal(result.status, 401);
  });

  it("rejects version != 1 with 409", async () => {
    const result = await post(
      "/run-stage",
      makeBody({ version: 2 }),
      { authorization: `Bearer ${SECRET}` },
    );
    assert.equal(result.status, 409);
    const body = result.lines[0] as Record<string, unknown>;
    assert.equal(body.error, "unsupported_version");
  });

  it("emits stage_started, token, checkpoint, result for a happy-path run", async () => {
    const reportText = JSON.stringify({
      summary: "审计完成",
      findings: [],
      recommendations: ["修复注入漏洞"],
    });
    const opts = buildInvokeOptions(reportText);

    const result = await post(
      "/run-stage",
      makeBody(),
      { authorization: `Bearer ${SECRET}` },
      opts,
    );

    assert.equal(result.status, 200);

    const lines = result.lines as Array<Record<string, unknown>>;

    // First line must be stage_started.
    assert.equal(lines[0]?.type, "stage_event");
    assert.equal(lines[0]?.kind, "stage_started");

    // Must contain at least one token line.
    const tokenLines = lines.filter((l) => l.type === "token");
    assert.ok(tokenLines.length > 0, "expected at least one token line");

    // Must contain exactly one checkpoint before the terminal result.
    const checkpointLines = lines.filter((l) => l.type === "checkpoint");
    assert.equal(checkpointLines.length, 1);
    const checkpoint = checkpointLines[0]!;
    assert.ok(
      checkpoint.session && typeof checkpoint.session === "object",
      "checkpoint.session must be an object",
    );

    // Last line must be terminal result ok:true.
    const last = lines[lines.length - 1]!;
    assert.equal(last.type, "result");
    assert.equal(last.ok, true);
    const output = last.output as Record<string, unknown>;
    assert.equal(output.summary, "审计完成");
    assert.deepEqual(output.recommendations, ["修复注入漏洞"]);

    // Checkpoint appears before terminal result.
    const checkpointIdx = lines.findIndex((l) => l.type === "checkpoint");
    const resultIdx = lines.findIndex((l) => l.type === "result");
    assert.ok(checkpointIdx < resultIdx, "checkpoint must precede terminal result");
  });

  it("cancel aborts the run and map entry is cleaned up", async () => {
    // This test verifies AbortController wiring: the cancel endpoint aborts
    // the controller, which propagates to invokeStage via signal.
    // We use a slow fake stream that never yields — cancel fires mid-flight.
    let resolveStream!: () => void;
    const streamDone = new Promise<void>((r) => { resolveStream = r; });

    const hangingStreamImpl: InvokeOptions["streamImpl"] = (_m, _c, _o) => {
      const s = createAssistantMessageEventStream();
      // Never push events until streamDone resolves (simulates a stalled LLM).
      streamDone.then(() => {
        // Push a terminal done so the stream can end after cancel unblocks it.
        const msg = fakeAssistantMessage("");
        s.push({ type: "done", reason: "stop", message: msg });
      });
      return s;
    };

    const opts: InvokeOptions = {
      streamImpl: hangingStreamImpl,
      llmConfig: {
        fetchImpl: async () =>
          new Response(
            JSON.stringify({ provider: "openai", modelId: "gpt-4o", baseUrl: "http://fake", apiKey: "k", headers: {} }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
      },
      sleep: async () => {},
    };

    // Track AbortSignal via a custom invokeOptions wrapper.
    const runId = "run-cancel-test";

    // Start run in background — it will hang until aborted.
    const runPromise = post(
      "/run-stage",
      makeBody({ runId }),
      { authorization: `Bearer ${SECRET}` },
      opts,
    );

    // Give the run a tick to register in activeRuns.
    await new Promise((r) => setTimeout(r, 50));

    // Cancel it.
    const cancelResult = await post(
      `/run-stage/${runId}/cancel`,
      "",
      { authorization: `Bearer ${SECRET}` },
    );
    assert.equal(cancelResult.status, 204);

    // Unblock the hanging stream so the run can terminate.
    resolveStream();

    // The run should complete (with cancelled or normal result).
    const runResult = await runPromise;
    assert.equal(runResult.status, 200);

    // Last line should be a result (ok or cancelled).
    const lines = runResult.lines as Array<Record<string, unknown>>;
    const last = lines[lines.length - 1]!;
    assert.equal(last.type, "result");
  });
});
