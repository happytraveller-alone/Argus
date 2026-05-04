import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SsrRouter } from "./ssrTestRouter.tsx";

globalThis.React = React;

test("SandboxTemplatesTable renders project-style template management columns and guards actions", async () => {
  const tableModule = await import("../src/pages/sandbox-management/SandboxTemplatesTable.tsx");
  const markup = renderToStaticMarkup(
    createElement(SsrRouter, {}, createElement(tableModule.default, {
      rows: [
        {
          id: "ready-record",
          kind: "codeql_cpp",
          status: "ready",
          templateId: "tpl-ready",
          imageRef: "argus/codeql:latest",
          imageFingerprint: "sha256:ready",
          errorMessage: null,
          createdAt: "2026-05-04T00:00:00Z",
          updatedAt: "2026-05-04T00:01:00Z",
          buildLogTail: "ready",
          consecutiveScanFailures: 0,
        },
        {
          id: "invalidated-record",
          kind: "opengrep",
          status: "invalidated",
          templateId: "tpl-invalidated",
          imageRef: "argus/opengrep:latest",
          imageFingerprint: null,
          errorMessage: "template invalidated",
          createdAt: "2026-05-04T00:00:00Z",
          updatedAt: "2026-05-04T00:02:00Z",
          buildLogTail: "invalidated",
          consecutiveScanFailures: 2,
        },
      ],
      deletingRecordId: null,
      onDeleteFailed: () => {},
    })),
  );

  assert.match(markup, /序号/);
  assert.match(markup, /模板类型/);
  assert.match(markup, /记录状态/);
  assert.match(markup, /模板 \/ 镜像/);
  assert.match(markup, /镜像/);
  assert.match(markup, /错误摘要/);
  assert.match(markup, /操作/);
  assert.match(markup, /删除 FAILED \/ INVALIDATED/);
  assert.match(markup, /仅 FAILED \/ INVALIDATED 可删/);
  assert.match(markup, /tpl-ready/);
  assert.match(markup, /tpl-invalidated/);
  assert.match(markup, /border-b-2/);
  assert.match(markup, /disabled/);
});
