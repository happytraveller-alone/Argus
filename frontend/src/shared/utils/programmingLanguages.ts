export function normalizeProgrammingLanguages(value: unknown): string[] {
	if (Array.isArray(value)) {
		return value.filter((item): item is string => typeof item === "string");
	}

	if (typeof value !== "string") return [];

	const trimmed = value.trim();
	if (!trimmed) return [];
	if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
		try {
			const parsed = JSON.parse(trimmed);
			if (Array.isArray(parsed)) {
				return parsed.filter((item): item is string => typeof item === "string");
			}
		} catch {
			return [];
		}
	}

	return trimmed
		.split(",")
		.map((item) => item.trim())
		.filter(Boolean);
}

export function normalizeCodeqlLanguages(value: unknown): string[] {
	const normalized = normalizeProgrammingLanguages(value)
		.map((language) => {
			const lowered = language.trim().toLowerCase();
			if (
				lowered === "javascript" ||
				lowered === "typescript" ||
				lowered === "javascript-typescript" ||
				lowered === "js" ||
				lowered === "ts"
			) {
				return "javascript-typescript";
			}
			if (lowered === "c" || lowered === "c++" || lowered === "cpp") {
				return "cpp";
			}
			if (lowered === "py") return "python";
			return lowered;
		})
		.filter((language) =>
			["cpp", "javascript-typescript", "python", "java", "go"].includes(
				language,
			),
		);

	return Array.from(new Set(normalized));
}
