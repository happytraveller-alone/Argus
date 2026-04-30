import type {
  ExternalToolStatusFilter,
  ExternalToolTypeFilter,
} from "./externalToolsViewModel";

export interface ExternalToolsUrlState {
  page: number;
  searchQuery: string;
  typeFilter: ExternalToolTypeFilter;
  statusFilter: ExternalToolStatusFilter;
}

export const DEFAULT_EXTERNAL_TOOLS_URL_STATE: ExternalToolsUrlState = {
  page: 1,
  searchQuery: "",
  typeFilter: "all",
  statusFilter: "all",
};

function isExternalToolTypeFilter(value: string): value is ExternalToolTypeFilter {
  return (
    value === "all" ||
    value === "skill" ||
    value === "prompt-builtin" ||
    value === "prompt-custom"
  );
}

function isExternalToolStatusFilter(value: string): value is ExternalToolStatusFilter {
  return value === "all" || value === "enabled" || value === "disabled";
}

export function parseExternalToolsUrlState(
  params: URLSearchParams,
): ExternalToolsUrlState {
  const parsedPage = Number(params.get("page") || "1");
  const normalizedPage =
    Number.isFinite(parsedPage) && parsedPage >= 1
      ? Math.floor(parsedPage)
      : DEFAULT_EXTERNAL_TOOLS_URL_STATE.page;
  const rawType = String(params.get("type") || "").trim();
  const rawStatus = String(params.get("status") || "").trim();

  return {
    page: normalizedPage,
    searchQuery: String(params.get("q") || ""),
    typeFilter: isExternalToolTypeFilter(rawType)
      ? rawType
      : DEFAULT_EXTERNAL_TOOLS_URL_STATE.typeFilter,
    statusFilter: isExternalToolStatusFilter(rawStatus)
      ? rawStatus
      : DEFAULT_EXTERNAL_TOOLS_URL_STATE.statusFilter,
  };
}

export function mergeExternalToolsUrlState(
  params: URLSearchParams,
  state: Partial<ExternalToolsUrlState>,
): URLSearchParams {
  const next = new URLSearchParams(params);
  ["page", "q", "type", "status"].forEach((key) => {
    next.delete(key);
  });

  const merged: ExternalToolsUrlState = {
    ...DEFAULT_EXTERNAL_TOOLS_URL_STATE,
    ...state,
  };

  if (merged.searchQuery.trim()) {
    next.set("q", merged.searchQuery);
  }
  if (merged.typeFilter !== "all") {
    next.set("type", merged.typeFilter);
  }
  if (merged.statusFilter !== "all") {
    next.set("status", merged.statusFilter);
  }
  if (merged.page > 1) {
    next.set("page", String(merged.page));
  }

  return next;
}
