// ---------------------------------------------------------------------------
// POST /run-stage  (Rust → sidecar, CONTRACT.md §1)
// POST /run-stage/{runId}/cancel
//
// Streams one pipeline stage as NDJSON. Each line is one event object.
// Auth: Bearer AGENT_ENGINE_SHARED_SECRET (same secret the sidecar uses
// to call /internal/* on the Rust backend — CONTRACT.md §2/§3).
// ---------------------------------------------------------------------------

import type { IncomingMessage, ServerResponse } from "node:http";

import type { Context } from "@earendil-works/pi-ai";

import { invokeStage, type InvokeOptions, type ModelCandidate } from "./invoke.js";

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function checkAuth(req: IncomingMessage): boolean {
  const secret = process.env.AGENT_ENGINE_SHARED_SECRET;
  if (!secret) return false;
  const header = req.headers["authorization"] ?? "";
  return header === `Bearer ${secret}`;
}

// ---------------------------------------------------------------------------
// Request body type (CONTRACT.md §1)
// ---------------------------------------------------------------------------

interface RunStageRequest {
  version: number;
  runId: string;
  taskId: string;
  sessionId: string;
  stage: string;
  model: {
    provider: string;
    api: string;
    modelId: string;
    baseUrl?: string;
    fallback?: Array<{ provider: string; api: string; modelId: string; baseUrl?: string }>;
  };
  inputs: Record<string, unknown>;
  limits: { maxTokensPerCall: number; stageDeadlineMs: number };
}

// ---------------------------------------------------------------------------
// In-flight run registry for cancel support
// ---------------------------------------------------------------------------

const activeRuns = new Map<string, AbortController>();

// ---------------------------------------------------------------------------
// NDJSON helper — writes one JSON line and flushes
// ---------------------------------------------------------------------------

function writeLine(res: ServerResponse, obj: unknown): void {
  res.write(JSON.stringify(obj) + "\n");
}

// ---------------------------------------------------------------------------
// Build pi Context from report stage inputs
// The report stage receives prior-stage outputs. We pass them verbatim as the
// user message so the LLM has full context. CONTRACT.md §1 "inputs" mirrors
// Rust stage input structs.
// ---------------------------------------------------------------------------

function buildReportContext(inputs: Record<string, unknown>): Context {
  const systemPrompt =
    "你是 Argus 智能审计系统的报告生成助手。根据用户提供的审计阶段输出，生成一份结构化的最终报告摘要。" +
    "所有自然语言字段使用简体中文；技术标识符、文件路径、JSON 键、代码片段保持原样。" +
    '输出格式：{"summary":"string","findings":[],"recommendations":["string"]}';

  const userMessage =
    "请根据以下审计阶段输出生成最终报告摘要：\n\n" + JSON.stringify(inputs, null, 2);

  return {
    systemPrompt,
    messages: [
      {
        role: "user",
        content: userMessage,
        timestamp: Date.now(),
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Parse raw request body as JSON
// ---------------------------------------------------------------------------

function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new Error("invalid JSON body"));
      }
    });
    req.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// POST /run-stage
// ---------------------------------------------------------------------------

