function parseProgrammingLanguages(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim().toLowerCase())
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
          .map((item) => String(item || "").trim().toLowerCase())
          .filter(Boolean);
      }
    } catch {
    }
  }

  return text
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

export function isPmdSupportedProjectLanguage(programmingLanguages: unknown): boolean {
  return parseProgrammingLanguages(programmingLanguages).includes("java");
}

export function isPmdBlockedProjectLanguage(programmingLanguages: unknown): boolean {
  const parsed = parseProgrammingLanguages(programmingLanguages);
  return parsed.length > 0 && !parsed.includes("java");
}

export function getPmdBlockedProjectMessage(): string {
  return "PMD 引擎暂时仅支持 Java 项目";
}
