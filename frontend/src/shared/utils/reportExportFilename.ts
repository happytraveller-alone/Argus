const INVALID_FILENAME_CHARS = /[<>:"/\\|?*\u0000-\u001f]+/g;
const TRAILING_DOTS_AND_SPACES = /[. ]+$/g;

export function sanitizeFilenameSegment(
  value: string | null | undefined,
  fallback: string,
): string {
  const text = String(value ?? "").trim();
  if (!text || text === "-") return fallback;
  const sanitized = text
    .replace(INVALID_FILENAME_CHARS, "-")
    .replace(/\s+/g, " ")
    .replace(TRAILING_DOTS_AND_SPACES, "")
    .trim();
  return sanitized || fallback;
}

export function buildReportDownloadBaseName(
  projectName: string | null | undefined,
  fallback: string,
  date = new Date(),
): string {
  const projectSegment = sanitizeFilenameSegment(projectName, fallback);
  const datePart = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
  return `漏洞报告-${projectSegment}-${datePart}`;
}

export function resolveFilenameFromDisposition(
  contentDisposition: string | undefined,
  fallback: string,
): string {
  if (!contentDisposition) return fallback;

  const filenameStarMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (filenameStarMatch?.[1]) {
    try {
      return decodeURIComponent(filenameStarMatch[1]);
    } catch {
      return filenameStarMatch[1];
    }
  }

  const filenameMatch = contentDisposition.match(/filename=([^;]+)/i);
  if (!filenameMatch?.[1]) return fallback;
  return filenameMatch[1].trim().replace(/['"]/g, "") || fallback;
}
