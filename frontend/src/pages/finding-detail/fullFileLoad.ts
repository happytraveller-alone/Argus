export const FULL_FILE_UNAVAILABLE_MESSAGE =
  "当前记录未关联可读取的完整文件，仅展示漏洞相关代码";
export const FULL_FILE_FAILED_MESSAGE = "完整文件加载失败，请稍后重试";

export type FullFileLoadFailure = {
  kind: "unavailable" | "failed";
  message: string;
};

export function classifyFullFileLoadError(error: unknown): FullFileLoadFailure {
  const status = Number(
    (error as { response?: { status?: number } } | null)?.response?.status || 0,
  );
  if (status === 400 || status === 404) {
    return {
      kind: "unavailable",
      message: FULL_FILE_UNAVAILABLE_MESSAGE,
    };
  }

  return {
    kind: "failed",
    message: FULL_FILE_FAILED_MESSAGE,
  };
}
