import type { PropsWithChildren } from "react";
import { createElement } from "react";
import { StaticRouter } from "react-router-dom";

export function SsrRouter({
  children,
  location = "/",
}: PropsWithChildren<{
  location?: string;
}>) {
  return createElement(StaticRouter, { location }, children);
}
