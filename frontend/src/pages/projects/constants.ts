import type { CreateProjectForm } from "@/shared/types";
import { SUPPORTED_LANGUAGES } from "@/shared/constants";

export const PROJECT_PAGE_SIZE = 10;
export const PROJECT_FETCH_BATCH_SIZE = 200;
export const MODULE_SCROLL_DELAY_MS = 80;
export const TASK_POOL_MAX_TOTAL = 800;
export const AGENT_TASK_PAGE_LIMIT = 100;
export const OPENGREP_TASK_PAGE_LIMIT = 200;
export const GITLEAKS_TASK_PAGE_LIMIT = 200;
export const BANDIT_TASK_PAGE_LIMIT = 200;
export const PHPSTAN_TASK_PAGE_LIMIT = 200;
export const LANGUAGE_STATS_RETRY_INTERVAL_MS = 2500;
export const LANGUAGE_STATS_MAX_RETRIES = 6;

export const PROJECT_ACTION_BTN =
	"border border-sky-400/35 bg-gradient-to-r from-sky-500/20 via-cyan-500/16 to-blue-500/20 text-sky-100 shadow-[0_8px_22px_-14px_rgba(14,165,233,0.9)] hover:from-sky-500/30 hover:via-cyan-500/24 hover:to-blue-500/30 hover:border-sky-300/55";

export const PROJECT_ACTION_BTN_SUBTLE =
	"border border-sky-500/30 bg-sky-500/12 text-sky-100 hover:bg-sky-500/22 hover:border-sky-400/55";

const ARCHIVE_SUFFIXES = [
	".tar.gz",
	".tar.bz2",
	".tar.xz",
	".tgz",
	".tbz2",
	".zip",
	".tar",
	".7z",
	".rar",
];

export function stripArchiveSuffix(filename: string) {
	const lower = filename.toLowerCase();
	const matched = ARCHIVE_SUFFIXES.find((suffix) => lower.endsWith(suffix));
	if (!matched) return filename;
	return filename.slice(0, filename.length - matched.length);
}

export function formatProjectLanguageName(lang: string): string {
	const nameMap: Record<string, string> = {
		javascript: "JavaScript",
		typescript: "TypeScript",
		python: "Python",
		java: "Java",
		go: "Go",
		rust: "Rust",
		cpp: "C++",
		csharp: "C#",
		php: "PHP",
		ruby: "Ruby",
		swift: "Swift",
		kotlin: "Kotlin",
	};
	return nameMap[lang] || lang.charAt(0).toUpperCase() + lang.slice(1);
}

export const SUPPORTED_PROJECT_LANGUAGES = SUPPORTED_LANGUAGES.map(
	formatProjectLanguageName,
);

export function createEmptyProjectForm(): CreateProjectForm {
	return {
		name: "",
		description: "",
		source_type: "zip",
		repository_url: undefined,
		repository_type: "other",
		default_branch: "main",
		programming_languages: [],
	};
}

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
