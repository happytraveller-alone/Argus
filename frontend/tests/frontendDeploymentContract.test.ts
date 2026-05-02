import test from "node:test";
import assert from "node:assert/strict";

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
