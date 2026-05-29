import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { buildCatalog } from "./catalog.js";
import { handleRunStage, handleCancelRun } from "./run-stage.js";

// ---------------------------------------------------------------------------
// argus agent-engine sidecar.
// Implements GET /healthz, GET /models, POST /run-stage, and
// POST /run-stage/{runId}/cancel (CONTRACT.md §1).
// ---------------------------------------------------------------------------

const PORT = Number.parseInt(process.env.AGENT_ENGINE_PORT ?? "18100", 10);
const HOST = process.env.AGENT_ENGINE_HOST ?? "0.0.0.0";
const STARTED_AT = Date.now();

// pi's catalog is static for the process lifetime — build it once.
const CATALOG = buildCatalog();

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

function handle(req: IncomingMessage, res: ServerResponse): void {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "GET" && url.pathname === "/healthz") {
    sendJson(res, 200, {
      status: "ok",
      service: "argus-agent-engine",
      uptimeMs: Date.now() - STARTED_AT,
    });
    return;
  }

  // Public model catalog (Phase 1B.1a). Static metadata only — NO API keys.
  // Proxied verbatim by the Rust backend's GET /api/v1/models.
  if (req.method === "GET" && url.pathname === "/models") {
    sendJson(res, 200, { version: 1, models: CATALOG });
    return;
  }

  // POST /run-stage — streaming NDJSON stage execution (CONTRACT.md §1).
  if (req.method === "POST" && url.pathname === "/run-stage") {
    handleRunStage(req, res).catch((err: unknown) => {
      console.error("[agent-engine] /run-stage unhandled error", err);
      if (!res.headersSent) {
        res.writeHead(500, { "content-type": "application/json; charset=utf-8" });
        res.end(JSON.stringify({ error: "internal_error" }));
      } else {
        res.end();
      }
    });
    return;
  }

  // POST /run-stage/{runId}/cancel — abort an in-flight run (CONTRACT.md §1).
  const cancelMatch = /^\/run-stage\/([^/]+)\/cancel$/.exec(url.pathname);
  if (req.method === "POST" && cancelMatch) {
    handleCancelRun(req, res, cancelMatch[1]!);
    return;
  }

  sendJson(res, 404, { error: "not_found", path: url.pathname });
}

const server = createServer(handle);

server.listen(PORT, HOST, () => {
  console.log(`[agent-engine] listening on http://${HOST}:${PORT}`);
});

function shutdown(signal: string): void {
  console.log(`[agent-engine] received ${signal}, shutting down`);
  server.close(() => process.exit(0));
  // Force-exit if connections do not drain promptly.
  setTimeout(() => process.exit(0), 5000).unref();
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
