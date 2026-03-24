import type { ReactNode } from "react";
import React, { createElement } from "react";
import { StaticRouter } from "react-router-dom/server";

export function SsrRouter({
  children,
  location = "/",
}: {
  children: ReactNode;
  location?: string;
}) {
  return createElement(StaticRouter, { location }, children);
}