export async function handleRunStage(
  req: IncomingMessage,
  res: ServerResponse,
  invokeOptions?: InvokeOptions,
): Promise<void> {
  if (!checkAuth(req)) {
    res.writeHead(401, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }

  let body: RunStageRequest;
  try {
    body = (await readBody(req)) as RunStageRequest;
  } catch {
    res.writeHead(400, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "bad_request", message: "invalid JSON body" }));
    return;
  }

  if (body.version !== 1) {
    res.writeHead(409, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "unsupported_version" }));
    return;
  }

  const { runId, model, inputs, limits } = body;

  // Set up abort controller; wire client-disconnect abort.
  const controller = new AbortController();
  activeRuns.set(runId, controller);

  req.on("close", () => {
    if (activeRuns.has(runId)) controller.abort();
  });

  // Build invoke request.
  const primaryCandidate: ModelCandidate = {
    provider: model.provider,
    modelId: model.modelId,
  };
  const fallback: ModelCandidate[] = (model.fallback ?? []).map((f) => ({
    provider: f.provider,
    modelId: f.modelId,
  }));

  const context = buildReportContext(inputs);

  const invokeReq = {
    model: primaryCandidate,
    fallback: fallback.length > 0 ? fallback : undefined,
    context,
    maxOutputTokens: limits.maxTokensPerCall > 0 ? limits.maxTokensPerCall : undefined,
    signal: controller.signal,
  };

  // Start NDJSON stream.
  res.writeHead(200, {
    "content-type": "application/x-ndjson; charset=utf-8",
    "transfer-encoding": "chunked",
    "x-content-type-options": "nosniff",
  });

  // First line: stage_started.
  writeLine(res, {
    type: "stage_event",
    kind: "stage_started",
    message: `stage ${body.stage} started`,
    data: {},
  });

  let lastOutput: { message: unknown; usage: unknown; model: string } | undefined;

  try {
    for await (const event of invokeStage(invokeReq, invokeOptions ?? {})) {
      if (event.type === "result") {
        if (event.ok) {
          lastOutput = event.output;
        }
        // Emit checkpoint before terminal result.
        writeLine(res, {
          type: "checkpoint",
          session: {
            sessionId: body.sessionId,
            taskId: body.taskId,
            stage: body.stage,
            assistantMessage: lastOutput?.message ?? null,
          },
        });
        // Terminal result — shape output as camelCase ReportOutput.
        if (event.ok) {
          // Parse the assistant message text as JSON to extract report fields.
          let reportOutput: {
            summary: string;
            findings: unknown[];
            recommendations: string[];
          } = { summary: "", findings: [], recommendations: [] };
          try {
            const text = extractText(lastOutput?.message);
            const parsed = JSON.parse(text ?? "{}");
            reportOutput = {
              summary: typeof parsed.summary === "string" ? parsed.summary : "",
              findings: Array.isArray(parsed.findings) ? parsed.findings : [],
              recommendations: Array.isArray(parsed.recommendations)
                ? parsed.recommendations
                : [],
            };
          } catch {
            // Non-JSON assistant reply — surface raw text in summary.
            reportOutput.summary = extractText(lastOutput?.message) ?? "";
          }
          writeLine(res, {
            type: "result",
            ok: true,
            output: reportOutput,
          });
        } else {
          writeLine(res, { type: "result", ok: false, error: event.error });
        }
        break;
      }
      // Relay stage_event and token lines as-is.
      writeLine(res, event);
    }
  } finally {
    activeRuns.delete(runId);
    res.end();
  }
}

// Extract concatenated text content from an AssistantMessage.
// AssistantMessage.content is (TextContent | ThinkingContent | ToolCall)[].
function extractText(msg: unknown): string | undefined {
  if (!msg || typeof msg !== "object") return undefined;
  const content = (msg as { content?: unknown }).content;
  if (!Array.isArray(content)) return undefined;
  const parts: string[] = [];
  for (const block of content) {
    if (block && typeof block === "object" && (block as { type?: string }).type === "text") {
      const t = (block as { text?: string }).text;
      if (typeof t === "string") parts.push(t);
    }
  }
  return parts.length > 0 ? parts.join("") : undefined;
}

// ---------------------------------------------------------------------------
// POST /run-stage/{runId}/cancel
// ---------------------------------------------------------------------------

export function handleCancelRun(
  req: IncomingMessage,
  res: ServerResponse,
  runId: string,
): void {
  if (!checkAuth(req)) {
    res.writeHead(401, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }

  const controller = activeRuns.get(runId);
  if (controller) {
    controller.abort();
    // Map entry removed by the run's finally block.
  }
  res.writeHead(204);
  res.end();
}
