import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

globalThis.React = React;

async function importOrFail<TModule = Record<string, unknown>>(
  relativePath: string,
): Promise<TModule> {
  try {
    return (await import(relativePath)) as TModule;
  } catch (error) {
    assert.fail(
      `expected helper module ${relativePath} to exist: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
}

test("DataTable renders grouped headers and local pagination summary", async () => {
  const dataTableModule = await importOrFail<any>(
    "../src/components/data-table/index.ts",
  );

  const markup = renderToStaticMarkup(
    createElement(dataTableModule.DataTable, {
      data: [
        { id: "p1", name: "Project One", completed: 2, high: 4 },
        { id: "p2", name: "Project Two", completed: 1, high: 2 },
      ],
      columns: [
        {
          id: "project",
          header: "项目",
          columns: [
            {
              accessorKey: "name",
              header: "项目名称",
            },
          ],
        },
        {
          id: "metrics",
          header: "指标",
          columns: [
            {
              accessorKey: "completed",
              header: "已完成",
            },
            {
              accessorKey: "high",
              header: "高危",
            },
          ],
        },
      ],
      pagination: {
        enabled: true,
      },
    }),
  );

  assert.match(markup, /项目名称/);
  assert.match(markup, /已完成/);
  assert.match(markup, /高危/);
  assert.match(markup, /<th[^>]*colSpan="2"[^>]*>指标<\/th>/);
  assert.match(markup, /共 2 条/);
});
