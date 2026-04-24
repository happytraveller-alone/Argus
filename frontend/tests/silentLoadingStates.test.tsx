import test from "node:test";
import assert from "node:assert/strict";
import React, { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DataTableLoadingState } from "../src/components/data-table/DataTableLoadingState.tsx";
import TaskRouteFallback from "../src/components/performance/TaskRouteFallback.tsx";
import { Skeleton } from "../src/components/ui/skeleton.tsx";

globalThis.React = React;

test("TaskRouteFallback renders a silent blank shell without skeleton boxes", () => {
  const markup = renderToStaticMarkup(createElement(TaskRouteFallback));

  assert.match(markup, /min-h-screen/);
  assert.doesNotMatch(markup, /data-slot="skeleton"/);
  assert.doesNotMatch(markup, /bg-muted/);
});

test("DataTableLoadingState stays silent without spinner or loading copy", () => {
  const markup = renderToStaticMarkup(createElement(DataTableLoadingState));

  assert.match(markup, /min-h-32/);
  assert.match(markup, /class="sr-only">加载中/);
  assert.doesNotMatch(markup, /animate-spin/);
});

test("Skeleton keeps layout space but no longer renders pulse or muted boxes", () => {
  const markup = renderToStaticMarkup(
    createElement(Skeleton, { className: "h-8 w-24" }),
  );

  assert.match(markup, /data-slot="skeleton"/);
  assert.match(markup, /bg-transparent/);
  assert.doesNotMatch(markup, /bg-muted/);
  assert.doesNotMatch(markup, /animate-pulse/);
});
