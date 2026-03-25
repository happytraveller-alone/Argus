import test from "node:test";
import assert from "node:assert/strict";

import { apiClient } from "../src/shared/api/serverClient.ts";
import { downloadAgentReport } from "../src/shared/api/agentTasks.ts";

function installBrowserShim() {
  const originalWindow = (globalThis as { window?: Window & typeof globalThis }).window;
  const originalDocument = (globalThis as { document?: Document }).document;

  let currentAnchor: {
    href: string;
    download: string;
    clickCount: number;
    parentNode: { removeChild: (node: unknown) => void };
    setAttribute: (name: string, value: string) => void;
    click: () => void;
  } | null = null;

  const fakeDocument = {
    body: {
      appendChild: (_node: unknown) => undefined,
    },
    createElement: (tag: string) => {
      assert.equal(tag, "a");
      currentAnchor = {
        href: "",
        download: "",
        clickCount: 0,
        parentNode: {
          removeChild: () => undefined,
        },
        setAttribute(name: string, value: string) {
          if (name === "download") this.download = value;
        },
        click() {
          this.clickCount += 1;
        },
      };
      return currentAnchor as unknown as HTMLAnchorElement;
    },
  } as unknown as Document;

  const fakeWindow = {
    URL: {
      createObjectURL: (_blob: Blob) => "blob:test-url",
      revokeObjectURL: (_url: string) => undefined,
    },
  } as unknown as Window & typeof globalThis;

  (globalThis as { window?: Window & typeof globalThis }).window = fakeWindow;
  (globalThis as { document?: Document }).document = fakeDocument;

  const restore = () => {
    (globalThis as { window?: Window & typeof globalThis }).window = originalWindow;
    (globalThis as { document?: Document }).document = originalDocument;
  };

  return {
    restore,
    getAnchor: () => currentAnchor,
  };
}

test("downloadAgentReport requests pdf format and prefers Content-Disposition filename", async () => {
  const originalGet = apiClient.get;
  const shim = installBrowserShim();

  const calls: Array<{ url: string; config: unknown }> = [];
  apiClient.get = (async (url: string, config?: unknown) => {
    calls.push({ url, config });
    return {
      data: new Blob(["pdf-bytes"], { type: "application/pdf" }),
      headers: {
        "content-disposition": 'attachment; filename="server-report.pdf"',
      },
    };
  }) as typeof apiClient.get;

  try {
    await downloadAgentReport("12345678-abcdef", "pdf");
  } finally {
    apiClient.get = originalGet;
    shim.restore();
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "/agent-tasks/12345678-abcdef/report");
  assert.deepEqual(calls[0]?.config, {
    params: { format: "pdf" },
    responseType: "blob",
  });

  const anchor = shim.getAnchor();
  assert.ok(anchor);
  assert.equal(anchor?.download, "server-report.pdf");
  assert.equal(anchor?.clickCount, 1);
});

test("downloadAgentReport falls back to pdf extension when header is missing", async () => {
  const originalGet = apiClient.get;
  const shim = installBrowserShim();

  apiClient.get = (async () => {
    return {
      data: new Blob(["pdf-bytes"], { type: "application/pdf" }),
      headers: {},
    };
  }) as typeof apiClient.get;

  try {
    await downloadAgentReport("12345678-abcdef", "pdf");
  } finally {
    apiClient.get = originalGet;
    shim.restore();
  }

  const anchor = shim.getAnchor();
  assert.ok(anchor);
  assert.equal(anchor?.download, "audit-report-12345678.pdf");
});
