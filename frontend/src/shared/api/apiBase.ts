const viteEnv =
  typeof import.meta !== "undefined" &&
  typeof import.meta.env === "object" &&
  import.meta.env !== null
    ? import.meta.env
    : undefined;

export const DEFAULT_API_BASE_URL = "/api/v1";

export function normalizeApiBaseUrl(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return DEFAULT_API_BASE_URL;
  }

  return normalized.replace(/\/+$/, "") || DEFAULT_API_BASE_URL;
}

export function getApiBaseUrl(): string {
  return normalizeApiBaseUrl(
    typeof viteEnv?.VITE_API_BASE_URL === "string" ? viteEnv.VITE_API_BASE_URL : undefined,
  );
}

export function buildApiUrl(pathname: string): string {
  const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `${getApiBaseUrl()}${normalizedPath}`;
}
