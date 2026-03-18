const YASA_LANGUAGE_ALIAS: Record<string, string> = {
  py: "python",
  python: "python",
  js: "javascript",
  javascript: "javascript",
  node: "javascript",
  nodejs: "javascript",
  ts: "typescript",
  typescript: "typescript",
  go: "golang",
  golang: "golang",
  java: "java",
  kotlin: "java",
  scala: "java",
};

const YASA_LANGUAGE_PRIORITY = [
  "java",
  "golang",
  "python",
  "typescript",
  "javascript",
] as const;

export const YASA_LANGUAGE_OPTIONS = [
  "auto",
  "python",
  "javascript",
  "typescript",
  "golang",
  "java",
] as const;

export type YasaLanguageOption = (typeof YASA_LANGUAGE_OPTIONS)[number];

function parseProgrammingLanguages(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }
  if (typeof value !== "string") return [];

  const text = value.trim();
  if (!text) return [];

  if (text.startsWith("[") && text.endsWith("]")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item) => String(item || "").trim())
          .filter(Boolean);
      }
    } catch {
      // fall through to csv parsing
    }
  }

  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseYasaLanguageOption(value: unknown): YasaLanguageOption {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "python") return "python";
  if (normalized === "javascript") return "javascript";
  if (normalized === "typescript") return "typescript";
  if (normalized === "golang") return "golang";
  if (normalized === "java") return "java";
  return "auto";
}

export function resolveYasaLanguageFromProgrammingLanguages(
  programmingLanguages: unknown,
): string | null {
  const parsedLanguages = parseProgrammingLanguages(programmingLanguages);
  // YASA auto policy: PHP-like projects should be skipped even if other
  // supported languages are also detected.
  const hasPhpLikeLanguage = parsedLanguages.some((item) =>
    String(item || "").trim().toLowerCase().startsWith("php"),
  );
  if (hasPhpLikeLanguage) return null;

  const candidates = parsedLanguages
    .map((item) => YASA_LANGUAGE_ALIAS[String(item || "").trim().toLowerCase()])
    .filter((item): item is string => Boolean(item));

  if (candidates.length === 0) return null;

  for (const preferred of YASA_LANGUAGE_PRIORITY) {
    if (candidates.includes(preferred)) return preferred;
  }

  return candidates[0] || null;
}

export function getYasaUnsupportedLanguageMessage(language?: string): string {
  if (language?.trim()) {
    return `不支持语言: ${language.trim().toLowerCase()}，YASA 仅支持 python/javascript/typescript/golang/java`;
  }
  return "未检测到可用于 YASA 的项目语言，请在创建时手动指定支持语言";
}
