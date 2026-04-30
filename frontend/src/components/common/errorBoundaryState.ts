export type ErrorBoundaryVariant = "generic" | "backend-offline";

export type ErrorBoundaryActionKey = "reset" | "home" | "reload";

export interface ErrorBoundaryAction {
  key: ErrorBoundaryActionKey;
  label: string;
  variant: "default" | "outline";
}

export interface ErrorBoundaryViewModel {
  variant: ErrorBoundaryVariant;
  statusCode: string;
  badgeLabel: string;
  title: string;
  description: string;
  summary: string;
  guidance: string;
  footer: string;
  actions: readonly ErrorBoundaryAction[];
}

const GENERIC_ACTIONS: readonly ErrorBoundaryAction[] = [
  { key: "reset", label: "重试", variant: "outline" },
  { key: "home", label: "返回首页", variant: "outline" },
  { key: "reload", label: "刷新页面", variant: "default" },
];

const BACKEND_OFFLINE_ACTIONS: readonly ErrorBoundaryAction[] = [
  { key: "reset", label: "重试连接", variant: "default" },
  { key: "home", label: "返回首页", variant: "outline" },
  { key: "reload", label: "刷新页面", variant: "outline" },
];

const VIEW_MODEL_MAP: Record<ErrorBoundaryVariant, ErrorBoundaryViewModel> = {
  generic: {
    variant: "generic",
    statusCode: "APP_ERROR",
    badgeLabel: "Runtime Fault",
    title: "出错了",
    description: "应用遇到了一个错误",
    summary: "界面在渲染过程中触发了未处理异常，当前页面已被安全中断。",
    guidance: "可以先重试当前界面；如果问题持续出现，请刷新页面或返回首页重新进入。",
    footer: "错误已被记录，我们会尽快修复",
    actions: GENERIC_ACTIONS,
  },
  "backend-offline": {
    variant: "backend-offline",
    statusCode: "SERVICE_OFFLINE",
    badgeLabel: "Backend Offline",
    title: "服务没有启动",
    description: "请启动后再使用项目",
    summary: "当前前端无法连接后端服务，项目数据、扫描任务与相关接口暂时不可用。",
    guidance: "请确认后端进程与 API 代理已经恢复，然后再点击重试连接。",
    footer: "后端服务恢复后，页面即可继续正常使用",
    actions: BACKEND_OFFLINE_ACTIONS,
  },
};

const BACKEND_OFFLINE_STATUS_CODES = new Set([502, 503, 504]);

type ErrorLike = {
  message?: unknown;
  response?: { status?: unknown; config?: { url?: unknown; baseURL?: unknown } };
  request?: { responseURL?: unknown };
  config?: { url?: unknown; baseURL?: unknown };
  status?: unknown;
  code?: unknown;
  isAxiosError?: unknown;
};

export function resolveErrorBoundaryViewModel(
  error: unknown,
): ErrorBoundaryViewModel {
  const variant = isBackendOfflineError(error) ? "backend-offline" : "generic";
  return VIEW_MODEL_MAP[variant];
}

function isBackendOfflineError(error: unknown): boolean {
  const message = getErrorMessage(error);
  const normalizedMessage = message.toLowerCase();
  const errorLike = asErrorLike(error);
  const statusCode = getStatusCode(errorLike);
  const apiRequest = isApiRequest(errorLike);
  const hasResponse = Boolean(errorLike?.response);

  if (isProjectsDynamicImportFailure(message)) {
    return true;
  }

  if (apiRequest && BACKEND_OFFLINE_STATUS_CODES.has(statusCode)) {
    return true;
  }

  if (apiRequest && !hasResponse && isAxiosLike(errorLike)) {
    return true;
  }

  if (normalizedMessage.includes("failed to fetch")) {
    return true;
  }

  if (normalizedMessage.includes("network error")) {
    return apiRequest || !hasResponse || error instanceof Error;
  }

  return false;
}

function isProjectsDynamicImportFailure(message: string): boolean {
  return (
    message.includes("Failed to fetch dynamically imported module") &&
    /Projects\.tsx(?:\?|$)/.test(message)
  );
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
    if (typeof message === "string") {
      return message;
    }
  }
  return "";
}

function asErrorLike(error: unknown): ErrorLike | null {
  if (!error || typeof error !== "object") {
    return null;
  }
  return error as ErrorLike;
}

function isAxiosLike(error: ErrorLike | null): boolean {
  if (!error) {
    return false;
  }
  return Boolean(
    error.isAxiosError ||
      error.config ||
      error.response ||
      error.request,
  );
}

function getStatusCode(error: ErrorLike | null): number {
  const rawStatus = error?.response?.status ?? error?.status;
  return typeof rawStatus === "number" ? rawStatus : Number(rawStatus || 0);
}

function isApiRequest(error: ErrorLike | null): boolean {
  if (!error) {
    return false;
  }

  const urlCandidates = [
    buildUrlCandidate(error.config?.baseURL, error.config?.url),
    buildUrlCandidate(error.response?.config?.baseURL, error.response?.config?.url),
    typeof error.request?.responseURL === "string"
      ? error.request.responseURL
      : "",
  ];

  return urlCandidates.some((candidate) => candidate.includes("/api/"));
}

function buildUrlCandidate(baseURL: unknown, url: unknown): string {
  const normalizedUrl = typeof url === "string" ? url : "";
  const normalizedBase = typeof baseURL === "string" ? baseURL : "";

  if (!normalizedUrl) {
    return normalizedBase;
  }

  if (normalizedUrl.startsWith("http://") || normalizedUrl.startsWith("https://")) {
    return normalizedUrl;
  }

  if (!normalizedBase) {
    return normalizedUrl;
  }

  const trimmedBase = normalizedBase.endsWith("/")
    ? normalizedBase.slice(0, -1)
    : normalizedBase;
  const trimmedUrl = normalizedUrl.startsWith("/")
    ? normalizedUrl
    : `/${normalizedUrl}`;

  return `${trimmedBase}${trimmedUrl}`;
}
