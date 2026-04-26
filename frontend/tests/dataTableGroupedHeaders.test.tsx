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

test("DataTable remote pagination uses server total instead of current page row count", async () => {
  const dataTableModule = await importOrFail<any>(
    "../src/components/data-table/index.ts",
  );

  const markup = renderToStaticMarkup(
    createElement(dataTableModule.DataTable, {
      data: [{ id: "p11", name: "Project Eleven" }],
      columns: [
        {
          accessorKey: "name",
          header: "项目名称",
        },
      ],
      mode: "manual",
      state: {
        pagination: {
          pageIndex: 1,
          pageSize: 10,
        },
      },
      pagination: {
        enabled: true,
        manual: true,
        totalCount: 37,
      },
    }),
  );

  assert.match(markup, /共 37 条，第 2 \/ 4 页/);
});

test("DataTable sizes columns from the current page header and cell content", async () => {
  const dataTableModule = await importOrFail<any>(
    "../src/components/data-table/index.ts",
  );

  const markup = renderToStaticMarkup(
    createElement(dataTableModule.DataTable, {
      data: [
        {
          id: "p1",
          name: "短",
          status: "visible-current-page",
        },
        {
          id: "p2",
          name: "off-page-value-that-must-not-size-the-column",
          status: "closed",
        },
      ],
      columns: [
        {
          accessorKey: "name",
          header: "长表头",
        },
        {
          accessorKey: "status",
          header: "状态",
        },
      ],
      defaultState: {
        pagination: {
          pageIndex: 0,
          pageSize: 1,
        },
      },
      pagination: {
        enabled: true,
      },
    }),
  );

  assert.match(markup, /style="width:256px"/);
  assert.match(markup, /style="width:72px;min-width:72px"/);
  assert.match(markup, /style="width:184px;min-width:184px"/);
  assert.doesNotMatch(markup, /off-page-value-that-must-not-size-the-column/);
  assert.doesNotMatch(markup, /style="width:520px;min-width:520px"/);
});

test("DataTable renders draggable resize handles when column resizing is enabled", async () => {
  const dataTableModule = await importOrFail<any>(
    "../src/components/data-table/index.ts",
  );

  const markup = renderToStaticMarkup(
    createElement(dataTableModule.DataTable, {
      data: [{ id: "p1", name: "Project One" }],
      columns: [
        {
          accessorKey: "name",
          header: "项目名称",
          meta: {
            label: "项目名称",
            width: 180,
            minWidth: 120,
          },
        },
      ],
      enableColumnResizing: true,
      pagination: false,
    }),
  );

  assert.match(markup, /data-data-table-column-resizer="true"/);
  assert.match(markup, /aria-label="调整项目名称列宽"/);
  assert.match(markup, /style="width:180px;min-width:120px"/);
  assert.match(markup, /class="[^"]*table-fixed/);
});
