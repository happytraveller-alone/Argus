const RETRYABLE_STATUS_CODES = new Set([502, 503, 504]);
const RETRYABLE_ERROR_CODES = new Set([
  "ECONNREFUSED",
  "ECONNRESET",
  "EHOSTUNREACH",
  "ENOTFOUND",
  "ERR_NETWORK",
]);

export const DEFAULT_PROJECT_READ_RETRY_DELAYS_MS = [0, 800, 1500, 2500, 4000] as const;
export const DEFAULT_PROJECT_READ_TIMEOUT_MS = 12000;

type ErrorLike = {
  message?: unknown;
  response?: { status?: unknown };
  code?: unknown;
  isAxiosError?: unknown;
};

export interface RetryProjectReadsOptions {
  delaysMs?: readonly number[];
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export async function retryProjectReads<T>(
  operation: () => Promise<T>,
  options: RetryProjectReadsOptions = {},
): Promise<T> {
  const delaysMs = normalizeRetryDelays(options.delaysMs);
  const timeoutMs = normalizeTimeoutMs(options.timeoutMs);
  const sleep = options.sleep ?? defaultSleep;
  const now = options.now ?? Date.now;
  const startedAt = now();

  for (let attempt = 0; attempt < delaysMs.length; attempt += 1) {
    const delayMs = delaysMs[attempt];
    if (delayMs > 0) {
      if (now() - startedAt + delayMs > timeoutMs) {
        break;
      }
      await sleep(delayMs);
    }

    try {
      return await operation();
    } catch (error) {
      const canRetry =
        isRetryableProjectReadError(error) &&
        attempt < delaysMs.length - 1 &&
        now() - startedAt < timeoutMs;

      if (!canRetry) {
        throw error;
      }
    }
  }

  throw new Error("retryProjectReads exhausted without executing the operation");
}

function normalizeRetryDelays(delaysMs?: readonly number[]): number[] {
  const source = delaysMs && delaysMs.length > 0
    ? [...delaysMs]
    : [...DEFAULT_PROJECT_READ_RETRY_DELAYS_MS];

  return source.map((value, index) => {
    if (index === 0) {
      return 0;
    }
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return 0;
    }
    return Math.max(0, Math.trunc(numericValue));
  });
}

function normalizeTimeoutMs(timeoutMs?: number): number {
  const numericValue = Number(timeoutMs);
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return DEFAULT_PROJECT_READ_TIMEOUT_MS;
  }
  return Math.trunc(numericValue);
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isRetryableProjectReadError(error: unknown): boolean {
  const errorLike = asErrorLike(error);
  const statusCode = getStatusCode(errorLike);
  if (RETRYABLE_STATUS_CODES.has(statusCode)) {
    return true;
  }

  const errorCode = getErrorCode(errorLike);
  if (RETRYABLE_ERROR_CODES.has(errorCode)) {
    return true;
  }

  const message = getErrorMessage(error).toLowerCase();
  if (!message) {
    return false;
  }

  return (
    message.includes("network error") ||
    message.includes("failed to fetch") ||
    message.includes("econnrefused") ||
    message.includes("socket hang up") ||
    message.includes("proxy error") ||
    message.includes("upstream connect error")
  );
}

function asErrorLike(error: unknown): ErrorLike | null {
  if (!error || typeof error !== "object") {
    return null;
  }
  return error as ErrorLike;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  if (error && typeof error === "object" && "message" in error) {
    const { message } = error as { message?: unknown };
    return typeof message === "string" ? message : "";
  }
  return "";
}

function getStatusCode(error: ErrorLike | null): number {
  const rawStatus = error?.response?.status;
  return typeof rawStatus === "number" ? rawStatus : Number(rawStatus || 0);
}

function getErrorCode(error: ErrorLike | null): string {
  const rawCode = error?.code;
  return typeof rawCode === "string" ? rawCode.toUpperCase() : "";
}
