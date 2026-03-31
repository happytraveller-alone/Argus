const YASA_LANGUAGE_ALIAS: Record<string, string> = {
  py: "python",
  python: "python",
  ts: "typescript",
  typescript: "typescript",
  go: "golang",
  golang: "golang",
  java: "java",
};

const YASA_LANGUAGE_PRIORITY = [
  "java",
  "golang",
  "typescript",
  "python",
] as const;

export const YASA_LANGUAGE_OPTIONS = [
  "auto",
  "java",
  "golang",
  "typescript",
  "python",
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

export function isYasaBlockedProjectLanguage(programmingLanguages: unknown): boolean {
  const parsed = parseProgrammingLanguages(programmingLanguages);
  if (parsed.length === 0) return true;
  return !parsed.some((item) => {
    const normalized = String(item || "").trim().toLowerCase();
    return Boolean(YASA_LANGUAGE_ALIAS[normalized]);
  });
}

export function parseYasaLanguageOption(value: unknown): YasaLanguageOption {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "java") return "java";
  if (normalized === "golang") return "golang";
  if (normalized === "typescript") return "typescript";
  if (normalized === "python") return "python";
  return "auto";
}

export function resolveYasaLanguageFromProgrammingLanguages(
  programmingLanguages: unknown,
): string | null {
  const parsedLanguages = parseProgrammingLanguages(programmingLanguages);
  if (isYasaBlockedProjectLanguage(parsedLanguages)) return null;

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
    return `不支持语言: ${language.trim().toLowerCase()}，YASA 仅支持 java/golang/typescript/python`;
  }
  return "未检测到可用于 YASA 的项目语言，请在创建时手动指定支持语言";
}

export function getYasaBlockedProjectMessage(): string {
  return "YASA 引擎仅支持 Java / Go / TypeScript / Python 项目";
}
