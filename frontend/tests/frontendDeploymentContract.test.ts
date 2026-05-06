import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { DEFAULT_API_BASE_URL, normalizeApiBaseUrl } from "../src/shared/api/apiBase.ts";

test("normalizeApiBaseUrl defaults to the same-origin deployment path", () => {
  assert.equal(DEFAULT_API_BASE_URL, "/api/v1");
  assert.equal(normalizeApiBaseUrl(undefined), "/api/v1");
  assert.equal(normalizeApiBaseUrl(""), "/api/v1");
  assert.equal(normalizeApiBaseUrl("  /api/v1/  "), "/api/v1");
  assert.equal(
    normalizeApiBaseUrl("https://audit.example.com/api/v1/"),
    "https://audit.example.com/api/v1",
  );
});

test("dev proxy targets the backend host port, not backend service DNS", () => {
  const envExample = readFileSync(new URL("../../env.example", import.meta.url), "utf8");
  const compose = readFileSync(new URL("../../docker-compose.yml", import.meta.url), "utf8");
  const viteConfig = readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");

  assert.match(envExample, /^VITE_API_TARGET=http:\/\/host\.docker\.internal:18000$/m);
  assert.doesNotMatch(envExample, /^VITE_API_TARGET=http:\/\/backend:8000$/m);
  assert.match(
    compose,
    /VITE_API_TARGET: \$\{VITE_API_TARGET:-http:\/\/host\.docker\.internal:18000\}/,
  );
  assert.match(compose, /"host\.docker\.internal:host-gateway"/);
  assert.match(viteConfig, /process\.env\.VITE_API_TARGET \|\| "http:\/\/127\.0\.0\.1:18000"/);
});
